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
static volatile int32_t s_link_mv;

int32_t contactors_link_mv(void) { return s_link_mv; }

// U10 clocks MCU_EN into the coil-return master FET on each WDI rising edge, and the watchdog clears it. Give
// it an edge now, so enabling or disabling takes effect at once rather than at the next kick.
static void master_enable(bool on)
{
    hal_out(OUT_MCU_EN, on);
    hal_out(OUT_WDI, false);
    hal_out(OUT_WDI, true);
    s_wdi = true;
}

static void drive(bool pre, bool pos)
{
    hal_out(OUT_HS_PRE, pre);
    hal_out(OUT_HS_MAINP, pos);
}

static void all_open(void)
{
    drive(false, false);
    hal_out(OUT_HS_MAINN, false);   // spare channel: no main- contactor on the Captur
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

// mean of the link over [from, from + CLOSE_AVG_MS) of the CLOSING window, in mV
static struct { int64_t sum; int n; } s_avg[2];

static void sample(uint32_t dt, int32_t bus_mv)
{
    const uint32_t start[2] = {MAIN_PICKUP_MS + CONTROL_PERIOD_MS, MAIN_PICKUP_MS + CLOSE_VERIFY_MS - CLOSE_AVG_MS};
    for (int i = 0; i < 2; i++) {
        if (dt >= start[i] && dt < start[i] + CLOSE_AVG_MS) {
            s_avg[i].sum += bus_mv;
            s_avg[i].n++;
        }
    }
}

static int64_t mean(int i) { return s_avg[i].n ? s_avg[i].sum / s_avg[i].n : 0; }

void contactors_tick(uint32_t now_ms, bool want_closed, bool may_start)
{
    int32_t bus_mv = 0;
    bool bus_ok = hal_bus_mv(&bus_mv);
    s_link_mv = bus_ok ? bus_mv : -1;
    int64_t pack_mv = (int64_t)g_pack.pack_mv;
    uint32_t dt = now_ms - s_t0;

    if (s_st != CT_OPEN && s_st != CT_FAULT) {
        if (!want_closed) { all_open(); s_st = CT_OPEN; return; }
        if (!bus_ok) { fault("bus voltage sense invalid"); return; }
        if (pack_mv <= 0) { fault("no pack voltage while energised"); return; }
        if ((int64_t)bus_mv * 100 > pack_mv * LINK_MAX_PCT + LINK_MAX_EXTRA_MV * 100) {
            fault("link above pack voltage: bus sense or BMS data implausible");
            return;
        }
        // a soft trip (or anything else that withdraws start permission) aborts a close that hasn't finished
        if (s_st != CT_CLOSED && !may_start) { fault("start permission withdrawn during close"); return; }
    }
    switch (s_st) {
    case CT_OPEN:
        if (!want_closed || !may_start || !g_pack.valid || pack_mv <= 0) break;
        if (!bus_ok) { fault("bus voltage sense invalid"); break; }
        // pack negative is hard-wired, so a live link with both coils off means main+ or precharge is welded
        if (bus_mv > DEAD_BUS_MV) { fault("link live with contactors open: main+ or precharge welded"); break; }
        master_enable(true);
        drive(true, false);
        enter(CT_PRECHARGE, now_ms);
        break;
    case CT_PRECHARGE:
        if (dt > PRECHARGE_TIMEOUT_MS) {   // deadline first: a late rise is still a failed precharge
            fault("precharge timeout (short on the bus?)");
        } else if ((int64_t)bus_mv * 100 >= pack_mv * PRECHARGE_PCT) {
            drive(true, true);                // main+ closes with precharge still holding the link up
            ESP_LOGI(TAG, "precharged in %lu ms", (unsigned long)dt);
            s_avg[0].sum = s_avg[1].sum = 0;
            s_avg[0].n = s_avg[1].n = 0;
            enter(CT_CLOSING, now_ms);
        }
        break;
    case CT_CLOSING:
        if (dt >= MAIN_PICKUP_MS) drive(false, true);   // main+ has had time to pick up: drop precharge
        sample(dt, bus_mv);
        if (dt >= MAIN_PICKUP_MS + CLOSE_VERIFY_MS) {
            int64_t first = mean(0), last = mean(1);
            if (last * 100 < pack_mv * CLOSED_MIN_PCT) { fault("main+ did not close"); break; }
            if (CLOSE_DROOP_PM && (first - last) * 1000 > pack_mv * CLOSE_DROOP_PM) {
                fault("link decays with precharge off: main+ open");
                break;
            }
            ESP_LOGI(TAG, "closed: link %lld -> %lld mV over %d ms", (long long)first, (long long)last,
                     CLOSE_VERIFY_MS - CLOSE_AVG_MS);
            enter(CT_CLOSED, now_ms);
        }
        break;
    case CT_CLOSED:
        if ((int64_t)bus_mv * 100 < pack_mv * BUS_COLLAPSE_PCT) fault("bus collapsed while closed");
        break;
    case CT_FAULT:
        break;   // latched: only contactors_clear_fault() (key-off) leaves here
    }
}
