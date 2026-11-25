// GVRET binary protocol (as used by GVRET/ESP32RET and SavvyCAN): streams every frame from all four buses
// and accepts frames to send from SavvyCAN.
#pragma once
#include <stddef.h>
#include <stdint.h>

void gvret_start(void);
// encode one frame into GVRET binary form; returns bytes written (max 20). Exposed for the simulation/tests.
size_t gvret_encode(const void *frame, uint8_t *out);
