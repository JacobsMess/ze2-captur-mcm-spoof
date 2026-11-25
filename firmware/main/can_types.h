#pragma once
#include <stdbool.h>
#include <stdint.h>
#include "config.h"

typedef struct {
    uint32_t id;       // 11 or 29 bit
    uint8_t ext : 1;
    uint8_t rtr : 1;
    uint8_t dlc : 4;
    uint8_t bus;       // bus_id_t
    uint8_t dir;       // 0 = received, 1 = transmitted by us
    uint8_t data[8];
    uint32_t ts_us;    // capture time (low 32 bits of esp_timer)
} can_frame_t;

// transmit on a bus; returns false if that bus's TX queue is full (frame dropped, counted)
bool can_send(bus_id_t bus, const can_frame_t *f);
