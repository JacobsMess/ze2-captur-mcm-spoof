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
