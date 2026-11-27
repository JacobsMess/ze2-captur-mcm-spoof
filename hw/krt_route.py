"""Route the placed board with KiCadRoutingTools (github.com/drandyhaas/KiCadRoutingTools).

usage (from hw/): KRT_DIR=<KiCadRoutingTools checkout, router built> python3 krt_route.py unrouted.kicad_pcb routed.kicad_pcb [old.kicad_pcb]

With old.kicad_pcb (normally the current ze2-mcm-spoof.kicad_pcb) it is an ECO: the old board's copper is copied
except what touches a moved/new/changed footprint, and the nets that touched it, changed pads or were already
incomplete are completed around the kept copper (minutes, not half an hour). Without it the whole board is routed.

1. adds the planes fab.py pours (GND / ISLGND on In1 and B) so the router taps them with vias instead of routing
   them as tracks, and a rule area over the HV isolation band (x 85.4-91.0) so no track or via lands in it;
2. routes, with the fab tier fixed at JLC standard (no escalation to finer rules) and no via in or touching an SMD
   pad: the USB and CAN pairs as coupled pairs, then the crystal nets on F.Cu, then the rest on F, In2 and B with
   this board's real widths (power-net table below);
3. converts the output to KiCad 7 (uuid -> tstamp on tracks and vias) and removes the rule area; the planes stay
   (cleanup.py needs them to see plane-tap vias as connected; fab.py replaces them). The project and rule files are copied beside the output.
A full route takes ~30 min on a laptop. Then cleanup.py, widen_power.py, tidy_silk.py, fab.py (build.sh runs the lot).
"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

import pcbnew

SRC, DST, OLD = (sys.argv + ["", "", ""])[1:4]
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
PLANES = {"GND", "ISLGND"}   # tapped by vias, so judged per item rather than by their (huge) pad sets
KEEP_CLEAR = 0.5             # mm around a changed footprint in which old copper is dropped


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
    _keepout(b)
    b.Save(dst)


def _keepout(b):
    ko = pcbnew.ZONE(b)
    ko.SetIsRuleArea(True); ko.SetZoneName(TAG)
    ko.SetDoNotAllowTracks(True); ko.SetDoNotAllowVias(True); ko.SetDoNotAllowCopperPour(True)
    ls = pcbnew.LSET()
    for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
        ls.AddLayer(l)
    ko.SetLayerSet(ls)
    outline(ko, HV_BAND)
    b.Add(ko)


def _geom(f):
    return (str(f.GetFPID().GetLibItemName()), f.GetPosition().x, f.GetPosition().y, round(f.GetOrientationDegrees(), 2),
            f.GetLayer())


def _fp_key(f):
    return _geom(f) + (tuple(sorted((p.GetNumber(), p.GetNetname()) for p in f.Pads())),)


def _changed_boxes(new_fp, old_fp, m):
    """Areas whose old copper is dropped: the whole part if it moved or changed footprint, else just the pads
    whose net changed (a big module with one re-assigned pin keeps the rest of its fan-out)."""
    if old_fp is not None and _geom(old_fp) == _geom(new_fp):
        onet = {p.GetNumber(): p.GetNetname() for p in old_fp.Pads()}
        out = []
        for p in new_fp.Pads():
            if onet.get(p.GetNumber()) != p.GetNetname():
                bb = p.GetBoundingBox()
                bb.Inflate(m)
                out.append(bb)
        return out
    bb = (new_fp or old_fp).GetBoundingBox(False, False)
    bb.Inflate(m)
    return [bb]


def _pads_by_net(b):
    out = {}
    for f in b.GetFootprints():
        for p in f.Pads():
            out.setdefault(p.GetNetname(), set()).add((f.GetReference(), p.GetNumber(), p.GetPosition().x, p.GetPosition().y))
    return out


def _unconnected(b):
    """Nets KiCad's DRC reports as not fully connected on board b (zones filled)."""
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
    rpt = os.path.join(tempfile.gettempdir(), "krt_eco_drc.txt")
    pcbnew.WriteDRCReport(b, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    nets = set()
    for blk in re.split(r"\n(?=\[)", open(rpt).read()):
        if blk.startswith("[unconnected_items]"):
            nets |= set(re.findall(r"\[([^\]]+)\] of ", blk))
    return nets - PLANES


def reuse(new_path, old_path):
    """Copy unchanged copper from old_path onto the prepped board at new_path; return the nets left to route."""
    new, old = pcbnew.LoadBoard(new_path), pcbnew.LoadBoard(old_path)
    ofp = {f.GetReference(): _fp_key(f) for f in old.GetFootprints()}
    m = pcbnew.FromMM(KEEP_CLEAR)
    boxes = []
    for f in new.GetFootprints():
        if ofp.get(f.GetReference()) != _fp_key(f):
            boxes += _changed_boxes(f, old.FindFootprintByReference(f.GetReference()), m)
    for f in old.GetFootprints():   # removed or moved parts: their old area too
        g = new.FindFootprintByReference(f.GetReference())
        if g is None or _geom(g) != _geom(f):
            boxes += _changed_boxes(f, None, m)
    npads, opads = _pads_by_net(new), _pads_by_net(old)
    todo = {n for n in npads if n and n not in PLANES and npads[n] != opads.get(n)} | _unconnected(old)
    cut = lambda t: any(t.GetBoundingBox().Intersects(x) for x in boxes)
    todo |= {t.GetNetname() for t in old.GetTracks() if cut(t)}
    todo -= {""}
    nets = new.GetNetsByName()
    copied = 0
    for t in old.GetTracks():   # everything but the copper over changed parts; the router completes the rest
        n = t.GetNetname()
        if n not in nets or cut(t):
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            c = pcbnew.PCB_VIA(new)
            c.SetPosition(t.GetPosition()); c.SetViaType(t.GetViaType()); c.SetDrill(t.GetDrillValue())
            c.SetWidth(t.GetWidth()); c.SetLayerPair(t.TopLayer(), t.BottomLayer())
        else:
            c = pcbnew.PCB_TRACK(new)
            c.SetStart(t.GetStart()); c.SetEnd(t.GetEnd()); c.SetWidth(t.GetWidth()); c.SetLayer(t.GetLayer())
        c.SetNet(nets[n])
        new.Add(c)
        copied += 1
    new.Save(new_path)
    hit = {p.GetNetname() for f in new.GetFootprints() for p in f.Pads() if any(x.Contains(p.GetPosition()) for x in boxes)}
    route_nets = sorted(todo - PLANES) + sorted(PLANES & (todo | hit))
    print(f"ECO: copied {copied} tracks/vias, routing {len(route_nets)} nets: {' '.join(route_nets)}")
    return route_nets


COMMON = ["--fab-tier", "standard", "--escalation", "off", "--clearance", "0.15", "--via-size", "0.6",
          "--via-drill", "0.3", "--same-net-pad-clearance", "0.1"]   # 0.1: no via in (or touching) an SMD pad
LAYERS = ["F.Cu", "In2.Cu", "B.Cu"]
# differential pairs: the router pairs X_P / X_N, so the CAN pairs are renamed for routing and back afterwards.
# USB stays on F.Cu over the In1 ground (0.2 / 0.15 mm: ~90 ohm on JLC04161H-7628, check JLC's calculator);
# CAN pairs keep coupled through connector, TVS, relay and transceiver (impedance not critical at 500 kbit/s).
CAN_PAIRS = {"CAN1": ("CAN1H", "CAN1L"), "MCM_CAN": ("MCM_CANH", "MCM_CANL"), "IMA_CAN": ("IMA_CANH", "IMA_CANL"),
             "DASH_CAN": ("DASH_CANH", "DASH_CANL")}
PAIRS = [(("USB_DP", "USB_DN"), ["F.Cu"], "0.2", "0.15")] + \
        [((f"{k}_P", f"{k}_N"), LAYERS, "0.15", "0.2") for k in CAN_PAIRS]
FIRST = ["OSC*"]   # crystal nets before anything else, top layer only: the short direct path is still free


def _rename(path, forward):
    b = pcbnew.LoadBoard(path)
    nets = b.GetNetsByName()
    for k, (h, l) in CAN_PAIRS.items():
        for old, new in ((h, f"{k}_P"), (l, f"{k}_N")) if forward else ((f"{k}_P", h), (f"{k}_N", l)):
            if old in nets:
                nets[old].SetNetname(new)
    b.Save(path)


def _with_project(path):
    """The board's project and rules beside a stage's input, unless the previous stage left its own (it records
    protected pairs and the via-off-pad clearance there)."""
    for ext in (".kicad_pro", ".kicad_dru"):
        dst = path.rsplit(".", 1)[0] + ext
        if not os.path.exists(dst):
            shutil.copy("ze2-mcm-spoof" + ext, dst)
    return path


def _run(script, src, dst, *args):
    _with_project(src)
    subprocess.run([sys.executable, os.path.join(KRT, "py_router", script), src, dst, *args], check=True)


def route(src, dst, nets=(), tmp="."):
    """Pairs, then the crystal nets, then everything else; with nets, only those (ECO)."""
    want = set(nets) if nets else None
    keep = lambda names: [n for n in names if want is None or n in want or
                          any(n == f"{k}_{s}" and (want & set(CAN_PAIRS[k])) for k in CAN_PAIRS for s in "PN")]
    cur, i = src, 0
    for pair, layers, w, gap in PAIRS:
        if not keep(pair):
            continue
        nxt = os.path.join(tmp, f"s{i}.kicad_pcb"); i += 1
        _run("route_diff.py", cur, nxt, "--nets", *pair, "--layers", *layers, "--track-width", w,
             "--diff-pair-gap", gap, *COMMON)
        cur = nxt
    power = ["--power-nets", *POWER, "--power-nets-widths", *map(str, POWER.values())]
    first = [n for n in FIRST if want is None] or sorted(n for n in (want or ()) if n.startswith("OSC"))
    if first:
        nxt = os.path.join(tmp, f"s{i}.kicad_pcb"); i += 1
        _run("route.py", cur, nxt, "--nets", *first, "--layers", "F.Cu", "--track-width", "0.15", *COMMON)
        cur = nxt
    rest = ["--nets", *nets] if nets else []   # ECO: complete them around the copper that was kept
    _run("route.py", cur, dst, *rest, "--layers", *LAYERS, "--track-width", "0.15", *COMMON, *power)


def to_kicad7(src, dst):
    txt = open(src).read()
    open(dst, "w").write(re.sub(r'^\t\t\(uuid "', '\t\t(tstamp "', txt, flags=re.M))
    b = pcbnew.LoadBoard(dst)
    for z in list(b.Zones()):
        if z.GetIsRuleArea() and z.GetZoneName() == TAG:  # planes stay: cleanup.py needs them, fab.py re-pours them
            b.Delete(z)
    b.Save(dst)
    _rename(dst, forward=False)


def main():
    with tempfile.TemporaryDirectory() as tmp:
        a, r = os.path.join(tmp, "in.kicad_pcb"), os.path.join(tmp, "out.kicad_pcb")
        prep(SRC, a)
        nets = reuse(a, OLD) if OLD else ()
        _rename(a, forward=True)
        nets = [n for n in nets]
        for k, (h, l) in CAN_PAIRS.items():   # ECO net names follow the rename
            nets = [f"{k}_P" if n == h else f"{k}_N" if n == l else n for n in nets]
        if OLD and not nets:
            shutil.copy(a, r)
        else:
            route(a, r, nets, tmp)
        to_kicad7(r, DST)
        left = sorted(_unconnected(pcbnew.LoadBoard(DST)))
        if left:   # finishing pass: those nets only, with In1 (the GND plane) allowed at a high cost
            print(f"finishing {len(left)} incomplete nets with In1 allowed: {' '.join(left)}")
            b = pcbnew.LoadBoard(DST)
            _keepout(b)
            b.Save(DST)
            _rename(DST, forward=True)
            fin = os.path.join(tmp, "fin.kicad_pcb")
            for ext in (".kicad_pro", ".kicad_dru"):
                shutil.copy(r.rsplit(".", 1)[0] + ext, DST.rsplit(".", 1)[0] + ext)
            names = [f"{k}_P" if n == h else f"{k}_N" if n == l else n
                     for n in left for k, (h, l) in [next(((k, v) for k, v in CAN_PAIRS.items() if n in v),
                                                          ("", ("", "")))]]
            _run("route.py", DST, fin, "--nets", *names, "--rip-existing-nets", "*", "--layers", "F.Cu", "In1.Cu",
                 *LAYERS[1:], "--layer-costs", "1", "20", "1", "1", "--track-width", "0.15", *COMMON,
                 "--power-nets", *POWER, "--power-nets-widths", *map(str, POWER.values()))
            to_kicad7(fin, DST)
    for ext in (".kicad_pro", ".kicad_dru"):
        shutil.copy("ze2-mcm-spoof" + ext, DST.rsplit(".", 1)[0] + ext)


if __name__ == "__main__":
    main()
