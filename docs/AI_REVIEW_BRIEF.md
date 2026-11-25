# Review brief: ZE2 Captur MCM spoof board

Paste this into an AI assistant (with access to this repo) to get a design review. It is a summary; the
files listed at the end are the source of truth.

## What it is

A stock Honda Insight ZE2 (IMA mild hybrid) gets a Renault Captur E-Tech lithium pack in place of its
failing NiMH pack. The stock Honda MCM (battery computer) stays in charge of the hybrid system. This
board sits between the MCM and the new pack and makes the MCM believe it still has a healthy NiMH pack.

- **Stage 1 (this board's job):** Captur modules in parallel, 34S2P, about 102-142 V. Stock MCM, MPI
  (motor inverter), DC-DC and junction board kept.
- **Stage 2 (later):** 68S, about 260 V, MCM removed, ZombieVerter VCU + Toyota inverter. The board is then
  only a CAN gateway; its HV side is not used.

Status: v0.6, designed, simulated, not built. One AI review has been folded in already (v0.6 in the git log). The designer is not an electronics engineer. The design was
produced with an AI assistant, so assume nothing has been checked by a human expert.

## The board

ESP32-S3-WROOM-1 module, 4-layer, 120 x 98 mm, parts on top, made and assembled by JLCPCB.

| Block | What it does | Main parts |
|---|---|---|
| Power | 12 V car feed -> reverse protection -> 5 V buck -> 3.3 V LDO | SS54 series Schottky, LMR16006 (60 V), TLV75733, SMCJ33CA TVS |
| CAN1 | EV bus: Captur BMS now, ZombieVerter later | ESP32 TWAI + TJA1051 |
| CAN2 / CAN3 | The IMA bus cut in two: MCM half and PCM half. Firmware forwards frames between them (man-in-the-middle) | MCP2518FD + TJA1051 each |
| Bypass relay | K4 (DPDT) joins the two IMA halves whenever the board is unpowered or not ready | Omron G6K-2F-Y |
| Switched terminations | 120 ohm at the board end of each split half, only while K4 is energised, each behind a solder jumper (open by default) | K4 spare contacts, AQY212GS photoMOS |
| CAN4 | Dash bus tap, listen only in stage 1 | MCP2518FD + TJA1051 |
| Cell taps | A 16-resistor divider across the real pack bus gives the MCM nine balanced "block" voltages. Two optoMOS connect it; unpowered = taps float = MCM faults safely | 47k 0.1 %, AQV214EH x2 |
| Bus sense | Isolated measurement of the pack bus voltage for precharge and weld checks | AMC3311 (isolated amplifier with its own isolated supply) |
| Analog island | Fakes the three NTC temperature inputs and adds a small offset to the Hall current-sensor signal (steers the MCM's own SOC count). Runs from the MCM's 5 V sensor supply, I2C-isolated from the rest | MCP4728 DAC, MCP6004, ADS1115 x2, ISO1540 |
| Contactor drive | Drives the Captur pack's precharge and main contactors and its BMS 12 V feed | VND7050AJ high-side x2; low-side master FET driven by an enable latch |
| Watchdog latch | Each watchdog kick (WDI edge) clocks MCU_EN into a D flip-flop whose Q drives the master FET. A watchdog timeout clears the flip-flop and it stays off until firmware re-arms; an RC gives a power-on clear | TPS3431, SN74LVC1G74 |

HV strip: right-hand edge, 150 V maximum, separated by a 5.6 mm copper-free band. Only three isolation
parts cross it (K2, K3, U12), with a short slot under each.

## Connectors

| Ref | Goes to | Signals |
|---|---|---|
| J1 (Micro-Fit 2x10) | Car harness / MCM | 12 V ignition feed, GND, IMA bus (PCM side), IMA bus (MCM side), dash CAN, CAN1 |
| J2 (Micro-Fit 2x8) | Captur pack LV | Coil supply, contactor coil drives (precharge, main+, main-, return), BMS 12 V, CAN1, coolant pump |
| J3 (5.08 mm terminal) | Pack HV bus | BUS+, BUS- |
| J4 (Mini-Fit 2x5) | MCM tap harness | Nine tap outputs VHB0-VHB8 |
| J6 (Micro-Fit 2x4) | MCM analog | MCM 5 V, sensor ground, three NTC lines, Hall sensor in and out |
| J5 (USB-C) | Laptop | Flashing and debug (Wi-Fi OTA after that) |

## How it behaves

- **Key on:** the board closes the Captur contactors (with precharge) before the MCM looks at the pack,
  then connects the taps. CAN2-4 start in listen-only.
- **Running:** taps follow the real pack; temperatures and SOC offset come from the Captur BMS over CAN1;
  IMA frames are forwarded (and can be modified) between CAN2 and CAN3.
- **Protection order:** steer SOC first; then float the taps so the MCM faults; last, open the contactors
  (the hardware watchdog does this if the firmware hangs). No regen below about 5 C.
- **Board dead:** IMA bus rejoins via K4, the dash still works, the pack drops out on purpose. The car runs
  engine-only with the IMA light on, and the 12 V battery is not charged.

## Known open items

- Pinouts taken from datasheets but not yet checked by a person: VND7050AJ (custom PowerSSO-16 footprint),
  TPS3431, SN74LVC1G74, AMC3311, K4 contact map, AQY212GS, H24VNT2B.
- Not stocked at JLC (hand fit): AQV214EH x2, TPS3431, and the five THT connectors. AMC3311 stock is low.
- HV strip gaps are 0.7 mm or more (IPC-2221 B2 uncoated, 101-150 V, wants 0.6 mm); conformal coating planned.
- Unknowns about the car: MCM tap input impedance and timing, NTC pull-ups, Hall sensor zero and scale,
  IMA bus load and terminations. These get measured before anything is connected.
- The bus-sense divider uses 1 % parts; its ratio is trimmed in firmware (`HV_DIV_X1000`).
- Firmware has only run in simulation (ESP32-S3 QEMU with modelled CAN controllers): no frames lost at
  any bus load, CAN core 22-71 % at realistic loads.

## What to review

Please look for, in priority order:

1. **Safety:** anything that could leave the pack connected when it shouldn't be, overcharge or
   over-discharge it, or put HV where it can reach the LV side or the car. Is the failure behaviour above
   actually what the circuit does?
2. **Would it work:** wrong pinouts, wrong values, missing pull-ups/decoupling, CAN termination and bypass
   logic, the tap divider, the analog island, the power path, load-dump survival.
3. **Layout:** HV spacing, grounding, current paths, anything a fab or assembler would reject.
4. **Firmware:** CAN forwarding, the safety ladder, contactor sequencing, the MCP2518FD driver.
5. **Approach:** whether spoofing the MCM is a sensible plan at all.

For each finding give: where (part reference, net or file:line), what is wrong, why it matters
(severity: safety / won't work / minor) and a suggested fix. Say plainly when you are unsure.

## Files

| File | What |
|---|---|
| `README.md` | Overview, status, ordering notes |
| `hw/build_board.py` | The circuit and placement as Python: every part, value and pin-to-net connection |
| `hw/parts.json` | The same netlist as JSON (easiest to read) |
| `hw/jlc_parts.py` | The ordered part for every BOM line |
| `docs/img/sheet*.png` | Block-level schematic sheets |
| `docs/img/layers_*.png`, `board_*.png` | Board images |
| `hw/out/drc_report.txt` | KiCad DRC result |
| `firmware/main/` | ESP-IDF firmware (`config.h` pins and limits, `safety.c`, `contactors.c`, `gateway.c`, `mcp2518fd.c`) |
| `firmware/README.md` | Firmware structure and simulation results |
| `tests/` | Automated checks on the netlist, board, JLC files and firmware-hardware parity |
