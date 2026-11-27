#include "control.h"

#include "contactors.h"
#include "hal.h"
#include "ignition.h"
#include "safety.h"

bool control_safety_step(uint32_t now_ms, bool stage1)
{
    int32_t vbat = 0;
    bool vbat_ok = hal_vbat_mv(&vbat);
    bool ign = ignition_update(now_ms, vbat_ok, vbat);
    if (!ign) contactors_clear_fault();   // key-off is the only reset
    const char *fault = contactors_faulted() ? contactors_fault()
                        : ignition_failed(now_ms) ? "ignition sense failed" : NULL;
    safety_in_t in = {.ignition = ign, .key_off_seen = ignition_off_confirmed(), .energised = contactors_energised(),
                      .closed = contactors_state() == CT_CLOSED, .fault = fault};
    safety_tick(now_ms, &in);
    // stage 2: the board is a CAN gateway only; the sequencer never runs, so coils stay off
    if (stage1) contactors_tick(now_ms, g_safety.contactors_permitted && ign, g_safety.start_permitted);
    return ign;
}
