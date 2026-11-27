// Board pin map, timing and protocol constants. Pins follow hw/parts.json (ESP32-S3-WROOM-1 module pins
// mapped to GPIOs). The Honda IMA IDs are not known yet (they come from SavvyCAN logs of the stock car); until
// then the gateway passes IMA traffic through unchanged.
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
#define PIN_WDI          6   // pin 6  TPS3431 watchdog kick; also U10 latch clock
#define PIN_MCU_EN       7   // pin 7  U10 latch D: contactor master enable, clocked in by WDI
#define PIN_HS_PRE       15  // pin 8  VND7050 precharge contactor
#define PIN_HS_MAINP     16  // pin 9  VND7050 main + contactor
#define PIN_HS_MAINN     17  // pin 10 VND7050 spare channel (the Captur has no main- contactor): never driven
#define PIN_I2C_SCL      18  // pin 11 to the analog island through ISO1540
#define PIN_I2C_SDA      8   // pin 12
#define PIN_CAN3_INT     3   // pin 15 MCP2518FD U18 (PCM side of the IMA bus)
#define PIN_SPI_CS3      9   // pin 17
#define PIN_IG_SENSE     10  // pin 18 board supply / 5.545 on ADC1 ch9 (ignition)
#define PIN_SPI_MOSI     11  // pin 19
#define PIN_SPI_SCK      12  // pin 20
#define PIN_SPI_MISO     13  // pin 21
#define PIN_CAN4_INT     14  // pin 22 MCP2518FD U20 (dash bus tap)
#define PIN_HS_BMS       21  // pin 23 Captur BMS 12 V feed
#define PIN_PUMP_PWM     47  // pin 24 coolant pump (U24 -> Q3)
#define PIN_PUMP_SENSE   35  // pin 28 Q26 drain (10k pull-up): LOW while the pump line is above ~6 V
#define PIN_SPI_CS4      48  // pin 25
#define PIN_CAN2_INT     38  // pin 31 MCP2518FD U6 (MCM side of the IMA bus)
#define PIN_SPI_CS2      39  // pin 32
#define PIN_OPTO_EN      41  // pin 34 tap-divider optoMOS K2/K3
#define PIN_RELAY_SPLIT  42  // pin 35 K4 bypass relay + U22 photoMOS (energised = IMA bus split)
#define PIN_AMC_P        1   // pin 39 AMC3311 output + (ADC1 ch0)
#define PIN_AMC_N        2   // pin 38 AMC3311 output - (ADC1 ch1)

// ---------------------------------------------------------------- buses
typedef enum { BUS_EV = 0, BUS_MCM = 1, BUS_PCM = 2, BUS_DASH = 3, BUS_COUNT = 4 } bus_id_t;
#define CAN_BITRATE        500000
#define MCP_SPI_HZ         16000000   // MCP2518FD: <= 0.85 x SYSCLK/2 = 17 MHz; 80 MHz / 5 on the S3
#define HV_DIV_X1000       90362      // (10k + 400k + 4.7k + 10k) / 4.7k incl. RF3/RF4; calibrate per board
#define MCP_OSC_HZ         40000000   // SYSCLK = crystal, PLL off

// ---------------------------------------------------------------- analog island (I2C)
#define I2C_HZ             400000
#define MCP4728_ADDR       0x60       // DAC: ch A-C NTC1-3 emulation, ch D current-sensor offset
#define ADS1115_A_ADDR     0x48       // readback: NTC lines, Hall in/out
#define ADS1115_B_ADDR     0x49       // readback: MCM 5 V, tap divider check
#define DAC_CH_OFFSET      3
#define AMC_CM_MIN_MV      1200       // AMC3311 output common mode 1.39-1.49 V, plus ADC error
#define AMC_CM_MAX_MV      1700
#define AMC_DIFF_MIN_MV    (-50)      // below: fail-safe output (HV side unpowered) or a fault
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
#define DEAD_BUS_MV        20000      // below this the link counts as dead (weld check)
#define MAIN_PICKUP_MS     100        // precharge held this long after main+ is commanded
#define CLOSE_VERIFY_MS    300        // then precharge off for this long: the link must hold up (below)
#define CLOSE_AVG_MS       50         // link averaged over the first and the last this-long of that window
#define CLOSED_MIN_PCT     92         // allows for the untrimmed 1 % bus-sense divider
// An open main+ with the link capacitance charged through precharge still reads ~100 %, so voltage alone can't
// prove closure. With precharge off it decays through the link's bleed: an open main+ shows as droop across
// the verify window, a closed one holds flat. Catches an open main+ if the link bleed time constant is under
// ~20 x CLOSE_VERIFY_MS / (CLOSE_DROOP_PM / 1000) = 4 s at these values; measure it (docs/BRINGUP.md) and
// tune before relying on it. 0 disables the check.
#define CLOSE_DROOP_PM     15         // per mille of pack voltage
#define LINK_MAX_PCT       108        // link above pack x this % + LINK_MAX_EXTRA_MV: sensor or BMS data wrong
#define LINK_MAX_EXTRA_MV  4000
#define BUS_COLLAPSE_PCT   70         // closed, link below this % of pack: fault
#define PACK_TOL_PCT       3          // BMS cell sum vs 68 x cell range: 3 % + 2 V
#define PACK_TOL_MV        2000

// ---------------------------------------------------------------- ignition (board supply after D7)
#define VBAT_DIV_X1000     5545       // (100k + 22k) / 22k
#define IGN_ON_MV          9000       // key-on above this for IGN_ON_MS
#define IGN_ON_MS          100
#define IGN_OFF_MV         6000       // key-off below this for IGN_OFF_MS (rides through a crank dip)
#define IGN_OFF_MS         2000
#define IGN_INVALID_MS     500        // no valid ignition reading for this long: latched fault, contactors open

// ---------------------------------------------------------------- coolant pump (pump.h)
#define PUMP_PWM_HZ        20000      // 2-wire brushed pump chopped above audio
#define PUMP_SIGNAL_HZ     100        // 3-wire pump signal line
#define PUMP_MIN_DUTY      0.3f       // PWM mode: below this a brushed pump may stall
#define PUMP_SETTLE_MS     100        // Q3 steady this long before the line readback counts

// ---------------------------------------------------------------- timing
#define CONTROL_PERIOD_MS  10
#define WDI_PERIOD_MS      100        // TPS3431 kick: one rising edge per period (timeout 1.36 s min)
#define WDT_STALL_MS       600        // loop gap this long with coils energised: latched fault
#define BUS_SILENT_MS      500        // IMA half quiet this long -> drop back to bypass
#define GW_ARM_MS          100        // both CAN controllers must confirm normal mode within this, or no split
#define ISLAND_FAIL_MS     250        // no good DAC write + ADC readback for this long: taps float
#define BMS_TIMEOUT_MS     1000       // any Captur value older than this -> hard trip (normally < 150 ms)

// ---------------------------------------------------------------- CAN IDs
#define CAPTUR_KEEPALIVE_ID 0x0F5     // Captur BMS stays awake while this arrives (captur.h)
#define CAPTUR_KEEPALIVE_MS 20
#define CAPTUR_UDS_REQ     0x18DADBF1 // UDS read requests to the BMS (29-bit)
#define CAPTUR_UDS_RESP    0x18DAF1DB // its replies
#define ZV_ID_BMS_BASE     0x3E0      // stage 2: ZombieVerter "simpBMS"-style frames (check against ZV firmware)
