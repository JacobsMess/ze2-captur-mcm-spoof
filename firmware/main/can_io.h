#pragma once
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "can_types.h"

// frames the application cares about (Captur BMS, Honda SOC etc.), for the control task on core 0
extern QueueHandle_t g_app_rx;

void can_io_start(void);           // init the MCP2518FDs + TWAI and start the CAN task on core 1
bool can_io_ready(int mcp_chip);   // chip initialised OK
bool can_io_healthy(void);         // all CAN controllers and the TWAI up, no SPI errors (OTA release check)
void can_io_kick(void);            // wake the CAN task (TX queued from another task)
