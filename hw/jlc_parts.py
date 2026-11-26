"""JLCPCB / LCSC part choice per BOM line, keyed by (value, footprint name) as written in parts.json.

Class: B = JLC Basic, P = Preferred (both: no loading fee), E = Extended (one fee per unique part, ~$3),
G = not stocked by JLC: order through JLC global sourcing or fit by hand. Prices are LCSC unit prices
(qty 1-10) from the jlcparts mirror on 2026-11-25; they move, so the BOM shows them as an estimate only.
Precision parts that stay Extended on purpose: the 0.1 % tap-ladder resistors (RD, matched block voltages to
the MCM). Everything else that has a Basic/Preferred equivalent uses it.
"""
ECON_EXT_FEE = 3.07   # USD per unique Extended SMT type, Economic assembly (Basic/Preferred free)
STD_FEEDER_FEE = 1.53  # USD per unique Basic or Extended SMT type, Standard assembly

# (value, footprint) -> (LCSC, MPN, class, unit USD)
PARTS = {
    # ------------------------------------------------------------------ passives
    ("100n", "C_0805_2012Metric"): ("C49678", "CC0805KRX7R9BB104 50V X7R", "B", 0.004),
    ("1u", "C_0805_2012Metric"): ("C28323", "CL21B105KBFNNNE 50V X7R", "B", 0.009),
    ("1n", "C_0805_2012Metric"): ("C46653", "CL21B102KBCNNNC 50V X7R", "B", 0.002),
    ("4.7n", "C_0805_2012Metric"): ("C1744", "0805B472K500NT 50V X7R", "B", 0.002),
    ("10n", "C_0805_2012Metric"): ("C1710", "CL21B103KBANNNC 50V X7R", "B", 0.002),
    ("22p", "C_0805_2012Metric"): ("C1804", "CL21C220JBANNNC 50V C0G", "B", 0.003),
    ("1n", "C_0603_1608Metric"): ("C1588", "CL10B102KB8NNNC 50V X7R", "B", 0.002),
    ("100n", "C_0603_1608Metric"): ("C14663", "CC0603KRX7R9BB104 50V X7R", "B", 0.002),
    ("1u", "C_0603_1608Metric"): ("C15849", "CL10A105KB8NNNC 50V X5R", "B", 0.004),
    ("10u 50V", "C_1206_3216Metric"): ("C13585", "CL31A106KBHNNNE 50V X5R", "B", 0.040),
    ("10u", "C_1206_3216Metric"): ("C13585", "CL31A106KBHNNNE 50V X5R", "B", 0.040),
    ("22u", "C_1206_3216Metric"): ("C12891", "CL31A226KAHNNNE 25V X5R", "B", 0.030),
    ("0", "R_0805_2012Metric"): ("C17477", "0805W8F0000T5E", "B", 0.002),
    ("56", "R_0805_2012Metric"): ("C17757", "0805W8F560JT5E 1%", "P", 0.002),
    ("100", "R_0805_2012Metric"): ("C17408", "0805W8F1000T5E 1%", "B", 0.002),
    ("120", "R_0805_2012Metric"): ("C17437", "0805W8F1200T5E 1%", "B", 0.002),
    ("270", "R_0805_2012Metric"): ("C17590", "0805W8F2700T5E 1%", "P", 0.002),
    ("470", "R_0805_2012Metric"): ("C17710", "0805W8F4700T5E 1%", "B", 0.002),
    ("1k", "R_0805_2012Metric"): ("C17513", "0805W8F1001T5E 1%", "B", 0.002),
    ("4.7k", "R_0805_2012Metric"): ("C17673", "0805W8F4701T5E 1%", "B", 0.002),
    ("5.1k", "R_0805_2012Metric"): ("C27834", "0805W8F5101T5E 1%", "B", 0.002),
    ("10k", "R_0805_2012Metric"): ("C17414", "0805W8F1002T5E 1%", "B", 0.002),
    ("22k", "R_0805_2012Metric"): ("C17560", "0805W8F2202T5E 1%", "B", 0.002),
    ("56k", "R_0805_2012Metric"): ("C17756", "0805W8F5602T5E 1%", "P", 0.002),
    ("100k", "R_0805_2012Metric"): ("C149504", "0805W8F1003T5E 1%", "B", 0.002),
    ("200k", "R_0805_2012Metric"): ("C17539", "0805W8F2003T5E 1%", "B", 0.002),
    ("0", "R_1206_3216Metric"): ("C17888", "1206W4F0000T5E", "B", 0.003),
    ("4.7k", "R_1206_3216Metric"): ("C17936", "1206W4F4701T5E 1%", "B", 0.003),
    ("100k", "R_1206_3216Metric"): ("C17900", "1206W4F1003T5E 1%", "B", 0.003),
    ("47k", "R_1206_3216Metric"): ("C2828891", "ARG06BTC4702 0.1% 25ppm", "E", 0.060),
    ("1k 1W fusible", "R_2512_6332Metric"): ("C54315", "25121WF1001T4E 1W 1%", "E", 0.034),
    ("22uH", "L_Bourns_SRP7028A_7.3x6.6mm"): ("C128694", "SMMS0630-220M 2.6A", "E", 0.085),
    ("40MHz", "Crystal_SMD_3225-4Pin_3.2x2.5mm"): ("C9010", "X322540MPB4SI 15pF", "E", 0.110),
    ("2A PTC", "Fuse_1812_4532Metric"): ("C960026", "BSMD1812-200-30V", "E", 0.110),
    ("5A", "Fuse_2920_7451Metric"): ("C19078763", "2920L500/30GR", "E", 0.161),
    # ------------------------------------------------------------------ discretes
    ("1N4148W", "D_SOD-123"): ("C81598", "1N4148W", "B", 0.012),
    ("B5819W", "D_SOD-123"): ("C64885", "B5819W", "P", 0.020),
    ("SS54", "D_SMA"): ("C22452", "SS54", "B", 0.045),
    ("SS36", "D_SMB"): ("C18199182", "SS36B", "P", 0.049),
    ("SMBJ33A", "D_SMB"): ("C19077586", "SMBJ33A", "P", 0.051),
    ("SMCJ33CA", "D_SMC"): ("C19077608", "SMCJ33CA", "P", 0.133),
    ("H24VNT2B", "SOT-23"): ("C20615827", "H24VNT2B", "P", 0.059),
    ("2N7002", "SOT-23"): ("C8545", "2N7002", "B", 0.018),
    ("NCE6020AK", "TO-252-2"): ("C108639", "NCE6020AK", "E", 0.156),
    ("RESET", "SW_SPST_TL3342"): ("C318884", "TS-1187A-B-A-B", "B", 0.021),
    ("BOOT", "SW_SPST_TL3342"): ("C318884", "TS-1187A-B-A-B", "B", 0.021),
    # ------------------------------------------------------------------ ICs and modules
    ("ESP32-S3-WROOM-1-N8R2", "ESP32-S3-WROOM-1"): ("C2913204", "ESP32-S3-WROOM-1-N8R2", "E", 4.599),
    ("MCP2518FD", "SOIC-14_3.9x8.7mm_P1.27mm"): ("C626758", "MCP2518FDT-E/SL", "E", 1.508),
    ("TJA1051T/3", "SOIC-8_3.9x4.9mm_P1.27mm"): ("C38695", "TJA1051T/3/1J", "E", 0.580),
    ("LMR16006Y-Q1", "SOT-23-6"): ("C544521", "LMR16006YQDDCRQ1", "E", 0.885),
    ("TLV75733PDBV", "SOT-23-5"): ("C485517", "TLV75733PDBVR", "E", 0.201),
    ("74LVC1G74", "VSSOP-8_2.3x2mm_P0.5mm"): ("C70285", "SN74LVC1G74DCUR", "E", 0.25),
    ("SN74LV1T34", "SOT-353_SC-70-5"): ("C78541", "SN74LV1T34DCKR", "E", 0.08),
    ("VND7050AJ", "ST_PowerSSO-16_3.9x4.9mm_P0.5mm_EP2.2x3.9mm"): ("C443997", "VND7050AJTR", "E", 1.659),
    ("ISO1540", "SOIC-8_3.9x4.9mm_P1.27mm"): ("C179739", "ISO1540DR", "E", 0.957),
    ("AMC3311", "SOIC-16W_7.5x10.3mm_P1.27mm"): ("C22441843", "AMC3311DWER (low JLC stock: check)", "E", 5.856),
    ("MCP4728", "MSOP-10_3x3mm_P0.5mm"): ("C478093", "MCP4728T-E/UN", "E", 2.637),
    ("MCP6004", "SOIC-14_3.9x8.7mm_P1.27mm"): ("C7378", "MCP6004T-I/SL", "E", 0.487),
    ("ADS1115", "MSOP-10_3x3mm_P0.5mm"): ("C37593", "ADS1115IDGSR", "E", 1.229),
    ("AQY212GS", "SOP-4_3.8x4.1mm_P2.54mm"): ("C719745", "AQY212GS", "E", 1.343),
    ("G6K-2F-Y 5VDC", "Relay_DPDT_Omron_G6K-2F-Y"): ("C47190", "G6K-2F-Y-TR DC5", "E", 1.049),
    ("USB-C", "USB_C_Receptacle_GCT_USB4105-xx-A_16P_TopMnt_Horizontal"): ("C3020560", "USB4105-GF-A", "E", 1.023),
    ("TPS3431-Q1", "VSON-8-1EP_3x3mm_P0.65mm_EP1.65x2.4mm"): ("", "TPS3431SDRBRQ1", "G", 1.50),
    ("AQV214EH", "SMDIP-6_W7.62mm"): ("", "AQV214EHAX", "G", 3.00),
    # ------------------------------------------------------------------ connectors (THT: JLC THT assembly or hand fit)
    ("J1 VEHICLE/MCM", "Molex_Micro-Fit_3.0_43045-2012_2x10_P3.00mm_Vertical"): ("C485575", "Molex 430452012", "E", 2.627),
    ("J2 CAPTUR LV", "Molex_Micro-Fit_3.0_43045-1612_2x08_P3.00mm_Vertical"): ("C491447", "Molex 430451612", "E", 1.179),
    ("J6 MCM ANALOG", "Molex_Micro-Fit_3.0_43045-0812_2x04_P3.00mm_Vertical"): ("C277661", "Molex 430450812", "E", 0.605),
    ("J4 TAPS", "Molex_Mini-Fit_Jr_5566-10A_2x05_P4.20mm_Vertical"): ("C504844", "Molex 39288100 (check peg holes)", "E", 0.516),
    ("J3 BUS", "PhoenixContact_MSTBA_2,5_2-G-5,08_1x02_P5.08mm_Horizontal"): ("C90074", "Phoenix 1757242", "E", 0.273),
}


def lookup(val, fpname):
    return PARTS.get((val, fpname))
