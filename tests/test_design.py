"""Circuit intent, checked against hw/parts.json (the netlist the board is built from)."""
import pcbnew

from conftest import ROOT


def net(parts, ref, pin):
    return parts[ref]["nets"][str(pin)]


def pins_on(parts, name):
    return {(r, p) for r, d in parts.items() for p, n in d["nets"].items() if n == name}


def test_bypass_relay_joins_ima_halves_when_unpowered(parts):
    # K4 normally-closed contacts join the PCM side (IMA_CAN*) to the MCM side (MCM_CAN*)
    nets = set(parts["K4"]["nets"].values())
    assert {"IMA_CANH", "IMA_CANL", "MCM_CANH", "MCM_CANL"} <= nets


def test_pcm_side_termination_only_through_k4_no_contacts(parts):
    assert net(parts, "K4", 4) == "K4_NO1" and net(parts, "K4", 5) == "K4_NO2"
    chain = {net(parts, "R86", 1), net(parts, "R86", 2), net(parts, "JP13", 1), net(parts, "JP13", 2)}
    assert {"K4_NO1", "K4_NO2"} <= chain
    assert not ({"IMA_CANH", "IMA_CANL"} & chain), "termination must not sit directly on the IMA bus"


def test_mcm_side_termination_switched_with_relay_coil(parts):
    assert net(parts, "U22", 2) == "K4_COIL", "photoMOS LED must be driven by the K4 coil switch"
    assert net(parts, "U22", 4) == "MCM_CANL"
    assert {net(parts, "R96", 1), net(parts, "R96", 2)} == {"MCM_CANH", "TERM2"}


def test_dash_bus_is_a_plain_tap(parts):
    assert ("K4" not in {r for r, _ in pins_on(parts, "DASH_CANH")})


def test_mitm_transceivers_default_silent(parts):
    # S pin pulled to 3V3 through 10k, solder jumper to GND enables TX
    for n in (2, 3, 4):
        s = f"CAN{n}_S"
        refs = {r for r, _ in pins_on(parts, s)}
        assert any(parts[r]["val"] == "10k" for r in refs if r.startswith("R")), s
        assert any(r.startswith("JP") for r in refs), s


def test_esp32_module_has_enough_flash_for_ota(parts):
    assert "N8" in parts["U4"]["mpn"] or "N16" in parts["U4"]["mpn"]


def test_can_controllers_are_mcp2518fd_soic14(parts):
    # MCP2518FD SOIC-14 pinout (DS20006027 table 1-1): 10 SCK, 11 SDI, 12 SDO, 13 nCS, 4 INT, 14 VDD, 7 VSS
    for ref, cs, intr in (("U6", "SPI_CS", "CAN2_INT"), ("U18", "SPI_CS3", "CAN3_INT"), ("U20", "SPI_CS4", "CAN4_INT")):
        assert parts[ref]["mpn"] == "MCP2518FDT-E/SL"
        assert [net(parts, ref, p) for p in (10, 11, 12, 13, 4, 14, 7)] == \
            ["SPI_SCK", "SPI_MOSI", "SPI_MISO", cs, intr, "+3V3", "GND"], ref


def test_can_crystals_are_40mhz(parts):
    for y in ("Y1", "Y2", "Y3"):
        assert parts[y]["val"] == "40MHz"


def test_split_terminations_within_iso11898(parts):
    # two halves in series must land in 100-130 ohm
    for a, b in (("R7", "R8"), ("R88", "R89")):
        assert 100 <= float(parts[a]["val"]) + float(parts[b]["val"]) <= 130


def test_watchdog_pinout_and_latch(parts):
    # TPS3431 DRB: 1 VDD, 2 CWD (open = 1.6 s), 3 EN, 4 GND, 5 SET1, 6 WDI, 7 WDO, 8 ENOUT
    u11 = parts["U11"]["nets"]
    assert (u11["1"], u11["6"], u11["7"], u11["5"]) == ("+3V3", "WDI", "WDT_OK", "+3V3"), "SET1 high: watchdog on"
    assert u11["3"].startswith("NC_"), "EN floats on its internal pull-up"
    assert u11["2"].startswith("NC_"), "CWD left open: factory 1.6 s timeout"
    # SN74LVC1G74: WDI edges clock MCU_EN in; the watchdog output clears it and it stays clear
    u10 = parts["U10"]["nets"]
    assert (u10["1"], u10["2"], u10["5"], u10["6"], u10["7"], u10["8"]) == \
        ("WDI", "MCU_EN", "MASTER_EN", "WDT_CLR", "+3V3", "+3V3")
    assert {net(parts, "R16", 1), net(parts, "R16", 2)} == {"Q2_DRV", "Q2_G"}
    assert {net(parts, "C27", 1), net(parts, "C27", 2)} == {"WDT_OK", "GND"}, "power-on clear of the latch"
    # the slow R19/C27 edge reaches CLR through a Schmitt buffer (SC-70: 1 NC, 2 A, 3 GND, 4 Y, 5 VCC)
    u25 = parts["U25"]
    assert u25["mpn"].startswith("SN74LVC1G17")
    assert (u25["nets"]["2"], u25["nets"]["3"], u25["nets"]["4"], u25["nets"]["5"]) == ("WDT_OK", "GND", "WDT_CLR", "+3V3")
    assert parts["U11"]["mpn"] == "TPS3431SQDRBRQ1", "TI's orderable -Q1 number"


def test_high_side_drivers_inputs_on_input_pins(parts):
    # VND7050AJ PowerSSO-16: 1 IN0, 2 FaultRST, 3 SEn, 4 GND, 5 SEL0, 6 SEL1, 7 MultiSense, 8 IN1
    for ref, in0, in1 in (("U8", "HS_PRE_R", "HS_MAINP_R"), ("U9", "HS_MAINN_R", "HS_BMS_R")):
        n = parts[ref]["nets"]
        assert (n["1"], n["8"]) == (in0, in1), ref
        assert n["2"] == n["4"] == n["6"] == "GND", ref
        ms = n["7"]
        assert any(set(parts[r]["nets"].values()) == {ms, "GND"} and parts[r]["val"] == "1k" for r in parts), \
            f"{ref} MultiSense needs 1k to GND"
    assert parts["U9"]["nets"]["3"] == parts["U9"]["nets"]["5"] == "GND", "U9 diagnostics unused"


def test_coil_current_sense(parts):
    # U8 MultiSense channel 0 (precharge coil): SEn high through ST's 15k Rprot, SEL0/SEL1 low; sense 1k at the
    # pin, then 15k + 10n into ADC1 (IO9, ch8), so VSENSEH (<= 6.6 V) can't overdrive the ESP32
    n = parts["U8"]["nets"]
    between = lambda a, b: [r for r, p in parts.items() if set(p["nets"].values()) == {a, b}]
    assert n["5"] == n["6"] == "GND" and n["1"] == "HS_PRE_R" and n["13"] == "COIL_PRE", "channel 0 = precharge"
    assert parts["U8"]["fp"][1].endswith("_GND4-6"), "GND bar must not short SEn (pin 3)"
    assert [parts[r]["val"] for r in between("+3V3", n["3"])] == ["15k"]
    assert [parts[r]["val"] for r in between(n["7"], "MS_ADC")] == ["15k"]
    assert [parts[r]["val"] for r in between("MS_ADC", "GND")] == ["10n"]
    esp = parts["U4"]["nets"]
    assert (esp["17"], esp["29"]) == ("MS_ADC", "SPI_CS3"), "IO9 ADC, IO36 CS3"
    cfg = (ROOT / "firmware" / "main" / "config.h").read_text()
    assert "#define PIN_MS_ADC       9 " in cfg and "#define PIN_SPI_CS3      36 " in cfg
    fp = pcbnew.FootprintLoad(str(ROOT / "hw" / "lib" / "ze2.pretty"), parts["U8"]["fp"][1])
    bar = [p for p in fp.Pads() if p.GetNumber() == "4" and p.GetSize().y > pcbnew.FromMM(0.5)][0]
    pin3 = [p for p in fp.Pads() if p.GetNumber() == "3"][0]
    assert pcbnew.ToMM(bar.GetPosition().y) - pcbnew.ToMM(bar.GetSize().y) / 2 > pcbnew.ToMM(pin3.GetPosition().y) + 0.14


def test_bypass_relay_contact_map(parts):
    # Omron G6K: COM 3/6, NC 2/7, NO 4/5. Coil off: PCM side (COM) joined to MCM side (NC).
    k = parts["K4"]["nets"]
    assert (k["3"], k["6"]) == ("IMA_CANH", "IMA_CANL")
    assert (k["2"], k["7"]) == ("MCM_CANH", "MCM_CANL")
    assert (k["4"], k["5"]) == ("K4_NO1", "K4_NO2")


def test_reverse_protection_and_isolated_sense(parts):
    assert "U1" not in parts and parts["D7"]["nets"] == {"1": "VBAT_P", "2": "VIG_F"}   # D_SMA pad 1 = cathode
    u = parts["U12"]["nets"]   # AMC3311: HV side 1-8, LV side 9-16
    assert parts["U12"]["mpn"].startswith("AMC3311")
    assert (u["1"], u["3"], u["6"], u["12"], u["13"], u["16"]) == ("HV5V", "HV5V", "SENSE_MID", "+5V", "AMC_LDO", "AMC_LDO")
    assert "PS1" not in parts


def test_low_side_fets_get_5v_gate_drive(parts):
    # NCE6020AK: RDS(on) specified from VGS = 4.5 V, VGS(th) up to 2.5 V, so 3.3 V logic goes through a 5 V
    # SN74LV1T34 (VIH 2.0 V at 5 V) to each gate (SC-70: 1 NC, 2 A, 3 GND, 4 Y, 5 VCC)
    for buf, src, drv, res, gate in (("U23", "MASTER_EN", "Q2_DRV", "R16", "Q2_G"), ("U24", "PUMP_PWM", "Q3_DRV", "R20", "Q3_G")):
        n = parts[buf]["nets"]
        assert parts[buf]["mpn"].startswith("SN74LV1T34")
        assert (n["2"], n["3"], n["4"], n["5"]) == (src, "GND", drv, "+5V"), buf
        assert {net(parts, res, 1), net(parts, res, 2)} == {drv, gate}


def test_pump_line_readback(parts):
    # the 12-16 V pump line never reaches the GPIO: it drives Q26's gate through R102/R103, Q26 pulls PUMP_SENSE
    # (10k to 3.3 V) low. On at 7.5 V even with the 2N7002's 2.5 V worst-case threshold; 40 V keeps VGS < 20 V.
    assert {net(parts, "R102", 1), net(parts, "R102", 2)} == {"PUMP_N", "PUMP_G"}
    assert {net(parts, "R103", 1), net(parts, "R103", 2)} == {"PUMP_G", "GND"}
    assert parts["Q26"]["mpn"] == "2N7002" and parts["Q26"]["nets"] == {"1": "PUMP_G", "2": "GND", "3": "PUMP_SENSE"}
    assert {net(parts, "R104", 1), net(parts, "R104", 2)} == {"+3V3", "PUMP_SENSE"}
    assert "PUMP_N" not in parts["U4"]["nets"].values() and parts["U4"]["nets"]["28"] == "PUMP_SENSE"
    k = lambda r: float(parts[r]["val"].rstrip("k")) * 1000
    ratio = k("R103") / (k("R102") + k("R103"))
    assert 7.5 * ratio >= 2.5 and 40.0 * ratio < 20.0


def test_photomos_on_maker_land_pattern(parts):
    # Panasonic AQV214EHA: six 1.5 x 1.9 mm lands on 8.3 mm rows; pin 5 (MOSFET midpoint) present, own HV-class net
    for ref in ("K2", "K3"):
        assert parts[ref]["fp"][1] == "Panasonic_PhotoMOS_DIP6_SMD_W8.3mm"
        assert parts[ref]["nets"]["5"] == f"{ref}_P5"
    fp = pcbnew.FootprintLoad(str(ROOT / "hw" / "lib" / "ze2.pretty"), "Panasonic_PhotoMOS_DIP6_SMD_W8.3mm")
    pads = {p.GetNumber(): p for p in fp.Pads()}
    assert sorted(pads) == list("123456")
    assert abs(pcbnew.ToMM(pads["5"].GetPosition().x - pads["2"].GetPosition().x) - 8.3) < 1e-3
    assert [round(pcbnew.ToMM(v), 2) for v in (pads["1"].GetSize().x, pads["1"].GetSize().y)] == [1.9, 1.5]


def test_hv_feeds_fault_protected(parts):
    # tap ladder: a DC-rated fuse in series with each end resistor; even a tap-to-tap harness short draws >= 10x
    # its rating (Littelfuse 242: 1000 % opens in < 2 ms; 300 % may take 10 s). Bus sense: the 10k ends keep any short in the divider within each resistor's 1 W.
    assert parts["F3"]["nets"] == {"1": "BUS_P", "2": "BUS_P_FS"} and parts["F4"]["nets"] == {"1": "BUS_N_FS", "2": "BUS_N"}
    assert all(parts[f]["mpn"] == "Littelfuse 0242.050UR" for f in ("F3", "F4"))
    assert {net(parts, "RF1", 1), net(parts, "RF1", 2)} == {"BUS_P_FS", "DIV_TOP_IN"}
    assert {net(parts, "RF2", 1), net(parts, "RF2", 2)} == {"DIV_BOT_IN", "BUS_N_FS"}
    r = lambda ref: float(parts[ref]["val"].split()[0].rstrip("k")) * (1000 if "k" in parts[ref]["val"].split()[0] else 1)
    assert 150.0 / (r("RF1") + r("RF2") + 2 * 11.3) >= 10 * 0.050
    for ref in ("RF3", "RF4"):
        assert 150.0 ** 2 / (2 * r(ref)) <= 1.0 * 1.15 and 150.0 ** 2 / (r(ref) + 400e3) < 1.0
    assert not any("fusible" in p["val"] or "fusible" in p["mpn"] for p in parts.values())


def test_tap_ladder_is_low_impedance(parts):
    rd = [p for r, p in parts.items() if r.startswith("RD")]
    assert len(rd) == 16 and {p["val"] for p in rd} == {"10k"}, "one 0.1 % SKU, low source impedance"
