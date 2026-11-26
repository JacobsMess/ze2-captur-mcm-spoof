"""v0.7 finishing pass on the routed board (after eco_v06_review.py and cleanup.py):
- nudge the DIV_TOP via that sits 0.68 mm from the AMC3311's HV-side capacitor (the custom rule asks 0.7 mm);
- widen the coil and pump current paths as far as the copper around them allows: 1.0 mm, else 0.75 mm, else
  left at 0.5 mm. Each step is checked with KiCad's own DRC (zones filled), and only the offending segments
  step back.

usage (from hw/): python3 eco_v07_finish.py routed.kicad_pcb out.kicad_pcb   (.kicad_pro/.kicad_dru beside it)
"""
import re
import shutil
import sys

import pcbnew

SRC, DST = sys.argv[1], sys.argv[2]
NETS = {"VCOIL", "VCOIL_RAW", "COIL_RTN", "COIL_MAINN", "COIL_MAINP", "COIL_PRE", "BMS12V", "PUMP_N"}
STEPS = (1.0, 0.75)
OX = OY = 50.0
mm = pcbnew.ToMM

for ext in (".kicad_pro", ".kicad_dru"):
    shutil.copy(SRC.rsplit(".", 1)[0] + ext, DST.rsplit(".", 1)[0] + ext)
b = pcbnew.LoadBoard(SRC)


def at(p, x, y, tol=0.01):
    return abs(mm(p.x) - OX - x) < tol and abs(mm(p.y) - OY - y) < tol


# 1. DIV_TOP via at (96.55, 18.55): 0.1 mm further from C44
for t in list(b.GetTracks()):
    if t.GetNetname() != "DIV_TOP":
        continue
    d = pcbnew.VECTOR2I(pcbnew.FromMM(0.1), 0)
    if t.Type() == pcbnew.PCB_VIA_T and at(t.GetPosition(), 96.55, 18.55):
        t.SetPosition(t.GetPosition() + d)
    elif t.Type() != pcbnew.PCB_VIA_T:
        if at(t.GetStart(), 96.55, 18.55):
            t.SetStart(t.GetStart() + d)
        if at(t.GetEnd(), 96.55, 18.55):
            t.SetEnd(t.GetEnd() + d)


def violations():
    """Tracks of NETS that DRC names in any copper rule violation."""
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    pcbnew.WriteDRCReport(b, "/tmp/eco_v07_drc.txt", pcbnew.EDA_UNITS_MILLIMETRES, True)
    txt = open("/tmp/eco_v07_drc.txt").read()
    bad = set()
    for blk in re.split(r"\n(?=\[)", txt):
        if not blk.startswith(("[clearance", "[shorting", "[tracks_crossing", "[hole_clearance", "[copper_edge",
                               "[solder_mask_bridge", "[unconnected")):
            continue
        for x, y, net, layer, length in re.findall(
                r"@\(([\d.]+) mm, ([\d.]+) mm\): Track \[([^\]]+)\] on (\S+), length ([\d.]+) mm", blk):
            if net in NETS:
                bad.add((float(x), float(y), net, layer, float(length)))
    hits = []
    for t in b.GetTracks():
        if t.Type() == pcbnew.PCB_VIA_T or t.GetNetname() not in NETS:
            continue
        for x, y, net, layer, length in bad:
            if (t.GetNetname() == net and b.GetLayerName(t.GetLayer()) == layer and abs(mm(t.GetLength()) - length) < 0.002
                    and any(abs(mm(p.x) - x) < 0.002 and abs(mm(p.y) - y) < 0.002 for p in (t.GetStart(), t.GetEnd()))):
                hits.append(t)
    return hits


base = violations()
assert not base, f"board not clean before widening: {len(base)} offending segments"
segs = [t for t in b.GetTracks() if t.Type() != pcbnew.PCB_VIA_T and t.GetNetname() in NETS]
orig = {t.m_Uuid.AsString(): t.GetWidth() for t in segs}
for t in segs:
    t.SetWidth(pcbnew.FromMM(STEPS[0]))
for _ in range(12):   # each pass steps every offender down one width; repeat until DRC is clean
    bad = violations()
    if not bad:
        break
    for t in bad:
        lower = [w for w in STEPS if pcbnew.FromMM(w) < t.GetWidth()]
        t.SetWidth(pcbnew.FromMM(lower[0]) if lower else orig[t.m_Uuid.AsString()])
assert not violations(), "widening left violations"

tot = {}
for t in segs:
    w = round(mm(t.GetWidth()), 2)
    tot[w] = tot.get(w, 0) + mm(t.GetLength())
print("coil/pump copper by width (mm: length mm):", {k: round(v, 1) for k, v in sorted(tot.items())})
b.Save(DST)
