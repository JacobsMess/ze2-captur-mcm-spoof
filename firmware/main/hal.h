// Hardware abstraction. hal_hw.c drives the real board; hal_sim.c (CONFIG_ZE2_SIM) replaces the SPI bus,
// MCP2518FDs, TWAI, I2C and GPIO with models so the same driver and application code runs in QEMU.
#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include "can_types.h"

void board_hal_init(void);

// CAN controller (MCP2518FD) chip select index: 0 = CAN2 (MCM), 1 = CAN3 (PCM), 2 = CAN4 (dash)
#define MCP_COUNT 3
bool hal_spi_xfer(int chip, const uint8_t *tx, uint8_t *rx, size_t len);   // false: transaction failed
bool hal_mcp_int_asserted(int chip);              // INT pin low
// the CAN I/O task registers itself; ISRs (or the sim) notify it with bit (1 << chip) / bit 3 for TWAI
void hal_set_can_task(void *task_handle);
#define NOTIFY_TWAI_BIT (1u << 3)

// CAN1 / TWAI
bool hal_twai_receive(can_frame_t *f);            // non-blocking
bool hal_twai_send(const can_frame_t *f);         // non-blocking
bool hal_twai_ok(void);                           // driver installed and started

// GPIO outputs
typedef enum { OUT_HS_PRE, OUT_HS_MAINP, OUT_HS_MAINN, OUT_HS_BMS, OUT_MCU_EN, OUT_WDI, OUT_OPTO_EN,
               OUT_RELAY_SPLIT, OUT_COUNT } hal_out_t;
void hal_out(hal_out_t o, bool on);
bool hal_vbat_mv(int32_t *mv);                    // board supply (VBAT_P); false: ADC read failed
void hal_pump_config(uint32_t hz);                // pump PWM frequency
void hal_pump_pwm(float duty);                    // 0..1: fraction of time Q3 is on
bool hal_pump_line_high(void);                    // PUMP_N above about 9 V (GPIO35 via R102/R103)

// analog
bool hal_dac_write4(const uint16_t code[4]);     // MCP4728, 12-bit codes, Vref = MCM 5 V
bool hal_adc_island(int dev, int ch, int32_t *mv); // ADS1115 single-ended, mV
// AMC3311 differential -> link mV after the divider scale. False when the reading can't be trusted: ADC or
// calibration error, output common mode out of range, or the negative fail-safe output (HV side unpowered).
bool hal_bus_mv(int32_t *mv);
