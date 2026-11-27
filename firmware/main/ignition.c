#include "ignition.h"

#include "config.h"

static bool s_on, s_started, s_off_seen;
static uint32_t s_last_valid;

bool ignition_update(uint32_t now_ms, bool valid, int32_t vbat_mv)
{
    static uint32_t since, low_since;   // start of the current run across the threshold / below IGN_OFF_MV
    static bool pending, low;
    if (!s_started) {
        s_started = true;
        s_last_valid = now_ms;
    }
    if (!valid) return s_on;
    s_last_valid = now_ms;
    bool crossing = s_on ? vbat_mv < IGN_OFF_MV : vbat_mv > IGN_ON_MV;
    if (!crossing) {
        pending = false;
    } else if (!pending) {
        pending = true;
        since = now_ms;
    } else if (now_ms - since >= (s_on ? IGN_OFF_MS : IGN_ON_MS)) {
        s_on = !s_on;
        pending = false;
    }
    if (vbat_mv >= IGN_OFF_MV) {
        low = false;
    } else if (!low) {
        low = true;
        low_since = now_ms;
    } else if (now_ms - low_since >= IGN_OFF_MS) {
        s_off_seen = true;
    }
    if (s_on) s_off_seen = false;
    return s_on;
}

bool ignition_off_confirmed(void) { return s_off_seen && !s_on; }

bool ignition_failed(uint32_t now_ms) { return s_started && now_ms - s_last_valid > IGN_INVALID_MS; }
