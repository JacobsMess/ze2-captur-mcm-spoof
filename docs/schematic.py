"""Human-readable schematic sheets for the Insight ZE2 lithium MCM spoof board.

Block-level schematics with key part values; explicit coordinates so labels never collide.
"""
import schemdraw
import schemdraw.elements as elm

schemdraw.use("matplotlib")
DPI = 160
SMALL = 9


def note(d, xy, text, size=SMALL, halign="left"):
    d += elm.Label().at(xy).label(text, fontsize=size, halign=halign, valign="top")


def ic(d, xy, w, h, label, left=(), right=(), top=(), bottom=(), lab_loc="top"):
    pins = [elm.IcPin(name=n, side="left") for n in left]
    pins += [elm.IcPin(name=n, side="right") for n in right]
    pins += [elm.IcPin(name=n, side="top") for n in top]
    pins += [elm.IcPin(name=n, side="bottom") for n in bottom]
    e = elm.Ic(pins=pins, size=(w, h), pinspacing=0.6, edgepadH=0.4, plblsize=9).theta(0).label(label, lab_loc, fontsize=10)
    d += e.at(xy)
    return e


def wire(d, a, b, shape="-|"):
    d += elm.Wire(shape).at(a).to(b)


def sheet1(path):
    with schemdraw.Drawing(show=False, fontsize=10) as d:
        d.config(unit=2.4)
        note(d, (0, 3.2), "Sheet 1 - Power input, MCU, CAN", 15)
        d += elm.Dot(open=True).at((0, 0)).label("J1 IG +12V", "left")
        d += elm.Fuse().right().label("F1 2A PTC")
        d += elm.Diode().right().label("Q1/U1 LM74700\nideal diode")
        d += (n1 := elm.Dot())
        d += elm.Line().right(1.2)
        d += (b1 := elm.Dot())
        d.push()
        d += elm.Zener().at(n1.center).down().reverse()
        d += elm.Ground()
        d.pop()
        note(d, (n1.center[0] + 0.3, -1.0), "D1 SMCJ33CA")
        buck = ic(d, (b1.center[0] + 1.0, -1.0), 2.6, 2.0, "U2 LMR16006Y-Q1\nbuck 5V (+D3B SS36)", left=("VIN",), right=("VOUT",), bottom=("GND",))
        wire(d, b1.center, buck.VIN)
        d += elm.Ground().at(buck.GND)
        d += elm.Line().at(buck.VOUT).right(1.5)
        d += (v5 := elm.Dot().label("+5V", "top"))
        ldo = ic(d, (v5.center[0] + 1.0, buck.VOUT[1] - 0.9), 2.4, 1.8, "U3 TLV75733\n3.3V LDO", left=("IN",), right=("OUT",), bottom=("GND",))
        wire(d, v5.center, ldo.IN)
        d += elm.Ground().at(ldo.GND)
        d += elm.Line().at(ldo.OUT).right(1.2)
        d += elm.Dot().label("+3V3", "top")

        mcu = ic(d, (10, -14), 6.5, 8.5, "U4 ESP32-S3-WROOM-1-N8R2\nWiFi: GVRET, web UI, OTA",
                 left=("SPI", "GPIO TWAI_RX", "GPIO TWAI_TX"),
                 right=("USB D+/D-", "IG_SENSE", "AMC1311 ADC", "OPTO_EN", "HS IN", "MCU_EN", "WDI", "I2C"))
        t1 = ic(d, (1.5, -8.6), 2.8, 2.2, "U5 TJA1051T/3\nCAN1 -> Captur BMS",
                left=("CANH", "CANL"), right=("TXD", "RXD"), bottom=("S",))
        wire(d, t1.TXD, mcu["GPIO TWAI_TX"], "-|")
        wire(d, t1.RXD, mcu["GPIO TWAI_RX"], "-|")
        d += elm.Line().at(t1.CANH).left(1.4).label("J2 CAN1_H", "left")
        d += elm.Line().at(t1.CANL).left(1.4).label("J2 CAN1_L", "left")
        d += elm.Line().at(t1.S).down(0.5)
        d += elm.Ground()
        note(d, (-2.6, -10.2), "H24VNT2B ESD, 2x56R split\ntermination via JP1")

        t2 = ic(d, (1.5, -15.5), 2.8, 2.2, "U7 TJA1051T/3\nCAN2 -> IMA CAN",
                left=("CANH", "CANL"), right=("TXD", "RXD"), bottom=("S",))
        mcp = ic(d, (5.6, -15.5), 2.4, 2.2, "U6 MCP2518FD\nlisten-only",
                 left=("TXCAN", "RXCAN"), right=("SPI",))
        wire(d, t2.TXD, mcp.TXCAN, "-")
        wire(d, t2.RXD, mcp.RXCAN, "-")
        wire(d, mcp.SPI, mcu.SPI, "-|")
        d += elm.Line().at(t2.CANH).left(1.4).label("J1 IMA_CANH", "left")
        d += elm.Line().at(t2.CANL).left(1.4).label("J1 IMA_CANL", "left")
        d += elm.Line().at(t2.S).down(0.6)
        d += elm.Dot().label("+3V3", "bottom")
        note(d, (-2.6, -18.6), "S tied HIGH = hardware SILENT mode: U7 cannot transmit.\nMCM-side termination is switched in only while split (sheet 5).")

        d += elm.Line().at(mcu["USB D+/D-"]).right(1).label("USB-C", "right")
        note(d, (18.8, -5.6),
             "GPIO map: IO4/5 TWAI (CAN1 EV bus), IO11/12/13 SPI,\n"
             "IO39 CS2 / IO38 INT2 (CAN2 MCM side), IO9 CS3 / IO3 INT3 (CAN3 car side),\n"
             "IO48 CS4 / IO14 INT4 (CAN4 dash), IO42 RELAY_SPLIT (sheet 5),\n"
             "IO15/16/17/21 HS IN, IO7 MCU_EN, IO6 WDI (sheet 2), IO47 PUMP_PWM,\n"
             "IO41 OPTO_EN, IO1/IO2 AMC1311 P/N (sheet 3), IO8/18 I2C -> ISO1540 (sheet 4),\n"
             "IO10 IG_SENSE (100k/22k), IO19/20 USB.")
        d.save(path, dpi=DPI, transparent=False)


def sheet2(path):
    with schemdraw.Drawing(show=False, fontsize=10) as d:
        d.config(unit=2.4)
        note(d, (0, 3.2), "Sheet 2 - Captur contactor drivers, watchdog, pump", 15)
        d += elm.Dot(open=True).at((0, 0)).label("J2 COIL_12V\n(own fused feed)", "left")
        d += elm.Fuse().right().label("F2 5A")
        d += elm.Line().right(0.6).label("VCOIL", "top")
        chans = [("PRE", "U8A"), ("MAIN+", "U8B"), ("MAIN-", "U9A"), ("BMS_PWR", "U9B")]
        xs = [6, 10.5, 15, 19.5]
        d += elm.Line().at((3.0, 0)).to((xs[-1], 0))
        rets = []
        for (n, ref), x in zip(chans, xs):
            d += elm.Dot().at((x, 0))
            hs = ic(d, (x - 1.2, -3.2), 2.4, 1.8, "", left=("IN",), top=("VCC",), bottom=("OUT",))
            wire(d, (x, 0), hs.VCC, "|-")
            note(d, (x + 1.4, -1.6), f"{ref}\nVND7050AJ", 8)
            d += elm.Line().at(hs.IN).left(0.8)
            d += elm.Label().label(f"HS_{n}", "left", fontsize=8)
            if n == "BMS_PWR":
                d += elm.Line().at(hs.OUT).down(1.0)
                d += elm.Dot(open=True).label("J2 BMS 12V out", "bottom")
            else:
                d += elm.Line().at(hs.OUT).down(0.6).label(f"J2 {n}", "right", fontsize=8)
                d += elm.Inductor2(loops=3).down(2.0).label(f"Captur\n{n} coil", "right", fontsize=8)
                d += (r := elm.Dot())
                rets.append(r.center)
        d += elm.Line().at(rets[0]).to(rets[-1])
        note(d, (rets[0][0], rets[0][1] - 0.3), "COIL_RTN (back via J2)", 8)
        d += elm.Line().at(rets[-1]).right(2.0)
        d += (rn := elm.Dot())
        d += elm.Zener().at(rn.center).right(2.2).reverse()
        d += elm.Ground()
        note(d, (rn.center[0] + 0.4, rn.center[1] + 1.0), "D2 SMBJ33A clamp", 8)
        d += elm.Line().at(rn.center).down(0.8)
        d += (q := elm.NFet(bulk=False).anchor("drain").down())
        d += elm.Ground().at(q.source)
        note(d, (q.drain[0] + 0.6, q.drain[1] - 0.2), "Q2 master\nlow-side FET", 8)
        g = ic(d, (q.gate[0] - 5.0, q.gate[1] - 1.6), 2.2, 1.8, "U10 74LVC1G08 AND", left=("A", "B"), right=("Y",), lab_loc="bottom")
        wire(d, g.Y, q.gate, "-|")
        d += elm.Line().at(g.B).left(1.4).label("MCU_EN", "left")
        wd = ic(d, (g.A[0] - 5.6, g.A[1] - 2.8), 2.4, 1.6, "U11 TPS3431\nwindow WDT", left=("WDI",), right=("WDO",), lab_loc="bottom")
        wire(d, wd.WDO, g.A, "-|")
        d += elm.Line().at(wd.WDI).left(1.2).label("WDI (MCU kick)", "left")

        note(d, (0, -14.5),
             "Every coil needs BOTH its high-side command AND the low-side master enable (MCU_EN AND WDT_OK).\n"
             "VND7050AJ: current limit, thermal shutdown, ~-40V internal clamp = fast-decay coil, fast contact opening.\n"
             "MultiSense / SEn / SEL tied to GND (diagnostics unused): contactor state is verified by the isolated bus-voltage sense (sheet 3). No plain flyback diodes on coils.")

        d += elm.Dot(open=True).at((0, -18.5)).label("VCOIL", "left")
        d += elm.Line().right(2)
        d += (p1 := elm.Dot())
        d += elm.Line().right(2).label("J2 PUMP+", "right")
        d += elm.Diode().at(p1.center).down(2.2).reverse().label("D3 SS54", "left")
        d += (p2 := elm.Dot())
        d += elm.Line().right(2).label("J2 PUMP-", "right")
        d += (qp := elm.NFet(bulk=False).at(p2.center).anchor("drain").down().reverse())
        d += elm.Ground().at(qp.source)
        d += elm.Line().at(qp.gate).left(1.0).label("PUMP_PWM", "left")
        note(d, (p2.center[0] + 0.6, p2.center[1] - 0.7), "Q3 60V logic FET", 8)
        note(d, (11, -18.5),
             "Option B (DNP): K1 12V relay, NO contact in series with MCM IG1\n"
             "(J1 IG1_IN -> IG1_OUT). Closed by firmware only after pack is up.")
        d.save(path, dpi=DPI, transparent=False)


def sheet3(path):
    with schemdraw.Drawing(show=False, fontsize=10) as d:
        d.config(unit=1.6)
        note(d, (-6, 3.0), "Sheet 3 - HV tap divider and isolated bus sense   (HV DOMAIN, interim MCM build only, <=150 V: 5.6 mm isolation band, short slots under the isolators)", 15)
        d += elm.Dot(open=True).at((0, 0)).label("J3 BUS+", "left")
        d += elm.ResistorIEC().down(1.6)
        note(d, (-5.6, -0.4), "RF1 1k 1W fusible", 8)
        d += elm.Switch().down(1.6)
        note(d, (-5.6, -2.0), "K2 AQV214EH 400V (OPTO_EN)", 8)
        d += elm.Line().down(0.4)
        d += elm.Dot()
        taps = list(range(8, -1, -1))
        for i, n in enumerate(taps):
            d.push()
            d += elm.Line().right(2.0)
            d += elm.ResistorIEC().right(1.6)
            d += elm.Dot(open=True).label(f"J4 VHB{n}", "right")
            d.pop()
            if i < len(taps) - 1:
                d += elm.Resistor().down(1.1)
                d += elm.Resistor().down(1.1)
                d += elm.Dot()
        d += elm.Line().down(0.4)
        y_sw = -4.0 - 8 * 2.2 - 0.4
        d += elm.Switch().down(1.6)
        note(d, (-5.6, y_sw - 0.2), "K3 AQV214EH 400V (OPTO_EN)", 8)
        d += elm.ResistorIEC().down(1.6)
        note(d, (-5.6, y_sw - 1.8), "RF2 1k 1W fusible", 8)
        d += elm.Dot(open=True).label("J3 BUS-", "left")
        note(d, (-5.6, -6.0), "Each segment = 2x 47k\n1206 0.1% in series\n(single short only\nhalves one segment)\n\n0R in each tap output\n(option: series R)\n\nRtrim footprint between\nBUS+ and VHB8: 0R default,\nfit to scale taps if needed", 8)

        d += elm.Dot(open=True).at((12, 0)).label("BUS+", "left")
        d += elm.Resistor().down(2.0)
        note(d, (12.4, -0.4), "4x 100k", 8)
        d += (m := elm.Dot())
        d += elm.Resistor().down(2.0)
        note(d, (12.4, -2.6), "4.7k", 8)
        d += elm.Dot(open=True).label("BUS-", "left")
        amc = ic(d, (14.0, -3.0), 4.4, 2.0, "", left=("VIN",), right=("VOUT",), top=("VDD1", "VDD2"))
        note(d, (14.0, -3.4), "U12 AMC1311\nreinforced isolated amp", 9)
        wire(d, m.center, amc.VIN, "-|")
        d += elm.Line().at(amc.VOUT).right(1.2).label("to MCU ADC (LV)", "right", fontsize=8)
        d += elm.Line().at(amc.VDD1).up(1.4)
        note(d, (13.0, amc.VDD1[1] + 2.4), "R1SX-0505 iso 5V\n(HV side)", 8)
        d += elm.Line().at(amc.VDD2).up(1.4)
        note(d, (amc.VDD2[0] + 0.2, amc.VDD2[1] + 2.4), "+5V (LV side)", 8)
        note(d, (12, -8.5),
             "Bus 0-172V -> 0-2.0V (1% parts, ratio trimmed in firmware). Uses: precharge complete (>=95% of BMS sum),\n"
             "weld check (<20V 500ms after open), BMS sum cross-check (5%).\n\n"
             "8 segments fitted (9 taps). 7-segment car: link VHB8 to VHB7, J4 pin 9 unused.\n"
             "Opto LEDs from 3V3 via 330R, switched by OPTO_EN: MCU dead = divider floats\n"
             "= MCM sees no pack = safe IMA-off state.\n"
             "Divider load ~0.17 mA at 130V; zero drain with IG off.\nHV netclass 0.6 mm (IPC-2221 B2, uncoated, 101-150V). Not fitted in the ZombieVerter build.")
        d.save(path, dpi=DPI, transparent=False)


def sheet4(path):
    with schemdraw.Drawing(show=False, fontsize=10) as d:
        d.config(unit=2.0)
        note(d, (-3, 3.4), "Sheet 4 - Analog island   (supply + reference = MCM sensor 5V / SG; isolated from board)", 15)
        iso = ic(d, (0, 0), 2.6, 1.4, "U13 ISO1540", left=("I2C1",), right=("I2C2",))
        d += elm.Line().at(iso.I2C1).left(1.2).label("MCU I2C", "left")
        dac = ic(d, (5.0, -4.6), 2.8, 4.0, "U14 MCP4728\nquad 12-bit DAC", left=("I2C",),
                 right=("VD", "VC", "VB", "VA"), top=("VDD=VREF",))
        wire(d, iso.I2C2, dac.I2C, "-|")
        d += elm.Line().at(dac["VDD=VREF"]).up(0.8)
        d += elm.Label().label("MCM 5V (JP2: or iso 5V)", "top", fontsize=8)
        adc = ic(d, (0.2, -4.6), 2.6, 2.2, "U16/U17\n2x ADS1115\nreadback", right=("I2C",), lab_loc="bottom")
        d += elm.Line().at(adc.I2C).to((dac.I2C[0], adc.I2C[1]))
        d += elm.Line().to((dac.I2C[0], dac.I2C[1]))
        d += elm.Dot()

        names = {"VA": "TBATT1", "VB": "TBATT2", "VC": "TBATT3"}
        for k, pin in enumerate(("VA", "VB", "VC")):
            y = 1.0 - k * 2.6
            buf = ic(d, (11.0, y - 0.6), 2.2, 1.2, f"U15{'ABC'[k]} buffer", left=("in",), right=("out",), lab_loc="top")
            xk = 8.6 + 0.7 * k
            d += elm.Line().at(dac[pin]).to((xk, dac[pin][1]))
            d += elm.Line().to((xk, buf["in"][1]))
            d += elm.Line().to(buf["in"])
            d += elm.ResistorIEC().at(buf.out).right(1.8)
            d += elm.Dot(open=True).label(f"J6 {names[pin]} -> MCM", "right")
            note(d, (buf.out[0] + 0.4, buf.out[1] + 0.7), "1k", 8)

        # current summer
        y0 = -11.0
        d += elm.Dot(open=True).at((1.0, y0)).label("J6 ISOC_IN (Hall)", "left")
        d += elm.Resistor().right(3.0)
        note(d, (2.3, y0 + 0.8), "Ra 10k", 8)
        d += (nd := elm.Dot())
        d += elm.Line().at(dac.VD).right(1.0)
        d += elm.Dot(open=True).label("VDAC_I", "right", fontsize=9)
        d += elm.Dot(open=True).at((nd.center[0], y0 + 3.4)).label("VDAC_I", "top", fontsize=9)
        d += elm.Resistor().down(3.4)
        note(d, (nd.center[0] - 2.0, y0 + 2.0), "Rb 200k", 8)
        op = elm.Opamp(leads=True).theta(0).anchor("in2").at((nd.center[0] + 2.5, nd.center[1]))
        d += elm.Line().at(nd.center).to(op.in2)
        d += op
        note(d, (op.center[0] - 0.4, op.center[1] - 1.4), "U15D", 8)
        d += elm.Line().at(op.in1).left(0.8)
        d += (fb := elm.Dot())
        d += elm.Line().up(1.2)
        d += (f2 := elm.Dot())
        d += elm.Resistor().up(2.0)
        d += elm.Dot(open=True).label("Vmid 2.5V (10k/10k from MCM 5V)", "top", fontsize=8)
        note(d, (f2.center[0] + 0.4, f2.center[1] + 1.4), "Rg 200k", 8)
        rx = op.out[0] + 0.8
        d += elm.Line().at(f2.center).right(0.6)
        d += elm.Resistor().to((rx - 0.6, f2.center[1]))
        note(d, ((f2.center[0] + rx) / 2, f2.center[1] + 0.9), "Rf 10k", 8)
        d += elm.Line().to((rx, f2.center[1]))
        d += elm.Line().to((rx, op.out[1]))
        d += elm.Dot()
        d += elm.Line().at(op.out).right(2.0)
        d += elm.Dot(open=True).label("J6 ISOC_OUT -> MCM", "right")

        note(d, (-3, -16.0),
             "Vout = Vhall + 0.05 x (Vdac - Vmid)  ->  +/-125 mV trim on the real sensor, full Hall bandwidth (pure analog path).\n"
             "U15 = MCP6004 rail-to-rail quad, VDD = MCM 5V. ADS1115s read back TBATT1-3, ISOC_IN, ISOC_OUT and MCM 5V.\n"
             "NTC lines: buffer drives through 1k into the MCM pull-up; firmware closes the loop on readback, so the pull-up value is calibrated out.\n"
             "Island ground = MCM sensor GND only (single point, J6). Island current < 15 mA. J6 = Micro-Fit 2x4 MCM analog connector.")
        d.save(path, dpi=DPI, transparent=False)


def sheet5(path):
    with schemdraw.Drawing(show=False, fontsize=10) as d:
        d.config(unit=2.4)
        note(d, (0, 3.2), "Sheet 5 - CAN3 (IMA car side), CAN4 (dash), fail-safe MITM bypass relay", 15)
        for k, (n, mcp, xc, canh, canl, cs, intr) in enumerate((("3", "U18", "U19", "IMA_CANH", "IMA_CANL", "SPI_CS3", "CAN3_INT"),
                                                                 ("4", "U20", "U21", "DASH_CANH", "DASH_CANL", "SPI_CS4", "CAN4_INT"))):
            y = -k * 7.0
            m = ic(d, (5, y - 2.5), 4.2, 2.6, f"{mcp} MCP2518FD + 40 MHz", left=("SPI", "CS/INT"), right=("TXCAN", "RXCAN"))
            d += elm.Line().at(m.SPI).left(1.2).label("SPI bus", "left")
            d += elm.Line().at(m["CS/INT"]).left(1.2).label(f"{cs} / {intr}", "left")
            t = ic(d, (11.5, y - 2.5), 2.8, 2.6, f"{xc} TJA1051T/3", left=("TXD", "RXD"), right=("CANH", "CANL"), bottom=("S",))
            wire(d, m.TXCAN, t.TXD, "-"); wire(d, m.RXCAN, t.RXD, "-")
            d += elm.Line().at(t.CANH).right(2.0).label(canh, "right")
            d += elm.Line().at(t.CANL).right(2.0).label(canl, "right")
            d += elm.Line().at(t.S).down(0.6)
            d += elm.Dot().label(f"CAN{n}_S: 10k to 3V3 (silent), JP to GND = TX", "bottom", fontsize=8)
        note(d, (19.5, 0.8), "Per port: H24VNT2B ESD.\nCAN4 (dash tap): 2x56R + 4.7n split termination via JP14,\ndefault open; close only if the board replaces a bus-end node.\nCAN3: no fixed termination - switched by K4 below.")
        k4 = ic(d, (6, -16.5), 6.5, 3.6, "K4 Omron G6K-2F-Y 5V (DPDT)", left=("COM1", "COM2", "COIL+"), right=("NC1", "NC2", "NO1", "NO2", "COIL-"), lab_loc="bottom")
        d += elm.Line().at(k4.COM1).left(1.5).label("IMA_CANH (car / PCM side)", "left")
        d += elm.Line().at(k4.COM2).left(1.5).label("IMA_CANL", "left")
        d += elm.Line().at(k4.NC1).right(1.5).label("MCM_CANH (CAN2 / U7)", "right")
        d += elm.Line().at(k4.NC2).right(1.5).label("MCM_CANL", "right")
        d += elm.Line().at(k4.NO1).right(1.5).label("R86 120R -> JP13 -> NO2  (PCM-side term)", "right")
        d += elm.Line().at(k4.NO2).right(1.5).label("NO2", "right")
        d += elm.Line().at(k4["COIL+"]).left(1.5).label("+5V", "left")
        d += elm.Line().at(k4["COIL-"]).right(1.5).label("Q4 drain", "right")
        note(d, (13.5, -12.2), "Q4 2N7002: gate = RELAY_SPLIT via 100R, 100k pull-down\nD11 1N4148W flyback across coil")
        u22 = ic(d, (6, -24.5), 6.5, 1.8, "U22 AQY212GS photoMOS (60 V, form A)", left=("LED A", "LED K"), right=("OUT1", "OUT2"), lab_loc="bottom")
        d += elm.Line().at(u22["LED A"]).left(1.5).label("+5V via R97 470R", "left")
        d += elm.Line().at(u22["LED K"]).left(1.5).label("Q4 drain (parallel with coil)", "left")
        d += elm.Line().at(u22.OUT1).right(1.5).label("MCM_CANL", "right")
        d += elm.Line().at(u22.OUT2).right(1.5).label("JP12 -> R96 120R -> MCM_CANH  (MCM-side term)", "right")
        note(d, (0, -29.0),
             "De-energised (board off, reset, crashed) = NC contacts join MCM side to car side: the IMA bus is stock,\n"
             "and both board terminations are disconnected (NO contact open, photoMOS off), so the stock bus sees no extra load.\n"
             "Energised = split: each half gets a 120R at the board end if its jumper is closed (JP13 PCM side, JP12 MCM side).\n"
             "Close a jumper only if that half measures ~120R instead of ~60R with the bus split (see write-up).\n"
             "Firmware energises K4 only when it is ready to man-in-the-middle; CAN2 and CAN3 then carry the two halves.\n"
             "CAN1 (TWAI) = EV bus: ZombieVerter, inverter logic board, Captur BMS (J1 6/7 and J2 6/7, same net).")
        d.save(path, dpi=DPI, transparent=False)


if __name__ == "__main__":
    import pathlib
    img = pathlib.Path(__file__).resolve().parent / "img"
    sheet5(str(img / "sheet5_can_mitm.png"))
    sheet1(str(img / "sheet1_power_mcu_can.png"))
    sheet2(str(img / "sheet2_drivers.png"))
    sheet3(str(img / "sheet3_hv_divider.png"))
    sheet4(str(img / "sheet4_analog_island.png"))
    print("ok")
