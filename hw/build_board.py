"""Generate the Insight ZE2 lithium MCM spoof board as a KiCad 7 PCB.

Single source of truth: PARTS below (ref -> footprint, value, MPN, pad->net). The script places
footprints, assigns nets, draws the outline + isolation slot, sets net classes and writes
spoof_board.kicad_pcb ready for Specctra autorouting.

Parts marked PLACEHOLDER use a stand-in footprint and/or an unverified pinout: check the datasheet
before ordering.
"""
import pcbnew

FP = "/usr/share/kicad/footprints/"
OX, OY = 50.0, 50.0  # board origin offset (mm)
W, H = 120.0, 98.0

R0805 = ("Resistor_SMD", "R_0805_2012Metric")
R1206 = ("Resistor_SMD", "R_1206_3216Metric")
R2512 = ("Resistor_SMD", "R_2512_6332Metric")
C0805 = ("Capacitor_SMD", "C_0805_2012Metric")
C1206 = ("Capacitor_SMD", "C_1206_3216Metric")
CEL = ("Capacitor_SMD", "CP_Elec_8x10")
SOIC8 = ("Package_SO", "SOIC-8_3.9x4.9mm_P1.27mm")

PARTS = {}  # ref: dict(fp=(lib,name), val, mpn, nets{pad:net}, pos(x,y), rot, note)


def part(ref, fp, val, mpn, nets, pos, rot=0, note=""):
    PARTS[ref] = dict(fp=fp, val=val, mpn=mpn, nets=nets, pos=pos, rot=rot, note=note)


def r(ref, val, a, b, pos, rot=0, fp=R0805, mpn=None):
    part(ref, fp, val, mpn or f"{val} {fp[1].split('_')[1]} 1%", {"1": a, "2": b}, pos, rot)


def c(ref, val, a, b, pos, rot=0, fp=C0805, mpn=None):
    part(ref, fp, val, mpn or f"{val} {fp[1].split('_')[1]} X7R", {"1": a, "2": b}, pos, rot)


# ---------------------------------------------------------------- connectors
j1 = {str(i): "NC_J1_%d" % i for i in range(13, 21)}
# Micro-Fit 2x10: pin n sits opposite pin n+10, so each CAN pair uses (n, n+10)
j1.update({str(i): "NC_J1_%d" % i for i in range(1, 13)})
j1.update({"1": "VIG_RAW", "11": "GND", "2": "GND", "12": "GND", "3": "IMA_CANH", "13": "IMA_CANL",
           "4": "CAN1H", "14": "CAN1L", "5": "MCM_CANH", "15": "MCM_CANL", "6": "DASH_CANH", "16": "DASH_CANL"})
part("J1", ("Connector_Molex", "Molex_Micro-Fit_3.0_43045-2012_2x10_P3.00mm_Vertical"), "J1 VEHICLE/MCM",
     "Molex 43045-2012", j1, (6.5, 4.5), 270)
j2 = {"1": "VCOIL_RAW", "2": "VCOIL_RAW", "3": "GND", "4": "GND", "5": "BMS12V", "6": "CAN1H", "7": "CAN1L",
      "8": "GND", "9": "COIL_PRE", "10": "COIL_MAINP", "11": "COIL_MAINN", "12": "COIL_RTN", "13": "VCOIL",
      "14": "PUMP_N", "15": "NC_J2_15", "16": "NC_J2_16"}
part("J2", ("Connector_Molex", "Molex_Micro-Fit_3.0_43045-1612_2x08_P3.00mm_Vertical"), "J2 CAPTUR LV",
     "Molex 43045-1612", j2, (6.5, 50.0), 270)
part("J6", ("Connector_Molex", "Molex_Micro-Fit_3.0_43045-0812_2x04_P3.00mm_Vertical"), "J6 MCM ANALOG",
     "Molex 43045-0812", {"1": "MCM5V", "2": "MCM_SG", "3": "TBATT1", "4": "TBATT2", "5": "TBATT3", "6": "ISOC_IN",
                          "7": "ISOC_OUT", "8": "MCM_SG"}, (58.5, 3.6), 0)
part("J3", ("Connector_Phoenix_MSTB", "PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal"), "J3 BUS",
     "Phoenix 1757242 MSTBA 2,5/2-G-5,08", {"1": "BUS_P", "2": "BUS_N"}, (106.0, 8.0), 180)
j4 = {str(i + 1): f"VHB{i}" for i in range(9)}
j4["10"] = "NC_J4_10"
part("J4", ("Connector_Molex", "Molex_Mini-Fit_Jr_5566-10A_2x05_P4.20mm_Vertical"), "J4 TAPS",
     "Molex 39-30-1100", j4, (108.0, 30.0), 90)
part("J5", ("Connector_USB", "USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal"), "USB-C",
     "GCT USB4105-GF-A", {"A1": "GND", "B12": "GND", "B1": "GND", "A12": "GND", "A4": "VBUS", "B9": "VBUS",
                          "B4": "VBUS", "A9": "VBUS", "A6": "USB_DP", "B6": "USB_DP", "A7": "USB_DN",
                          "B7": "USB_DN", "A5": "CC1", "B5": "CC2", "S1": "GND", "A8": "NC_SBU1", "B8": "NC_SBU2"},
     (78.0, 94.0), 0)
r("R60", "5.1k", "CC1", "GND", (70.5, 92.0), 90)
r("R61", "5.1k", "CC2", "GND", (84.0, 89.5), 90)
part("D10", ("Diode_SMD", "D_SOD-123"), "B5819W", "B5819W", {"1": "+5V", "2": "VBUS"}, (78.8, 86.6), 0)

# ---------------------------------------------------------------- power input (sheet 1)
part("F1", ("Fuse", "Fuse_1812_4532Metric"), "2A PTC", "PTC 1812 2A 30V", {"1": "VIG_RAW", "2": "VIG_F"}, (52.0, 38.0), 0)
part("U1", ("Package_TO_SOT_SMD", "SOT-23-6"), "LM74700-Q1", "LM74700QDBVRQ1",
     {"1": "LM_VCAP", "2": "VIG_F", "3": "GND", "4": "VIG_F", "5": "LM_GATE", "6": "VBAT_P"}, (58.0, 42.0), 0,
     "PLACEHOLDER pinout - verify against datasheet")
c("C1", "100n", "LM_VCAP", "VIG_F", (58.0, 45.5), 0)
part("Q1", ("Package_TO_SOT_SMD", "TO-252-2"), "N-FET 40V", "PLACEHOLDER 40V N-FET DPAK (e.g. auto-grade 40V 5mOhm)",
     {"1": "LM_GATE", "2": "VBAT_P", "3": "VIG_F"}, (66.0, 40.0), 0)
part("D1", ("Diode_SMD", "D_SMC"), "SMCJ33A", "SMCJ33A", {"1": "VBAT_P", "2": "GND"}, (66.0, 48.0), 0)
c("C2", "10u 50V", "VBAT_P", "GND", (73.0, 40.0), 90, fp=C1206)
c("C3", "10u 50V", "VBAT_P", "GND", (76.0, 40.0), 90, fp=C1206)
c("C4", "10u 50V", "VBAT_P", "GND", (75.0, 44.0), 90, fp=C1206)
# buck LMR16006 (SOT-23-6: 1 CB, 2 GND, 3 FB, 4 EN, 5 VIN, 6 SW)
part("U2", ("Package_TO_SOT_SMD", "SOT-23-6"), "LMR16006Y-Q1", "LMR16006YQDDCRQ1",
     {"1": "BUCK_CB", "2": "GND", "3": "BUCK_FB", "4": "VBAT_P", "5": "VBAT_P", "6": "BUCK_SW"}, (58.0, 58.0), 0)
c("C5", "100n", "BUCK_CB", "BUCK_SW", (58.0, 54.5), 0)
part("D3B", ("Diode_SMD", "D_SMB"), "SS36", "SS36 60V 3A Schottky", {"1": "BUCK_SW", "2": "GND"}, (58.0, 64.0), 180)
part("L1", ("Inductor_SMD", "L_Bourns_SRP7028A_7.3x6.6mm"), "22uH", "Bourns SRP7028A-220M", {"1": "BUCK_SW", "2": "+5V"}, (66.0, 60.0), 0)
r("R1", "56k", "+5V", "BUCK_FB", (52.0, 56.0), 90)
r("R2", "10k", "BUCK_FB", "GND", (52.0, 60.0), 90)
c("C6", "22u", "+5V", "GND", (72.0, 56.0), 90, fp=C1206)
c("C7", "22u", "+5V", "GND", (72.0, 61.0), 90, fp=C1206)
part("U3", ("Package_TO_SOT_SMD", "SOT-23-5"), "TLV75733PDBV", "TLV75733PDBVR",
     {"1": "+5V", "2": "GND", "3": "+5V", "4": "NC_U3_4", "5": "+3V3"}, (78.0, 58.0), 0)
c("C8", "1u", "+5V", "GND", (78.0, 54.5), 0)
c("C9", "10u", "+3V3", "GND", (78.0, 62.0), 0, fp=C1206)
r("R3", "100k", "VBAT_P", "IG_SENSE", (44.0, 44.0), 90)
r("R4", "22k", "IG_SENSE", "GND", (44.0, 48.0), 90)
c("C10", "100n", "IG_SENSE", "GND", (47.0, 48.0), 90)

# ---------------------------------------------------------------- MCU
esp = {"1": "GND", "40": "GND", "41": "GND", "2": "+3V3", "3": "ESP_EN", "4": "TWAI_TX", "5": "TWAI_RX",
       "6": "WDI", "7": "MCU_EN", "8": "HS_PRE", "9": "HS_MAINP", "10": "HS_MAINN", "11": "SCL1", "12": "SDA1",
       "13": "USB_DN", "14": "USB_DP", "15": "CAN3_INT", "16": "NC_IO46", "17": "SPI_CS3", "18": "IG_SENSE",
       "19": "SPI_MOSI", "20": "SPI_SCK", "21": "SPI_MISO", "22": "CAN4_INT", "23": "HS_BMS", "24": "PUMP_PWM",
       "25": "SPI_CS4", "26": "NC_IO45", "27": "BOOT", "28": "NC_IO35", "29": "NC_IO36", "30": "NC_IO37",
       "31": "CAN2_INT", "32": "SPI_CS", "33": "NC_IO40", "34": "OPTO_EN", "35": "RELAY_SPLIT", "36": "NC_RXD0",
       "37": "NC_TXD0", "38": "AMC_N", "39": "AMC_P"}
part("U4", ("RF_Module", "ESP32-S3-WROOM-1"), "ESP32-S3-WROOM-1-N8R2", "ESP32-S3-WROOM-1-N8R2", esp, (30.0, 15.0), 0)
c("C11", "10u", "+3V3", "GND", (19.0, 27.0), 90, fp=C1206)
c("C12", "100n", "+3V3", "GND", (22.0, 27.0), 90)
r("R5", "10k", "+3V3", "ESP_EN", (41.0, 22.0), 90)
c("C13", "1u", "ESP_EN", "GND", (41.0, 26.0), 90)
r("R6", "10k", "+3V3", "BOOT", (44.0, 22.0), 90)
part("SW1", ("Button_Switch_SMD", "SW_SPST_TL3342"), "RESET", "TL3342", {"1": "ESP_EN", "2": "GND"}, (23.0, 44.0), 0)
part("SW2", ("Button_Switch_SMD", "SW_SPST_TL3342"), "BOOT", "TL3342", {"1": "BOOT", "2": "GND"}, (31.0, 44.0), 0)

# ---------------------------------------------------------------- CAN1 (Captur BMS)
part("U5", SOIC8, "TJA1051T/3", "TJA1051T/3/1J",
     {"1": "TWAI_TX", "2": "GND", "3": "+5V", "4": "TWAI_RX", "5": "+3V3", "6": "CAN1L", "7": "CAN1H", "8": "GND"},
     (21.0, 34.0), 0)
c("C14", "100n", "+5V", "GND", (16.5, 31.0), 90)
c("C15", "100n", "+3V3", "GND", (16.5, 37.0), 90)
r("R7", "62", "CAN1H", "CAN1_TERM", (26.0, 30.5), 0)
r("R8", "62", "CAN1_TERM_MID", "CAN1L", (26.0, 37.5), 0)
part("JP1", ("Jumper", "SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm"), "TERM", "solder jumper",
     {"1": "CAN1_TERM", "2": "CAN1_TERM_MID"}, (29.5, 34.0), 90)
c("C16", "4.7n", "CAN1_TERM_MID", "GND", (26.0, 40.5), 0)
part("D4", ("Package_TO_SOT_SMD", "SOT-23"), "PESD2CAN", "PESD2CAN,215", {"1": "CAN1L", "2": "CAN1H", "3": "GND"}, (14.0, 41.0), 0)

# ---------------------------------------------------------------- CAN2 (IMA, listen only)
part("U6", ("Package_SO", "SOIC-18W_7.5x11.6mm_P1.27mm"), "MCP2515", "MCP2515-I/SO",
     {"1": "CAN2_TXD", "2": "CAN2_RXD", "3": "NC_CLKOUT", "4": "+3V3", "5": "+3V3", "6": "+3V3", "7": "OSC2",
      "8": "OSC1", "9": "GND", "10": "NC_RX1BF", "11": "NC_RX0BF", "12": "CAN2_INT", "13": "SPI_SCK",
      "14": "SPI_MOSI", "15": "SPI_MISO", "16": "SPI_CS", "17": "ESP_EN", "18": "+3V3"}, (42.0, 34.0), 0)
c("C17", "100n", "+3V3", "GND", (48.0, 28.0), 0)
part("Y1", ("Crystal", "Crystal_SMD_3225-4Pin_3.2x2.5mm"), "16MHz", "16MHz 3225 18pF",
     {"1": "OSC1", "2": "GND", "3": "OSC2", "4": "GND"}, (50.0, 34.0), 90)
c("C18", "18p", "OSC1", "GND", (53.0, 31.5), 0, mpn="18pF 0805 C0G")
c("C19", "18p", "OSC2", "GND", (53.0, 36.5), 0, mpn="18pF 0805 C0G")
part("U7", SOIC8, "TJA1051T/3", "TJA1051T/3/1J",
     {"1": "CAN2_TXD", "2": "GND", "3": "+5V", "4": "CAN2_RXD", "5": "+3V3", "6": "MCM_CANL", "7": "MCM_CANH", "8": "CAN2_S"},
     (32.0, 34.0), 0, "CAN2 = IMA bus, MCM side. S pulled high (silent) until JP2 closed")
c("C20", "100n", "+5V", "GND", (36.0, 30.0), 90)
part("D5", ("Package_TO_SOT_SMD", "SOT-23"), "PESD2CAN", "PESD2CAN,215", {"1": "MCM_CANL", "2": "MCM_CANH", "3": "GND"}, (14.0, 24.0), 0)
r("R70", "10k", "+3V3", "CAN2_S", (30.0, 39.5), 0)
part("JP2", ("Jumper", "SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm"), "CAN2 TX EN", "solder jumper",
     {"1": "CAN2_S", "2": "GND"}, (34.0, 39.5), 0)

# ---------------------------------------------------------------- CAN3 (IMA, car/PCM side) + CAN4 (dash) + bypass relay
def can_port(n, mcp, xcvr, xtal, x, canh, canl, cs, intr, term=True):
    part(mcp, ("Package_SO", "SOIC-18W_7.5x11.6mm_P1.27mm"), "MCP2515", "MCP2515-I/SO",
         {"1": f"CAN{n}_TXD", "2": f"CAN{n}_RXD", "3": f"NC_CLKOUT{n}", "4": "+3V3", "5": "+3V3", "6": "+3V3",
          "7": f"OSC{n}_2", "8": f"OSC{n}_1", "9": "GND", "10": f"NC_RX1BF{n}", "11": f"NC_RX0BF{n}", "12": intr,
          "13": "SPI_SCK", "14": "SPI_MOSI", "15": "SPI_MISO", "16": cs, "17": "ESP_EN", "18": "+3V3"}, (x, 89.0), 0)
    part(xtal, ("Crystal", "Crystal_SMD_3225-4Pin_3.2x2.5mm"), "16MHz", "16MHz 3225 18pF",
         {"1": f"OSC{n}_1", "2": "GND", "3": f"OSC{n}_2", "4": "GND"}, (x + 8.0, 85.5), 90)
    c(f"C{60 + 4 * n}", "18p", f"OSC{n}_1", "GND", (x + 8.0, 82.0), 0, mpn="18pF 0805 C0G")
    c(f"C{61 + 4 * n}", "18p", f"OSC{n}_2", "GND", (x + 8.0, 89.0), 0, mpn="18pF 0805 C0G")
    c(f"C{62 + 4 * n}", "100n", "+3V3", "GND", (x, 96.2), 0)
    part(xcvr, SOIC8, "TJA1051T/3", "TJA1051T/3/1J",
         {"1": f"CAN{n}_TXD", "2": "GND", "3": "+5V", "4": f"CAN{n}_RXD", "5": "+3V3", "6": canl, "7": canh, "8": f"CAN{n}_S"},
         (x + 14.5, 89.0), 0, f"CAN{n}: S pulled high (silent) until JP{n + 3} closed")
    c(f"C{63 + 4 * n}", "100n", "+5V", "GND", (x + 14.5, 94.8), 0)
    r(f"R{70 + n}", "10k", "+3V3", f"CAN{n}_S", (x + 14.5, 83.2), 0)
    part(f"JP{n + 3}", ("Jumper", "SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm"), f"CAN{n} TX EN", "solder jumper",
         {"1": f"CAN{n}_S", "2": "GND"}, (x + 18.5, 83.2), 90)
    part(f"D{12 + n}", ("Package_TO_SOT_SMD", "SOT-23"), "PESD2CAN", "PESD2CAN,215", {"1": canl, "2": canh, "3": "GND"},
         (x + 20.5, 87.0), 90)
    if not term:
        return
    # split termination (open by default: the car bus already has its own terminations)
    r(f"R{80 + 2 * n}", "62", canh, f"TERM{n}", (x + 19.5, 93.5), 90)
    r(f"R{81 + 2 * n}", "62", f"TERM{n}_MID", canl, (x + 21.5, 93.5), 90)
    part(f"JP{n + 10}", ("Jumper", "SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm"), f"TERM{n}", "solder jumper",
         {"1": f"TERM{n}", "2": f"TERM{n}_MID"}, (x + 23.5, 89.5), 90)
    c(f"C{90 + n}", "4.7n", f"TERM{n}_MID", "GND", (x + 23.5, 94.0), 90)


can_port(3, "U18", "U19", "Y2", 14.0, "IMA_CANH", "IMA_CANL", "SPI_CS3", "CAN3_INT", term=False)
can_port(4, "U20", "U21", "Y3", 45.0, "DASH_CANH", "DASH_CANL", "SPI_CS4", "CAN4_INT")
# fail-safe bypass: relay de-energised = MCM side wired straight to car side (stock behaviour)
part("K4", ("Relay_SMD", "Relay_DPDT_Omron_G6K-2F-Y"), "G6K-2F-Y 5VDC", "Omron G6K-2F-Y DC5",
     {"1": "+5V", "8": "K4_COIL", "2": "IMA_CANH", "3": "MCM_CANH", "4": "K4_NO1",
      "7": "IMA_CANL", "6": "MCM_CANL", "5": "K4_NO2"}, (80.5, 79.3), 0,
     "PLACEHOLDER pin map: verify coil 1/8, COM 2/7, NC 3/6 against Omron datasheet")
part("Q4", ("Package_TO_SOT_SMD", "SOT-23"), "2N7002", "2N7002", {"1": "Q4_G", "2": "GND", "3": "K4_COIL"}, (74.0, 85.4), 90)
r("R78", "100", "RELAY_SPLIT", "Q4_G", (70.6, 83.6), 90)
r("R79", "100k", "Q4_G", "GND", (72.0, 80.0), 90)
part("D11", ("Diode_SMD", "D_SOD-123"), "1N4148W", "1N4148W", {"1": "+5V", "2": "K4_COIL"}, (74.5, 80.0), 90)
# IMA-bus terminations only exist while the bus is split (relay energised); de-energised = stock bus, no extra load.
# PCM side: switched by K4's spare NO contacts. MCM side: photoMOS driven in parallel with the K4 coil.
r("R86", "120", "K4_NO1", "TERM3", (82.15, 86.8), 90)
part("JP13", ("Jumper", "SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm"), "TERM3", "solder jumper",
     {"1": "TERM3", "2": "K4_NO2"}, (84.4, 86.8), 90)
r("R96", "120", "MCM_CANH", "TERM2", (75.0, 71.5), 0)
part("JP12", ("Jumper", "SolderJumper-2_P1.3mm_Open_RoundedPad1.0x1.5mm"), "TERM2", "solder jumper",
     {"1": "TERM2", "2": "TERM2_SW"}, (78.6, 71.5), 0)
part("U22", ("Package_SO", "SOP-4_4.4x2.6mm_P1.27mm"), "AQY212GS", "Panasonic AQY212GSZ (60 V photoMOS)",
     {"1": "TERM2_LED", "2": "K4_COIL", "3": "TERM2_SW", "4": "MCM_CANL"}, (80.5, 66.6), 0,
     "PLACEHOLDER pinout: 1 LED A, 2 LED K, 3/4 output - verify")
r("R97", "470", "+5V", "TERM2_LED", (75.05, 66.5), 90)

# ---------------------------------------------------------------- contactor drivers (sheet 2)
part("F2", ("Fuse", "Fuse_2920_7451Metric"), "5A", "PTC/fuse 2920 5A 30V", {"1": "VCOIL_RAW", "2": "VCOIL"}, (20.0, 58.0), 0)
vnd_note = "PLACEHOLDER: VND7050AJ is PowerSSO-16; HTSSOP-16 stand-in footprint and assumed pinout - verify"
for ref, pos, out0, out1, in0, in1 in (("U8", (20.0, 70.0), "COIL_PRE", "COIL_MAINP", "HS_PRE_R", "HS_MAINP_R"),
                                       ("U9", (32.0, 70.0), "COIL_MAINN", "BMS12V", "HS_MAINN_R", "HS_BMS_R")):
    nets = {"1": "GND", "2": in0, "3": "GND", "4": "GND", "5": "GND", "6": in1, "7": "NC_%s_7" % ref,
            "8": "NC_%s_8" % ref, "9": out1, "10": out1, "11": out1, "12": out1, "13": out0, "14": out0,
            "15": out0, "16": out0, "17": "VCOIL"}
    part(ref, ("Package_SO", "HTSSOP-16-1EP_4.4x5mm_P0.65mm_EP3.4x5mm"), "VND7050AJ", "VND7050AJTR", nets, pos, 0, vnd_note)
for ref, a, b, pos in (("R10", "HS_PRE", "HS_PRE_R", (16.0, 64.0)), ("R11", "HS_MAINP", "HS_MAINP_R", (19.0, 64.0)),
                       ("R12", "HS_MAINN", "HS_MAINN_R", (28.0, 64.0)), ("R13", "HS_BMS", "HS_BMS_R", (31.0, 64.0))):
    r(ref, "4.7k", a, b, pos, 90)
c("C23", "100n", "VCOIL", "GND", (16.0, 76.0), 90)
c("C24", "100n", "VCOIL", "GND", (28.0, 76.0), 90)
c("C25", "10u 50V", "VCOIL", "GND", (26.0, 58.0), 90, fp=C1206)
part("Q2", ("Package_TO_SOT_SMD", "TO-252-2"), "N-FET 60V logic", "PLACEHOLDER 60V logic-level N-FET DPAK",
     {"1": "Q2_G", "2": "COIL_RTN", "3": "GND"}, (45.0, 70.0), 0)
r("R16", "100", "AND_Y", "Q2_G", (40.0, 64.0), 90)
r("R17", "100k", "Q2_G", "GND", (40.0, 76.0), 90)
part("D2", ("Diode_SMD", "D_SMB"), "SMBJ33A", "SMBJ33A", {"1": "COIL_RTN", "2": "GND"}, (45.0, 77.0), 0)
part("U10", ("Package_TO_SOT_SMD", "SOT-23-5"), "74LVC1G08", "SN74LVC1G08DBVR",
     {"1": "WDT_OK", "2": "MCU_EN", "3": "GND", "4": "AND_Y", "5": "+5V"}, (38.0, 58.0), 0)
c("C26", "100n", "+5V", "GND", (38.0, 54.5), 0)
r("R18", "100k", "MCU_EN", "GND", (34.0, 54.5), 0)
part("U11", ("Package_SON", "VSON-8-1EP_3x3mm_P0.65mm_EP1.65x2.4mm"), "TPS3431-Q1", "TPS3431SDRBRQ1",
     {"1": "+3V3", "2": "WDT_CWD", "3": "WDT_OK", "4": "GND", "5": "+3V3", "6": "GND", "7": "+3V3", "8": "WDI", "9": "GND"},
     (44.0, 58.0), 0, "PLACEHOLDER pinout - verify against TPS3431 datasheet")
r("R19", "10k", "+3V3", "WDT_OK", (44.0, 54.0), 0)
c("C27", "100n", "WDT_CWD", "GND", (48.0, 58.0), 90, mpn="CWD cap - value per TPS3431 timing")
c("C28", "100n", "+3V3", "GND", (48.0, 62.0), 90)
# pump
part("Q3", ("Package_TO_SOT_SMD", "TO-252-2"), "N-FET 60V logic", "PLACEHOLDER 60V logic-level N-FET DPAK",
     {"1": "Q3_G", "2": "PUMP_N", "3": "GND"}, (55.0, 70.0), 0)
r("R20", "100", "PUMP_PWM", "Q3_G", (51.0, 64.0), 90)
r("R21", "100k", "Q3_G", "GND", (51.0, 76.0), 90)
part("D6", ("Diode_SMD", "D_SMC"), "SS54", "SS54", {"1": "VCOIL", "2": "PUMP_N"}, (56.0, 77.0), 180)

# ---------------------------------------------------------------- analog island (sheet 4)
part("U13", SOIC8, "ISO1540", "ISO1540DR",
     {"1": "+3V3", "2": "SDA1", "3": "SCL1", "4": "GND", "5": "ISLGND", "6": "SCL2", "7": "SDA2", "8": "ISL5V"},
     (44.5, 13.0), 0)
c("C30", "100n", "+3V3", "GND", (40.0, 8.0), 90)
c("C31", "100n", "ISL5V", "ISLGND", (49.0, 8.0), 90)
r("R30", "4.7k", "+3V3", "SDA1", (40.0, 16.5), 90)
r("R31", "4.7k", "+3V3", "SCL1", (42.0, 19.5), 90)
r("R32", "4.7k", "ISL5V", "SDA2", (49.0, 17.0), 90)
r("R33", "4.7k", "ISL5V", "SCL2", (51.0, 17.0), 90)
r("R34", "0", "MCM5V", "ISL5V", (54.0, 23.0), 0, mpn="0R 0805 (JP2: island supply = MCM 5V)")
r("R35", "0", "MCM_SG", "ISLGND", (54.0, 26.0), 0, mpn="0R 0805 single-point island ground")
part("U14", ("Package_SO", "MSOP-10_3x3mm_P0.5mm"), "MCP4728", "MCP4728-E/UN",
     {"1": "ISL5V", "2": "SCL2", "3": "SDA2", "4": "ISLGND", "5": "NC_RDY", "6": "DAC_A", "7": "DAC_B",
      "8": "DAC_C", "9": "DAC_D", "10": "ISLGND"}, (56.0, 10.0), 0)
c("C32", "100n", "ISL5V", "ISLGND", (56.0, 5.5), 0)
part("U15", ("Package_SO", "SOIC-14_3.9x8.7mm_P1.27mm"), "MCP6004", "MCP6004-E/SL",
     {"1": "OUTA", "2": "OUTA", "3": "DAC_A", "4": "ISL5V", "5": "DAC_B", "6": "OUTB", "7": "OUTB", "8": "OUTC",
      "9": "OUTC", "10": "DAC_C", "11": "ISLGND", "12": "SUM_P", "13": "SUM_N", "14": "OUTD"}, (66.0, 12.0), 0)
c("C33", "100n", "ISL5V", "ISLGND", (61.0, 5.5), 0)
r("R36", "1k", "OUTA", "TBATT1", (72.0, 7.0), 0)
r("R37", "1k", "OUTB", "TBATT2", (72.0, 10.0), 0)
r("R38", "1k", "OUTC", "TBATT3", (72.0, 13.0), 0)
r("R39", "10k", "ISOC_IN", "SUM_P", (60.0, 20.0), 0, mpn="10k 0805 0.1%")
r("R40", "200k", "DAC_D", "SUM_P", (60.0, 23.0), 0, mpn="200k 0805 0.1%")
r("R41", "200k", "VMID", "SUM_N", (66.0, 20.0), 0, mpn="200k 0805 0.1%")
r("R42", "10k", "SUM_N", "OUTD", (66.0, 23.0), 0, mpn="10k 0805 0.1%")
r("R43", "100", "OUTD", "ISOC_OUT", (72.0, 17.0), 0)
r("R44", "10k", "ISL5V", "VMID", (60.0, 27.0), 0, mpn="10k 0805 0.1%")
r("R45", "10k", "VMID", "ISLGND", (66.0, 27.0), 0, mpn="10k 0805 0.1%")
c("C34", "1u", "VMID", "ISLGND", (72.0, 27.0), 0)
part("U16", ("Package_SO", "MSOP-10_3x3mm_P0.5mm"), "ADS1115", "ADS1115IDGSR",
     {"1": "ISLGND", "2": "NC_ALRT16", "3": "ISLGND", "4": "TBATT1", "5": "TBATT2", "6": "TBATT3", "7": "ISOC_OUT",
      "8": "ISL5V", "9": "SDA2", "10": "SCL2"}, (78.0, 10.0), 0)
part("U17", ("Package_SO", "MSOP-10_3x3mm_P0.5mm"), "ADS1115", "ADS1115IDGSR",
     {"1": "ISL5V", "2": "NC_ALRT17", "3": "ISLGND", "4": "ISOC_IN", "5": "ISL5V_HALF", "6": "VMID", "7": "ISLGND",
      "8": "ISL5V", "9": "SDA2", "10": "SCL2"}, (78.0, 20.0), 0)
c("C35", "100n", "ISL5V", "ISLGND", (82.5, 10.0), 90)
c("C36", "100n", "ISL5V", "ISLGND", (82.5, 20.0), 90)
r("R46", "10k", "ISL5V", "ISL5V_HALF", (78.0, 25.5), 0)
r("R47", "10k", "ISL5V_HALF", "ISLGND", (78.0, 28.5), 0)

# Isolation slots: only under the four parts that bridge the HV/LV gap (U12, PS1, K2, K3), where flux or dirt
# trapped under a body could bridge their pads. Elsewhere the 5.6 mm copper-free band alone gives the creepage
# needed at <=150 V. 1.2 mm wide (JLC NPTH slot minimum is 1.0 mm). Board mm, origin = top-left corner.
SLOTS = [(87.5, 14.5, 88.7, 21.5), (87.5, 25.8, 88.7, 39.6), (87.5, 41.6, 88.7, 50.4), (87.5, 53.6, 88.7, 62.4)]

# ---------------------------------------------------------------- bridging parts (straddle the slot)
part("U12", ("Package_SO", "SOIC-8_7.5x5.85mm_P1.27mm"), "AMC1311-Q1", "AMC1311QDWVRQ1",
     {"1": "HV5V", "2": "SENSE_MID", "3": "BUS_N_F", "4": "BUS_N_F", "5": "GND", "6": "AMC_OUTN", "7": "AMC_OUTP", "8": "+5V"},
     (88.1, 18.0), 180, "DWV 7.5 mm body, 8.5 mm creepage")
r("R50", "100", "AMC_OUTP", "AMC_P", (80.0, 34.0), 90)
r("R51", "100", "AMC_OUTN", "AMC_N", (82.0, 34.0), 90)
c("C37", "10n", "AMC_P", "GND", (80.0, 38.0), 90)
c("C38", "10n", "AMC_N", "GND", (82.0, 38.0), 90)
c("C39", "100n", "+5V", "GND", (82.0, 24.0), 90)
part("PS1", ("Converter_DCDC", "Converter_DCDC_Murata_NXExSxxxxMC_SMD"), "R1SX-0505", "RECOM R1SX-0505 1 kVDC (PLACEHOLDER: NXE footprint stand-in)",
     {"1": "+5V", "3": "GND", "7": "GND", "8": "BUS_N_F", "14": "HV5V"}, (88.1, 34.0), 0,
     "PLACEHOLDER: footprint is Murata NXE1 stand-in; check isolation DC-DC pinout")
c("C40", "1u", "HV5V", "BUS_N_F", (95.0, 28.0), 90)
for ref, y, en_net in (("K2", 46.0, "K2_LED"), ("K3", 58.0, "K3_LED")):
    top = ("DIV_TOP_IN", "DIV_TOP") if ref == "K2" else ("DIV_BOT", "DIV_BOT_IN")
    part(ref, ("Package_DIP", "SMDIP-6_W7.62mm"), "AQV214EH", "Panasonic AQV214EHAX (400 V)",
         {"1": en_net, "2": "GND", "3": "NC_%s_3" % ref, "4": top[0], "5": "NC_%s_5" % ref, "6": top[1]}, (88.1, y), 0)
r("R52", "270", "OPTO_EN", "K2_LED", (80.0, 46.0), 90)
r("R53", "270", "OPTO_EN", "K3_LED", (80.0, 58.0), 90)

# ---------------------------------------------------------------- HV strip (sheet 3)
r("RF1", "1k 1W fusible", "BUS_P", "DIV_TOP_IN", (97.0, 8.0), 0, fp=R2512, mpn="PLACEHOLDER 1k 1W fusible flameproof 2512")
r("RF2", "1k 1W fusible", "DIV_BOT_IN", "BUS_N", (97.0, 76.0), 0, fp=R2512, mpn="PLACEHOLDER 1k 1W fusible flameproof 2512")
part("RF3", R2512, "1k 1W fusible", "PLACEHOLDER 1k 1W fusible flameproof 2512", {"1": "BUS_P", "2": "BUS_P_F"}, (110.0, 14.0), 90)
part("RF4", R2512, "1k 1W fusible", "PLACEHOLDER 1k 1W fusible flameproof 2512", {"1": "BUS_N", "2": "BUS_N_F"}, (114.0, 14.0), 90)
nodes = ["DIV_TOP", "TAP7", "TAP6", "TAP5", "TAP4", "TAP3", "TAP2", "TAP1", "DIV_BOT"]
for i in range(8):
    y = 17.0 + i * 7.0
    r(f"RD{2*i+1}", "47k", nodes[i], f"DIVM{i}", (98.5, y), 0, fp=R1206, mpn="47k 1206 0.1% 25ppm")
    r(f"RD{2*i+2}", "47k", f"DIVM{i}", nodes[i + 1], (98.5, y + 3.5), 0, fp=R1206, mpn="47k 1206 0.1% 25ppm")
vhb = {"DIV_TOP": "VHB8", "TAP7": "VHB7", "TAP6": "VHB6", "TAP5": "VHB5", "TAP4": "VHB4", "TAP3": "VHB3",
       "TAP2": "VHB2", "TAP1": "VHB1", "DIV_BOT": "VHB0"}
for i, nd in enumerate(nodes):
    r(f"RT{8 - i}", "0", nd, vhb[nd], (104.0, 17.5 + i * 7.0 - (3.5 if i == 8 else 0)), 0, fp=R1206, mpn="0R 1206 (series tap R option)")
for i in range(4):
    a = "BUS_P_F" if i == 0 else f"SNS{i}"
    b = "SENSE_MID" if i == 3 else f"SNS{i+1}"
    r(f"RS{i+1}", "249k", a, b, (112.0, 22.0 + i * 4.0), 90, fp=R1206, mpn="249k 1206 0.1%")
r("RS5", "13.3k", "SENSE_MID", "BUS_N_F", (112.0, 40.0), 90, fp=R1206, mpn="13.3k 1206 0.1% (0-152 V full scale)")
c("C41", "1n", "SENSE_MID", "BUS_N_F", (115.0, 40.0), 90)

for i, (x, y) in enumerate(((52.0, 50.0), (116.5, 3.5), (3.5, 94.5), (116.5, 94.5))):
    if x is None:
        continue  # left corners: ESP32 antenna keepout / J2; H1 moved inboard for a 3-point mount
    part(f"H{i+1}", ("MountingHole", "MountingHole_3.2mm_M3"), "M3", "M3 mounting hole", {}, (x, y), 0)


# ---------------------------------------------------------------- placement pass (overrides)
MOVES = {
    "J1": ((9.5, 7.0), 270), "J2": ((9.5, 46.0), 270), "J3": ((109.0, 4.5), 0), "J4": ((104.0, 72.0), 90),
    "D4": ((17.0, 41.0), 0), "D5": ((17.0, 20.0), 0), "C11": ((17.0, 25.0), 90), "C12": ((17.0, 29.0), 90),
    "R5": ((46.0, 22.0), 90), "R6": ((48.5, 22.0), 90), "C13": ((46.0, 26.0), 90), "C30": ((44.0, 7.0), 0),
    "U7": ((34.0, 34.0), 0), "C20": ((34.0, 29.0), 0), "JP1": ((28.5, 34.0), 90),
    "R50": ((76.0, 34.0), 90), "R51": ((78.0, 34.0), 90), "C37": ((76.0, 38.0), 90), "C38": ((78.0, 38.0), 90),
    "R52": ((82.0, 44.0), 90), "R53": ((82.0, 56.0), 90),
    "U10": ((36.0, 58.0), 0), "U11": ((42.0, 58.0), 0), "C27": ((45.5, 57.0), 90), "C28": ((45.5, 61.0), 90),
    "R19": ((42.0, 54.5), 0), "C26": ((36.0, 54.5), 0), "R18": ((32.0, 54.5), 0), "Q2": ((44.0, 71.0), 0), "R16": ((40.0, 64.0), 90), "R17": ((40.0, 76.0), 90), "D2": ((50.0, 64.0), 90),
    "Q3": ((56.0, 71.0), 0), "R20": ((53.0, 64.0), 90), "R21": ((51.0, 76.0), 90), "D6": ((62.0, 71.0), 90),
    "U2": ((64.0, 55.0), 0), "C5": ((64.0, 51.5), 0), "D3B": ((65.0, 61.5), 180), "L1": ((72.0, 58.0), 0),
    "R1": ((60.0, 54.0), 90), "R2": ((60.0, 58.0), 90), "C6": ((77.0, 53.0), 90), "C7": ((77.0, 58.0), 90),
    "U3": ((81.5, 62.0), 0), "C8": ((81.5, 58.5), 0), "C9": ((81.5, 65.5), 0),
    "D1": ((65.0, 48.5), 0), "Q1": ((66.0, 39.5), 0), "U1": ((58.0, 41.0), 0), "C1": ((58.0, 44.5), 0),
    "F1": ((52.0, 40.0), 90), "C2": ((71.0, 44.0), 90), "C3": ((73.0, 44.0), 90),
    "RS1": ((115.0, 22.0), 90), "RS2": ((115.0, 26.0), 90), "RS3": ((115.0, 30.0), 90), "RS4": ((115.0, 34.0), 90),
    "RS5": ((115.0, 38.0), 90), "C41": ((117.5, 38.0), 90), "RF3": ((112.0, 14.0), 90), "RF4": ((116.0, 14.0), 90),
}
MOVES.update({
    "J1": ((9.5, 9.0), 270), "U6": ((44.0, 34.0), 0), "Y1": ((56.0, 34.0), 90), "C18": ((56.0, 30.0), 0),
    "C19": ((56.0, 38.0), 0), "C17": ((50.0, 27.0), 0), "C20": ((37.0, 30.0), 0), "R20": ((54.0, 64.0), 90),
    "D6": ((64.0, 72.0), 90), "D3B": ((64.0, 62.0), 180), "C6": ((78.5, 53.0), 90), "C7": ((78.5, 58.0), 90),
    "U3": ((72.0, 66.5), 0), "C8": ((69.0, 66.5), 90), "C9": ((72.0, 63.0), 0),
    "C2": ((72.5, 44.0), 90), "C3": ((74.5, 44.0), 90), "C4": ((76.5, 44.0), 90), "Q1": ((66.0, 38.0), 0),
    "D1": ((66.0, 47.0), 0), "C5": ((64.0, 52.0), 0), "J4": ((105.0, 70.0), 90), "J3": ((110.0, 4.5), 0),
    "RF3": ((112.0, 19.0), 90), "RF4": ((116.0, 19.0), 90), "RS1": ((115.0, 26.0), 90), "RS2": ((115.0, 30.0), 90),
    "RS3": ((115.0, 34.0), 90), "RS4": ((115.0, 38.0), 90), "RS5": ((115.0, 42.0), 90), "C41": ((117.5, 42.0), 90),
    "H2": ((116.5, 50.0), 0), "C35": ((78.0, 6.5), 0), "C36": ((78.0, 16.3), 0), "D5": ((17.0, 17.0), 0),
    "C12": ((17.0, 21.5), 90), "SW2": ((33.0, 45.0), 0), "C16": ((21.5, 38.6), 0),
})
MOVES.update({
    "J3": ((103.5, 3.0), 0), "H2": ((116.5, 3.5), 0), "RF1": ((94.5, 8.5), 90), "J4": ((107.0, 68.0), 90),
    "C2": ((72.0, 44.0), 90), "C3": ((74.6, 44.0), 90), "C4": ((77.2, 44.0), 90), "U1": ((57.5, 41.0), 0),
    "RS1": ((115.0, 24.0), 90), "RS2": ((115.0, 28.6), 90), "RS3": ((115.0, 33.2), 90), "RS4": ((115.0, 37.8), 90),
    "RS5": ((115.0, 42.4), 90), "C41": ((117.5, 42.4), 90), "J1": ((9.5, 11.5), 270), "C12": ((17.0, 21.0), 90),
    "C14": ((16.0, 31.0), 90), "C15": ((16.0, 37.0), 90), "R17": ((39.5, 76.0), 90), "R21": ((50.5, 76.5), 90),
    "R60": ((72.5, 71.0), 0), "R61": ((83.5, 71.0), 0), "C20": ((36.0, 29.5), 0), "D4": ((16.5, 40.5), 0),
    "C30": ((44.0, 9.5), 0),
})
MOVES.update({
    "R60": ((71.5, 72.0), 90), "R61": ((84.5, 72.0), 90), "R17": ((39.0, 76.5), 90), "J1": ((9.5, 10.5), 270),
    "J2": ((9.5, 47.0), 270), "RF4": ((116.0, 18.0), 90), "RF3": ((112.0, 18.0), 90), "RS1": ((115.0, 24.5), 90),
    "R30": ((41.0, 17.0), 90), "U6": ((44.0, 35.0), 0), "C30": ((44.0, 8.8), 0), "C40": ((92.5, 28.0), 90),
})
MOVES.update({
    "R30": ((41.0, 21.0), 90), "R31": ((43.5, 21.0), 90), "RS1": ((115.0, 24.5), 90), "RS2": ((115.0, 29.2), 90),
    "RS3": ((115.0, 33.9), 90), "RS4": ((115.0, 38.6), 90), "RS5": ((115.0, 43.3), 90), "C41": ((117.6, 43.3), 90),
    "J1": ((9.5, 10.8), 270), "J2": ((9.5, 47.9), 270), "C40": ((93.0, 24.5), 0),
})
for ref, (pos, rot) in MOVES.items():
    PARTS[ref]["pos"], PARTS[ref]["rot"] = pos, rot

MOVES.update({
    "U14": ((52.5, 16.5), 0), "C32": ((52.5, 12.5), 0), "C31": ((48.5, 6.0), 0), "R32": ((50.0, 9.5), 90),
    "R33": ((52.0, 9.5), 90), "R34": ((69.0, 4.0), 0), "R35": ((69.0, 7.0), 0), "U15": ((60.0, 17.0), 0),
    "C33": ((63.5, 11.0), 0), "R36": ((67.0, 14.0), 0), "R37": ((67.0, 16.5), 0), "R38": ((67.0, 19.0), 0),
    "R43": ((67.0, 21.5), 0), "U16": ((75.0, 14.0), 0), "U17": ((75.0, 23.0), 0), "C35": ((79.5, 14.0), 90),
    "C36": ((79.5, 23.0), 90), "R46": ((73.0, 28.5), 90), "R47": ((75.5, 28.5), 90), "R39": ((57.0, 24.0), 0),
    "R40": ((57.0, 26.5), 0), "R41": ((63.0, 24.0), 0), "R42": ((63.0, 26.5), 0), "R44": ((57.0, 29.0), 0),
    "R45": ((63.0, 29.0), 0), "C34": ((69.0, 26.5), 90),
    "R34": ((74.0, 4.0), 0), "R35": ((74.0, 7.0), 0), "C33": ((66.5, 12.0), 0), "R32": ((49.8, 14.0), 90),
    "R33": ((49.8, 17.5), 90), "U14": ((54.0, 17.5), 0), "U15": ((61.0, 17.0), 0), "R36": ((68.0, 14.0), 0),
    "R37": ((68.0, 16.5), 0), "R38": ((68.0, 19.0), 0), "R43": ((68.0, 21.5), 0), "C32": ((54.0, 13.0), 0),
    "R44": ((68.4, 24.0), 0), "R45": ((68.4, 26.5), 0), "C34": ((53.5, 23.0), 0),
})
for ref, (pos, rot) in MOVES.items():
    PARTS[ref]["pos"], PARTS[ref]["rot"] = pos, rot

MOVES.update({
    "U8": ((24.0, 71.0), 270), "U9": ((34.0, 71.0), 270), "R10": ((21.5, 64.0), 90), "R11": ((24.0, 64.0), 90),
    "R12": ((31.5, 64.0), 90), "R13": ((34.0, 64.0), 90), "C23": ((19.0, 77.5), 0), "C24": ((29.0, 77.5), 0), })
for ref, (pos, rot) in MOVES.items():
    PARTS[ref]["pos"], PARTS[ref]["rot"] = pos, rot

MOVES.update({
    "C8": ((68.4, 66.5), 90), "D2": ((50.0, 62.5), 90), "D6": ((65.5, 72.0), 90), "R7": ((26.8, 30.5), 0),
    "R8": ((26.8, 37.5), 0), "C2": ((73.0, 44.0), 90), "C3": ((75.6, 44.0), 90), "C4": ((78.2, 44.0), 90),
    "D3B": ((63.5, 62.5), 180), "J1": ((9.5, 12.0), 270), "J2": ((9.5, 49.2), 270), "C30": ((41.3, 13.5), 90),
    "C31": ((50.5, 11.0), 90),
})
for ref, (pos, rot) in MOVES.items():
    PARTS[ref]["pos"], PARTS[ref]["rot"] = pos, rot

MOVES.update({"C30": ((40.8, 17.5), 90), "C31": ((50.2, 11.2), 0), "J1": ((9.5, 13.0), 270), "J2": ((9.5, 50.4), 270),
              "C8": ((76.2, 63.4), 0)})
for ref, (pos, rot) in MOVES.items():
    PARTS[ref]["pos"], PARTS[ref]["rot"] = pos, rot

MOVES.update({"J3": ((100.5, 3.0), 0), "J4": ((110.0, 74.0), 90), "RF1": ((93.5, 9.0), 90)})
# v0.4: J3 turned 180 so the wire entry faces off the board edge, and overhangs it slightly
MOVES.update({"J3": ((105.58, 9.5), 180)})  # body front ~1.5 mm past the top edge
for ref, (pos, rot) in MOVES.items():
    PARTS[ref]["pos"], PARTS[ref]["rot"] = pos, rot

MOVES.update({
    "RS1": ((115.0, 24.5), 90), "RS2": ((115.0, 29.5), 90), "RS3": ((115.0, 34.5), 90), "RS4": ((115.0, 39.5), 90),
    "RS5": ((115.0, 44.5), 90), "C41": ((117.6, 44.5), 90), "RF3": ((111.5, 18.0), 90), "RF4": ((116.5, 18.0), 90),
})
MOVES["J5"] = ((78.0, 95.13), 0)  # USB-C face ~0.85 mm past the bottom edge
for ref, (pos, rot) in MOVES.items():
    PARTS[ref]["pos"], PARTS[ref]["rot"] = pos, rot

# ================================================================== build
def mm(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(OX + x), pcbnew.FromMM(OY + y))


def build(path):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    ds = board.GetDesignSettings()
    ds.SetCopperLayerCount(4)
    ds.m_TrackMinWidth = pcbnew.FromMM(0.15)
    ds.m_ViasMinSize = pcbnew.FromMM(0.45)
    ds.m_MinClearance = pcbnew.FromMM(0.15)

    nets = {}

    def net(name):
        if name not in nets:
            n = pcbnew.NETINFO_ITEM(board, name)
            board.Add(n)
            nets[name] = n
        return nets[name]

    for ref, p in PARTS.items():
        lib, name = p["fp"]
        fp = pcbnew.FootprintLoad(FP + lib + ".pretty", name)
        if fp is None:
            raise SystemExit(f"missing footprint {lib}:{name}")
        fp.SetReference(ref)
        fp.SetValue(p["val"])
        fp.SetPosition(mm(*p["pos"]))
        board.Add(fp)
        fp.SetOrientationDegrees(p["rot"])
        for pad in fp.Pads():
            num = pad.GetNumber()
            if num in p["nets"] and not p["nets"][num].startswith("NC_"):
                pad.SetNet(net(p["nets"][num]))
        unknown = set(p["nets"]) - {pd.GetNumber() for pd in fp.Pads()}
        if unknown:
            raise SystemExit(f"{ref}: pads {unknown} not in footprint {name}")
        fp.Reference().SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.8), pcbnew.FromMM(0.8)))
        fp.Reference().SetTextThickness(pcbnew.FromMM(0.12))
        fp.Value().SetVisible(False)
        fp.SetLocalClearance(0)
        if ref in ("K2", "K3"):  # AQV216 pin 5 is not connected: drop the pad to keep HV spacing on the output side
            for pad in list(fp.Pads()):
                if pad.GetNumber() == "5":
                    fp.Remove(pad)
        for pad in fp.Pads():
            pad.SetLocalClearance(0)

    # outline + isolation slot
    def rect(x0, y0, x1, y1, layer=pcbnew.Edge_Cuts, width=0.1):
        s = pcbnew.PCB_SHAPE(board)
        s.SetShape(pcbnew.SHAPE_T_RECT)
        s.SetStart(mm(x0, y0)); s.SetEnd(mm(x1, y1))
        s.SetLayer(layer); s.SetWidth(pcbnew.FromMM(width))
        board.Add(s)
    rect(0, 0, W, H)
    for sx0, sy0, sx1, sy1 in SLOTS:
        rect(sx0, sy0, sx1, sy1)

    # ESP32 antenna: no copper on any layer under the antenna end of the module
    ko = pcbnew.ZONE(board)
    ko.SetIsRuleArea(True)
    ko.SetDoNotAllowCopperPour(True); ko.SetDoNotAllowTracks(True); ko.SetDoNotAllowVias(True)
    ls = pcbnew.LSET(); [ls.AddLayer(l) for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)]
    ko.SetLayerSet(ls)
    ol = ko.Outline(); ol.NewOutline()
    for x, y in ((20.0, 0.0), (40.0, 0.0), (40.0, 8.6), (20.0, 8.6)):
        ol.Append(mm(x, y))
    board.Add(ko)

    def silk(text, x, y, size=1.2, layer=pcbnew.F_SilkS):
        t = pcbnew.PCB_TEXT(board)
        t.SetText(text); t.SetPosition(mm(x, y)); t.SetLayer(layer)
        t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(size), pcbnew.FromMM(size)))
        t.SetTextThickness(pcbnew.FromMM(size * 0.15))
        board.Add(t)
    silk("HV <=150V DANGER", 104.0, 96.0, 1.5)
    silk("ZE2 LiB MCM SPOOF v0.4", 96.0, 91.5, 1.0)
    silk("ANALOG ISLAND", 66.0, 2.0, 1.0)
    rect(90.5, 1.0, 119.0, 97.0, layer=pcbnew.F_SilkS, width=0.25)

    board.Save(path)
    return board


if __name__ == "__main__":
    import json, sys
    build(sys.argv[1] if len(sys.argv) > 1 else "spoof_board.kicad_pcb")
    json.dump({k: {kk: (list(vv) if isinstance(vv, tuple) else vv) for kk, vv in v.items()} for k, v in PARTS.items()},
              open("parts.json", "w"), indent=1)
    print(len(PARTS), "parts")
