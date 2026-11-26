// Simulation build only: traffic generators for the four buses and the MCP2518FD register-level models.
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "can_types.h"

typedef struct {
    const char *name;
    float ev_load, ima_load, dash_load;   // fraction of 500 kbit/s bus time (1.0 = back-to-back frames)
} sim_scenario_t;

void sim_start(void);                      // runs every scenario and prints SIMRESULT lines, then SIMDONE

// used by hal_sim.c
void sim_model_spi(int chip, const uint8_t *tx, uint8_t *rx, size_t len);
bool sim_model_int(int chip);
bool sim_twai_pop(can_frame_t *f);
void sim_twai_tx(const can_frame_t *f);    // frames the firmware sends on CAN1 (the BMS model answers)
void sim_set_can_task(void *t);
extern bool g_sim_relay_split;
