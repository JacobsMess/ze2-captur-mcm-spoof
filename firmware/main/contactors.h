// Captur contactor sequencing. Close: weld check of each pole, then precharge, then main+ with precharge still
// held until main+ has picked up, then verify. Assumes the stock Captur layout: precharge relay + resistor in
// parallel with main+, main- on its own.
// The coil-return master FET follows U10, a flip-flop that each watchdog kick (WDI edge) clocks MCU_EN into and
// the TPS3431 clears on a timeout. A stall the firmware notices on resume is a latched fault, so the next kick
// can never quietly re-energise coils the firmware has stopped tracking.
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef enum { CT_OPEN, CT_CHECK_NEG, CT_CHECK_POS, CT_PRECHARGE, CT_CLOSING, CT_CLOSED, CT_FAULT } ct_state_t;

void contactors_init(void);
// want_closed: close or stay closed; may_start: permission to begin a close from open (stricter)
void contactors_tick(uint32_t now_ms, bool want_closed, bool may_start);
ct_state_t contactors_state(void);
bool contactors_energised(void);       // any contactor commanded on
bool contactors_faulted(void);
const char *contactors_fault(void);
void contactors_clear_fault(void);     // key-off only
void contactors_kick_watchdog(uint32_t now_ms);   // first thing in every control-loop pass
