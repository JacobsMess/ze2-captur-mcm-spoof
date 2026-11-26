// Simulation HAL: the real MCP2518FD driver talks to register-level models through this SPI shim, which also
// burns the time a real 16 MHz SPI transaction takes, so SPI cost lands on the CAN task as it would on the
// board. I2C writes block (without CPU) for their bus time, like the interrupt-driven I2C driver does.
#include "sdkconfig.h"
#if CONFIG_ZE2_SIM
#include "config.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "hal.h"
#include "sim.h"

// per transaction: ESP-IDF's SPI master docs give 9 us for a one-byte polling transaction via CPU on the
// ESP32-S3 (setup + FIFO + transfer); taken here as 8 us fixed + 0.5 us per byte at 16 MHz
#define SPI_OVERHEAD_US 8
#define SPI_NS_PER_BYTE 500

static bool s_out[OUT_COUNT];
static int64_t s_bus_t;
static int32_t s_bus_mv;

void board_hal_init(void) {}
void hal_set_can_task(void *t) { sim_set_can_task(t); }

bool hal_spi_xfer(int chip, const uint8_t *tx, uint8_t *rx, size_t len)
{
    int64_t until = esp_timer_get_time() + SPI_OVERHEAD_US + (int64_t)(len * SPI_NS_PER_BYTE + 999) / 1000;
    sim_model_spi(chip, tx, rx, len);
    while (esp_timer_get_time() < until) { }
    return true;
}

bool hal_mcp_int_asserted(int chip) { return sim_model_int(chip); }
bool hal_twai_receive(can_frame_t *f) { return sim_twai_pop(f); }
bool hal_twai_send(const can_frame_t *f)
{
    sim_twai_tx(f);
    return true;
}
bool hal_twai_ok(void) { return true; }

void hal_out(hal_out_t o, bool on)
{
    s_out[o] = on;
    if (o == OUT_RELAY_SPLIT) g_sim_relay_split = on;
}

bool hal_vbat_mv(int32_t *mv) { *mv = 13800; return true; }
void hal_pump_config(uint32_t hz) {}
void hal_pump_pwm(float duty) {}
bool hal_pump_line_high(void) { return true; }

bool hal_dac_write4(const uint16_t code[4])
{
    vTaskDelay(1);   // 13 bytes at 400 kHz ~ 0.3 ms, interrupt driven: the task blocks, the CPU is free
    return true;
}

bool hal_adc_island(int dev, int ch, int32_t *mv)
{
    vTaskDelay(2);
    *mv = 2500;
    return true;
}

bool hal_bus_mv(int32_t *out)
{
    // bus side of the Captur contactors: RC charge through the precharge resistor (tau 150 ms), instant
    // through the main contactor, slow bleed when open
    const int32_t pack = 125600;   // matches the simulated BMS (34 x 3.695 V)
    int64_t now = esp_timer_get_time();
    float dt = (now - s_bus_t) / 1e6f;
    s_bus_t = now;
    if (s_out[OUT_HS_MAINP]) s_bus_mv = pack;   // Captur: pack negative hard-wired, main+ and precharge only
    else if (s_out[OUT_HS_PRE]) s_bus_mv += (int32_t)((pack - s_bus_mv) * (dt / 0.15f > 1 ? 1 : dt / 0.15f));
    else s_bus_mv -= (int32_t)(s_bus_mv * (dt / 5.0f > 1 ? 1 : dt / 5.0f));
    *out = s_bus_mv;
    return true;
}
#endif
