// MCP2515 driver, written for low SPI time per frame: READ STATUS (2 bytes) tells which RX/TX buffers need
// attention, READ RX BUFFER (14 bytes) fetches a frame and clears its flag in the same transaction, and
// LOAD TX BUFFER + RTS sends one. All SPI traffic happens on the CAN task (core 1), so no bus locking.
#include "mcp2515.h"

#include <string.h>
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "hal.h"

static const char *TAG = "mcp2515";

// instructions
#define I_RESET      0xC0
#define I_READ       0x03
#define I_WRITE      0x02
#define I_BITMOD     0x05
#define I_STATUS     0xA0
#define I_READ_RXB0  0x90
#define I_READ_RXB1  0x94
#define I_LOAD_TXB(n) (0x40 + 2 * (n))
// registers
#define R_CANSTAT 0x0E
#define R_CANCTRL 0x0F
#define R_CNF3    0x28
#define R_CNF2    0x29
#define R_CNF1    0x2A
#define R_CANINTE 0x2B
#define R_CANINTF 0x2C
#define R_EFLG    0x2D
#define R_RXB0CTRL 0x60
#define R_RXB1CTRL 0x70
// CANINTF bits
#define INT_RX0 0x01
#define INT_RX1 0x02
#define INT_TX0 0x04
#define INT_TX1 0x08
#define INT_TX2 0x10
#define INT_ERR 0x20
#define INT_MERR 0x80
// READ STATUS bits
#define ST_RX0IF 0x01
#define ST_RX1IF 0x02
#define ST_TXREQ(n) (0x04 << (2 * (n)))
#define ST_TXIF(n)  (0x08 << (2 * (n)))

#define TXQ_LEN 64

typedef struct {
    can_frame_t q[TXQ_LEN];
    volatile uint16_t head, tail;   // producer: head (any task, under lock); consumer: tail (CAN task)
    uint8_t busy;                   // bit n = TX buffer n loaded and not yet reported complete
    portMUX_TYPE lock;
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

static void wr(int chip, uint8_t reg, uint8_t v)
{
    uint8_t tx[3] = {I_WRITE, reg, v}, rx[3];
    xfer(chip, tx, rx, 3);
}

static uint8_t rd(int chip, uint8_t reg)
{
    uint8_t tx[3] = {I_READ, reg, 0}, rx[3] = {0};
    xfer(chip, tx, rx, 3);
    return rx[2];
}

static void bitmod(int chip, uint8_t reg, uint8_t mask, uint8_t v)
{
    uint8_t tx[4] = {I_BITMOD, reg, mask, v}, rx[4];
    xfer(chip, tx, rx, 4);
}

static bool set_mode(int chip, uint8_t reqop)
{
    bitmod(chip, R_CANCTRL, 0xE0, reqop);
    for (int i = 0; i < 50; i++) {
        if ((rd(chip, R_CANSTAT) & 0xE0) == reqop) return true;
    }
    return false;
}

bool mcp_init(int chip, bool listen_only)
{
    mcp_t *m = &s_mcp[chip];
    memset(m, 0, sizeof(*m));
    portMUX_INITIALIZE(&m->lock);
    uint8_t r = I_RESET, d;
    xfer(chip, &r, &d, 1);
    // config mode after reset; 500 kbit/s from 16 MHz: TQ 125 ns, 16 TQ/bit = sync 1 + prop 3 + PS1 7 + PS2 5
    // (sample point 69 %), SJW 2 TQ
    wr(chip, R_CNF1, 0x40);
    wr(chip, R_CNF2, 0xB2);
    wr(chip, R_CNF3, 0x04);
    wr(chip, R_RXB0CTRL, 0x64);   // receive everything, roll over into RXB1
    wr(chip, R_RXB1CTRL, 0x60);
    wr(chip, R_CANINTE, INT_RX0 | INT_RX1 | INT_ERR);   // TX completion is polled via READ STATUS
    wr(chip, R_CANINTF, 0x00);
    m->listen_only = listen_only;
    m->pending_mode = -1;
    bool ok = set_mode(chip, listen_only ? 0x60 : 0x00);
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
    return set_mode(chip, listen_only ? 0x60 : 0x00);
}

static void decode(const uint8_t *b, can_frame_t *f)
{
    // b: SIDH SIDL EID8 EID0 DLC D0..D7
    if (b[1] & 0x08) {
        f->ext = 1;
        f->id = ((uint32_t)b[0] << 21) | ((uint32_t)(b[1] & 0xE0) << 13) | ((uint32_t)(b[1] & 0x03) << 16) |
                ((uint32_t)b[2] << 8) | b[3];
        f->rtr = (b[4] >> 6) & 1;
    } else {
        f->ext = 0;
        f->id = ((uint32_t)b[0] << 3) | (b[1] >> 5);
        f->rtr = (b[1] >> 4) & 1;
    }
    uint8_t dlc = b[4] & 0x0F;
    f->dlc = dlc > 8 ? 8 : dlc;
    memcpy(f->data, &b[5], 8);
}

static void encode(const can_frame_t *f, uint8_t *b)
{
    if (f->ext) {
        b[0] = f->id >> 21;
        b[1] = ((f->id >> 13) & 0xE0) | 0x08 | ((f->id >> 16) & 0x03);
        b[2] = f->id >> 8;
        b[3] = f->id;
    } else {
        b[0] = f->id >> 3;
        b[1] = (f->id & 7) << 5;
        b[2] = b[3] = 0;
    }
    b[4] = (f->dlc & 0x0F) | (f->rtr ? 0x40 : 0);
    memcpy(&b[5], f->data, 8);
}

static void read_rxb(int chip, int n, mcp_rx_cb_t cb)
{
    uint8_t tx[14] = {n ? I_READ_RXB1 : I_READ_RXB0}, rx[14];
    xfer(chip, tx, rx, 14);   // CS release clears RXnIF
    can_frame_t f = {0};
    decode(&rx[1], &f);
    f.ts_us = (uint32_t)esp_timer_get_time();
    s_mcp[chip].st.rx++;
    cb(chip, &f);
}

static uint8_t read_status(int chip)
{
    uint8_t tx[2] = {I_STATUS, 0}, rx[2];
    xfer(chip, tx, rx, 2);
    // TXREQ bits are the truth for which transmit buffers are still on the wire (no TX interrupts used)
    s_mcp[chip].busy = ((rx[1] & ST_TXREQ(0)) ? 1 : 0) | ((rx[1] & ST_TXREQ(1)) ? 2 : 0) | ((rx[1] & ST_TXREQ(2)) ? 4 : 0);
    return rx[1];
}

void mcp_tx_pump(int chip)
{
    mcp_t *m = &s_mcp[chip];
    if (m->tail == m->head) return;
    if (m->listen_only) {
        m->tail = m->head;   // can't transmit: discard (counted at queue time)
        return;
    }
    if (m->busy == 7) read_status(chip);   // all three looked busy: check whether any has finished
    for (int n = 0; n < 3 && m->tail != m->head; n++) {
        if (m->busy & (1 << n)) continue;
        uint8_t tx[14] = {I_LOAD_TXB(n)}, rx[14];
        encode(&m->q[m->tail], &tx[1]);
        xfer(chip, tx, rx, 14);
        uint8_t rts = 0x80 | (1 << n), d;
        xfer(chip, &rts, &d, 1);
        m->busy |= 1 << n;
        m->tail = (m->tail + 1) % TXQ_LEN;
        m->st.tx++;
    }
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
    int got = 0;
    // one round per call: the CAN task round-robins the chips so a busy bus can't starve the others
    // (each MCP2515 only has two receive buffers). Per received frame: READ STATUS (2 bytes) + READ RX
    // BUFFER (14 bytes); TX completion is read from the same status byte, so no TX interrupts to clear.
    if (hal_mcp_int_asserted(chip)) {
        uint8_t st = read_status(chip);
        // RXB0 first: with rollover the older frame is in RXB0
        if (st & ST_RX0IF) { read_rxb(chip, 0, cb); got++; }
        if (st & ST_RX1IF) { read_rxb(chip, 1, cb); got++; }
        if (!got) {
            uint8_t intf = rd(chip, R_CANINTF);
            if (intf & (INT_ERR | INT_MERR)) {
                uint8_t eflg = rd(chip, R_EFLG);
                if (eflg & 0x40) m->st.rx_overflow++;
                if (eflg & 0x80) m->st.rx_overflow++;
                m->st.errors++;
                bitmod(chip, R_EFLG, 0xC0, 0);
                bitmod(chip, R_CANINTF, INT_ERR | INT_MERR, 0);
            }
        }
    }
    return got;
}

const mcp_stats_t *mcp_stats(int chip) { return &s_mcp[chip].st; }

void mcp_stats_reset(void)
{
    for (int i = 0; i < MCP_COUNT; i++) memset(&s_mcp[i].st, 0, sizeof(mcp_stats_t));
}
