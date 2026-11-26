"""Firmware against hardware: pin map, CAN controller clock and bit timing, HV divider scale."""
import re

from conftest import ROOT

MAIN = ROOT / "firmware" / "main"
# ESP32-S3-WROOM-1 module pin -> GPIO (Espressif datasheet, pin definitions table)
WROOM = {4: 4, 5: 5, 6: 6, 7: 7, 8: 15, 9: 16, 10: 17, 11: 18, 12: 8, 13: 19, 14: 20, 15: 3, 16: 46, 17: 9,
         18: 10, 19: 11, 20: 12, 21: 13, 22: 14, 23: 21, 24: 47, 25: 48, 26: 45, 27: 0, 28: 35, 29: 36, 30: 37,
         31: 38, 32: 39, 33: 40, 34: 41, 35: 42, 36: 44, 37: 43, 38: 2, 39: 1}
NET_OF = {"I2C_SCL": "SCL1", "I2C_SDA": "SDA1", "SPI_CS2": "SPI_CS"}  # define name -> net where they differ


def defines(path):
    out = {}
    for m in re.finditer(r"^#define\s+(\w+)\s+(\d+)", path.read_text(), re.M):
        out[m.group(1)] = int(m.group(2))
    return out


CFG = defines(MAIN / "config.h")


def test_every_firmware_pin_lands_on_its_net(parts):
    gpio_net = {WROOM[int(p)]: n for p, n in parts["U4"]["nets"].items() if int(p) in WROOM}
    pins = {k[4:]: v for k, v in CFG.items() if k.startswith("PIN_")}
    assert len(set(pins.values())) == len(pins), "a GPIO is used twice"
    for name, gpio in pins.items():
        assert gpio_net.get(gpio) == NET_OF.get(name, name), f"PIN_{name} = GPIO{gpio} is {gpio_net.get(gpio)} on the board"


def test_can_controller_clock_matches_crystal(parts):
    assert CFG["MCP_OSC_HZ"] == int(parts["Y1"]["val"].rstrip("MHz")) * 1_000_000
    assert CFG["MCP_SPI_HZ"] <= 0.85 * CFG["MCP_OSC_HZ"] / 2, "MCP2518FD SPI limit is 0.85 x SYSCLK / 2"


def test_nominal_bit_timing_gives_500k():
    src = (MAIN / "mcp2518fd.c").read_text()
    brp, tseg1, tseg2, sjw = map(int, re.search(
        r"R_NBTCFG, \((\d+)u << 24\) \| \((\d+)u << 16\) \| \((\d+)u << 8\) \| (\d+)u\)", src).groups())
    tq = 1 + (tseg1 + 1) + (tseg2 + 1)
    assert CFG["MCP_OSC_HZ"] / (brp + 1) / tq == CFG["CAN_BITRATE"]
    assert 0.75 <= (1 + tseg1 + 1) / tq <= 0.875 and sjw <= tseg2


def test_crystal_load_caps_suit_the_crystal(parts):
    cl = float(re.search(r"(\d+)pF", parts["Y1"]["mpn"]).group(1))
    want = 2 * (cl - 3.0)  # two caps in series with ~3 pF of board and pin stray
    for c in ("C18", "C19", "C72", "C73", "C76", "C77"):
        assert abs(float(parts[c]["val"].rstrip("p")) - want) / want < 0.15, c


def ohms(v):
    v = v.split()[0]
    return float(v.rstrip("k")) * (1000 if v.endswith("k") else 1)


def test_hv_divider_scale_matches_firmware(parts):
    # the whole string carries the same current: RF3 + RS1-RS4 above the sensed RS5, RF4 below it
    top = ohms(parts["RF3"]["val"]) + sum(ohms(parts[f"RS{i}"]["val"]) for i in range(1, 5))
    bot = ohms(parts["RS5"]["val"])
    total = top + bot + ohms(parts["RF4"]["val"])
    assert abs(CFG["HV_DIV_X1000"] - 1000 * total / bot) < 5
    assert 2.0 * total / bot > 4.2 * 34 + 10, "full scale must clear a full 34S pack with margin"


def test_spi_and_twai_config_fit_the_hardware():
    hw = (MAIN / "hal_hw.c").read_text()
    drv = (MAIN / "mcp2518fd.c").read_text()
    assert "SPI_DMA_DISABLED" in hw and ".max_transfer_sz = 64" in hw
    assert re.search(r"#define MCP_MAX_XFER 64", drv), "bursts must fit the 64-byte non-DMA buffer"
    assert "ESP_INTR_FLAG_IRAM" not in hw.split("TWAI_GENERAL_CONFIG_DEFAULT")[1].split("twai_driver_install")[0], \
        "TWAI IRAM interrupt needs CONFIG_TWAI_ISR_IN_IRAM"


def test_bms_data_freshness_is_per_group():
    src = (MAIN / "captur.c").read_text()
    assert "for (int g = 0; g < GRP_COUNT; g++)" in src
    z = (MAIN / "zombie.c").read_text()
    assert "captur_fresh(now_ms) && g_safety.level < SAFE_SOFT_TRIP" in z


def test_analog_inputs_are_on_adc1(parts):
    # ADC1 (GPIO1-10) works alongside Wi-Fi; ADC2 does not
    for name in ("PIN_IG_SENSE", "PIN_AMC_P", "PIN_AMC_N"):
        assert 1 <= CFG[name] <= 10, name
    hw = (MAIN / "hal_hw.c").read_text()
    assert f"ADC_CHANNEL_{CFG['PIN_IG_SENSE'] - 1}" in hw, "IG_SENSE GPIO10 is ADC1 channel 9"
    r3, r4 = ohms(parts["R3"]["val"]), ohms(parts["R4"]["val"])
    assert abs(CFG["VBAT_DIV_X1000"] - 1000 * (r3 + r4) / r4) < 5
    assert 16000 * r4 / (r3 + r4) < 3100, "16 V supply must stay inside the 12 dB ADC range"


def test_control_loop_kicks_watchdog_first():
    body = (MAIN / "main.c").read_text().split("for (;;) {", 1)[1]
    assert body.index("contactors_kick_watchdog") < body.index("xQueueReceive"), "stall check before anything else"
