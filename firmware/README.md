# Firmware

ESP-IDF v5.4 firmware for the ESP32-S3-WROOM-1-N8R2. It builds cleanly. It has **not run on a board
yet**, and the Honda and Captur CAN IDs are placeholders until they're decoded from logs.

## What it does

| Core | Task | Job |
|---|---|---|
| 1 | `can_io` (priority 23) | The only code that touches the SPI bus and TWAI: services the three MCP2515s round-robin, forwards IMA frames between the MCM and PCM halves, logs every frame |
| 0 | `control` (100 Hz) | Captur BMS decode, protection ladder, contactor sequencing and watchdog kick, NTC and SOC spoofing (stage 1), ZombieVerter BMS frames (stage 2), gateway state |
| 0 | `gvret` | Streams all four buses to SavvyCAN over Wi-Fi (GVRET protocol, TCP port 23), accepts frames to send |
| 0 | Wi-Fi, HTTP | Access point `ZE2-SPOOF` (or station mode from NVS), status at `/`, firmware update at `POST /update` |

- **Gateway:** starts in bypass (K4 relaxed, both IMA controllers listen-only). It splits the bus only when
  enabled in NVS (`ze2/mitm`, off by default). It falls back to bypass, latched until key-off, if either
  half goes quiet for 500 ms. Rewrite hooks per CAN ID; with none registered, frames pass through
  unchanged.
- **Protection:** BMS silent for 500 ms, a cell or temperature hard limit, or the precharge failing opens the
  contactors. A hard trip holds until key-off. Below 5 °C or near full, regen is inhibited by steering
  the MCM's SOC; near empty, assist is.
- **OTA:** accepted only with ignition off and the contactors open. Two app slots (3.75 MB each, the
  image is 0.85 MB). A new image runs on probation and is rolled back automatically unless it comes up
  with all three CAN controllers working.
- **Placeholders (`main/config.h`, `captur.c`, `gateway.c`):** Captur frame IDs and layouts, the Honda SOC
  frame, the Honda NTC curve and pull-up, and the ZombieVerter BMS frame format.

## Build

```
idf.py set-target esp32s3 build          # real board
sim/run_sim.sh                           # simulation build + QEMU runs + report
```

## Simulation: is the S3 up to it?

`CONFIG_ZE2_SIM` swaps the hardware layer for models. The rest is the production firmware: CAN task,
MCP2515 driver, gateway, GVRET encoder, control loop.
- The three MCP2515s are modelled at register level: two receive buffers with rollover, three transmit
  buffers, flags and the INT line.
- Every SPI transaction takes the time ESP-IDF documents for the S3 (9 µs for a one-byte polling
  transaction), plus 0.8 µs per byte at 10 MHz.
- Each bus gets 8-byte frames at a set share of 500 kbit/s. All four run at once, everything is streamed
  over GVRET, and the IMA bus is split with every frame forwarded.

It runs on Espressif's ESP32-S3 QEMU with instruction counting at two CPU speeds:
- **250 MIPS:** about one instruction per clock at 240 MHz (optimistic);
- **125 MIPS:** about one per two clocks, allowing for cache and flash stalls (pessimistic).

The full results are in [`sim/out/report.md`](sim/out/report.md) and the raw logs are in `sim/out/`.

| Scenario | Core 0 / core 1 load | SPI bus busy | IMA forward latency (avg) | Frames lost: IMA / dash / EV |
|---|---|---|---|---|
| Typical: EV 30 %, IMA 40 %, dash 30 % | 18-28 % / 20-27 % | 15-19 % | 71-110 µs | 0.01-0.08 % / 0.2-0.3 % / ~0 |
| Busy: 60 / 70 / 60 % | 26-40 % / 36-50 % | 28-34 % | 72-118 µs | 0.2-0.3 % / 0.7-0.9 % / 0 |
| Worst case: all four buses 100 % | 35-45 % / 54-70 % | 42-52 % | 70-130 µs | 0.3-0.4 % / 2-5 % / ~0 |

The first figure in each range is the 250 MIPS run, the second the 125 MIPS run. IMA losses are
counted over both halves. The SavvyCAN stream peaks at 0.32 MB/s (2.5 Mbit/s). ESP-IDF's Wi-Fi guide
gives the S3 up to 20 Mbit/s TCP throughput.

**Conclusions:**
- **The ESP32-S3 has headroom.** Even with every bus saturated and the slow CPU model, core 1 peaks at
  70 % and core 0 at 45 %.
- **Wi-Fi and TCP cost isn't in these numbers,** because QEMU has no Wi-Fi. That load lands on core 0,
  which has the spare capacity. Forwarding sits on core 1, away from it.
- **The weak point is the MCP2515s, not the S3.** Each MCP2515 holds only two received frames. On a
  saturated bus that is about 0.5 ms of slack before frames are lost, and the lost frames are still ACKed
  on the bus. Every loss in the simulation was a receive overflow on an MCP2515. None were lost in the S3's
  own queues or log ring.
- **Part of that loss is emulation, not silicon.** QEMU runs the two cores in turn. A probe measured core 1
  frozen for up to 0.5 ms while core 0 ran, which is the same size as that slack. Real cores run in
  parallel, so the losses here should be pessimistic. How pessimistic can only be measured on a board.

**What to do about it:**
1. Measure the real bus loads first: the first SavvyCAN log of the stock car (bypass mode, nothing
   transmitted) gives them. Typical car buses run well below the "busy" case.
2. The dash tap only logs in stage 1. If it's busy, filter it in the MCP2515's acceptance filters.
3. Never write flash (NVS, OTA) while driving. A flash write stalls both cores. The firmware only writes
   with the ignition off.
4. If the IMA bus turns out heavily loaded, or the first bench test drops frames, change the IMA
   controllers to MCP2518FD (31-frame receive FIFO, 20 MHz SPI). The firmware structure stays the same;
   only `mcp2515.c` and the footprints change.
