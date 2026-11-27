#include "safety.h"

#include <stddef.h>

#include "captur.h"
#include "config.h"
#include "esp_log.h"

static const char *TAG = "safety";
safety_t g_safety = {.level = SAFE_HARD_TRIP, .reason = "boot"};
static bool s_latched;
static const char *s_latch_reason = "";
static bool s_ign, s_energised;
static bool s_seen_bms;   // BMS heard since key-on: before that, "BMS silent" is just start-up, not a trip
static bool s_island_ok;
static const char *s_boot_latch;

bool safety_ota_allowed(void) { return !s_ign && !s_energised; }
void safety_island_report(bool ok) { s_island_ok = ok; }
void safety_boot_latch(const char *reason) { s_boot_latch = reason; }

void safety_tick(uint32_t now_ms, const safety_in_t *in)
{
    bool ignition = in->ignition;
    const char *ct_fault = in->fault;
    s_ign = ignition;
    s_energised = in->energised;
    if (in->key_off_seen) s_boot_latch = NULL;
    safety_t s = {.level = SAFE_OK, .taps_enabled = true, .contactors_permitted = true, .reason = "ok"};
    const pack_state_t *p = &g_pack;
    bool fresh = captur_fresh(now_ms);

    if (fresh) s_seen_bms = true;
    if (!ignition) {   // debounced key-off (ignition.c): the only thing that clears a latched trip
        s.level = SAFE_HARD_TRIP;
        s.reason = "ignition off";
        s_latched = false;
        s_seen_bms = false;
    } else if (ct_fault) {
        s.level = SAFE_HARD_TRIP;
        s.reason = ct_fault;
    } else if (!fresh) {
        s.level = SAFE_HARD_TRIP;
        s.reason = "BMS silent";
    } else if (!captur_consistent()) {
        s.level = SAFE_HARD_TRIP;
        s.reason = "pack voltage disagrees with cells";
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
    if (s_latched) {   // a hard trip holds until key-off
        s.level = SAFE_HARD_TRIP;
        s.reason = s_latch_reason;
    }
    if (s_boot_latch) {
        s.level = SAFE_HARD_TRIP;
        s.reason = s_boot_latch;
    }
    s.regen_inhibit = p->temp_min_c < CHARGE_MIN_TEMP_C || p->cell_max_mv >= CELL_MAX_MV;
    s.assist_inhibit = p->cell_min_mv <= CELL_MIN_MV;
    // the MCM sees the pack only through verified-closed contactors and with the island's outputs under control
    if (s.level >= SAFE_SOFT_TRIP || !in->closed || !s_island_ok) s.taps_enabled = false;
    if (s.level == SAFE_HARD_TRIP) {
        s.contactors_permitted = false;
        if (ignition && !s_latched && (s_seen_bms || ct_fault)) {
            ESP_LOGE(TAG, "HARD TRIP: %s", s.reason);
            s_latched = true;
            s_latch_reason = s.reason;
        }
    }
    s.start_permitted = s.contactors_permitted && s.level <= SAFE_STEER;
    g_safety = s;
}
