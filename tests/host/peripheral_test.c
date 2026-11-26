// Host tests of the pump driver and the NTC line handling (pump.c, spoof.c) against small models:
//   - the pump line: Q3 pulls it low; with Q3 off a connected pump (or a 3-wire pump's pull-up) holds it high;
//   - each TBATT line: the MCM's input as a pull-up (Vth behind Rth), our op-amp behind 1k, an ADS1115 readback.
// One scenario per process: ./peripheral_test <scenario>; exit 0 = pass.
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "captur.h"
#include "gateway.h"
#include "hal.h"
#include "pump.h"
#include "safety.h"
#include "spoof.h"

pack_state_t g_pack = {.valid = true, .temp_min_c = 18, .temp_max_c = 30, .soc_pct = 60};
safety_t g_safety = {.level = SAFE_OK, .taps_enabled = true};
honda_state_t g_honda;

// ------------------------------------------------------------------ pump line
static float duty;
static uint32_t hz;
static bool pump_connected = true, q3_dead_open;
void hal_pump_config(uint32_t f) { hz = f; }
void hal_pump_pwm(float d) { duty = d; }
bool hal_pump_line_high(void)
{
    bool q3_on = duty >= 1 && !q3_dead_open;
    return !q3_on && pump_connected;
}

// ------------------------------------------------------------------ NTC lines
static float rth = 6800, vth = 5.0f, dac_gain = 1.0f;
static uint16_t dac[4];
bool hal_dac_write4(const uint16_t c[4]) { memcpy(dac, c, sizeof dac); return true; }
static float node_v(int ch)
{
    float vo = dac[ch] / 4095.0f * 5.0f * dac_gain;
    return (vo * rth + vth * 1000) / (rth + 1000);
}
bool hal_adc_island(int dev, int ch, int32_t *mv)
{
    if (dev != 0 || ch > 2) return false;
    *mv = (int32_t)lroundf(node_v(ch) * 1000);
    return true;
}
void hal_out(hal_out_t o, bool on) {}

// ------------------------------------------------------------------ scenarios
static int fails;
#define CHECK(c, msg) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d %s\n", __func__, __LINE__, msg); fails++; } } while (0)
static uint32_t now = 1000;
static void run_spoof(uint32_t ms) { for (uint32_t t = 0; t < ms; t += 10) spoof_tick(now += 10); }
static void run_pump(uint32_t ms, float demand) { for (uint32_t t = 0; t < ms; t += 10) pump_tick(now += 10, demand); }

static void ntc_measures_mcm_input(void)
{
    run_spoof(2000);
    for (int i = 0; i < 3; i++) {
        CHECK(g_spoof.fit[i].valid && fabsf(g_spoof.fit[i].rth - rth) < 0.03f * rth, "pull-up found");
        CHECK(fabsf(g_spoof.fit[i].vth - vth) < 0.05f, "pull-up voltage found");
        CHECK(fabsf(node_v(i) - g_spoof.ntc_node_v[i]) < 0.01f, "line at the target voltage");
    }
    // the MCM's own divider with the real sensor at 18 C would read this:
    float r = spoof_ntc_ohms(18);
    CHECK(fabsf(node_v(0) - vth * r / (r + rth)) < 0.01f, "18 C reads as 18 C through the MCM's divider");
}

static void ntc_trim_absorbs_dac_error(void)
{
    dac_gain = 1.03f;   // 3 % DAC/op-amp gain error after the fit
    run_spoof(500);
    dac_gain = 0.97f;
    run_spoof(3000);
    for (int i = 0; i < 3; i++) CHECK(fabsf(node_v(i) - g_spoof.ntc_node_v[i]) < 0.01f, "readback trim holds the line");
}

static void ntc_no_pullup_falls_back(void)
{
    rth = 1e7f;   // no pull-up: the op-amp sets the line on its own
    run_spoof(500);
    CHECK(!g_spoof.fit[0].valid && g_spoof.fit[0].rth == 10000.0f, "falls back to 10k to 5 V");
}

static void pump_onoff_default(void)
{
    pump_init((pump_cfg_t){0});
    run_pump(500, 0.4f);
    CHECK(duty == 1, "ON/OFF: any demand is fully on (never chops a 2-wire pump)");
    CHECK(!*pump_fault(), "healthy");
    run_pump(500, 0);
    CHECK(duty == 0 && !*pump_fault(), "off, line high through the pump");
}

static void pump_open_circuit(void)
{
    pump_init((pump_cfg_t){0});
    pump_connected = false;
    run_pump(500, 0);
    CHECK(strstr(pump_fault(), "open"), "no pump: line low with Q3 off");
}

static void pump_q3_failed(void)
{
    pump_init((pump_cfg_t){0});
    q3_dead_open = true;
    run_pump(500, 1);
    CHECK(strstr(pump_fault(), "Q3"), "line high with Q3 on");
}

static void pump_signal_mode(void)
{
    pump_init((pump_cfg_t){.mode = PUMP_SIGNAL, .invert = true});
    CHECK(hz == 100, "3-wire signal at 100 Hz by default");
    run_pump(100, 0.05f);
    CHECK(fabsf(duty - 0.9f) < 1e-6f, "demand clamped to 10 %, inverted");
    run_pump(100, 1);
    CHECK(fabsf(duty - 0.1f) < 1e-6f, "demand clamped to 90 %, inverted");
    run_pump(100, 0);
    CHECK(duty == 0, "off: line released");
}

static void pump_pwm_mode(void)
{
    pump_init((pump_cfg_t){.mode = PUMP_PWM});
    CHECK(hz == 20000, "brushed pump chopped at 20 kHz by default");
    run_pump(100, 0.1f);
    CHECK(fabsf(duty - 0.3f) < 1e-6f, "minimum duty so a brushed pump starts");
}

static const struct { const char *name; void (*fn)(void); } SCEN[] = {
    {"ntc_measures_mcm_input", ntc_measures_mcm_input}, {"ntc_trim_absorbs_dac_error", ntc_trim_absorbs_dac_error},
    {"ntc_no_pullup_falls_back", ntc_no_pullup_falls_back}, {"pump_onoff_default", pump_onoff_default},
    {"pump_open_circuit", pump_open_circuit}, {"pump_q3_failed", pump_q3_failed},
    {"pump_signal_mode", pump_signal_mode}, {"pump_pwm_mode", pump_pwm_mode},
};

int main(int argc, char **argv)
{
    if (argc < 2) {
        for (size_t i = 0; i < sizeof SCEN / sizeof SCEN[0]; i++) printf("%s\n", SCEN[i].name);
        return 0;
    }
    for (size_t i = 0; i < sizeof SCEN / sizeof SCEN[0]; i++) {
        if (strcmp(argv[1], SCEN[i].name)) continue;
        SCEN[i].fn();
        return fails ? 1 : 0;
    }
    fprintf(stderr, "unknown scenario %s\n", argv[1]);
    return 2;
}
