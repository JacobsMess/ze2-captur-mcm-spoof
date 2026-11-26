// What the MCM measures: the three battery NTC lines and the Hall current sensor offset (SOC steering).
// The cell taps come straight off the real pack through the divider; firmware only switches them on or off.
// NTC lines: the MCM's input circuit (pull-up value and voltage) is measured by the board at start-up, by driving
// two voltages and reading the line back (ADS1115 A), and the readback then trims each line continuously. Only
// the Honda sensor's own curve (spoof.c) is assumed.
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef struct {
    float slope, icpt;   // node = slope * drive + icpt
    float rth, vth;      // the MCM's input as a Thevenin source: pull-up ohms and volts
    bool valid;          // false: no usable pull-up found, 10k to 5 V assumed
} ntc_fit_t;

typedef struct {
    float ntc_c[3];         // temperature the MCM is shown
    float ntc_node_v[3];    // line voltage that means that temperature to the MCM
    float offset_mv;        // added to the Hall signal (+ = MCM sees more discharge)
    uint16_t dac[4];
    ntc_fit_t fit[3];
} spoof_out_t;

extern spoof_out_t g_spoof;
void spoof_tick(uint32_t now_ms);
float spoof_ntc_ohms(float temp_c);                                       // Honda sensor curve
bool spoof_ntc_fit(float v1, float n1, float v2, float n2, ntc_fit_t *f);  // exposed for tests
float spoof_ntc_node_volts(const ntc_fit_t *f, float temp_c);
