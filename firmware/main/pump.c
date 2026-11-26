#include "pump.h"

#include "config.h"
#include "esp_log.h"
#include "hal.h"

static const char *TAG = "pump";
static pump_cfg_t s_cfg;
static float s_duty;
static const char *s_fault = "";
static uint32_t s_since;   // Q3 steady (fully on or fully off) since

void pump_init(pump_cfg_t cfg)
{
    if (!cfg.hz) cfg.hz = cfg.mode == PUMP_SIGNAL ? PUMP_SIGNAL_HZ : PUMP_PWM_HZ;
    s_cfg = cfg;
    hal_pump_config(cfg.mode == PUMP_ONOFF ? PUMP_PWM_HZ : cfg.hz);
    hal_pump_pwm(0);
}

const char *pump_fault(void) { return s_fault; }
float pump_duty(void) { return s_duty; }

static float clampf(float v, float lo, float hi) { return v < lo ? lo : v > hi ? hi : v; }

void pump_tick(uint32_t now_ms, float demand)
{
    float duty;
    bool run = demand > 0;
    switch (s_cfg.mode) {
    case PUMP_PWM:
        duty = run ? clampf(demand, PUMP_MIN_DUTY, 1) : 0;
        break;
    case PUMP_SIGNAL:
        duty = run ? clampf(demand, 0.1f, 0.9f) : 0;
        if (run && s_cfg.invert) duty = 1 - duty;
        break;
    default:
        duty = run ? 1 : 0;
        break;
    }
    if (duty != s_duty) {
        s_duty = duty;
        hal_pump_pwm(duty);
        s_since = now_ms;
    }

    // the line readback only means something while Q3 is steady; otherwise keep the last verdict
    const char *f = s_fault;
    if ((s_duty == 0 || s_duty == 1) && now_ms - s_since >= PUMP_SETTLE_MS) {
        bool high = hal_pump_line_high();
        f = "";
        if (s_duty == 0 && !high) {
            f = s_cfg.mode == PUMP_SIGNAL ? "signal line low (no pump, or pump fault)" : "open circuit (no pump?)";
        }
        if (s_duty == 1 && high) f = "line high with Q3 on (Q3 or gate drive failed)";
    }
    if (f != s_fault) {
        if (*f) ESP_LOGW(TAG, "%s", f);
        s_fault = f;
    }
}
