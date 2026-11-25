// Firmware update over Wi-Fi: POST the .bin to http://<board>/update. Accepted only with ignition off and the
// Captur contactors open. A new image runs on probation: it is marked good after it has been up for
// OTA_PROBATION_S with all CAN controllers initialised, otherwise the bootloader rolls back to the old one.
#pragma once
#include <stdbool.h>
#include <stdint.h>

#define OTA_PROBATION_S 30

void ota_start(void);
void ota_tick(uint32_t now_ms, bool healthy);
