// Key-on/key-off from the board supply (VBAT_P, after D7), read by the ADC on IG_SENSE. Thresholds with
// hysteresis and dwell times: a crank dip must not look like key-off, because key-off is what clears a latched
// hard trip and a contactor fault.
#pragma once
#include <stdbool.h>
#include <stdint.h>

// valid: the ADC read worked. An invalid read changes nothing.
bool ignition_update(uint32_t now_ms, bool valid, int32_t vbat_mv);
