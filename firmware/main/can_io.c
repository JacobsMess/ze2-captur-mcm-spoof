// The CAN task: the only code that touches the SPI bus and the TWAI receive queue. Pinned to core 1 at high
// priority so man-in-the-middle forwarding is never held up by Wi-Fi (core 0). Each received frame is
// forwarded (gateway), copied to the log ring for GVRET, and passed to the control task if it's of interest.
#include "can_io.h"

#include "captur.h"
#include "canlog.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/task.h"
#include "gateway.h"
#include "hal.h"
#include "mcp.h"
#include "stats.h"

static const char *TAG = "can_io";
#define NOTIFY_TX_BIT (1u << 4)

QueueHandle_t g_app_rx;
static TaskHandle_t s_task;
static bool s_ready[MCP_COUNT];
static const bus_id_t CHIP_BUS[MCP_COUNT] = {BUS_MCM, BUS_PCM, BUS_DASH};

static int bus_chip(bus_id_t b) { return b == BUS_MCM ? 0 : b == BUS_PCM ? 1 : b == BUS_DASH ? 2 : -1; }

static void handle_rx(const can_frame_t *f)
{
    g_stats.rx[f->bus]++;
    canlog_push(f);
    gateway_on_frame(f);
    if (captur_wants(f) || gateway_wants(f)) xQueueSend(g_app_rx, f, 0);
}

static void mcp_rx(int chip, const can_frame_t *fin)
{
    can_frame_t f = *fin;
    f.bus = CHIP_BUS[chip];
    f.dir = 0;
    handle_rx(&f);
}

bool can_send(bus_id_t bus, const can_frame_t *fin)
{
    can_frame_t f = *fin;
    f.bus = bus;
    f.dir = 1;
    f.ts_us = (uint32_t)esp_timer_get_time();
    bool ok;
    if (bus == BUS_EV) {
        ok = hal_twai_send(&f);
    } else {
        ok = mcp_queue_tx(bus_chip(bus), &f);
        if (ok && xTaskGetCurrentTaskHandle() != s_task) can_io_kick();
    }
    if (ok) {
        g_stats.tx[bus]++;
        canlog_push(&f);
    } else {
        g_stats.tx_drop[bus]++;
    }
    return ok;
}

void can_io_kick(void)
{
    if (s_task) xTaskNotify(s_task, NOTIFY_TX_BIT, eSetBits);
}

static void can_task(void *arg)
{
    for (;;) {
        uint32_t bits = 0;
        xTaskNotifyWait(0, UINT32_MAX, &bits, pdMS_TO_TICKS(5));
        int64_t t0 = esp_timer_get_time();
        for (int c = 0; c < MCP_COUNT; c++) if (s_ready[c]) mcp_apply_pending(c);   // mode changes
        // round-robin every chip whose INT is low (not just the notified ones: catches edges that arrived
        // while a pass was running), one READ STATUS round each, then start any queued transmissions
        for (int pass = 0; pass < 64; pass++) {
            int busy = 0;
            for (int c = 0; c < MCP_COUNT; c++) {
                if (s_ready[c] && hal_mcp_int_asserted(c)) busy += mcp_service(c, mcp_rx) + 1;
            }
            can_frame_t f;
            for (int n = 0; n < 4 && hal_twai_receive(&f); n++) {
                f.bus = BUS_EV;
                f.dir = 0;
                handle_rx(&f);
                busy++;
            }
            for (int c = 0; c < 2; c++) if (s_ready[c]) mcp_tx_pump(c);   // IMA halves: forwarded frames
            if (!busy) break;
        }
        if (bits & NOTIFY_TX_BIT) {   // frames queued by the control task
            for (int c = 0; c < MCP_COUNT; c++) if (s_ready[c]) mcp_tx_pump(c);
        }
        uint32_t dt = (uint32_t)(esp_timer_get_time() - t0);
        if (dt > g_stats.can_task_max_us) g_stats.can_task_max_us = dt;
    }
}

bool can_io_ready(int chip) { return s_ready[chip]; }

void can_io_start(void)
{
    g_app_rx = xQueueCreate(64, sizeof(can_frame_t));
    // MCM side starts listen-only: the board must not talk on the IMA bus until the gateway splits it.
    // The dash tap is listen-only in stage 1.
    s_ready[0] = mcp_init(0, true);
    s_ready[1] = mcp_init(1, true);
    s_ready[2] = mcp_init(2, true);
    for (int c = 0; c < MCP_COUNT; c++) {
        if (!s_ready[c]) ESP_LOGE(TAG, "MCP2518FD #%d init failed", c);
    }
    xTaskCreatePinnedToCore(can_task, "can_io", 4096, NULL, configMAX_PRIORITIES - 2, &s_task, 1);
    hal_set_can_task(s_task);
    canlog_set_can_task(s_task);
}
