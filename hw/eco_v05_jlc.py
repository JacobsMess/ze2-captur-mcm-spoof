"""v0.5 ECO on the routed, silk-tidied board: apply parts.json (MCP2518FD in SOIC-14, 40 MHz crystals,
JLC basic/preferred swaps), rip the copper around every footprint that changed shape, and rejoin.

usage: python3 eco_v05_jlc.py tidy_v04.kicad_pcb routed_v05.kicad_pcb   (run from hw/; the .kicad_pro beside the input carries the rules)
Then tidy_silk.py and fab.py as usual. Footprints are swapped in place (same position and rotation).
Every net with copper in a rip box is rejoined island-to-island with the A* router (existing copper is an
obstacle); plane-net pads that lost their stub get a new stub + via; dangling ends are pruned last.
"""
import json
import math
import sys

import numpy as np
import pcbnew

SRC, DST = sys.argv[1], sys.argv[2]
TMP = "/tmp/v05_pre.kicad_pcb"
FP = "/usr/share/kicad/footprints/"
MARGIN = 0.8  # mm around the old+new pad extents
PLANE = {"GND", "ISLGND"}

parts = json.load(open("parts.json"))
b = pcbnew.LoadBoard(SRC)
nets = b.GetNetsByName()


def net(name):
    if name not in nets:
        n = pcbnew.NETINFO_ITEM(b, name); b.Add(n); nets[name] = n
    return nets[name]


def pad_extent(fp):
    e = [(pcbnew.ToMM(p.GetBoundingBox().GetLeft()), pcbnew.ToMM(p.GetBoundingBox().GetTop()),
          pcbnew.ToMM(p.GetBoundingBox().GetRight()), pcbnew.ToMM(p.GetBoundingBox().GetBottom())) for p in fp.Pads()]
    return min(a[0] for a in e), min(a[1] for a in e), max(a[2] for a in e), max(a[3] for a in e)


boxes, swapped = [], []  # boxes: (box, nets of the old and new pads, ref)
for ref, p in parts.items():
    fp = b.FindFootprintByReference(ref)
    if fp is None:
        continue
    lib, name = p["fp"]
    if str(fp.GetFPID().GetLibItemName()) != name:
        old = pad_extent(fp)
        own = {pd.GetNetname() for pd in fp.Pads()} | {n for n in p["nets"].values() if not n.startswith("NC_")}
        cp = lambda v: pcbnew.VECTOR2I(int(v.x), int(v.y))  # SWIG returns refs into the footprint: copy before Delete
        pos, rot = cp(fp.GetPosition()), fp.GetOrientationDegrees()
        rpos, rrot = cp(fp.Reference().GetPosition()), fp.Reference().GetTextAngleDegrees()
        b.Delete(fp)
        fp = pcbnew.FootprintLoad(FP + lib + ".pretty", name)
        fp.SetReference(ref)
        fp.Reference().SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.8), pcbnew.FromMM(0.8)))
        fp.Reference().SetTextThickness(pcbnew.FromMM(0.12))
        fp.Value().SetVisible(False)
        b.Add(fp)
        fp.SetPosition(pos); fp.SetOrientationDegrees(rot)
        fp.Reference().SetPosition(rpos); fp.Reference().SetTextAngleDegrees(rrot)
        new = pad_extent(fp)
        boxes.append(((min(old[0], new[0]) - MARGIN, min(old[1], new[1]) - MARGIN,
                       max(old[2], new[2]) + MARGIN, max(old[3], new[3]) + MARGIN), own - {""}, ref))
        swapped.append(ref)
    fp.SetValue(p["val"])
    for pad in fp.Pads():
        n = p["nets"].get(pad.GetNumber(), "")
        if n and not n.startswith("NC_"):
            pad.SetNet(net(n))
        elif ref in swapped:
            pad.SetNet(net(""))
print("swapped", swapped)


def seg_hits_box(a, c, bx):
    """Segment a-c (mm) touches the axis-aligned box: endpoint inside or crossing (sampled every 0.1 mm)."""
    n = max(2, int(math.hypot(c[0] - a[0], c[1] - a[1]) / 0.1) + 1)
    for i in range(n + 1):
        x, y = a[0] + (c[0] - a[0]) * i / n, a[1] + (c[1] - a[1]) * i / n
        if bx[0] <= x <= bx[2] and bx[1] <= y <= bx[3]:
            return True
    return False


R_CLR = {}  # per-net clearance is only needed coarsely here; route.py's classes are applied when rejoining
mm2 = lambda v: (pcbnew.ToMM(v.x), pcbnew.ToMM(v.y))
def new_pad_boxes(ref, grow):
    out = []
    for pd in b.FindFootprintByReference(ref).Pads():
        bb_ = pd.GetBoundingBox()
        out.append((pcbnew.ToMM(bb_.GetLeft()) - grow, pcbnew.ToMM(bb_.GetTop()) - grow,
                    pcbnew.ToMM(bb_.GetRight()) + grow, pcbnew.ToMM(bb_.GetBottom()) + grow, pd.GetNetname()))
    return out


# signal nets of the re-pinned CAN controllers are ripped whole and routed fresh (their pins moved sides)
FULL = {n for bx, own, ref in boxes if ref.startswith("U") for n in own} - PLANE - {"+3V3"} | {"ESP_EN", "IG_SENSE", "VIG_RAW"}
# rip (a) the footprint's own nets inside its box, (b) any other net's copper that now crowds a new pad
ripped, kill = set(), []
for t in b.GetTracks():
    nn = t.GetNetname()
    via = t.Type() == pcbnew.PCB_VIA_T
    pts = [mm2(t.GetPosition())] * 2 if via else [mm2(t.GetStart()), mm2(t.GetEnd())]
    half = pcbnew.ToMM(t.GetWidth()) / 2
    top = via or t.GetLayer() == pcbnew.F_Cu  # new pads are all top-side SMD
    inbox = lambda q, bx: bx[0] <= q[0] <= bx[2] and bx[1] <= q[1] <= bx[3]
    if nn in FULL:
        kill.append(t); continue
    for bx, own, ref in boxes:
        if nn in own and (any(inbox(q, bx) for q in pts) or top and seg_hits_box(pts[0], pts[1], bx)):
            kill.append(t); break
        grow = half + max(R_CLR.get(nn, 0.15), 0.15) + 0.05
        if top and nn not in own and any(pn != nn and seg_hits_box(pts[0], pts[1], q[:4]) for q in new_pad_boxes(ref, grow)
                                 for pn in [q[4]]):
            kill.append(t); break
for t in kill:
    ripped.add(t.GetNetname()); b.Delete(t)
b.Save(TMP)
print("ripped nets", sorted(ripped))

sys.argv = ["route.py", TMP, DST]
import route as R  # noqa: E402  (builds pad obstacles from TMP)

copper, vcells = {}, {}  # vcells: net -> (x, y) where copper really joins the layers (vias, THT pads)
LI = {L: i for i, L in enumerate(R.LAYERS)}
for t in R.board.GetTracks():
    nn = t.GetNetname()
    me, clr = R.nid(nn), R.cls_of(nn)[1]
    cells = copper.setdefault(nn, set())
    if t.Type() == pcbnew.PCB_VIA_T:
        x, y = mm2(t.GetPosition()); rr = pcbnew.ToMM(t.GetWidth()) / 2
        o = R.capsule_obs(me, x, y, x, y, rr, clr)
        for li in range(3):
            R.OBS[li].append(o)
        gx, gy = np.nonzero(o.dist <= 1e-6)
        for li in range(3):
            cells |= {(li, int(o.sl[0].start + a), int(o.sl[1].start + c)) for a, c in zip(gx, gy)}
        vcells.setdefault(nn, set()).update((int(o.sl[0].start + a), int(o.sl[1].start + c)) for a, c in zip(gx, gy))
        continue
    if t.GetLayer() not in LI:
        continue
    li = LI[t.GetLayer()]
    (ax, ay), (bx_, by) = mm2(t.GetStart()), mm2(t.GetEnd())
    o = R.capsule_obs(me, ax, ay, bx_, by, pcbnew.ToMM(t.GetWidth()) / 2, clr)
    R.OBS[li].append(o)
    gx, gy = np.nonzero(o.dist <= 1e-6)
    cells |= {(li, int(o.sl[0].start + a), int(o.sl[1].start + c)) for a, c in zip(gx, gy)}

from scipy.ndimage import label  # noqa: E402


def components(cells, vias_xy):
    grid = np.zeros((3, R.NX, R.NY), bool)
    for li, x, y in cells:
        grid[li, x, y] = True
    labs, off = [], 0
    for li in range(3):
        lab, n = label(grid[li])  # 4-connected: diagonal grid neighbours are not necessarily touching copper
        labs.append(np.where(lab > 0, lab + off, 0)); off += n
    parent = list(range(off + 1))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    for x, y in vias_xy:
        ls = [li for li in range(3) if grid[li, x, y]]
        for li in ls[1:]:
            parent[find(labs[li][x, y])] = find(labs[ls[0]][x, y])
    comp = {}
    for li, x, y in cells:
        comp.setdefault(find(labs[li][x, y]), set()).add((li, x, y))
    return list(comp.values())


tracks, vias, failed = [], [], []

# plane pads with no copper on them any more: stub + via (same rule as route.py's plane pass)
for pn in sorted(PLANE):
    have = copper.get(pn, set())
    for p in R.pads_by_net.get(pn, []):
        if p["tht"] or len(p["layers"]) == 3 or p.get("thermal_vias") or (R.pad_cells(p) & have):
            continue
        vm = np.zeros((R.NX, R.NY), bool)
        for li in range(3):
            vm |= R.blocked(pn, li, R.VIA_D)
        cx, cy = R.to_grid(p["x"], p["y"])
        cand = [(p["layers"][0], cx + dx, cy + dy) for dx in range(-12, 13) for dy in range(-12, 13)
                if 0 <= cx + dx < R.NX and 0 <= cy + dy < R.NY and not vm[cx + dx, cy + dy] and (dx, dy) != (0, 0)]
        cand.sort(key=lambda c: math.hypot(c[1] - cx, c[2] - cy))
        path = R.astar(pn, R.pad_cells(p), set(cand[:20]), 0.2, R.VIA_D, layers=(p["layers"][0],), limit=40000) if cand else None
        if not path:
            failed.append((pn, p["ref"] + "." + p["num"])); continue
        R.commit(pn, path, 0.2, R.VIA_D, R.VIA_DRILL, tracks, vias)
        li, x, y = path[-1]
        vias.append((pn, x, y, R.VIA_D, R.VIA_DRILL))
        for l2 in range(3):
            R.OBS[l2].append(R.capsule_obs(R.NET_ID[pn], *R.gxy(x, y), *R.gxy(x, y), R.VIA_D / 2, R.cls_of(pn)[1]))
        print("plane stub", pn, p["ref"], p["num"])

for nn in sorted(FULL, key=lambda n: len(R.pads_by_net.get(n, []))):
    if len(R.pads_by_net.get(nn, [])) > 1:
        R.route_net(nn, tracks, vias, failed)
        print("routed", nn)
join = sorted((ripped | {pd.GetNetname() for ref in swapped for pd in R.board.FindFootprintByReference(ref).Pads()})
              - PLANE - FULL - {""})
# short nets first (crystal, INT, CS, TX/RX), shared buses last so they route around the locals
join.sort(key=lambda n: len(R.pads_by_net.get(n, [])))
for nn in join:
    pads = R.pads_by_net.get(nn, [])
    if len(pads) < 2:
        continue
    w, _ = R.cls_of(nn)
    pw = R.cls_name(nn) == "Power"
    allc = set(copper.get(nn, set()))
    for p in pads:
        allc |= R.pad_cells(p)
    vx = set(vcells.get(nn, set()))
    for p in pads:
        if len(p["layers"]) == 3:
            vx |= {(x, y) for _, x, y in R.pad_cells(p)}
    comps = [c for c in components(allc, vx) if any(R.pad_cells(p) & c for p in pads)]
    comps.sort(key=lambda c: -sum(1 for p in pads if R.pad_cells(p) & c))
    tree = set(comps[0])
    for tgt in comps[1:]:
        if tgt & tree:
            continue
        ww, vd, vdr = w, (R.PVIA_D if pw else R.VIA_D), (R.PVIA_DRILL if pw else R.VIA_DRILL)
        path = R.astar(nn, tree, tgt, ww, vd)
        if path is None and w > 0.25:
            ww, vd, vdr = 0.25, R.VIA_D, R.VIA_DRILL
            path = R.astar(nn, tree, tgt, ww, vd)
        names = sorted({p["ref"] + "." + p["num"] for p in pads if R.pad_cells(p) & tgt})
        if path is None:
            failed.append((nn, names)); continue
        R.commit(nn, path, ww, vd, vdr, tracks, vias)
        tree |= set(path) | tgt
        for (l0, x0, y0), (l1, x1, y1) in zip(path, path[1:]):
            if l0 != l1:
                vcells.setdefault(nn, set()).add((x1, y1))
        print("joined", nn, names)

R.write_board(tracks, vias)
print("FAILED", failed)
touched = set(join) | ripped

# prune what the old footprints leave dangling (e.g. ESP_EN to the MCP2515 RESET pin): KiCad's own DRC decides
import re  # noqa: E402
import shutil  # noqa: E402

shutil.copy(SRC.rsplit(".", 1)[0] + ".kicad_pro", DST.rsplit(".", 1)[0] + ".kicad_pro") if __import__("os").path.exists(
    SRC.rsplit(".", 1)[0] + ".kicad_pro") else None
def unconnected(bd):
    bd.BuildConnectivity()
    return bd.GetConnectivity().GetUnconnectedCount(False)


def safe_delete(bd, t, why):
    base = unconnected(bd)
    keep = t.Duplicate()
    bd.Delete(t)
    if unconnected(bd) > base:
        bd.Add(keep); print("kept", why); return keep
    print(why); return None


def safe_move(bd, t, setter, getter, pt, why):
    base, old = unconnected(bd), pcbnew.VECTOR2I(int(getter().x), int(getter().y))
    setter(pt)
    if unconnected(bd) > base:
        setter(old); print("kept", why); return False
    print(why); return True


for _ in range(12):
    bb = pcbnew.LoadBoard(DST)
    pcbnew.WriteDRCReport(bb, "/tmp/v05_drc.txt", pcbnew.EDA_UNITS_MILLIMETRES, False)
    rep = open("/tmp/v05_drc.txt").read()
    co = re.findall(r"\[(?:holes_co_located|hole_near_hole)\].*?@\(([\d.]+) mm, ([\d.]+) mm\): Via \[([^\]]*)\].*?@\(([\d.]+) mm, ([\d.]+) mm\): Via \[([^\]]*)\]", rep, re.S)
    gone = False
    for x0, y0, n0, x1, y1, n1 in co:
        if n0 != n1:
            continue
        for t in list(bb.GetTracks()):
            if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == n1 and math.dist(mm2(t.GetPosition()), (float(x1), float(y1))) < 0.01:
                q0, q1 = (float(x0), float(y0)), (float(x1), float(y1))
                if q0 != q1:  # near, not co-located: bridge on F.Cu so nothing hangs off the deleted via
                    tr = pcbnew.PCB_TRACK(bb); tr.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(q0[0]), pcbnew.FromMM(q0[1])))
                    tr.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(q1[0]), pcbnew.FromMM(q1[1]))); tr.SetLayer(pcbnew.F_Cu)
                    tr.SetWidth(pcbnew.FromMM(0.2)); tr.SetNet(t.GetNet()); bb.Add(tr)
                    for o in list(bb.GetTracks()):  # move every track end on the deleted via onto the kept one
                        if o.Type() != pcbnew.PCB_VIA_T and o.GetNetname() == n1:
                            for g, st in ((o.GetStart, o.SetStart), (o.GetEnd, o.SetEnd)):
                                if math.dist(mm2(g()), q1) < 0.01:
                                    st(pcbnew.VECTOR2I(pcbnew.FromMM(q0[0]), pcbnew.FromMM(q0[1])))
                    bb.Delete(tr)
                gone |= safe_delete(bb, t, f"drop duplicate via {n1} {q1}") is None
                break
    if gone:
        bb.Save(DST); continue
    hits = re.findall(r"\[via_dangling\].*?@\(([\d.]+) mm, ([\d.]+) mm\): (Via) \[([^\]]*)\]", rep, re.S)
    bb.BuildConnectivity()
    conn = bb.GetConnectivity()
    for t in bb.GetTracks():  # DRC reports a track by its start point; ask connectivity which end hangs
        pos = pcbnew.VECTOR2I()
        if t.Type() != pcbnew.PCB_VIA_T and t.GetNetname() in touched and conn.TestTrackEndpointDangling(t, False, pos):
            hits.append((pcbnew.ToMM(pos.x), pcbnew.ToMM(pos.y), "Track", t.GetNetname()))
    if not hits:
        break
    done = set()
    for x, y, kind, nn in hits:
        if nn not in touched:
            continue
        p = (float(x), float(y))
        for t in list(bb.GetTracks()):
            uid = t.m_Uuid.AsString()
            if uid in done or t.GetNetname() != nn or (t.Type() == pcbnew.PCB_VIA_T) != (kind == "Via"):
                continue
            if kind == "Via":
                if math.dist(p, mm2(t.GetPosition())) < 0.01:
                    done.add(uid); safe_delete(bb, t, f"prune via {nn} {p}")
                continue
            a, c = mm2(t.GetStart()), mm2(t.GetEnd())
            if math.dist(p, a) < 0.01:
                dang, keep, setd, getd = a, c, t.SetStart, t.GetStart
            elif math.dist(p, c) < 0.01:
                dang, keep, setd, getd = c, a, t.SetEnd, t.GetEnd
            else:
                continue
            done.add(uid)
            # pull the dangling end back to the connection nearest it (a T-junction, via or pad on this segment)
            L = math.dist(keep, dang)
            ux, uy = ((dang[0] - keep[0]) / L, (dang[1] - keep[1]) / L) if L else (0, 0)
            w = pcbnew.ToMM(t.GetWidth()) / 2
            best = 0.0
            for o in bb.GetTracks():
                if o.GetNetname() != nn or o.m_Uuid.AsString() == uid:
                    continue
                cands = [mm2(o.GetPosition())] if o.Type() == pcbnew.PCB_VIA_T else (
                    [mm2(o.GetStart()), mm2(o.GetEnd())] if o.GetLayer() == t.GetLayer() else [])
                for q in cands:
                    s_ = (q[0] - keep[0]) * ux + (q[1] - keep[1]) * uy
                    if 0 < s_ < L - 1e-3 and abs((q[0] - keep[0]) * uy - (q[1] - keep[1]) * ux) <= w + 1e-3:
                        best = max(best, s_)
            for fp in bb.GetFootprints():
                for pd in fp.Pads():
                    if pd.GetNetname() != nn or not pd.IsOnLayer(t.GetLayer()):
                        continue
                    for k in range(1, 200):
                        s_ = L * k / 200
                        if pd.HitTest(pcbnew.VECTOR2I(pcbnew.FromMM(keep[0] + ux * s_), pcbnew.FromMM(keep[1] + uy * s_))):
                            best = max(best, s_)
            at = lambda s_: pcbnew.VECTOR2I(pcbnew.FromMM(keep[0] + ux * s_), pcbnew.FromMM(keep[1] + uy * s_))
            if best < 0.05:
                t = safe_delete(bb, t, f"prune track {nn} {p}")
                if t is None:
                    continue
                setd, getd = (t.SetStart, t.GetStart) if dang == a else (t.SetEnd, t.GetEnd)
            if L - best > 0.05 and safe_move(bb, t, setd, getd, at(best), f"trim track {nn} {p} by {round(L - best, 2)}"):
                continue
            # the junction was not found geometrically: shortest length that keeps KiCad's connectivity
            base, lo, hi = unconnected(bb), 0.0, L
            for _ in range(12):
                mid = (lo + hi) / 2
                setd(at(mid))
                if unconnected(bb) > base:
                    lo = mid
                else:
                    hi = mid
            setd(at(hi)); print("trim track (search)", nn, p, "to", round(hi, 3), "of", round(L, 3))
            if hi > L - 1e-3:  # needed at full length: it stops just short of a pad, so finish it at the pad centre
                near = [pd for fp in bb.GetFootprints() for pd in fp.Pads() if pd.GetNetname() == nn and
                        pd.IsOnLayer(t.GetLayer()) and math.dist(mm2(pd.GetPosition()), dang) < 1.0]
                if near:
                    pc = min(near, key=lambda pd: math.dist(mm2(pd.GetPosition()), dang)).GetPosition()
                    setd(pcbnew.VECTOR2I(int(pc.x), int(pc.y))); print("extend track to pad", nn, p)
    bb.Save(DST)
