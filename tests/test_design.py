"""Circuit intent, checked against hw/parts.json (the netlist the board is built from)."""


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
    assert (u11["6"], u11["7"], u11["5"], u11["3"]) == ("WDI", "WDT_OK", "+3V3", "+3V3")
    assert u11["2"].startswith("NC_"), "CWD left open: factory 1.6 s timeout"
    # SN74LVC1G74: WDI edges clock MCU_EN in; the watchdog output clears it and it stays clear
    u10 = parts["U10"]["nets"]
    assert (u10["1"], u10["2"], u10["5"], u10["6"], u10["7"], u10["8"]) == \
        ("WDI", "MCU_EN", "MASTER_EN", "WDT_OK", "+3V3", "+3V3")
    assert {net(parts, "R16", 1), net(parts, "R16", 2)} == {"MASTER_EN", "Q2_G"}
    assert {net(parts, "C27", 1), net(parts, "C27", 2)} == {"WDT_OK", "GND"}, "power-on clear of the latch"


def test_high_side_drivers_inputs_on_input_pins(parts):
    # VND7050AJ PowerSSO-16: 1 IN0, 2 FaultRST, 3 SEn, 4 GND, 5 SEL0, 6 SEL1, 7 MultiSense, 8 IN1
    for ref, in0, in1 in (("U8", "HS_PRE_R", "HS_MAINP_R"), ("U9", "HS_MAINN_R", "HS_BMS_R")):
        n = parts[ref]["nets"]
        assert (n["1"], n["8"]) == (in0, in1), ref
        assert all(n[p] == "GND" for p in "23456"), ref
        ms = n["7"]
        assert any(set(parts[r]["nets"].values()) == {ms, "GND"} and parts[r]["val"] == "1k" for r in parts), \
            f"{ref} MultiSense needs 1k to GND"


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
