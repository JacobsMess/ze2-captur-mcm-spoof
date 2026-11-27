"""Write the .kicad_pro with net classes (KiCad 7 format) and the .kicad_dru custom rules."""
import json, sys

def cls(name, clr, w, vd=0.6, vdr=0.3):
    return {"name": name, "clearance": clr, "track_width": w, "via_diameter": vd, "via_drill": vdr,
            "microvia_diameter": 0.3, "microvia_drill": 0.1, "diff_pair_gap": 0.25, "diff_pair_width": 0.2,
            "diff_pair_via_gap": 0.25, "bus_width": 12, "line_style": 0, "pcb_color": "rgba(0, 0, 0, 0.000)",
            "schematic_color": "rgba(0, 0, 0, 0.000)", "wire_width": 6}

PATTERNS = {
    "Power": ["VBAT_P", "VIG_*", "VCOIL*", "COIL_*", "BMS12V", "PUMP_N", "BUCK_SW", "+5V", "LM_GATE"],
    "HV": ["BUS_P*", "DIV*", "TAP*", "VHB*", "SNS*", "K2_P5", "K3_P5"],
    "HVLOW": ["BUS_N*", "SENSE_MID", "HV5V*"],
}
pro = {
    "board": {"design_settings": {"rules": {"min_clearance": 0.12, "min_track_width": 0.12, "min_via_diameter": 0.45,
                                            "min_through_hole_diameter": 0.2, "min_copper_edge_clearance": 0.3}}},
    "meta": {"filename": sys.argv[1] + ".kicad_pro", "version": 1},
    "net_settings": {
        "classes": [cls("Default", 0.15, 0.15), cls("Power", 0.2, 0.5, 0.8, 0.4), cls("HV", 0.6, 0.25, 0.6, 0.3), cls("HVLOW", 0.2, 0.2, 0.6, 0.3)],
        "meta": {"version": 3},
        "netclass_patterns": [{"netclass": k, "pattern": p} for k, ps in PATTERNS.items() for p in ps],
    },
}
json.dump(pro, open(sys.argv[1] + ".kicad_pro", "w"), indent=2)

# Every HV-class net (bus positive, tap ladder and taps, sense chain, both sides of each zero-ohm link and fuse)
# against everything tied to the bus-negative side (the AMC3311's HV supply and input, the divider bottom):
# 0.7 mm, i.e. IPC-2221 B2's 0.6 mm for 101-150 V uncoated plus 0.1 mm for etch tolerance. Between two HV nets the
# class clearance (0.6 mm) applies; adjacent taps differ by ~18 V, the ladder ends by the full bus.
DRU = """(version 1)
(rule "HV to bus-negative side"
  (condition "A.NetClass == 'HV' && B.NetClass == 'HVLOW'")
  (constraint clearance (min 0.7mm)))
"""
open(sys.argv[1] + ".kicad_dru", "w").write(DRU)
