# Bring-up and first article

What to prove, in order, before the board goes near the car's HV link. Each step needs only what the
previous one proved. Everything runs with SavvyCAN on the board's Wi-Fi (GVRET) and the status page at `/`.

## 1. Bare board, bench supply

| Check | How | Pass |
|---|---|---|
| Rails | 13.8 V on J1 IG (current-limited to 0.5 A) | 5 V and 3.3 V within 3 %; idle current noted |
| Rails under load | Wi-Fi streaming + all four CAN buses busy, then sweep the supply 6-16 V | 3.3 V stays in spec down to the crank-dip floor you expect; no reset |
| Brownout with the key on | Dip the supply below the 3.3 V regulator's dropout for ~100 ms, then restore | Board restarts **tripped** ("reset while running: brownout") and stays so until the supply is removed |
| USB | Flash and monitor over USB-C only | Enumerates; flashing works |
| Watchdog latch | Coil outputs into 56R/22R dummy loads, closed state forced in a test build; halt the CPU over USB-JTAG (OpenOCD) | Coils drop within 1.4 s (TPS3431 clears U10). K4 stays as it was: a halted CPU can't reset itself (the IMA bus just loses its gateway) |
| Task watchdog | Test build that spins in the control task, with `mitm` on and K4 energised | Chip resets within ~2 s, K4 clicks back to bypass, board comes up tripped ("reset while running: panic") |
| Pump readback | 12 V lamp or pump on J2 13/14 | `pump_line` high with Q3 off, low with Q3 on; open circuit reported |
| NTC lines / Hall | 5 V on the MCM side of J6, 10k from each TBATT to 5 V | Fit finds ~10k; Hall offset moves +/-125 mV |
| Island loss | Pull J6's 5 V while running | Taps float within 250 ms (status: `island_ok` and `taps` false) |

## 2. Captur BMS and contactors, no HV link

Captur pack on its own, LV connector to J2 (see the README table), J3 left open, the car not involved.

| Check | How | Pass |
|---|---|---|
| Keep-alive and decode | Key-on (12 V on J1 IG) | 0x0F5 every 20 ms, UDS replies decoded: cells, sum, temps, SOC plausible; cell sum agrees with 68 x extremes |
| Weld check | Key-on with J3 open | Dead link (< 20 V) seen, precharge contactor clicks |
| Open main+ (no load) | J3 open: there is no link capacitor, so the link never rises | "precharge timeout" fault after 3 s, latched; key-off clears it |

## 3. Captur pack into a dummy link (no car)

J3 to a capacitor bank of about the Insight's link capacitance (1-2 mF, rated 200 V) with a bleed resistor,
behind an HV fuse, inside an enclosure. **This is the step that calibrates the open-main+ check.**

| Check | How | Pass |
|---|---|---|
| Normal close | Key-on | Precharge in < 1 s, main+ clicks, "closed: link X -> X mV" with no droop; taps switch on only after that |
| Link bleed time constant | Close, then pull main+'s coil wire (J2 10) so main+ opens while precharge is off | Log the link decay; the time constant must be well under 4 s, or the droop check (`CLOSE_DROOP_PM`, `CLOSE_VERIFY_MS`) won't see an open main+: lengthen the window, or add a bleed resistor at J3 |
| Main+ stuck open | J2 10 disconnected from the start | "link decays with precharge off: main+ open" (or "did not close"), taps never on |
| Main+ / precharge weld | Short main+ with a wire (fused) before key-on | "link live with contactors open" fault, no coil energised |
| Bus sense | Meter on J3 | Status page `link_mv` within 1 %; trim `HV_DIV_X1000` if not |
| Taps | Meter each J4 VHB pin to VHB0, closed | ~1/8 of the link per block, equal within 0.5 %; all float with taps off |
| Fault path | Short J4 VHB8 to VHB0 through a 2 A fuse wire (enclosed) | F3/F4 open; nothing else damaged |

## 4. On the car, MCM connected, IMA bus in bypass

- Log the stock IMA and dash buses with the board in bypass (nothing transmitted). Find the MCM SOC frame and
  set `HONDA_ID_MCM_SOC`; without it SOC steering is open-loop.
- Record the MCM's tap sampling (scope on two adjacent J4 pins), the NTC readings the MCM reports against the
  Captur temperatures, and the Hall zero/scale with the board's offset at zero.
- Confirm the Honda cuts regen when the board shows cold-pack inhibit, and that both parallel strings are
  supervised by the Captur BMS (34S2P).
- Lost main+, welded precharge and sensor-loss faults repeated with the car's own link: same results as step 3.
- Split mode (`mitm` on) only after the rewrite rules are proven: demonstrate bypass on controller fault,
  SPI fault and CPU hang before driving with it.

## 5. Before an energised vehicle trial

A qualified HV reviewer signs off the enclosure, harness protection and first-article insulation results
(insulation resistance HV-to-chassis and HV-to-LV at 500 V DC, after conformal coating).

## Factory acceptance (per board)

Firmware identity (status page), jumper configuration (JP termination and silent-mode jumpers), rails, all
four CAN interfaces (loopback through a second node), contactor and pump outputs into dummy loads, the
watchdog drop-out, isolation (500 V DC between the HV strip and LV ground), and bus-sense and NTC calibration.
Deliver the results with the board.
