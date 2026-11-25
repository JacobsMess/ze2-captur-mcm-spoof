"""Add planes, fill zones, run DRC and write JLCPCB fab outputs (gerbers, drill, BOM, CPL).

usage (from hw/): python3 fab.py tidy.kicad_pcb ze2-mcm-spoof.kicad_pcb [out/jlc]
"""
import csv
import json
import os
import subprocess
import sys
import zipfile
from collections import OrderedDict

import pcbnew

SRC, OUT = sys.argv[1], sys.argv[2]
OUTDIR = sys.argv[3] if len(sys.argv) > 3 else "out/jlc"  # gerbers, drill, BOM, CPL, DRC report
OX, OY = 50.0, 50.0
b = pcbnew.LoadBoard(SRC)
nets = b.GetNetsByName()


def zone(net, layer, pts, prio=0, clearance=0.3, min_w=0.25):
    z = pcbnew.ZONE(b)
    z.SetLayer(layer)
    z.SetNet(nets[net])
    z.SetAssignedPriority(prio)
    z.SetLocalClearance(pcbnew.FromMM(clearance))
    z.SetMinThickness(pcbnew.FromMM(min_w))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetThermalReliefGap(pcbnew.FromMM(0.3))
    z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.35))
    ol = z.Outline(); ol.NewOutline()
    for x, y in pts:
        ol.Append(pcbnew.VECTOR2I(pcbnew.FromMM(OX + x), pcbnew.FromMM(OY + y)))
    b.Add(z)
    return z


LV = [(0.3, 0.3), (85.2, 0.3), (85.2, 97.7), (0.3, 97.7)]
ISLAND = [(45.5, 0.5), (80.6, 0.5), (80.6, 30.8), (70.5, 30.8), (70.5, 28.0), (51.5, 28.0), (51.5, 19.5), (45.5, 19.5)]
zone("GND", pcbnew.In1_Cu, LV, prio=0)
zone("ISLGND", pcbnew.In1_Cu, ISLAND, prio=1)
zone("GND", pcbnew.B_Cu, LV, prio=0)
zone("ISLGND", pcbnew.B_Cu, ISLAND, prio=1)
# HV return plane on In1 under the divider strip (keeps HV copper referenced, away from LV)

filler = pcbnew.ZONE_FILLER(b)
filler.Fill(b.Zones())
b.Save(OUT)

# DRC
os.makedirs(os.path.join(OUTDIR, "gerbers"), exist_ok=True)
try:
    pcbnew.WriteDRCReport(b, os.path.join(OUTDIR, "drc_report.txt"), pcbnew.EDA_UNITS_MILLIMETRES, True)
except Exception as e:  # noqa: BLE001
    open(os.path.join(OUTDIR, "drc_report.txt"), "w").write(f"DRC not available from python: {e}\n")

# Gerbers + drill + positions via kicad-cli
layers = "F.Cu,In1.Cu,In2.Cu,B.Cu,F.Paste,B.Paste,F.SilkS,B.SilkS,F.Mask,B.Mask,Edge.Cuts"
r = subprocess.run(["kicad-cli", "pcb", "export", "gerbers", "--layers", layers, "--subtract-soldermask",
                    "--no-x2", "-o", os.path.join(OUTDIR, "gerbers/"), OUT], capture_output=True, text=True)
print(r.stdout[-500:], r.stderr[-500:])
r.check_returncode()
subprocess.run(["kicad-cli", "pcb", "export", "drill", "--format", "excellon", "--excellon-separate-th",
                "--generate-map", "--map-format", "gerberx2", "-o", os.path.join(OUTDIR, "gerbers/"), OUT], check=True)
subprocess.run(["kicad-cli", "pcb", "export", "pos", "--format", "csv", "--units", "mm", "--side", "both",
                "--smd-only", "-o", os.path.join(OUTDIR, "pos_raw.csv"), OUT], check=True)

with zipfile.ZipFile(os.path.join(OUTDIR, "gerbers.zip"), "w", zipfile.ZIP_DEFLATED) as zf:
    for f in sorted(os.listdir(os.path.join(OUTDIR, "gerbers"))):
        zf.write(os.path.join(os.path.join(OUTDIR, "gerbers"), f), f)

# BOM (JLCPCB columns first; LCSC numbers and classes from jlc_parts.py)
import jlc_parts  # noqa: E402

parts = json.load(open("parts.json"))
groups = OrderedDict()
for ref, p in sorted(parts.items(), key=lambda kv: (kv[0].rstrip("0123456789"), int("".join(c for c in kv[0] if c.isdigit()) or 0))):
    if ref.startswith(("H", "JP")):
        continue
    key = (p["val"], p["fp"][1])
    if jlc_parts.lookup(*key) is None:
        raise SystemExit(f"{ref}: no jlc_parts.py entry for {key}")
    groups.setdefault(key, dict(refs=[], notes=set()))["refs"].append(ref)
    if p.get("note"):
        groups[key]["notes"].add(p["note"])
cost = dict(parts=0.0, ext=set(), ext_tht=set(), glob=[], cls={})
with open(os.path.join(OUTDIR, "bom.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "Qty", "Class", "MPN", "Unit USD", "Notes"])
    for (val, fpn), g in groups.items():
        lcsc, mpn, cls, usd = jlc_parts.lookup(val, fpn)
        tht = fpn.startswith(("Molex", "PhoenixContact"))
        notes = sorted(g["notes"]) + (["THT"] if tht else [])
        if cls == "G":
            notes.append("not stocked at JLC: global sourcing or hand fit")
            cost["glob"].append(f"{mpn} (~${usd * len(g['refs']):.0f})")
        if cls == "E":
            (cost["ext_tht"] if tht else cost["ext"]).add(lcsc)
        cost["parts"] += usd * len(g["refs"])
        cost["cls"][cls] = cost["cls"].get(cls, 0) + 1
        w.writerow([val, ",".join(g["refs"]), fpn, lcsc, len(g["refs"]), cls, mpn, f"{usd:.3f}", "; ".join(notes)])
fee = jlc_parts.EXT_FEE
with open(os.path.join(OUTDIR, "cost.md"), "w") as fh:
    fh.write("# One-board cost estimate (JLC assembly)\n\n"
             "LCSC unit prices from `hw/jlc_parts.py`; fees are JLC's standard-assembly figures. PCB fabrication and\n"
             "shipping are not included.\n\n"
             "| Item | USD |\n|---|---|\n"
             f"| Parts, one board (all lines) | {cost['parts']:.2f} |\n"
             f"| Extended-part fees, {len(cost['ext'])} SMT types x ${fee:.0f} | {len(cost['ext']) * fee:.0f} |\n"
             f"| Extended-part fees, {len(cost['ext_tht'])} THT connectors (skip: fit them by hand) | {len(cost['ext_tht']) * fee:.0f} |\n\n"
             f"BOM lines by class: " + ", ".join(f"{k} {v}" for k, v in sorted(cost['cls'].items())) +
             " (B basic, P preferred, E extended, G not at JLC)\n\n"
             f"Not stocked at JLC: {', '.join(cost['glob'])}. JLC global sourcing can buy them, or fit by hand.\n")
print(open(os.path.join(OUTDIR, "cost.md")).read())

# CPL (JLCPCB format)
with open(os.path.join(OUTDIR, "pos_raw.csv")) as fh, open(os.path.join(OUTDIR, "cpl.csv"), "w", newline="") as out:
    rd = csv.DictReader(fh)
    w = csv.writer(out)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for row in rd:
        w.writerow([row["Ref"], f"{float(row['PosX']):.3f}mm", f"{float(row['PosY']):.3f}mm",
                    "Top" if row["Side"] == "top" else "Bottom", row["Rot"]])
os.remove(os.path.join(OUTDIR, "pos_raw.csv"))
print("fab outputs written")
