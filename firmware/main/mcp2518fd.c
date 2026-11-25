// MCP2518FD driver (classic CAN 2.0 at 500 kbit/s), written for low SPI time per frame and no lost frames:
// FIFO2 is a 32-deep receive FIFO, FIFO1 a 16-deep transmit FIFO, both 8-byte payload, no timestamps, no TEF.
// RX: one READ of FIFO2's status gives the head index (FIFOCI, as Linux's mcp251xfd does); the driver keeps
// the tail itself, reads every waiting object in one burst (two at the RAM wrap) and pops each with UINC.
// TX: objects are written at the driver's own head index and handed over with UINC|TXREQ; FIFO1's status
// is read only when the driver believes the FIFO is full. All SPI traffic happens on the CAN task (core 1).
#include "mcp.h"

#include <string.h>
#include "config.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "hal.h"

static const char *TAG = "mcp2518fd";

// SPI instructions: 4-bit command + 12-bit address
#define CMD_RESET 0x0
#define CMD_WRITE 0x2
#define CMD_READ  0x3
// SFRs (MCP25xxFD family reference manual)
#define R_CON      0x000
#define R_NBTCFG   0x004
#define R_INT      0x01C
#define R_TREC     0x034
#define R_FIFOCON(m) (0x050 + 12 * (m))
#define R_FIFOSTA(m) (0x054 + 12 * (m))
#define R_FIFOUA(m)  (0x058 + 12 * (m))
#define R_FLTCON0  0x1D0
#define R_FLTOBJ0  0x1F0
#define R_MASK0    0x1F4
#define RAM_BASE   0x400
#define R_OSC      0xE00
#define R_IOCON    0xE04
// C1CON
#define CON_REQOP_SHIFT 24
#define CON_OPMOD_SHIFT 21
#define MODE_CAN20  6
#define MODE_LISTEN 3
#define MODE_CONFIG 4
// FIFOCON / FIFOSTA
#define FC_TFNRFNIE (1u << 0)
#define FC_RXOVIE   (1u << 3)
#define FC_TXEN     (1u << 7)
#define FC_UINC     0x01           // byte 1
#define FC_TXREQ    0x02           // byte 1
#define FC_TXAT_UNLIMITED (3u << 21)
#define FC_FSIZE(n) ((uint32_t)((n) - 1) << 24)
#define FS_TFNRFNIF (1u << 0)
#define FS_TFERFFIF (1u << 2)
#define FS_RXOVIF   (1u << 3)
#define FS_FIFOCI(v) (((v) >> 8) & 0x1F)
// C1INT enables
#define INT_RXIE    (1u << 17)
#define INT_RXOVIE  (1u << 27)
#define OSC_OSCRDY  (1u << 10)

#define TXF 1                      // transmit FIFO
#define RXF 2                      // receive FIFO
#define TX_DEPTH 16
#define RX_DEPTH 32
#define OBJ 16                     // 8-byte header + 8 data bytes
#define RX_BATCH 8                 // frames per service call, so one busy bus can't starve the other chips
#define TXQ_LEN 64

typedef struct {
    can_frame_t q[TXQ_LEN];
    volatile uint16_t head, tail;   // software queue: head (any task, under lock), tail (CAN task)
    portMUX_TYPE lock;
    uint16_t rx_tail, tx_head;      // FIFO indices kept by the driver
    uint16_t tx_free;               // transmit FIFO slots believed free
    uint16_t rx_ram, tx_ram;        // RAM offsets of the FIFOs' first objects
    mcp_stats_t st;
    bool listen_only;
    volatile int8_t pending_mode;   // -1 none, 0 normal, 1 listen-only
} mcp_t;

static mcp_t s_mcp[MCP_COUNT];

static inline void xfer(int chip, const uint8_t *tx, uint8_t *rx, size_t n)
{
    int64_t t0 = esp_timer_get_time();
    hal_spi_xfer(chip, tx, rx, n);
    s_mcp[chip].st.spi_us += (uint32_t)(esp_timer_get_time() - t0);
}

static inline void hdr(uint8_t *b, uint8_t cmd, uint16_t addr)
{
    b[0] = (uint8_t)(cmd << 4 | (addr >> 8 & 0x0F));
    b[1] = (uint8_t)addr;
}

static void read_n(int chip, uint16_t addr, uint8_t *out, size_t n)
{
    uint8_t tx[2 + 8 * OBJ] = {0}, rx[2 + 8 * OBJ];
    hdr(tx, CMD_READ, addr);
    xfer(chip, tx, rx, n + 2);
    memcpy(out, rx + 2, n);
}

static uint32_t rd32(int chip, uint16_t addr)
{
    uint8_t b[4];
    read_n(chip, addr, b, 4);
    return b[0] | b[1] << 8 | b[2] << 16 | (uint32_t)b[3] << 24;
}

static void write_n(int chip, uint16_t addr, const uint8_t *in, size_t n)
{
    uint8_t tx[2 + TX_DEPTH * OBJ], rx[2 + TX_DEPTH * OBJ];
    hdr(tx, CMD_WRITE, addr);
    memcpy(tx + 2, in, n);
    xfer(chip, tx, rx, n + 2);
}

static void wr32(int chip, uint16_t addr, uint32_t v)
{
    uint8_t b[4] = {(uint8_t)v, (uint8_t)(v >> 8), (uint8_t)(v >> 16), (uint8_t)(v >> 24)};
    write_n(chip, addr, b, 4);
}

static void wr8(int chip, uint16_t addr, uint8_t v) { write_n(chip, addr, &v, 1); }

static bool set_mode(int chip, uint8_t mode)
{
    wr8(chip, R_CON + 3, mode);                     // REQOP (byte 3, bits 0-2); ABAT and TXBWS = 0
    for (int i = 0; i < 100; i++) {
        uint8_t b;
        read_n(chip, R_CON + 2, &b, 1);
        if ((b >> 5) == mode) return true;          // OPMOD (byte 2, bits 5-7)
    }
    return false;
}

bool mcp_init(int chip, bool listen_only)
{
    mcp_t *m = &s_mcp[chip];
    memset(m, 0, sizeof(*m));
    portMUX_INITIALIZE(&m->lock);
    uint8_t tx[2] = {0}, rx[2];
    hdr(tx, CMD_RESET, 0);
    xfer(chip, tx, rx, 2);                          // back in configuration mode, 40 MHz SYSCLK, PLL off
    int i = 0;
    while (!(rd32(chip, R_OSC) & OSC_OSCRDY) && ++i < 100) { }
    if (i >= 100 || (rd32(chip, R_CON) >> CON_OPMOD_SHIFT & 7) != MODE_CONFIG) {
        ESP_LOGE(TAG, "chip %d: no oscillator / not in config mode after reset", chip);
        return false;
    }
    // 500 kbit/s from 40 MHz: TQ 25 ns, 80 TQ/bit = sync 1 + TSEG1 63 + TSEG2 16 (sample point 80 %), SJW 16
    wr32(chip, R_NBTCFG, (0u << 24) | (62u << 16) | (15u << 8) | 15u);
    wr8(chip, R_CON + 2, 0x00);                     // TXQ off, TEF off, unlimited retransmissions
    wr32(chip, R_FIFOCON(TXF), FC_TXEN | FC_TXAT_UNLIMITED | FC_FSIZE(TX_DEPTH));
    wr32(chip, R_FIFOCON(RXF), FC_TFNRFNIE | FC_RXOVIE | FC_FSIZE(RX_DEPTH));
    wr32(chip, R_FLTOBJ0, 0);                       // filter 0: accept everything (mask 0) into FIFO2
    wr32(chip, R_MASK0, 0);
    wr8(chip, R_FLTCON0, 0x80 | RXF);
    wr32(chip, R_INT, INT_RXIE | INT_RXOVIE);       // INT pin: RX FIFO not empty or overflowed
    wr8(chip, R_IOCON, 0x00);                       // INT0/INT1 unused: drive them low rather than float
    // FIFO RAM: empty FIFOs report their first object's offset
    m->tx_ram = (uint16_t)rd32(chip, R_FIFOUA(TXF));
    m->rx_ram = (uint16_t)rd32(chip, R_FIFOUA(RXF));
    m->tx_free = TX_DEPTH;
    m->listen_only = listen_only;
    m->pending_mode = -1;
    bool ok = set_mode(chip, listen_only ? MODE_LISTEN : MODE_CAN20);
    if (!ok) ESP_LOGE(TAG, "chip %d did not enter %s mode", chip, listen_only ? "listen-only" : "normal");
    return ok;
}

void mcp_request_listen_only(int chip, bool listen_only) { s_mcp[chip].pending_mode = listen_only ? 1 : 0; }

void mcp_apply_pending(int chip)
{
    int8_t p = s_mcp[chip].pending_mode;
    if (p >= 0) {
        s_mcp[chip].pending_mode = -1;
        mcp_set_listen_only(chip, p == 1);
    }
}

bool mcp_set_listen_only(int chip, bool listen_only)
{
    s_mcp[chip].listen_only = listen_only;
    return set_mode(chip, listen_only ? MODE_LISTEN : MODE_CAN20);
}

static void decode(const uint8_t *b, can_frame_t *f)
{
    uint32_t r0 = b[0] | b[1] << 8 | b[2] << 16 | (uint32_t)b[3] << 24;
    uint8_t r1 = b[4];
    f->ext = (r1 >> 4) & 1;
    f->rtr = (r1 >> 5) & 1;
    f->id = f->ext ? ((r0 & 0x7FF) << 18) | ((r0 >> 11) & 0x3FFFF) : (r0 & 0x7FF);
    uint8_t dlc = r1 & 0x0F;
    f->dlc = dlc > 8 ? 8 : dlc;
    memcpy(f->data, b + 8, 8);
}

static void encode(const can_frame_t *f, uint8_t *b)
{
    uint32_t t0 = f->ext ? (((f->id >> 18) & 0x7FF) | ((f->id & 0x3FFFF) << 11)) : (f->id & 0x7FF);
    memset(b, 0, 8);
    b[0] = (uint8_t)t0; b[1] = (uint8_t)(t0 >> 8); b[2] = (uint8_t)(t0 >> 16); b[3] = (uint8_t)(t0 >> 24);
    b[4] = (uint8_t)((f->dlc & 0x0F) | (f->ext ? 0x10 : 0) | (f->rtr ? 0x20 : 0));
    memcpy(b + 8, f->data, 8);
}

void mcp_tx_pump(int chip)
{
    mcp_t *m = &s_mcp[chip];
    if (m->tail == m->head) return;
    if (m->listen_only) {
        m->tail = m->head;   // can't transmit: discard (counted at queue time)
        return;
    }
    if (!m->tx_free) {   // believed full: FIFOCI is the next object to go out, so in-flight = head - CI
        uint32_t sta = rd32(chip, R_FIFOSTA(TXF));
        m->tx_free = !(sta & FS_TFNRFNIF) ? 0 : TX_DEPTH - ((m->tx_head - FS_FIFOCI(sta)) & (TX_DEPTH - 1));
        if (!m->tx_free) return;
    }
    uint8_t buf[TX_DEPTH * OBJ];
    int n = 0;
    uint16_t start = m->tx_head;
    while (m->tail != m->head && n < m->tx_free && start + n < TX_DEPTH) {   // contiguous run up to the wrap
        encode(&m->q[m->tail], buf + n * OBJ);
        m->tail = (m->tail + 1) % TXQ_LEN;
        n++;
    }
    write_n(chip, RAM_BASE + m->tx_ram + start * OBJ, buf, n * OBJ);
    for (int i = 0; i < n; i++) wr8(chip, R_FIFOCON(TXF) + 1, FC_UINC | FC_TXREQ);
    m->tx_head = (m->tx_head + n) % TX_DEPTH;
    m->tx_free -= n;
    m->st.tx += n;
}

bool mcp_queue_tx(int chip, const can_frame_t *f)
{
    mcp_t *m = &s_mcp[chip];
    bool ok;
    taskENTER_CRITICAL(&m->lock);
    uint16_t next = (m->head + 1) % TXQ_LEN;
    ok = next != m->tail && !m->listen_only;
    if (ok) {
        m->q[m->head] = *f;
        m->head = next;
    }
    taskEXIT_CRITICAL(&m->lock);
    if (!ok) m->st.tx_queue_drop++;
    return ok;
}

int mcp_service(int chip, mcp_rx_cb_t cb)
{
    mcp_t *m = &s_mcp[chip];
    if (!hal_mcp_int_asserted(chip)) return 0;
    uint32_t sta = rd32(chip, R_FIFOSTA(RXF));
    if (sta & FS_RXOVIF) {
        m->st.rx_overflow++;
        m->st.errors++;
        wr8(chip, R_FIFOSTA(RXF), 0x00);              // clears RXOVIF; the other flags are read-only
    }
    if (!(sta & FS_TFNRFNIF)) return 0;
    int avail = (FS_FIFOCI(sta) - m->rx_tail) & (RX_DEPTH - 1);
    if (!avail) avail = RX_DEPTH;                     // not empty and head == tail: full
    int n = avail < RX_BATCH ? avail : RX_BATCH;
    if (m->rx_tail + n > RX_DEPTH) n = RX_DEPTH - m->rx_tail;   // stop at the RAM wrap; the rest next call
    uint8_t buf[RX_BATCH * OBJ];
    read_n(chip, RAM_BASE + m->rx_ram + m->rx_tail * OBJ, buf, n * OBJ);
    uint32_t now = (uint32_t)esp_timer_get_time();
    for (int i = 0; i < n; i++) {
        wr8(chip, R_FIFOCON(RXF) + 1, FC_UINC);      // pop before the callback: the slot is free again sooner
        can_frame_t f = {0};
        decode(buf + i * OBJ, &f);
        f.ts_us = now;
        m->st.rx++;
        cb(chip, &f);
    }
    m->rx_tail = (m->rx_tail + n) % RX_DEPTH;
    return n;
}

const mcp_stats_t *mcp_stats(int chip) { return &s_mcp[chip].st; }

void mcp_stats_reset(void)
{
    for (int i = 0; i < MCP_COUNT; i++) memset(&s_mcp[i].st, 0, sizeof(mcp_stats_t));
}
