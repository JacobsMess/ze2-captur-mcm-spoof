// The safety-relevant part of the 100 Hz control pass, kept free of RTOS and radio code so the host tests
// (tests/host) run exactly this sequence. Call contactors_kick_watchdog() and decode received frames first.
#pragma once
#include <stdbool.h>
#include <stdint.h>

// ignition -> safety ladder -> contactor sequencer (stage 1 only). Returns the debounced ignition state.
bool control_safety_step(uint32_t now_ms, bool stage1);
