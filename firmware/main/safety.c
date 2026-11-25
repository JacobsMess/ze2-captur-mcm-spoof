#include "safety.h"

#include "captur.h"
#include "config.h"
#include "esp_log.h"

static const char *TAG = "safety";
safety_t g_safety = {.level = SAFE_HARD_TRIP, .reason = "boot"};
static bool s_latched;
static bool s_ign, s_closed;
static bool s_seen_bms;   // BMS heard since key-on: before that, "BMS silent" is just start-up, not a trip

void safety_reset_latch(void) { s_latched = false; }

bool safety_ota_allowed(void) { return !s_ign && !s_closed; }

void safety_tick(uint32_t now_ms, bool ignition, bool contactors_closed)
{
    s_ign = ignition;
    s_closed = contactors_closed;
    safety_t s = {.level = SAFE_OK, .taps_enabled = true, .contactors_permitted = true, .reason = "ok"};
    const pack_state_t *p = &g_pack;

    if (captur_fresh(now_ms)) s_seen_bms = true;
    if (!ignition) {
        s.level = SAFE_HARD_TRIP;
        s.reason = "ignition off";
        s_latched = false;
        s_seen_bms = false;
    } else if (!captur_fresh(now_ms)) {
        s.level = SAFE_HARD_TRIP;
        s.reason = "BMS silent";
    } else if (p->cell_max_mv >= CELL_HARD_MAX_MV || p->cell_min_mv <= CELL_HARD_MIN_MV ||
               p->temp_max_c >= PACK_MAX_TEMP_C + 5) {
        s.level = SAFE_HARD_TRIP;
        s.reason = "cell/temp hard limit";
    } else if (p->cell_max_mv >= CELL_MAX_MV + 25 || p->cell_min_mv <= CELL_MIN_MV - 50 ||
               p->temp_max_c >= PACK_MAX_TEMP_C) {
        s.level = SAFE_SOFT_TRIP;
        s.reason = "soft limit exceeded despite steering";
    } else if (p->cell_max_mv >= CELL_MAX_MV || p->cell_min_mv <= CELL_MIN_MV) {
        s.level = SAFE_STEER;
        s.reason = "near cell limit";
    }
    if (s_latched) s.level = SAFE_HARD_TRIP;   // a hard trip holds until key-off
    s.regen_inhibit = p->temp_min_c < CHARGE_MIN_TEMP_C || p->cell_max_mv >= CELL_MAX_MV;
    s.assist_inhibit = p->cell_min_mv <= CELL_MIN_MV;
    if (s.level >= SAFE_SOFT_TRIP) s.taps_enabled = false;
    if (s.level == SAFE_HARD_TRIP) {
        s.contactors_permitted = false;
        if (ignition && !s_latched && s_seen_bms) {
            ESP_LOGE(TAG, "HARD TRIP: %s", s.reason);
            s_latched = true;
        }
    }
    g_safety = s;
}
