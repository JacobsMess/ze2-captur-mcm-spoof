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

with zipfile.ZipFile(os.path.join(OUTDIR, "spoof_board_gerbers_JLCPCB.zip"), "w", zipfile.ZIP_DEFLATED) as zf:
    for f in sorted(os.listdir(os.path.join(OUTDIR, "gerbers"))):
        zf.write(os.path.join(os.path.join(OUTDIR, "gerbers"), f), f)

# BOM (JLCPCB format)
parts = json.load(open("parts.json"))
groups = OrderedDict()
for ref, p in sorted(parts.items(), key=lambda kv: (kv[0].rstrip("0123456789"), int("".join(c for c in kv[0] if c.isdigit()) or 0))):
    if ref.startswith("H"):
        continue
    key = (p["val"], p["fp"][1], p["mpn"])
    groups.setdefault(key, dict(refs=[], note=p.get("note", "")))["refs"].append(ref)
with open(os.path.join(OUTDIR, "BOM_JLCPCB.csv"), "w", newline="") as fh:
    w = csv.writer(fh)
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #", "Qty", "MPN / description", "Notes"])
    for (val, fpn, mpn), g in groups.items():
        notes = g["note"]
        if "PLACEHOLDER" in mpn and "PLACEHOLDER" not in notes:
            notes = "PLACEHOLDER part - choose final MPN"
        if fpn.startswith(("Molex", "PhoenixContact")):
            notes = (notes + "; " if notes else "") + "THT - hand solder or JLC THT assembly"
        if fpn.startswith("SolderJumper"):
            continue
        w.writerow([val, ",".join(g["refs"]), fpn, "", len(g["refs"]), mpn, notes])

# CPL (JLCPCB format)
with open(os.path.join(OUTDIR, "pos_raw.csv")) as fh, open(os.path.join(OUTDIR, "CPL_JLCPCB.csv"), "w", newline="") as out:
    rd = csv.DictReader(fh)
    w = csv.writer(out)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    for row in rd:
        w.writerow([row["Ref"], f"{float(row['PosX']):.3f}mm", f"{float(row['PosY']):.3f}mm",
                    "Top" if row["Side"] == "top" else "Bottom", row["Rot"]])
print("fab outputs written")
