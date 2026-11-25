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
void hal_spi_xfer(int chip, const uint8_t *tx, uint8_t *rx, size_t len);
bool hal_mcp_int_asserted(int chip);              // INT pin low
// the CAN I/O task registers itself; ISRs (or the sim) notify it with bit (1 << chip) / bit 3 for TWAI
void hal_set_can_task(void *task_handle);
#define NOTIFY_TWAI_BIT (1u << 3)

// CAN1 / TWAI
bool hal_twai_receive(can_frame_t *f);            // non-blocking
bool hal_twai_send(const can_frame_t *f);         // non-blocking

// GPIO outputs
typedef enum { OUT_HS_PRE, OUT_HS_MAINP, OUT_HS_MAINN, OUT_HS_BMS, OUT_MCU_EN, OUT_WDI, OUT_OPTO_EN,
               OUT_RELAY_SPLIT, OUT_COUNT } hal_out_t;
void hal_out(hal_out_t o, bool on);
bool hal_ignition_on(void);
void hal_pump_pwm(float duty);                    // 0..1

// analog
bool hal_dac_write4(const uint16_t code[4]);     // MCP4728, 12-bit codes, Vref = MCM 5 V
bool hal_adc_island(int dev, int ch, int32_t *mv); // ADS1115 single-ended, mV
int32_t hal_bus_mv(void);                        // AMC1311 differential -> pack bus mV (after divider scale)
