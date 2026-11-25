#include "contactors.h"

#include "captur.h"
#include "config.h"
#include "esp_log.h"
#include "hal.h"

static const char *TAG = "contactors";
static ct_state_t s_st = CT_OPEN;
static uint32_t s_t0;
static const char *s_fault = "";

static bool s_wdi;

// U10 (D flip-flop) clocks MCU_EN into the coil-return master FET on each WDI rising edge, and the watchdog
// clears it. Give it an edge now, so enabling or disabling takes effect at once rather than at the next kick.
static void master_enable(bool on)
{
    hal_out(OUT_MCU_EN, on);
    hal_out(OUT_WDI, false);
    hal_out(OUT_WDI, true);
    s_wdi = true;
}

static void all_open(void)
{
    hal_out(OUT_HS_MAINP, false);
    hal_out(OUT_HS_PRE, false);
    hal_out(OUT_HS_MAINN, false);
    master_enable(false);
}

void contactors_init(void)
{
    all_open();
    hal_out(OUT_HS_BMS, true);   // keep the Captur BMS powered while the board runs
}

ct_state_t contactors_state(void) { return s_st; }
const char *contactors_fault(void) { return s_fault; }

void contactors_kick_watchdog(uint32_t now_ms)
{
    static uint32_t last;
    if (now_ms - last >= WDI_PERIOD_MS / 2) {   // toggle: one edge per WDI_PERIOD_MS/2
        last = now_ms;
        s_wdi = !s_wdi;
        hal_out(OUT_WDI, s_wdi);
    }
}

static void fault(const char *why)
{
    all_open();
    s_fault = why;
    s_st = CT_FAULT;
    ESP_LOGE(TAG, "fault: %s", why);
}

void contactors_tick(uint32_t now_ms, bool want_closed)
{
    int32_t bus_mv = hal_bus_mv();
    uint32_t pack_mv = g_pack.pack_mv;
    switch (s_st) {
    case CT_OPEN:
        if (want_closed && g_pack.valid) {
            // weld check: with everything open the bus side must be dead
            if (bus_mv > 20000) { fault("bus live with contactors open (weld?)"); break; }
            master_enable(true);
            hal_out(OUT_HS_MAINN, true);
            hal_out(OUT_HS_PRE, true);
            s_t0 = now_ms;
            s_st = CT_PRECHARGE;
        }
        break;
    case CT_PRECHARGE:
        if (!want_closed) { all_open(); s_st = CT_OPEN; break; }
        if ((uint64_t)bus_mv * 100 >= (uint64_t)pack_mv * PRECHARGE_PCT && pack_mv > 0) {
            hal_out(OUT_HS_MAINP, true);
            hal_out(OUT_HS_PRE, false);
            s_st = CT_CLOSED;
            ESP_LOGI(TAG, "closed after %lu ms precharge", (unsigned long)(now_ms - s_t0));
        } else if (now_ms - s_t0 > PRECHARGE_TIMEOUT_MS) {
            fault("precharge timeout (short on the bus?)");
        }
        break;
    case CT_CLOSED:
        if (!want_closed) { all_open(); s_st = CT_OPEN; break; }
        if (pack_mv && (uint64_t)bus_mv * 100 < (uint64_t)pack_mv * 70) fault("bus collapsed while closed");
        break;
    case CT_FAULT:
        if (!want_closed) s_st = CT_OPEN;   // cleared by a key-off (safety drops the request)
        break;
    }
}
