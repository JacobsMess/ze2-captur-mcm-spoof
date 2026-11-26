// Coolant pump on J2. Q3 pulls J2.14 (PUMP_N) low; J2.13 is the fused coil/pump 12 V. One board, three kinds
// of pump, chosen in NVS ("ze2" namespace) without touching the hardware:
//   pump_mode 0 ON/OFF (default): 2-wire pump, + to J2.13, - to J2.14. Q3 fully on or off. Safe for any 2-wire
//               pump, including brushless ones with their own electronics, which must not see a chopped supply.
//   pump_mode 1 PWM:    2-wire brushed pump: Q3 chops its supply at pump_hz (default 20 kHz); D6 freewheels.
//   pump_mode 2 SIGNAL: 3-wire PWM pump: + to J2.13, ground to a spare J2 ground, signal to J2.14. Q3 is the
//               open-collector driver at pump_hz (default 100 Hz), running demand clamped to 10-90 % low time;
//               pump_inv 1 if the pump reads line-high time as demand. Check the pump's own spec.
// Budget: F2 (5 A) also feeds the Captur coils (< 0.8 A): keep the pump under about 3 A.
// Readback (GPIO35, high above about 9 V): Q3 off and the line low = nothing connected (no pump, or no pull-up
// in a 3-wire pump); Q3 on and the line high = Q3 or its gate drive failed. Reported, not tripped: the safety
// ladder already acts on pack temperature.
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef enum { PUMP_ONOFF, PUMP_PWM, PUMP_SIGNAL } pump_mode_t;

typedef struct {
    pump_mode_t mode;
    uint32_t hz;
    bool invert;
} pump_cfg_t;

void pump_init(pump_cfg_t cfg);
void pump_tick(uint32_t now_ms, float demand);   // demand 0 (off) .. 1 (full)
const char *pump_fault(void);                    // "" when fine
float pump_duty(void);                           // fraction of time Q3 is on
