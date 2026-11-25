// What the MCM measures: the three battery NTC lines and the Hall current sensor offset (SOC steering).
// The cell taps come straight off the real pack through the divider; firmware only switches them on or off.
#pragma once
#include <stdint.h>

typedef struct {
    float ntc_c[3];         // temperature the MCM is shown
    float offset_mv;        // added to the Hall signal (+ = MCM sees more discharge)
    uint16_t dac[4];
} spoof_out_t;

extern spoof_out_t g_spoof;
void spoof_tick(uint32_t now_ms);
float spoof_ntc_volts(float temp_c);   // exposed for tests
