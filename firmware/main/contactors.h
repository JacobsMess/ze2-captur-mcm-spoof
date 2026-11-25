// Captur contactor sequencing: BMS feed -> precharge -> main- and main+ -> drop precharge. The low-side master
// FET only conducts while MCU_EN is high AND the TPS3431 window watchdog is happy, so a hung firmware opens
// the contactors in hardware.
#pragma once
#include <stdbool.h>
#include <stdint.h>

typedef enum { CT_OPEN, CT_PRECHARGE, CT_CLOSED, CT_FAULT } ct_state_t;

void contactors_init(void);
void contactors_tick(uint32_t now_ms, bool want_closed);
ct_state_t contactors_state(void);
const char *contactors_fault(void);
void contactors_kick_watchdog(uint32_t now_ms);
