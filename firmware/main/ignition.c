#include "ignition.h"

#include "config.h"

bool ignition_update(uint32_t now_ms, bool valid, int32_t vbat_mv)
{
    static bool on;
    static uint32_t since;   // start of the current run on the other side of the threshold
    static bool pending;
    if (!valid) return on;
    bool crossing = on ? vbat_mv < IGN_OFF_MV : vbat_mv > IGN_ON_MV;
    if (!crossing) {
        pending = false;
    } else if (!pending) {
        pending = true;
        since = now_ms;
    } else if (now_ms - since >= (on ? IGN_OFF_MS : IGN_ON_MS)) {
        on = !on;
        pending = false;
    }
    return on;
}
