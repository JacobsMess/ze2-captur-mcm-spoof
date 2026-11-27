"""Route the placed board with KiCadRoutingTools (github.com/drandyhaas/KiCadRoutingTools).

usage (from hw/): KRT_DIR=<KiCadRoutingTools checkout, router built> python3 krt_route.py unrouted.kicad_pcb routed.kicad_pcb

1. adds the planes fab.py pours (GND / ISLGND on In1 and B) so the router taps them with vias instead of routing
   them as tracks, and a rule area over the HV isolation band (x 85.4-91.0) so no track or via lands in it;
2. runs the router on F, In2 and B with this board's real widths (power-net table below) and the fab tier fixed
   at JLC standard (no escalation to finer rules);
3. converts the output to KiCad 7 (uuid -> tstamp on tracks and vias) and removes the rule area; the planes stay
   (cleanup.py needs them to see plane-tap vias as connected; fab.py replaces them). The project and rule files are copied beside the output.
Takes ~30 min on a laptop. Then: cleanup.py, eco_v07_finish.py, tidy_silk.py, fab.py as before.
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pcbnew

SRC, DST = (sys.argv + ["", ""])[1:3]
KRT = os.environ.get("KRT_DIR", "../../KiCadRoutingTools")
OX = OY = 50.0
LV = [(0.3, 0.3), (85.2, 0.3), (85.2, 97.7), (0.3, 97.7)]
ISLAND = [(45.5, 0.5), (80.6, 0.5), (80.6, 30.8), (70.5, 30.8), (70.5, 28.0), (51.5, 28.0), (51.5, 19.5), (45.5, 19.5)]
HV_BAND = [(85.4, 0.0), (91.0, 0.0), (91.0, 98.0), (85.4, 98.0)]
# net pattern -> track width (mm); everything else 0.15 mm
POWER = {
    "VCOIL*": 1.0, "COIL_*": 1.0, "PUMP_N": 1.0,
    "VBAT_P": 0.5, "VIG_*": 0.5, "BMS12V": 0.5, "BUCK_SW": 0.5, "+5V": 0.5,
    "BUS_P*": 0.25, "DIV*": 0.25, "TAP*": 0.25, "VHB*": 0.25,
    "SNS*": 0.2, "BUS_N*": 0.2, "SENSE_MID": 0.2, "HV5V*": 0.2,
}
TAG = "krt"


def outline(z, pts):
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(pcbnew.VECTOR2I(pcbnew.FromMM(OX + x), pcbnew.FromMM(OY + y)))


def prep(src, dst):
    b = pcbnew.LoadBoard(src)
    nets = b.GetNetsByName()
    for layer in (pcbnew.In1_Cu, pcbnew.B_Cu):
        for net, pts, prio in (("GND", LV, 0), ("ISLGND", ISLAND, 1)):
            z = pcbnew.ZONE(b)
            z.SetLayer(layer); z.SetNet(nets[net]); z.SetAssignedPriority(prio); z.SetZoneName(TAG)
            z.SetLocalClearance(pcbnew.FromMM(0.3)); z.SetMinThickness(pcbnew.FromMM(0.25))
            z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
            z.SetThermalReliefGap(pcbnew.FromMM(0.3)); z.SetThermalReliefSpokeWidth(pcbnew.FromMM(0.35))
            outline(z, pts)
            b.Add(z)
    ko = pcbnew.ZONE(b)
    ko.SetIsRuleArea(True); ko.SetZoneName(TAG)
    ko.SetDoNotAllowTracks(True); ko.SetDoNotAllowVias(True); ko.SetDoNotAllowCopperPour(True)
    ls = pcbnew.LSET()
    for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
        ls.AddLayer(l)
    ko.SetLayerSet(ls)
    outline(ko, HV_BAND)
    b.Add(ko)
    b.Save(dst)


def route(src, dst):
    cmd = [sys.executable, os.path.join(KRT, "py_router", "route.py"), src, dst,
           "--layers", "F.Cu", "In2.Cu", "B.Cu", "--track-width", "0.15", "--clearance", "0.15",
           "--via-size", "0.6", "--via-drill", "0.3", "--fab-tier", "standard", "--escalation", "off",
           "--power-nets", *POWER, "--power-nets-widths", *map(str, POWER.values())]
    subprocess.run(cmd, check=True)


def to_kicad7(src, dst):
    txt = open(src).read()
    open(dst, "w").write(re.sub(r'^\t\t\(uuid "', '\t\t(tstamp "', txt, flags=re.M))
    b = pcbnew.LoadBoard(dst)
    for z in list(b.Zones()):
        if z.GetIsRuleArea() and z.GetZoneName() == TAG:  # planes stay: cleanup.py needs them, fab.py re-pours them
            b.Delete(z)
    b.Save(dst)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        a, r = os.path.join(tmp, "in.kicad_pcb"), os.path.join(tmp, "out.kicad_pcb")
        prep(SRC, a)
        route(a, r)
        to_kicad7(r, DST)
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy("ze2-mcm-spoof" + ext, DST.rsplit(".", 1)[0] + ext)


if __name__ == "__main__":
    main()
