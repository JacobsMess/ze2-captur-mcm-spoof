# Firmware

ESP-IDF v5.4 firmware for the ESP32-S3-WROOM-1-N8R2. It builds cleanly. It has **not run on a board
yet**. The Captur BMS protocol is the one decoded on the bench; the Honda IMA IDs are placeholders until
they're decoded from logs.

## What it does

| Core | Task | Job |
|---|---|---|
| 1 | `can_io` (priority 23) | The only code that touches the SPI bus and TWAI: services the three MCP2518FDs round-robin, forwards IMA frames between the MCM and PCM halves, logs every frame |
| 0 | `control` (100 Hz) | Captur BMS decode, protection ladder, contactor sequencing and watchdog kick, NTC and SOC spoofing (stage 1), ZombieVerter BMS frames (stage 2), gateway state |
| 0 | `gvret` | Streams all four buses to SavvyCAN over Wi-Fi (GVRET protocol, TCP port 23); accepts frames to send only with the ignition off and the contactors open |
| 0 | Wi-Fi, HTTP | Access point `ZE2-SPOOF` (or station mode from NVS), status at `/`, firmware update at `POST /update` |

- **Gateway:** starts in bypass (K4 relaxed, both IMA controllers listen-only). It splits the bus only when
  enabled in NVS (`ze2/mitm`, off by default), and then only after both controllers confirm normal mode by
  reading OPMOD back (within 100 ms, else bypass). It falls back to bypass, latched until key-off, if either
  half goes quiet for 500 ms or a controller leaves normal mode. The control task is on the ESP-IDF task
  watchdog (2 s, panic): a hung loop resets the chip, the GPIOs float and K4 drops to bypass. Rewrite hooks per CAN ID; with none registered, frames pass through
  unchanged.
- **Ignition:** the board supply (after D7) on the ADC: on above 9 V for 100 ms, off below 6 V for 2 s, so
  a crank dip is not a key-off. Key-off is the only thing that clears a latched trip or contactor fault.
  No valid reading for 500 ms is a latched fault (contactors open) that the sense recovering doesn't clear.
- **Reset while running:** a brownout, watchdog or panic reset (`esp_reset_reason`) starts the board tripped,
  until a real key-off is seen (in practice the next power cycle), since the RAM latch didn't survive.
- **Captur BMS (`captur.c`):** 0x0F5 keep-alive every 20 ms (`7D`, counter, CRC-8 poly 0x1D init 0xC4, `FF D7
  F8 00 D0`) and one UDS read every 20 ms on 0x18DADBF1 / 0x18DAF1DB, round-robin over 9007/9009 (max/min
  cell), 9006 (cell sum), 9013/9014 (min/max temperature), 9001 (SOC) and 9005 (pack voltage, logged only).
  Read-only service 0x22 only. Current (900D) has no known scale yet, so it isn't used.
- **Contactors (`contactors.c`):** main+ and precharge (pack negative is hard-wired; the board's third high
  side is a spare that stays off). The link must be dead with both coils off (rules out a weld), then
  precharge to 90 % of the series string (cell sum x 34/68 in stage 1), main+ with precharge held 100 ms,
  then precharge off for 300 ms: the link must reach 92 % and its mean over the last 50 ms may not be more
  than 1.5 % (`CLOSE_DROOP_PM`) below its mean over the first 50 ms. A link charged through precharge reads
  ~100 % with main+ open too; it is the decay through the link's bleed that gives an open main+ away. That
  works while the bleed time constant is under ~4 s: measure it ([BRINGUP](../docs/BRINGUP.md)) and tune.
  In PRECHARGE and CLOSING the deadline is checked first, losing start permission (a soft trip) aborts, and so
  does a link above 108 % of pack + 4 V (sensor or BMS data wrong).
  Any fault (weld, bus sense invalid, precharge timeout, main+ not closed or decaying, link implausible,
  permission lost mid-close, link collapse, a control-loop stall) is latched and is a hard trip.
  Stage 2 never runs the sequencer.
- **Taps:** OPTO_EN only in CT_CLOSED (verified) with the analog island healthy (a good DAC write and ADC
  readback within 250 ms) and nothing at soft trip or above.
- **Watchdog latch:** every kick clocks MCU_EN into U10. A gap over 600 ms between loop passes with coils
  energised is a latched fault, caught before the next kick can clock MCU_EN back in.
- **Bus sense:** a reading counts only if both ADC reads and calibration work, the AMC3311 output common
  mode is in range and the differential is not negative (its fail-safe output). No close without a valid
  dead-link reading.
- **Protection:** any BMS value older than 1 s (each timed from its arrival; normally under 150 ms), cell sum outside 68 x the
  extreme cells (3 % + 2 V), a cell or temperature hard limit, or any contactor fault: hard trip, held
  until key-off. A soft trip floats the taps and keeps a closed pack closed but never starts a close.
  Below 5 °C or near full, regen is inhibited by steering the MCM's SOC; near empty, assist is.
- **Pump (`pump.c`):** on/off (default), PWM at 20 kHz or a 3-wire pump's signal line, set in NVS
  (`pump_mode`, `pump_hz`, `pump_inv`). The line readback reports an open circuit or a failed Q3.
- **NTC lines (`spoof.c`):** at start-up each line is driven to 2 V and 3 V and read back, which gives the
  MCM's pull-up (ohms and volts); the line is then set to the voltage that means the wanted temperature
  through that pull-up, and the readback trims each line continuously. Shown on the status page.
- **Decoder:** replies need the 29-bit response ID, no RTR, a positive 0x62 reply and the ISO-TP length and
  DLC for that DID.
- **OTA:** accepted only with ignition off and the contactors open. Two app slots (3.75 MB each, the
  image is 0.85 MB). A new image runs on probation and is rolled back automatically unless it comes up
  with all three CAN controllers and the TWAI working and no SPI errors.
- **Placeholders (`main/config.h`, `gateway.c`):** the Honda SOC
  frame, the Honda NTC curve and pull-up, and the ZombieVerter BMS frame format.

## Build

```
idf.py set-target esp32s3 build          # real board
sim/run_sim.sh                           # simulation build + QEMU runs + report (fails if a run is incomplete)
python3 -m pytest tests/test_host_control.py   # from the repo root: safety chain on the PC
```

`tests/host/peripheral_test.c` checks the pump modes and readback and the NTC fit and trim against a
modelled MCM input. `tests/host/control_test.c` compiles `captur.c`, `safety.c`, `contactors.c`, `ignition.c`, `control.c` and
`zombie.c` with gcc against a model of the Captur contactors (with optional welded poles), the U10/U11 latch
and the bus sense, and runs 14 scenarios: normal close, stale or partial BMS data, a live link while open,
soft trip before start and while closed, a cell sum disagreeing with the extreme cells, welded main+ and
precharge,
sense invalid or lost, a 2 s loop stall and resume, a crank dip, and the decoder's frame checks.

## Simulation: is the S3 up to it?

`CONFIG_ZE2_SIM` swaps the hardware layer for models. The rest is the production firmware: CAN task,
MCP2518FD driver, gateway, GVRET encoder, control loop.
- The three MCP2518FDs are modelled at register level: 32-deep receive FIFO, 16-deep transmit FIFO,
  FIFO status and user-address registers, UINC/TXREQ, overflow flag and the INT line.
- Every SPI transaction takes the time ESP-IDF documents for the S3 (9 µs for a one-byte polling
  transaction), plus 0.5 µs per byte at 16 MHz. Transactions are capped at 64 bytes, the S3's limit
  without DMA, so the driver moves at most three frames per burst.
- Each bus gets 8-byte frames at a set share of 500 kbit/s. All four run at once, everything is streamed
  over GVRET, and the IMA bus is split with every frame forwarded.

The Captur BMS is modelled too: it answers the firmware's UDS reads, so the keep-alive, polling and
contactor sequence run end to end (the report fails unless the contactors finish closed in every run).

It runs on Espressif's ESP32-S3 QEMU with instruction counting at two CPU speeds:
- **250 MIPS:** about one instruction per clock at 240 MHz (optimistic);
- **125 MIPS:** about one per two clocks, allowing for cache and flash stalls (pessimistic).

The full results are in [`sim/out/report.md`](sim/out/report.md) and the raw logs are in `sim/out/`.

| Scenario | Core 0 / core 1 load | SPI bus busy | IMA forward latency (avg) | Frames lost |
|---|---|---|---|---|
| Typical: EV 30 %, IMA 40 %, dash 30 % | 18-27 % / 22-44 % | 18-28 % | 92-162 µs | 0 |
| Busy: 60 / 70 / 60 % | 28-38 % / 41-71 % | 33-50 % | 93-167 µs | 0 |
| Worst case: all four buses 100 % | 36-42 % / 62-93 % | 51-73 % | 99-266 µs | 0 (8 in one earlier run, see below) |

The first figure in each range is the 250 MIPS run, the second the 125 MIPS run. The SavvyCAN stream
peaks at 0.32 MB/s (2.5 Mbit/s). ESP-IDF's Wi-Fi guide gives the S3 up to 20 Mbit/s TCP throughput.

**Conclusions:**
- **No frames lost at realistic loads.** With every bus saturated on the slow CPU model core 1 runs at
  92-93 %, which is the edge: one v0.7 run lost 8 of about 480,000 frames there; the others lost none.
- **No frames lost, even with every bus saturated, on the fast model.** The v0.4 board's MCP2515s (two-frame receive
  buffer) lost up to 0.4 % of IMA and 5 % of dash frames in the same runs. Each MCP2518FD buffers 32
  frames, which rides out QEMU's 0.5 ms core freezes and any real stall of the same size.
- **The price is SPI time.** A received frame costs a status read, an object read and a FIFO pop (the
  MCP2515 needed two transactions), so SPI load and latency are higher at low load. Under load the
  driver reads several frames per burst, which brings the cost per frame down.
- **The ESP32-S3 has headroom** at realistic loads. Only the saturated, slow-CPU case pushes core 1 to
  92 %, where it starts to lose the odd frame. Wi-Fi and TCP cost isn't in these numbers (QEMU has no Wi-Fi); that
  load lands on core 0, which has spare capacity.

**What to do about it:**
1. Measure the real bus loads first: the first SavvyCAN log of the stock car (bypass mode, nothing
   transmitted) gives them. Typical car buses run well below the "busy" case.
2. The dash tap only logs in stage 1. If it's busy, filter it in the MCP2518FD's acceptance filters.
3. Never write flash (NVS, OTA) while driving. A flash write stalls both cores. The firmware only writes
   with the ignition off.
