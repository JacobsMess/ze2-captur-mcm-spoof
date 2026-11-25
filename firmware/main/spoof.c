#include "spoof.h"

#include <math.h>
#include "captur.h"
#include "config.h"
#include "gateway.h"
#include "hal.h"
#include "safety.h"

spoof_out_t g_spoof;

// Honda TBATT sensor model (PLACEHOLDER until measured on the car): 10k NTC, B 3435, 10k pull-up to the MCM's
// 5 V. The DAC (ratiometric to the same 5 V) drives the node voltage through the op-amp buffer.
#define NTC_R25   10000.0f
#define NTC_B     3435.0f
#define NTC_RPU   10000.0f
#define VREF      5.0f

float spoof_ntc_volts(float t_c)
{
    float r = NTC_R25 * expf(NTC_B * (1.0f / (t_c + 273.15f) - 1.0f / 298.15f));
    return VREF * r / (r + NTC_RPU);
}

static uint16_t code(float volts)
{
    float c = volts / VREF * 4095.0f;
    return c < 0 ? 0 : c > 4095 ? 4095 : (uint16_t)c;
}

void spoof_tick(uint32_t now_ms)
{
    static float integ;
    const pack_state_t *p = &g_pack;
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

    for (int i = 0; i < 3; i++) g_spoof.dac[i] = code(spoof_ntc_volts(g_spoof.ntc_c[i]));
    g_spoof.dac[DAC_CH_OFFSET] = code(VREF / 2 + off / 1000.0f / OFFSET_GAIN);
    static uint32_t last_write;
    if (now_ms - last_write >= 50) {   // 20 Hz is plenty for temperatures and a slow SOC loop
        last_write = now_ms;
        hal_dac_write4(g_spoof.dac);
    }
    hal_out(OUT_OPTO_EN, g_safety.taps_enabled);
}
