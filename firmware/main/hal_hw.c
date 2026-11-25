// Real-board HAL. Compiled out in the simulation build (hal_sim.c takes over).
#include "sdkconfig.h"
#if !CONFIG_ZE2_SIM
#include <string.h>
#include "config.h"
#include "driver/gpio.h"
#include "driver/i2c_master.h"
#include "driver/ledc.h"
#include "driver/spi_master.h"
#include "driver/twai.h"
#include "esp_adc/adc_cali.h"
#include "esp_adc/adc_cali_scheme.h"
#include "esp_adc/adc_oneshot.h"
#include "esp_attr.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "hal.h"

static const char *TAG = "hal";
static spi_device_handle_t s_spi[MCP_COUNT];
static const int INT_PIN[MCP_COUNT] = {PIN_CAN2_INT, PIN_CAN3_INT, PIN_CAN4_INT};
static const int CS_PIN[MCP_COUNT] = {PIN_SPI_CS2, PIN_SPI_CS3, PIN_SPI_CS4};
static const int OUT_PIN[OUT_COUNT] = {PIN_HS_PRE, PIN_HS_MAINP, PIN_HS_MAINN, PIN_HS_BMS, PIN_MCU_EN, PIN_WDI,
                                       PIN_OPTO_EN, PIN_RELAY_SPLIT};
static TaskHandle_t s_can_task;
static i2c_master_dev_handle_t s_dac, s_adc[2];
static adc_oneshot_unit_handle_t s_adc1;
static adc_cali_handle_t s_cali;

static void IRAM_ATTR int_isr(void *arg)
{
    BaseType_t woken = pdFALSE;
    if (s_can_task) xTaskNotifyFromISR(s_can_task, 1u << (int)(intptr_t)arg, eSetBits, &woken);
    portYIELD_FROM_ISR(woken);
}

void hal_set_can_task(void *t) { s_can_task = t; }

void board_hal_init(void)
{
    // outputs low (everything off, relay relaxed = IMA bus joined) before anything else
    uint64_t mask = 0;
    for (int i = 0; i < OUT_COUNT; i++) mask |= 1ULL << OUT_PIN[i];
    gpio_config_t o = {.pin_bit_mask = mask, .mode = GPIO_MODE_OUTPUT};
    gpio_config(&o);
    for (int i = 0; i < OUT_COUNT; i++) gpio_set_level(OUT_PIN[i], 0);
    gpio_config_t ig = {.pin_bit_mask = 1ULL << PIN_IG_SENSE, .mode = GPIO_MODE_INPUT};
    gpio_config(&ig);

    // SPI: three MCP2518FDs on one bus, polling transactions from the CAN task
    spi_bus_config_t bus = {.mosi_io_num = PIN_SPI_MOSI, .miso_io_num = PIN_SPI_MISO, .sclk_io_num = PIN_SPI_SCK,
                            .quadwp_io_num = -1, .quadhd_io_num = -1, .max_transfer_sz = 64};
    // no DMA: every transaction fits the 64-byte CPU buffer (mcp2518fd.c caps its bursts at MCP_MAX_XFER)
    ESP_ERROR_CHECK(spi_bus_initialize(SPI2_HOST, &bus, SPI_DMA_DISABLED));
    for (int i = 0; i < MCP_COUNT; i++) {
        spi_device_interface_config_t d = {.clock_speed_hz = MCP_SPI_HZ, .mode = 0, .spics_io_num = CS_PIN[i],
                                           .queue_size = 2};
        ESP_ERROR_CHECK(spi_bus_add_device(SPI2_HOST, &d, &s_spi[i]));
    }
    gpio_install_isr_service(ESP_INTR_FLAG_IRAM);
    for (int i = 0; i < MCP_COUNT; i++) {
        gpio_config_t c = {.pin_bit_mask = 1ULL << INT_PIN[i], .mode = GPIO_MODE_INPUT,
                           .pull_up_en = GPIO_PULLUP_ENABLE, .intr_type = GPIO_INTR_NEGEDGE};
        gpio_config(&c);
        gpio_isr_handler_add(INT_PIN[i], int_isr, (void *)(intptr_t)i);
    }

    // TWAI (CAN1, EV bus)
    twai_general_config_t g = TWAI_GENERAL_CONFIG_DEFAULT(PIN_TWAI_TX, PIN_TWAI_RX, TWAI_MODE_NORMAL);
    g.rx_queue_len = 128;
    g.tx_queue_len = 32;
    twai_timing_config_t t = TWAI_TIMING_CONFIG_500KBITS();
    twai_filter_config_t f = TWAI_FILTER_CONFIG_ACCEPT_ALL();
    if (twai_driver_install(&g, &t, &f) == ESP_OK) twai_start();
    else ESP_LOGE(TAG, "TWAI install failed");

    // I2C to the analog island (through the ISO1540)
    i2c_master_bus_config_t ib = {.i2c_port = 0, .sda_io_num = PIN_I2C_SDA, .scl_io_num = PIN_I2C_SCL,
                                  .clk_source = I2C_CLK_SRC_DEFAULT, .glitch_ignore_cnt = 7};
    i2c_master_bus_handle_t i2c;
    ESP_ERROR_CHECK(i2c_new_master_bus(&ib, &i2c));
    i2c_device_config_t dc = {.dev_addr_length = I2C_ADDR_BIT_LEN_7, .scl_speed_hz = I2C_HZ};
    dc.device_address = MCP4728_ADDR;
    i2c_master_bus_add_device(i2c, &dc, &s_dac);
    dc.device_address = ADS1115_A_ADDR;
    i2c_master_bus_add_device(i2c, &dc, &s_adc[0]);
    dc.device_address = ADS1115_B_ADDR;
    i2c_master_bus_add_device(i2c, &dc, &s_adc[1]);

    // AMC1311 outputs on ADC1 ch0/ch1
    adc_oneshot_unit_init_cfg_t u = {.unit_id = ADC_UNIT_1};
    adc_oneshot_new_unit(&u, &s_adc1);
    adc_oneshot_chan_cfg_t cc = {.atten = ADC_ATTEN_DB_12, .bitwidth = ADC_BITWIDTH_DEFAULT};
    adc_oneshot_config_channel(s_adc1, ADC_CHANNEL_0, &cc);
    adc_oneshot_config_channel(s_adc1, ADC_CHANNEL_1, &cc);
    adc_cali_curve_fitting_config_t cf = {.unit_id = ADC_UNIT_1, .atten = ADC_ATTEN_DB_12,
                                          .bitwidth = ADC_BITWIDTH_DEFAULT};
    adc_cali_create_scheme_curve_fitting(&cf, &s_cali);

    // coolant pump PWM, 1 kHz
    ledc_timer_config_t lt = {.speed_mode = LEDC_LOW_SPEED_MODE, .duty_resolution = LEDC_TIMER_10_BIT,
                              .timer_num = LEDC_TIMER_0, .freq_hz = 1000, .clk_cfg = LEDC_AUTO_CLK};
    ledc_timer_config(&lt);
    ledc_channel_config_t lc = {.gpio_num = PIN_PUMP_PWM, .speed_mode = LEDC_LOW_SPEED_MODE,
                                .channel = LEDC_CHANNEL_0, .timer_sel = LEDC_TIMER_0, .duty = 0};
    ledc_channel_config(&lc);
}

void IRAM_ATTR hal_spi_xfer(int chip, const uint8_t *tx, uint8_t *rx, size_t len)
{
    spi_transaction_t t = {.length = len * 8, .tx_buffer = tx, .rx_buffer = rx};
    spi_device_polling_transmit(s_spi[chip], &t);
}

bool hal_mcp_int_asserted(int chip) { return gpio_get_level(INT_PIN[chip]) == 0; }

bool hal_twai_receive(can_frame_t *f)
{
    twai_message_t m;
    if (twai_receive(&m, 0) != ESP_OK) return false;
    f->id = m.identifier;
    f->ext = m.extd;
    f->rtr = m.rtr;
    f->dlc = m.data_length_code > 8 ? 8 : m.data_length_code;
    memcpy(f->data, m.data, 8);
    f->ts_us = (uint32_t)esp_timer_get_time();
    return true;
}

bool hal_twai_send(const can_frame_t *f)
{
    twai_message_t m = {.identifier = f->id, .extd = f->ext, .rtr = f->rtr, .data_length_code = f->dlc};
    memcpy(m.data, f->data, 8);
    return twai_transmit(&m, 0) == ESP_OK;
}

void hal_out(hal_out_t o, bool on) { gpio_set_level(OUT_PIN[o], on); }
bool hal_ignition_on(void) { return gpio_get_level(PIN_IG_SENSE); }

void hal_pump_pwm(float duty)
{
    ledc_set_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0, (uint32_t)(duty * 1023));
    ledc_update_duty(LEDC_LOW_SPEED_MODE, LEDC_CHANNEL_0);
}

bool hal_dac_write4(const uint16_t code[4])
{
    // MCP4728 multi-write: per channel 0x40|ch<<1, then VREF=Vdd (0), PD=00, gain x1 + code
    uint8_t b[12];
    for (int ch = 0; ch < 4; ch++) {
        b[3 * ch] = 0x40 | ch << 1;
        b[3 * ch + 1] = (code[ch] >> 8) & 0x0F;
        b[3 * ch + 2] = code[ch] & 0xFF;
    }
    return i2c_master_transmit(s_dac, b, sizeof(b), 5) == ESP_OK;
}

bool hal_adc_island(int dev, int ch, int32_t *mv)
{
    // single-shot, single-ended AINch, +/-4.096 V, 860 SPS
    uint16_t cfg = 0x8000 | (0x4 + ch) << 12 | 0x1 << 9 | 0x1 << 8 | 0x7 << 5 | 0x3;
    uint8_t w[3] = {0x01, cfg >> 8, cfg & 0xFF};
    if (i2c_master_transmit(s_adc[dev], w, 3, 5) != ESP_OK) return false;
    vTaskDelay(pdMS_TO_TICKS(2));
    uint8_t reg = 0x00, r[2];
    if (i2c_master_transmit_receive(s_adc[dev], &reg, 1, r, 2, 5) != ESP_OK) return false;
    *mv = (int16_t)(r[0] << 8 | r[1]) * 4096 / 32768;
    return true;
}

int32_t hal_bus_mv(void)
{
    int raw, p = 0, n = 0;
    adc_oneshot_read(s_adc1, ADC_CHANNEL_0, &raw);
    adc_cali_raw_to_voltage(s_cali, raw, &p);
    adc_oneshot_read(s_adc1, ADC_CHANNEL_1, &raw);
    adc_cali_raw_to_voltage(s_cali, raw, &n);
    // AMC1311: differential out = input (2 V full scale). Divider RS1-RS4 4 x 100k over RS5 4.7k (1 %):
    // x86.1, 172 V full scale. Trim HV_DIV_X1000 against a meter on the pack once.
    int32_t mv = (int32_t)((int64_t)(p - n) * HV_DIV_X1000 / 1000);
    return mv < 0 ? 0 : mv;
}
#endif
