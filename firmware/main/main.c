// ZE2 Captur MCM spoof board firmware.
// Core 1: CAN task (all SPI/TWAI I/O, IMA man-in-the-middle forwarding). Core 0: control loop (100 Hz:
// Captur BMS, safety ladder, contactors, MCM spoofing, ZombieVerter), GVRET streaming, Wi-Fi, OTA.
#include <stdio.h>
#include "can_io.h"
#include "captur.h"
#include "contactors.h"
#include "control.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "gateway.h"
#include "gvret.h"
#include "hal.h"
#include "net.h"
#include "nvs.h"
#include "nvs_flash.h"
#include "ota.h"
#include "pump.h"
#include "safety.h"
#include "sdkconfig.h"
#include "sim.h"
#include "spoof.h"
#include "stats.h"
#include "zombie.h"

static const char *TAG = "main";

typedef struct {
    uint8_t stage;        // 1: MCM kept and spoofed; 2: MCM removed, ZombieVerter
    bool mitm;            // allow the gateway to split the IMA bus (off until the rewrite rules are proven)
    pump_cfg_t pump;      // pump.h: pump_mode, pump_hz, pump_inv
} cfg_t;

static cfg_t load_cfg(void)
{
    cfg_t c = {.stage = 1, .mitm = ZE2_SIM};
    nvs_handle_t h;
    if (nvs_open("ze2", NVS_READONLY, &h) == ESP_OK) {
        uint8_t v;
        if (nvs_get_u8(h, "stage", &v) == ESP_OK) c.stage = v;
        if (nvs_get_u8(h, "mitm", &v) == ESP_OK) c.mitm = v;
        if (nvs_get_u8(h, "pump_mode", &v) == ESP_OK && v <= PUMP_SIGNAL) c.pump.mode = (pump_mode_t)v;
        if (nvs_get_u8(h, "pump_inv", &v) == ESP_OK) c.pump.invert = v;
        uint32_t hz;
        if (nvs_get_u32(h, "pump_hz", &hz) == ESP_OK) c.pump.hz = hz;
        nvs_close(h);
    }
    return c;
}

static void control_task(void *arg)
{
    cfg_t cfg = *(cfg_t *)arg;
    TickType_t wake = xTaskGetTickCount();
    for (;;) {
        int64_t now_us = esp_timer_get_time();
        uint32_t now = (uint32_t)(now_us / 1000);
        contactors_kick_watchdog(now);   // first: a stall is caught before anything can re-arm the latch
        can_frame_t f;
        while (xQueueReceive(g_app_rx, &f, 0) == pdTRUE) {
            // freshness from arrival time; a frame stamped after now_us was read (other core) is 0 ms old
            int32_t age_us = (int32_t)((uint32_t)now_us - f.ts_us);
            uint32_t rx_ms = now - (age_us > 0 ? (uint32_t)age_us / 1000 : 0);
            captur_decode(&f, rx_ms);
            gateway_decode(&f, rx_ms);
        }
        bool ign = control_safety_step(now, cfg.stage == 1);
        if (cfg.stage == 1) spoof_tick(now);   // stage 2: taps stay off
        captur_tick(now);
        zombie_tick(now, cfg.stage == 2);
        gateway_tick(now, ign && cfg.mitm);
        pump_tick(now, ign ? (g_pack.temp_max_c > 35 ? 1.0f : 0.4f) : 0);
        ota_tick(now, can_io_healthy());
        vTaskDelayUntil(&wake, pdMS_TO_TICKS(CONTROL_PERIOD_MS));
    }
}

void app_main(void)
{
    esp_err_t e = nvs_flash_init();
    if (e == ESP_ERR_NVS_NO_FREE_PAGES || e == ESP_ERR_NVS_NEW_VERSION_FOUND) {
        nvs_flash_erase();
        nvs_flash_init();
    }
    static cfg_t cfg;
    cfg = load_cfg();
    ESP_LOGI(TAG, "stage %d, IMA man-in-the-middle %s%s", cfg.stage, cfg.mitm ? "enabled" : "disabled",
             ZE2_SIM ? " [SIMULATION BUILD]" : "");
    board_hal_init();                   // all outputs off, K4 relaxed: car runs as if the board weren't there
    captur_set_series(cfg.stage == 2 ? 2 * PACK_SERIES : PACK_SERIES);
    gateway_init();
    contactors_init();
    pump_init(cfg.pump);
#if CONFIG_ZE2_SIM
    sim_start();                  // models must exist before the drivers talk to them
#endif
    can_io_start();
    xTaskCreatePinnedToCore(control_task, "control", 4096, &cfg, 10, NULL, 0);
    gvret_start();
    net_start();
    ota_start();
}
