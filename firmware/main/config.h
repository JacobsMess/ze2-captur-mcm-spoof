// Board pin map, timing and protocol placeholders. Pins follow hw/parts.json (ESP32-S3-WROOM-1 module pins
// mapped to GPIOs). CAN IDs marked TODO are not known yet: they come from SavvyCAN logs of the stock car and
// the Captur pack. Until then the gateway passes IMA traffic through unchanged.
#pragma once
#include <stdint.h>
#include "sdkconfig.h"

#ifdef CONFIG_ZE2_SIM
#define ZE2_SIM 1
#else
#define ZE2_SIM 0
#endif

// ---------------------------------------------------------------- GPIO (module pin -> GPIO)
#define PIN_TWAI_TX      4   // pin 4  CAN1 (EV bus) TJA1051
#define PIN_TWAI_RX      5   // pin 5
#define PIN_WDI          6   // pin 6  TPS3431 window watchdog kick
#define PIN_MCU_EN       7   // pin 7  firmware half of the contactor master enable (AND with WDO)
#define PIN_HS_PRE       15  // pin 8  VND7050 precharge contactor
#define PIN_HS_MAINP     16  // pin 9  VND7050 main + contactor
#define PIN_HS_MAINN     17  // pin 10 VND7050 main - contactor
#define PIN_I2C_SCL      18  // pin 11 to the analog island through ISO1540
#define PIN_I2C_SDA      8   // pin 12
#define PIN_CAN3_INT     3   // pin 15 MCP2518FD U18 (PCM side of the IMA bus)
#define PIN_SPI_CS3      9   // pin 17
#define PIN_IG_SENSE     10  // pin 18 ignition sense (high = key on)
#define PIN_SPI_MOSI     11  // pin 19
#define PIN_SPI_SCK      12  // pin 20
#define PIN_SPI_MISO     13  // pin 21
#define PIN_CAN4_INT     14  // pin 22 MCP2518FD U20 (dash bus tap)
#define PIN_HS_BMS       21  // pin 23 Captur BMS 12 V feed
#define PIN_PUMP_PWM     47  // pin 24 coolant pump
#define PIN_SPI_CS4      48  // pin 25
#define PIN_CAN2_INT     38  // pin 31 MCP2518FD U6 (MCM side of the IMA bus)
#define PIN_SPI_CS2      39  // pin 32
#define PIN_OPTO_EN      41  // pin 34 tap-divider optoMOS K2/K3
#define PIN_RELAY_SPLIT  42  // pin 35 K4 bypass relay + U22 photoMOS (energised = IMA bus split)
#define PIN_AMC_P        1   // pin 39 AMC1311 output + (ADC1 ch0)
#define PIN_AMC_N        2   // pin 38 AMC1311 output - (ADC1 ch1)

// ---------------------------------------------------------------- buses
typedef enum { BUS_EV = 0, BUS_MCM = 1, BUS_PCM = 2, BUS_DASH = 3, BUS_COUNT = 4 } bus_id_t;
#define CAN_BITRATE        500000
#define MCP_SPI_HZ         16000000   // MCP2518FD: <= 0.85 x SYSCLK/2 = 17 MHz; 80 MHz / 5 on the S3
#define HV_DIV_X1000       86106      // (400k + 4.7k) / 4.7k; calibrate per board
#define MCP_OSC_HZ         40000000   // SYSCLK = crystal, PLL off

// ---------------------------------------------------------------- analog island (I2C)
#define I2C_HZ             400000
#define MCP4728_ADDR       0x60       // DAC: ch A-C NTC1-3 emulation, ch D current-sensor offset
#define ADS1115_A_ADDR     0x48       // readback: NTC lines, Hall in/out
#define ADS1115_B_ADDR     0x49       // readback: MCM 5 V, tap divider check
#define DAC_CH_OFFSET      3
#define OFFSET_GAIN        0.05f      // summer: Vout = Vhall + 0.05 * (Vdac - Vmid)
#define OFFSET_MAX_MV      125.0f

// ---------------------------------------------------------------- pack and limits (34S2P stage 1)
#define PACK_SERIES        34
#define CELL_MAX_MV        4150       // soft limit (NMC); hard trip at +50 mV
#define CELL_MIN_MV        3100       // soft limit; hard trip at -100 mV
#define CELL_HARD_MAX_MV   4200
#define CELL_HARD_MIN_MV   3000
#define CHARGE_MIN_TEMP_C  5          // no regen (charge) below this
#define PACK_MAX_TEMP_C    55
#define PRECHARGE_PCT      90         // bus must reach this % of pack voltage
#define PRECHARGE_TIMEOUT_MS 3000

// ---------------------------------------------------------------- timing
#define CONTROL_PERIOD_MS  10
#define WDI_PERIOD_MS      100        // TPS3431 kick, inside its open window
#define BUS_SILENT_MS      500        // IMA half quiet this long -> drop back to bypass
#define BMS_TIMEOUT_MS     500        // Captur BMS quiet this long -> hard trip

// ---------------------------------------------------------------- CAN IDs (TODO: fill from logs)
#define CAPTUR_ID_CELLS    0x000      // TODO min/max cell mV
#define CAPTUR_ID_PACK     0x000      // TODO pack V, I, SOC
#define CAPTUR_ID_TEMPS    0x000      // TODO module temperatures
#define CAPTUR_ID_CONTACTOR_CMD 0x000 // TODO HEV ECU -> BMS contactor request
#define ZV_ID_BMS_BASE     0x3E0      // stage 2: ZombieVerter "simpBMS"-style frames (check against ZV firmware)
