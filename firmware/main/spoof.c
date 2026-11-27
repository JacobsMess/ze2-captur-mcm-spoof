#include "spoof.h"

#include <math.h>
#include "captur.h"
#include "config.h"
#include "gateway.h"
#include "hal.h"
#include "safety.h"

spoof_out_t g_spoof;

// Honda TBATT sensor: 10k NTC, B 3435 (PLACEHOLDER curve until checked against the MCM's own reported
// temperature in a CAN log). The MCM's input circuit is NOT assumed: the board measures it (see ntc_fit).
#define NTC_R25   10000.0f
#define NTC_B     3435.0f
#define VREF      5.0f      // DAC reference = MCM 5 V
#define R_SERIES  1000.0f   // R36-R38 between each op-amp and its TBATT line
#define FIT_V1    2.0f      // probe voltages for the fit: inside the normal temperature range
#define FIT_V2    3.0f
#define TRIM_MAX  0.2f      // readback trim limit, V
#define ADS_TBATT 0         // ADS1115 A: AIN0-2 = TBATT1-3 (connector side of R36-R38)

static ntc_fit_t s_fit[3];
static float s_trim[3];

float spoof_ntc_ohms(float t_c) { return NTC_R25 * expf(NTC_B * (1.0f / (t_c + 273.15f) - 1.0f / 298.15f)); }

bool spoof_ntc_fit(float v1, float n1, float v2, float n2, ntc_fit_t *f)
{
    // The line seen from our side is the MCM's Thevenin source (Vth behind Rth) and our op-amp behind R_SERIES:
    // node = s * vout + b, with s = Rth / (Rth + R_SERIES) and b = Vth * (1 - s). Two drive points give s and b.
    float s = (n2 - n1) / (v2 - v1), b = n1 - s * v1;
    if (!(s > 0.5f && s < 0.995f)) return false;   // no usable pull-up, or a read went wrong: keep the default
    f->slope = s;
    f->icpt = b;
    f->rth = R_SERIES * s / (1 - s);
    f->vth = b / (1 - s);
    f->valid = f->vth > 3.0f && f->vth < 5.5f;
    return f->valid;
}

float spoof_ntc_node_volts(const ntc_fit_t *f, float t_c)
{
    // what the MCM's own divider would show with the real sensor at t_c
    float r = spoof_ntc_ohms(t_c);
    return f->vth * r / (r + f->rth);
}

static uint16_t code(float volts)
{
    float c = volts / VREF * 4095.0f;
    return c < 0 ? 0 : c > 4095 ? 4095 : (uint16_t)c;
}

static float drive_for(int ch, float node)
{
    const ntc_fit_t *f = &s_fit[ch];
    return (node - f->icpt) / f->slope + s_trim[ch];
}

// Measure each line's input circuit: drive FIT_V1, then FIT_V2, read the node back. A few milliseconds at
// start-up, at voltages inside the normal temperature range. Without a fit, a 10k pull-up to 5 V is assumed.
static bool characterise(void)
{
    uint16_t c[4] = {code(FIT_V1), code(FIT_V1), code(FIT_V1), code(VREF / 2)};   // Hall offset: zero
    int32_t n1[3], n2[3];
    if (!hal_dac_write4(c)) return false;
    for (int i = 0; i < 3; i++) if (!hal_adc_island(ADS_TBATT, i, &n1[i])) return false;
    c[0] = c[1] = c[2] = code(FIT_V2);
    if (!hal_dac_write4(c)) return false;
    for (int i = 0; i < 3; i++) if (!hal_adc_island(ADS_TBATT, i, &n2[i])) return false;
    for (int i = 0; i < 3; i++) {
        if (!spoof_ntc_fit(FIT_V1, n1[i] / 1000.0f, FIT_V2, n2[i] / 1000.0f, &s_fit[i])) {
            float s = 10000.0f / (10000.0f + R_SERIES);
            s_fit[i] = (ntc_fit_t){.slope = s, .icpt = VREF * (1 - s), .rth = 10000.0f, .vth = VREF, .valid = false};
        }
    }
    return true;
}

void spoof_tick(uint32_t now_ms)
{
    static float integ;
    static bool fitted;
    static uint32_t last_write;
    static int trim_ch;
    static uint32_t last_ok;
    static bool ever_ok;
    const pack_state_t *p = &g_pack;

    if (!fitted) fitted = characterise();   // retried until the island (MCM 5 V) answers

    // temperatures: show the MCM the real pack range, clamped to what a healthy NiMH pack would report
    float t_lo = p->valid ? p->temp_min_c : 20, t_hi = p->valid ? p->temp_max_c : 20;
    if (g_safety.regen_inhibit && t_lo < CHARGE_MIN_TEMP_C) t_lo = -5;   // NiMH is also charge-limited when cold
    g_spoof.ntc_c[0] = t_lo;
    g_spoof.ntc_c[1] = (t_lo + t_hi) / 2;
    g_spoof.ntc_c[2] = t_hi;

    // SOC steering: PI on (MCM's SOC - real SOC). Positive offset = MCM counts more discharge = its SOC falls.
    float err = 0;
    if (g_honda.valid && p->valid) err = g_honda.mcm_soc_pct - p->soc_pct;
    integ += err * CONTROL_PERIOD_MS / 1000.0f;
    if (integ > 200) integ = 200;
    if (integ < -200) integ = -200;
    float off = 2.0f * err + 0.4f * integ;
    if (g_safety.regen_inhibit) off -= 60;     // MCM thinks it's fuller -> less regen
    if (g_safety.assist_inhibit) off += 60;    // MCM thinks it's emptier -> less assist
    if (off > OFFSET_MAX_MV) off = OFFSET_MAX_MV;
    if (off < -OFFSET_MAX_MV) off = -OFFSET_MAX_MV;
    g_spoof.offset_mv = off;
    g_spoof.dac[DAC_CH_OFFSET] = code(VREF / 2 + off / 1000.0f / OFFSET_GAIN);

    if (fitted && now_ms - last_write >= 50) {   // 20 Hz is plenty for temperatures and a slow SOC loop
        last_write = now_ms;
        for (int i = 0; i < 3; i++) {
            g_spoof.ntc_node_v[i] = spoof_ntc_node_volts(&s_fit[i], g_spoof.ntc_c[i]);
            g_spoof.dac[i] = code(drive_for(i, g_spoof.ntc_node_v[i]));
        }
        bool wrote = hal_dac_write4(g_spoof.dac);
        // close the loop on one line per pass with the readback: soaks up DAC, op-amp and fit errors
        int32_t mv;
        bool read = hal_adc_island(ADS_TBATT, trim_ch, &mv);
        if (wrote && read) {
            last_ok = now_ms;
            ever_ok = true;
        }
        if (read) {
            float t = s_trim[trim_ch] + 0.5f * (g_spoof.ntc_node_v[trim_ch] - mv / 1000.0f) / s_fit[trim_ch].slope;
            s_trim[trim_ch] = t > TRIM_MAX ? TRIM_MAX : t < -TRIM_MAX ? -TRIM_MAX : t;
        }
        trim_ch = (trim_ch + 1) % 3;
    }
    for (int i = 0; i < 3; i++) g_spoof.fit[i] = s_fit[i];
    // island I/O failing for ISLAND_FAIL_MS: the NTC and Hall outputs are no longer ours, so the taps float
    // (safety.c) and the MCM faults rather than running on stale analogue values
    g_spoof.island_ok = fitted && ever_ok && now_ms - last_ok < ISLAND_FAIL_MS;
    safety_island_report(g_spoof.island_ok);
    hal_out(OUT_OPTO_EN, g_safety.taps_enabled);
}
