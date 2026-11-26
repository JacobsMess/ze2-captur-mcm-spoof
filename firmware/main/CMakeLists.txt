idf_component_register(
    SRCS "main.c" "can_io.c" "mcp2518fd.c" "gateway.c" "canlog.c" "gvret.c" "captur.c" "spoof.c"
         "contactors.c" "control.c" "ignition.c" "pump.c" "safety.c" "zombie.c" "stats.c" "hal_hw.c" "hal_sim.c" "sim.c" "net.c" "ota.c"
    INCLUDE_DIRS "."
    REQUIRES driver esp_driver_gpio esp_driver_spi esp_driver_i2c esp_driver_ledc esp_adc esp_timer
             esp_wifi esp_netif esp_event nvs_flash esp_http_server app_update lwip)
