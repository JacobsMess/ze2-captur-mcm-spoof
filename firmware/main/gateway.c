#include "gateway.h"

#include "can_io.h"
#include "config.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "hal.h"
#include "mcp.h"
#include "stats.h"

static const char *TAG = "gateway";

#define HONDA_ID_MCM_SOC 0x000   // TODO: MCM -> PCM/dash frame carrying SOC (from a stock-car log)
#define MAX_HOOKS 16

honda_state_t g_honda;
static volatile gw_state_t s_state = GW_BYPASS;
static volatile uint32_t s_last_rx_ms[BUS_COUNT];
static struct { uint32_t id; gw_hook_t fn; } s_hooks[MAX_HOOKS];
static int s_nhooks;

void gateway_init(void)
{
    hal_out(OUT_RELAY_SPLIT, false);
    s_state = GW_BYPASS;
}

bool gateway_add_hook(uint32_t id, gw_hook_t hook)
{
    if (s_nhooks >= MAX_HOOKS) return false;
    s_hooks[s_nhooks].id = id;
    s_hooks[s_nhooks].fn = hook;
    s_nhooks++;
    return true;
}

gw_state_t gateway_state(void) { return s_state; }

void gateway_on_frame(const can_frame_t *fin)
{
    s_last_rx_ms[fin->bus] = (uint32_t)(esp_timer_get_time() / 1000);
    if (s_state != GW_SPLIT || (fin->bus != BUS_MCM && fin->bus != BUS_PCM)) return;
    can_frame_t f = *fin;
    for (int i = 0; i < s_nhooks; i++) {
        if (s_hooks[i].id == f.id && !s_hooks[i].fn((bus_id_t)fin->bus, &f)) return;
    }
#if CONFIG_ZE2_SIM
    // simulated frames carry their bus arrival time in bytes 4..7: measure arrival -> TX buffer loaded
    uint32_t born = f.data[4] | f.data[5] << 8 | f.data[6] << 16 | (uint32_t)f.data[7] << 24;
    stats_fwd_latency((uint32_t)esp_timer_get_time() - born);
#endif
    can_send(fin->bus == BUS_MCM ? BUS_PCM : BUS_MCM, &f);
}

bool gateway_wants(const can_frame_t *f)
{
    return HONDA_ID_MCM_SOC && f->id == HONDA_ID_MCM_SOC && (f->bus == BUS_MCM || f->bus == BUS_PCM);
}

void gateway_decode(const can_frame_t *f, uint32_t now_ms)
{
    if (HONDA_ID_MCM_SOC && f->id == HONDA_ID_MCM_SOC) {
        g_honda.mcm_soc_pct = f->data[0] * 0.5f;   // TODO scale
        g_honda.valid = true;
        g_honda.last_ms = now_ms;
    }
}

static const char *name(gw_state_t st)
{
    return st == GW_SPLIT ? "SPLIT" : st == GW_BYPASS ? "BYPASS" : st == GW_ARMING ? "ARMING" : "FAILED";
}

static uint32_t s_armed_ms;

static void enter(gw_state_t st, uint32_t now_ms)
{
    if (st == s_state) return;
    ESP_LOGW(TAG, "%s -> %s", name(s_state), name(st));
    if (st == GW_ARMING) {
        // talk on both halves first, then split: the MCM and PCM lose each other for only the relay's
        // switching time (~3 ms) and the board is already forwarding when they reappear
        mcp_request_listen_only(0, false);
        mcp_request_listen_only(1, false);
        can_io_kick();
        s_armed_ms = now_ms;
    } else if (st == GW_SPLIT) {
        hal_out(OUT_RELAY_SPLIT, true);
    } else {
        hal_out(OUT_RELAY_SPLIT, false);
        mcp_request_listen_only(0, true);
        mcp_request_listen_only(1, true);
        can_io_kick();
    }
    s_state = st;
}

// signed: the CAN task may stamp a frame after the control task read the clock
static int32_t age(uint32_t now_ms, int bus) { return (int32_t)(now_ms - s_last_rx_ms[bus]); }

void gateway_tick(uint32_t now_ms, bool allow_split)
{
    if (!can_io_ready(0) || !can_io_ready(1)) {
        enter(GW_FAILED, now_ms);
        return;
    }
    switch (s_state) {
    case GW_BYPASS:
        // only split once traffic has been seen on the joined bus recently (car awake)
        if (allow_split && age(now_ms, BUS_MCM) < 100) enter(GW_ARMING, now_ms);
        break;
    case GW_ARMING:
        if (!allow_split) {
            enter(GW_BYPASS, now_ms);
        } else if (mcp_mode(0) == 0 && mcp_mode(1) == 0) {
            enter(GW_SPLIT, now_ms);
        } else if (now_ms - s_armed_ms > GW_ARM_MS) {
            ESP_LOGE(TAG, "controllers did not confirm normal mode: bypass, latched until key-off");
            enter(GW_FAILED, now_ms);
        }
        break;
    case GW_SPLIT:
        if (!allow_split) {
            enter(GW_BYPASS, now_ms);
        } else if (mcp_mode(0) != 0 || mcp_mode(1) != 0) {
            ESP_LOGE(TAG, "controller left normal mode while split: bypass, latched until key-off");
            enter(GW_FAILED, now_ms);
        } else if (age(now_ms, BUS_MCM) > BUS_SILENT_MS || age(now_ms, BUS_PCM) > BUS_SILENT_MS) {
            ESP_LOGE(TAG, "IMA half silent while split: bypass, latched until key-off");
            enter(GW_FAILED, now_ms);
        }
        break;
    case GW_FAILED:
        if (!allow_split) {
            hal_out(OUT_RELAY_SPLIT, false);
            s_state = GW_BYPASS;   // re-armed at key-off
        }
        break;
    }
}
