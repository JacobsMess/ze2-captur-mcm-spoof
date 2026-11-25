// Simulation build: four virtual CAN buses at a chosen load, three MCP2518FDs modelled at register level (a
// 32-deep receive FIFO, 16-deep transmit FIFO, FIFO status/user address, INT line), and a TWAI receive queue.
// A 125 us "bus clock" (esp_timer, ISR dispatch) delivers frames and completes transmissions. Everything
// else is the production firmware: CAN task, gateway, GVRET encoder, control loop.
#include "sdkconfig.h"
#if CONFIG_ZE2_SIM
#include "sim.h"

#include <stdio.h>
#include <string.h>
#include "canlog.h"
#include "captur.h"
#include "contactors.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "gateway.h"
#include "hal.h"
#include "mcp.h"
#include "safety.h"
#include "stats.h"

#define TICK_US 125              // half a frame time
#define FRAME_US 250             // 8-byte standard frame incl. average bit stuffing at 500 kbit/s (~125 bits)

bool g_sim_relay_split;
static TaskHandle_t s_can_task;

// ------------------------------------------------------------------ MCP2518FD model
// Register level, as much as the driver uses: RESET/READ/WRITE with auto-increment, C1CON mode request,
// FIFOCON/FIFOSTA/FIFOUA for one TX and one RX FIFO (8-byte payload objects, no timestamps) laid out in a
// 2 KB RAM in FIFO order, FIFOCI head/tail indices, UINC/TXREQ, RXOVIF, C1INT enables and the INT line.
#define M_RAM 2048
typedef struct {
    uint8_t sfr[0x300];
    uint8_t ram[M_RAM];
    uint8_t osc[0x18];
    struct { bool tx; uint8_t depth, head, tail, count; uint16_t ram; bool ovf, txreq; } f[3];   // FIFO1, FIFO2
    int32_t tx_left_us;          // >0: a frame is on the wire
    uint32_t overflow, delivered, transmitted;
    portMUX_TYPE lock;
} mcp_model_t;

static mcp_model_t s_m[MCP_COUNT];
#define OBJ 16

static uint32_t sfr32(const mcp_model_t *m, int a) { return m->sfr[a] | m->sfr[a + 1] << 8 | m->sfr[a + 2] << 16 | (uint32_t)m->sfr[a + 3] << 24; }
static uint8_t mode_of(const mcp_model_t *m) { return m->sfr[3] & 7; }   // OPMOD follows REQOP at once
static bool on_bus(const mcp_model_t *m) { return mode_of(m) == 6 || mode_of(m) == 3; }

static bool int_low(const mcp_model_t *m)
{
    uint32_t ie = sfr32(m, 0x1C) >> 16;
    return ((ie & 0x02) && m->f[2].count) || ((ie & 0x800) && m->f[2].ovf);
}

static void model_reset(mcp_model_t *m)
{
    memset(m->sfr, 0, sizeof(m->sfr));
    memset(m->f, 0, sizeof(m->f));
    m->sfr[0x02] = 0x98; m->sfr[0x03] = 0x04;   // C1CON reset value 0x0498_0760: configuration mode
    m->sfr[0x00] = 0x60; m->sfr[0x01] = 0x07;
    memset(m->osc, 0, sizeof(m->osc));
    m->osc[1] = 0x04;                           // OSCRDY
    m->tx_left_us = 0;
}

static void layout(mcp_model_t *m)              // RAM allocation in FIFO order, TXQ and TEF disabled
{
    uint16_t a = 0;
    for (int k = 1; k <= 2; k++) {
        uint32_t con = sfr32(m, 0x50 + 12 * k);
        m->f[k].tx = con & 0x80;
        m->f[k].depth = ((con >> 24) & 0x1F) + 1;
        m->f[k].ram = a;
        m->f[k].head = m->f[k].tail = m->f[k].count = 0;
        a += m->f[k].depth * OBJ;
    }
}

static uint8_t rd_byte(mcp_model_t *m, uint16_t a)
{
    if (a >= 0x400 && a < 0x400 + M_RAM) return m->ram[a - 0x400];
    if (a >= 0xE00 && a < 0xE18) return m->osc[a - 0xE00];
    if (a == 0x02) return (m->sfr[2] & 0x1F) | (mode_of(m) << 5);
    for (int k = 1; k <= 2; k++) {
        int sta = 0x54 + 12 * k, ua = 0x58 + 12 * k;
        if (a >= sta && a < sta + 4) {
            uint32_t v = 0;
            if (m->f[k].tx) v = (m->f[k].count < m->f[k].depth ? 1 : 0) | (m->f[k].count == 0 ? 4 : 0);
            else v = (m->f[k].count ? 1 : 0) | (m->f[k].count == m->f[k].depth ? 4 : 0) | (m->f[k].ovf ? 8 : 0);
            v |= (uint32_t)(m->f[k].tx ? m->f[k].tail : m->f[k].head) << 8;   // FIFOCI
            return v >> (8 * (a - sta));
        }
        if (a >= ua && a < ua + 4) {
            uint32_t v = m->f[k].ram + (m->f[k].tx ? m->f[k].head : m->f[k].tail) * OBJ;
            return v >> (8 * (a - ua));
        }
    }
    return a < sizeof(m->sfr) ? m->sfr[a] : 0;
}

static void wr_byte(mcp_model_t *m, uint16_t a, uint8_t v)
{
    if (a >= 0x400 && a < 0x400 + M_RAM) { m->ram[a - 0x400] = v; return; }
    if (a >= 0xE00) return;
    for (int k = 1; k <= 2; k++) {
        int con = 0x50 + 12 * k;
        if (a == con + 1) {                         // UINC / TXREQ / FRESET
            if (v & 0x01) {
                if (m->f[k].tx) { if (m->f[k].count < m->f[k].depth) { m->f[k].head = (m->f[k].head + 1) % m->f[k].depth; m->f[k].count++; } }
                else if (m->f[k].count) { m->f[k].tail = (m->f[k].tail + 1) % m->f[k].depth; m->f[k].count--; }
            }
            if (v & 0x02) m->f[k].txreq = true;
            return;
        }
        if (a == 0x54 + 12 * k) { if (!(v & 0x08)) m->f[k].ovf = false; return; }   // FIFOSTA: RXOVIF clear
    }
    if (a < sizeof(m->sfr)) m->sfr[a] = v;
    if (a >= 0x5C && a < 0x5C + 24 && mode_of(m) == 4) layout(m);
}

void sim_model_spi(int chip, const uint8_t *tx, uint8_t *rx, size_t len)
{
    mcp_model_t *m = &s_m[chip];
    memset(rx, 0, len);
    if (len < 2) return;
    uint8_t cmd = tx[0] >> 4;
    uint16_t a = (uint16_t)((tx[0] & 0x0F) << 8 | tx[1]);
    taskENTER_CRITICAL(&m->lock);
    if (cmd == 0x0) {
        model_reset(m);
    } else if (cmd == 0x3) {
        for (size_t i = 2; i < len; i++) rx[i] = rd_byte(m, a + i - 2);
    } else if (cmd == 0x2) {
        for (size_t i = 2; i < len; i++) wr_byte(m, a + i - 2, tx[i]);
    }
    taskEXIT_CRITICAL(&m->lock);
}

bool sim_model_int(int chip) { return int_low(&s_m[chip]); }

static void IRAM_ATTR notify(uint32_t bit, BaseType_t *woken)
{
    if (s_can_task) xTaskNotifyFromISR(s_can_task, bit, eSetBits, woken);
}

// a frame arrives from the wire into chip's receive FIFO
static void IRAM_ATTR deliver(int chip, uint32_t id, uint32_t now, BaseType_t *woken)
{
    mcp_model_t *m = &s_m[chip];
    taskENTER_CRITICAL_ISR(&m->lock);
    bool was_low = int_low(m);
    if (!on_bus(m)) {
        taskEXIT_CRITICAL_ISR(&m->lock);
        return;
    }
    if (m->f[2].count == m->f[2].depth) {
        m->f[2].ovf = true;
        m->overflow++;
    } else {
        uint8_t *b = &m->ram[m->f[2].ram + m->f[2].head * OBJ];
        memset(b, 0, 8);
        b[0] = id; b[1] = (id >> 8) & 0x07;           // SID, IDE = 0
        b[4] = 8;                                     // DLC
        b[8] = m->delivered;
        b[9] = m->delivered >> 8;
        b[10] = chip;
        b[11] = 0x55;
        memcpy(&b[12], &now, 4);                      // arrival time -> gateway latency
        m->f[2].head = (m->f[2].head + 1) % m->f[2].depth;
        m->f[2].count++;
        m->delivered++;
    }
    bool low = int_low(m);
    taskEXIT_CRITICAL_ISR(&m->lock);
    if (low && !was_low) notify(1u << chip, woken);    // falling edge on INT, like the GPIO interrupt
}

static void IRAM_ATTR tx_progress(int chip, BaseType_t *woken)
{
    mcp_model_t *m = &s_m[chip];
    taskENTER_CRITICAL_ISR(&m->lock);
    if (m->tx_left_us > 0 && (m->tx_left_us -= TICK_US) <= 0) {
        m->tx_left_us = 0;
        m->f[1].tail = (m->f[1].tail + 1) % m->f[1].depth;
        m->f[1].count--;
        m->transmitted++;
    }
    if (!m->tx_left_us && m->f[1].count && m->f[1].txreq && mode_of(m) == 6) m->tx_left_us = FRAME_US;
    taskEXIT_CRITICAL_ISR(&m->lock);
    (void)woken;
}

// ------------------------------------------------------------------ TWAI model
static QueueHandle_t s_twai_q;
static uint32_t s_twai_overflow;

bool sim_twai_pop(can_frame_t *f) { return s_twai_q && xQueueReceive(s_twai_q, f, 0) == pdTRUE; }

void sim_set_can_task(void *t) { s_can_task = t; }

// ------------------------------------------------------------------ traffic
static volatile float s_load[BUS_COUNT];     // per origin: EV, MCM-side, PCM-side, dash
static float s_credit[BUS_COUNT];
static uint32_t s_gen[BUS_COUNT];
static volatile uint32_t s_gen_us;           // time spent in the generator itself (subtracted from core 0)
static uint32_t s_seq;
static volatile uint32_t s_ticks;

static void IRAM_ATTR bus_tick(void *arg)
{
    int64_t t0 = esp_timer_get_time();
    uint32_t now = (uint32_t)t0;
    BaseType_t woken = pdFALSE;
    s_ticks++;
    for (int c = 0; c < MCP_COUNT; c++) tx_progress(c, &woken);
    // EV bus (TWAI): the Captur frames at 100 Hz each, the rest filler
    s_credit[BUS_EV] += s_load[BUS_EV] * TICK_US / FRAME_US;
    if (s_credit[BUS_EV] >= 1) {
        s_credit[BUS_EV] -= 1;
        can_frame_t f = {.dlc = 8, .bus = BUS_EV, .ts_us = now};
        uint32_t k = s_seq++ % 40;
        if (k == 0) {          // cells: min 3.68 V, max 3.71 V
            f.id = 0x5D7; f.data[0] = 3680 & 0xFF; f.data[1] = 3680 >> 8; f.data[2] = 3710 & 0xFF; f.data[3] = 3710 >> 8;
        } else if (k == 1) {   // pack 125.0 V, 12.3 A, SOC 62 %
            f.id = 0x5D8; f.data[0] = 1250 & 0xFF; f.data[1] = 1250 >> 8; f.data[2] = 123; f.data[4] = 124;
        } else if (k == 2) {   // temps 18..22 C
            f.id = 0x5D9; f.data[0] = 58; f.data[1] = 62;
        } else {
            f.id = 0x100 + k;
        }
        s_gen[BUS_EV]++;
        if (xQueueSendFromISR(s_twai_q, &f, &woken) != pdTRUE) s_twai_overflow++;
        notify(NOTIFY_TWAI_BIT, &woken);
    }
    // IMA bus: frames start on the MCM side or the PCM side. Joined (bypass): both chips hear every frame.
    for (int side = BUS_MCM; side <= BUS_PCM; side++) {
        s_credit[side] += s_load[side] * TICK_US / FRAME_US;
        if (s_credit[side] >= 1) {
            s_credit[side] -= 1;
            uint32_t id = (side == BUS_MCM ? 0x100 : 0x300) + (s_gen[side] % 24);
            s_gen[side]++;
            if (g_sim_relay_split) {
                deliver(side == BUS_MCM ? 0 : 1, id, now, &woken);
            } else {
                deliver(0, id, now, &woken);
                deliver(1, id, now, &woken);
            }
        }
    }
    s_credit[BUS_DASH] += s_load[BUS_DASH] * TICK_US / FRAME_US;
    if (s_credit[BUS_DASH] >= 1) {
        s_credit[BUS_DASH] -= 1;
        deliver(2, 0x1A0 + (s_gen[BUS_DASH]++ % 16), now, &woken);
    }
    s_gen_us += (uint32_t)(esp_timer_get_time() - t0);
    (void)woken;
}

// ------------------------------------------------------------------ emulator check
// QEMU runs the two cores in turn, not in parallel. This probe spins on core 1 (above the CAN task) for
// 300 ms and records the longest gap between two reads of the clock: time core 1 was frozen while core 0
// ran. Real silicon doesn't do this, so any loss that lines up with these gaps is an emulation artefact.
static volatile uint32_t s_freeze_max_us;
static void probe_task(void *arg)
{
    int64_t end = esp_timer_get_time() + 300000, last = esp_timer_get_time();
    uint32_t worst = 0;
    while (last < end) {
        int64_t t = esp_timer_get_time();
        if (t - last > worst) worst = (uint32_t)(t - last);
        last = t;
    }
    s_freeze_max_us = worst;
    vTaskDelete(NULL);
}

static uint32_t measure_freeze(void)
{
    s_freeze_max_us = 0;
    xTaskCreatePinnedToCore(probe_task, "probe", 2048, NULL, configMAX_PRIORITIES - 1, NULL, 1);
    while (!s_freeze_max_us) vTaskDelay(pdMS_TO_TICKS(50));
    return s_freeze_max_us;
}

// ------------------------------------------------------------------ scenarios
static const sim_scenario_t SCEN[] = {
    {"typical (EV 30%, IMA 40%, dash 30%)", 0.30f, 0.40f, 0.30f},
    {"busy (EV 60%, IMA 70%, dash 60%)", 0.60f, 0.70f, 0.60f},
    {"worst case (all four buses 100%)", 1.00f, 1.00f, 1.00f},
};

static void set_loads(const sim_scenario_t *s)
{
    s_load[BUS_EV] = s->ev_load;
    s_load[BUS_MCM] = s->ima_load / 2;   // the IMA bus load is shared by frames from both ends
    s_load[BUS_PCM] = s->ima_load / 2;
    s_load[BUS_DASH] = s->dash_load;
}

static void sim_task(void *arg)
{
    esp_timer_handle_t t;
    // ISR dispatch would be cheaper, but QEMU's ESP32-S3 doesn't deliver esp_timer ISR-dispatch alarms; the
    // esp_timer task (core 0, top priority) is used instead, so core 0 also pays a context switch per tick.
    esp_timer_create_args_t a = {.callback = bus_tick, .dispatch_method = ESP_TIMER_TASK, .name = "bus"};
    ESP_ERROR_CHECK(esp_timer_create(&a, &t));
    ESP_ERROR_CHECK(esp_timer_start_periodic(t, TICK_US));
    vTaskDelay(pdMS_TO_TICKS(200));
    printf("SIM bus clock: %lu ticks in 200 ms (expect ~1600)\n", (unsigned long)s_ticks);
    float load[2];
    for (size_t i = 0; i < sizeof(SCEN) / sizeof(SCEN[0]); i++) {
        const sim_scenario_t *sc = &SCEN[i];
        set_loads(sc);
        vTaskDelay(pdMS_TO_TICKS(700));           // settle (gateway splits the bus, contactors close)
        uint32_t freeze = measure_freeze();
        vTaskDelay(pdMS_TO_TICKS(300));
        stats_reset();
        uint32_t gen0[BUS_COUNT], ovf0[MCP_COUNT], tx0[MCP_COUNT], two0 = s_twai_overflow;
        memcpy(gen0, s_gen, sizeof(gen0));
        for (int c = 0; c < MCP_COUNT; c++) { ovf0[c] = s_m[c].overflow; tx0[c] = s_m[c].transmitted; }
        stats_cpu_load(load);
        uint32_t g0 = s_gen_us;
        int64_t t0 = esp_timer_get_time();
        vTaskDelay(pdMS_TO_TICKS(CONFIG_ZE2_SIM_SECONDS * 1000));
        float secs = (esp_timer_get_time() - t0) / 1e6f;
        stats_cpu_load(load);
        float gen_pct = (s_gen_us - g0) / (secs * 1e4f);
        uint32_t ovf = 0, wire_tx = 0;
        for (int c = 0; c < MCP_COUNT; c++) { ovf += s_m[c].overflow - ovf0[c]; wire_tx += s_m[c].transmitted - tx0[c]; }
        uint32_t spi_us = 0;
        for (int c = 0; c < MCP_COUNT; c++) spi_us += mcp_stats(c)->spi_us;
        uint32_t fwd = g_stats.fwd ? g_stats.fwd : 1;
        printf("SIMRESULT {\"scenario\":\"%s\",\"seconds\":%.2f,"
               "\"generated\":{\"ev\":%lu,\"mcm_side\":%lu,\"pcm_side\":%lu,\"dash\":%lu},"
               "\"received\":{\"ev\":%lu,\"mcm\":%lu,\"pcm\":%lu,\"dash\":%lu},"
               "\"mcp_rx_overflows\":%lu,\"twai_queue_overflows\":%lu,\"forwarded\":%lu,\"wire_tx\":%lu,"
               "\"tx_drops\":%lu,\"fwd_latency_us\":{\"avg\":%lu,\"max\":%lu,"
               "\"hist_lt\":{\"100\":%lu,\"200\":%lu,\"400\":%lu,\"800\":%lu,\"1600\":%lu,\"3200\":%lu,\"6400\":%lu,\"more\":%lu}},"
               "\"spi_busy_pct\":%.1f,\"can_task_longest_pass_us\":%lu,"
               "\"gvret_kbyte_s\":%.1f,\"log_drops\":%lu,"
               "\"cpu_pct\":{\"core0_raw\":%.1f,\"core0_minus_sim\":%.1f,\"core1\":%.1f},"
               "\"qemu_core1_freeze_max_us\":%lu,\"gateway\":%d,\"contactors\":%d,\"safety\":%d}\n",
               sc->name, secs,
               (unsigned long)(s_gen[BUS_EV] - gen0[BUS_EV]), (unsigned long)(s_gen[BUS_MCM] - gen0[BUS_MCM]),
               (unsigned long)(s_gen[BUS_PCM] - gen0[BUS_PCM]), (unsigned long)(s_gen[BUS_DASH] - gen0[BUS_DASH]),
               (unsigned long)g_stats.rx[BUS_EV], (unsigned long)g_stats.rx[BUS_MCM],
               (unsigned long)g_stats.rx[BUS_PCM], (unsigned long)g_stats.rx[BUS_DASH],
               (unsigned long)ovf, (unsigned long)(s_twai_overflow - two0), (unsigned long)g_stats.fwd,
               (unsigned long)wire_tx,
               (unsigned long)(g_stats.tx_drop[1] + g_stats.tx_drop[2] + mcp_stats(0)->tx_queue_drop + mcp_stats(1)->tx_queue_drop),
               (unsigned long)(g_stats.fwd_lat_sum_us / fwd), (unsigned long)g_stats.fwd_lat_max_us,
               (unsigned long)g_stats.fwd_lat_hist[0], (unsigned long)g_stats.fwd_lat_hist[1],
               (unsigned long)g_stats.fwd_lat_hist[2], (unsigned long)g_stats.fwd_lat_hist[3],
               (unsigned long)g_stats.fwd_lat_hist[4], (unsigned long)g_stats.fwd_lat_hist[5],
               (unsigned long)g_stats.fwd_lat_hist[6], (unsigned long)g_stats.fwd_lat_hist[7],
               spi_us / (secs * 1e4f), (unsigned long)g_stats.can_task_max_us,
               g_stats.gvret_bytes / secs / 1000.0f, (unsigned long)g_stats.log_drop,
               load[0], load[0] - gen_pct, load[1],
               (unsigned long)freeze, gateway_state(), contactors_state(), g_safety.level);
    }
    printf("SIMDONE\n");
    vTaskDelete(NULL);
}

void sim_start(void)
{
    for (int c = 0; c < MCP_COUNT; c++) { portMUX_INITIALIZE(&s_m[c].lock); model_reset(&s_m[c]); }
    s_twai_q = xQueueCreate(128, sizeof(can_frame_t));   // the real driver's rx_queue_len
    xTaskCreatePinnedToCore(sim_task, "sim", 4096, NULL, 3, NULL, 0);
}
#endif
