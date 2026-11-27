// Key-on/key-off from the board supply (VBAT_P, after D7), read by the ADC on IG_SENSE. Thresholds with
// hysteresis and dwell times: a crank dip must not look like key-off, because key-off is what clears a latched
// hard trip and a contactor fault.
#pragma once
#include <stdbool.h>
#include <stdint.h>

// valid: the ADC read worked. An invalid read changes nothing; IGN_INVALID_MS of them is ignition_failed().
bool ignition_update(uint32_t now_ms, bool valid, int32_t vbat_mv);
// A real key-off has been seen: the supply read below IGN_OFF_MV for IGN_OFF_MS (not merely "not yet on" at
// boot). Clears the unexpected-reset latch (safety.h).
bool ignition_off_confirmed(void);
bool ignition_failed(uint32_t now_ms);
