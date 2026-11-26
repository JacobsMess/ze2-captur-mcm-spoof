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

// U10 clocks MCU_EN into the coil-return master FET on each WDI rising edge, and the watchdog clears it. Give
// it an edge now, so enabling or disabling takes effect at once rather than at the next kick.
static void master_enable(bool on)
{
    hal_out(OUT_MCU_EN, on);
    hal_out(OUT_WDI, false);
    hal_out(OUT_WDI, true);
    s_wdi = true;
}

static void drive(bool neg, bool pre, bool pos)
{
    hal_out(OUT_HS_MAINN, neg);
    hal_out(OUT_HS_PRE, pre);
    hal_out(OUT_HS_MAINP, pos);
}

static void all_open(void)
{
    drive(false, false, false);
    master_enable(false);
}

static void enter(ct_state_t st, uint32_t now_ms)
{
    s_st = st;
    s_t0 = now_ms;
}

static void fault(const char *why)
{
    all_open();
    s_fault = why;
    s_st = CT_FAULT;
    ESP_LOGE(TAG, "fault: %s", why);
}

void contactors_init(void)
{
    all_open();
    hal_out(OUT_HS_BMS, true);   // keep the Captur BMS powered while the board runs
}

ct_state_t contactors_state(void) { return s_st; }
bool contactors_energised(void) { return s_st != CT_OPEN && s_st != CT_FAULT; }
bool contactors_faulted(void) { return s_st == CT_FAULT; }
const char *contactors_fault(void) { return s_fault; }

void contactors_clear_fault(void)
{
    if (s_st == CT_FAULT) s_st = CT_OPEN;
    s_fault = "";
}

void contactors_kick_watchdog(uint32_t now_ms)
{
    static uint32_t last_pass, last_edge;
    static bool started;
    // A gap this long means the loop stalled. U11 may already have cleared the latch; either way the coils are
    // no longer under control, so drop everything before the next kick can clock MCU_EN back in.
    if (started && now_ms - last_pass > WDT_STALL_MS && contactors_energised()) fault("control loop stalled");
    started = true;
    last_pass = now_ms;
    if (now_ms - last_edge >= WDI_PERIOD_MS / 2) {   // toggle: one rising edge per WDI_PERIOD_MS
        last_edge = now_ms;
        s_wdi = !s_wdi;
        hal_out(OUT_WDI, s_wdi);
    }
}

void contactors_tick(uint32_t now_ms, bool want_closed, bool may_start)
{
    int32_t bus_mv = 0;
    bool bus_ok = hal_bus_mv(&bus_mv);
    uint64_t pack_mv = g_pack.pack_mv;
    uint32_t dt = now_ms - s_t0;

    if (s_st != CT_OPEN && s_st != CT_FAULT) {
        if (!want_closed) { all_open(); s_st = CT_OPEN; return; }
        if (!bus_ok) { fault("bus voltage sense invalid"); return; }
    }
    switch (s_st) {
    case CT_OPEN:
        if (!want_closed || !may_start || !g_pack.valid) break;
        if (!bus_ok) { fault("bus voltage sense invalid"); break; }
        if (bus_mv > DEAD_BUS_MV) { fault("bus live with contactors open (weld?)"); break; }
        master_enable(true);
        drive(false, true, false);            // precharge alone: a live bus now means main- is welded
        enter(CT_CHECK_NEG, now_ms);
        break;
    case CT_CHECK_NEG:
        if (bus_mv > DEAD_BUS_MV) { fault("main- welded"); break; }
        if (dt >= WELD_CHECK_MS) {
            drive(true, false, false);        // main- alone: a live bus now means main+ or precharge is welded
            enter(CT_CHECK_POS, now_ms);
        }
        break;
    case CT_CHECK_POS:
        if (bus_mv > DEAD_BUS_MV) { fault("main+ or precharge welded"); break; }
        if (dt >= WELD_CHECK_MS) {
            drive(true, true, false);
            enter(CT_PRECHARGE, now_ms);
        }
        break;
    case CT_PRECHARGE:
        if ((uint64_t)bus_mv * 100 >= pack_mv * PRECHARGE_PCT && pack_mv > 0) {
            drive(true, true, true);          // main+ closes with precharge still holding the bus up
            ESP_LOGI(TAG, "precharged in %lu ms", (unsigned long)dt);
            enter(CT_CLOSING, now_ms);
        } else if (dt > PRECHARGE_TIMEOUT_MS) {
            fault("precharge timeout (short on the bus?)");
        }
        break;
    case CT_CLOSING:
        if (dt >= MAIN_PICKUP_MS) drive(true, false, true);   // main+ has had time to pick up: drop precharge
        if (dt >= MAIN_PICKUP_MS + CLOSE_VERIFY_MS) {
            if ((uint64_t)bus_mv * 100 < pack_mv * CLOSED_MIN_PCT) { fault("main+ did not close"); break; }
            enter(CT_CLOSED, now_ms);
        }
        break;
    case CT_CLOSED:
        if (pack_mv && (uint64_t)bus_mv * 100 < pack_mv * BUS_COLLAPSE_PCT) fault("bus collapsed while closed");
        break;
    case CT_FAULT:
        break;   // latched: only contactors_clear_fault() (key-off) leaves here
    }
}
