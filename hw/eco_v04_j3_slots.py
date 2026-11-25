"""Incremental router for the v0.4 ECO: J3 overhanging the top edge + short isolation slots (copy of route_v04.py): keeps every existing track/via as an obstacle and only routes
the new termination nets plus the stubs that join new pads onto existing nets.
usage: python3 route_v04.py patched.kicad_pcb routed.kicad_pcb
"""
import math
import sys

import numpy as np
import pcbnew

SRC, DST = sys.argv[1], sys.argv[2]
TMP = "/tmp/v04_pre.kicad_pcb"
NEW_NETS = []
JOIN_NETS = ["BUS_P", "BUS_N"]
MOVE = {"J3": ((105.58, 9.5), 180)}       # board mm, origin = board corner
RIP_BOX = (94.0, 0.0, 114.5, 21.0)           # delete these nets' copper inside this box, then rejoin
RIP_NETS = {"BUS_P", "BUS_N"}


def mmxy(v):
    return pcbnew.ToMM(v.x) - 50, pcbnew.ToMM(v.y) - 50


def inside(p):
    x, y = mmxy(p)
    return RIP_BOX[0] <= x <= RIP_BOX[2] and RIP_BOX[1] <= y <= RIP_BOX[3]


b = pcbnew.LoadBoard(SRC)
for ref, ((x, y), rot) in MOVE.items():
    f = b.FindFootprintByReference(ref)
    f.SetOrientationDegrees(rot)
    f.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x + 50), pcbnew.FromMM(y + 50)))
import build_board as BB  # noqa: E402  (SLOTS is the source of truth)
for d in list(b.GetDrawings()):  # replace interior Edge.Cuts with the short slots
    if d.GetLayer() == pcbnew.Edge_Cuts:
        bb = d.GetBoundingBox()
        if pcbnew.ToMM(bb.GetLeft()) - 50 > 1:
            b.Delete(d)
for x0, y0, x1, y1 in BB.SLOTS:
    sh = pcbnew.PCB_SHAPE(b); sh.SetShape(pcbnew.SHAPE_T_RECT)
    sh.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(x0 + 50), pcbnew.FromMM(y0 + 50)))
    sh.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(x1 + 50), pcbnew.FromMM(y1 + 50)))
    sh.SetLayer(pcbnew.Edge_Cuts); sh.SetWidth(pcbnew.FromMM(0.1)); b.Add(sh)
for t in list(b.GetTracks()):
    if t.GetNetname() in RIP_NETS:
        pts = [t.GetPosition()] if t.Type() == pcbnew.PCB_VIA_T else [t.GetStart(), t.GetEnd()]
        if any(inside(p) for p in pts):
            b.Delete(t)
b.Save(TMP)

sys.argv = ["route.py", TMP, DST]
import route as R  # noqa: E402  (builds pad obstacles from TMP)

board = R.board
copper = {}  # net -> set of (li, gx, gy) cells lying on existing copper
LI = {L: i for i, L in enumerate(R.LAYERS)}
for t in board.GetTracks():
    net = t.GetNetname()
    me, clr = R.nid(net), R.cls_of(net)[1]
    cells = copper.setdefault(net, set())
    if t.Type() == pcbnew.PCB_VIA_T:
        x, y, rr = pcbnew.ToMM(t.GetPosition().x), pcbnew.ToMM(t.GetPosition().y), pcbnew.ToMM(t.GetWidth()) / 2
        for li in range(3):
            R.OBS[li].append(R.capsule_obs(me, x, y, x, y, rr, clr))
        o = R.capsule_obs(me, x, y, x, y, rr, clr)
        gx, gy = np.nonzero(o.dist <= 1e-6)
        for li in range(3):
            cells |= {(li, int(o.sl[0].start + a), int(o.sl[1].start + c)) for a, c in zip(gx, gy)}
        continue
    if t.GetLayer() not in LI:
        continue
    li = LI[t.GetLayer()]
    ax, ay = pcbnew.ToMM(t.GetStart().x), pcbnew.ToMM(t.GetStart().y)
    bx, by = pcbnew.ToMM(t.GetEnd().x), pcbnew.ToMM(t.GetEnd().y)
    w = pcbnew.ToMM(t.GetWidth())
    o = R.capsule_obs(me, ax, ay, bx, by, w / 2, clr)
    R.OBS[li].append(o)
    gx, gy = np.nonzero(o.dist <= 1e-6)
    cells |= {(li, int(o.sl[0].start + a), int(o.sl[1].start + c)) for a, c in zip(gx, gy)}

tracks, vias, failed = [], [], []
for net in NEW_NETS:
    R.route_net(net, tracks, vias, failed)

from scipy.ndimage import label  # noqa: E402


def components(cells):
    """Connected copper islands of one net: 8-connected per layer, joined across layers where a cell is on all."""
    grid = np.zeros((3, R.NX, R.NY), bool)
    for li, x, y in cells:
        grid[li, x, y] = True
    labs, off = [], 0
    for li in range(3):
        lab, n = label(grid[li], structure=np.ones((3, 3), int))
        labs.append(np.where(lab > 0, lab + off, 0)); off += n
    parent = list(range(off + 1))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]; i = parent[i]
        return i
    multi = grid[0] & grid[1] & grid[2]
    for x, y in zip(*np.nonzero(multi)):
        r0 = find(labs[0][x, y])
        for li in (1, 2):
            parent[find(labs[li][x, y])] = r0
    comp = {}
    for li, x, y in cells:
        comp.setdefault(find(labs[li][x, y]), set()).add((li, x, y))
    return list(comp.values())


for net in JOIN_NETS:
    w, _ = R.cls_of(net)
    pw = R.cls_name(net) == "Power"
    pads = R.pads_by_net[net]
    allc = set(copper.get(net, set()))
    for p in pads:
        allc |= R.pad_cells(p)
    comps = [c for c in components(allc)]
    padcomp = [c for c in comps if any(R.pad_cells(p) & c for p in pads)]
    padcomp.sort(key=lambda c: -sum(1 for p in pads if R.pad_cells(p) & c))
    tree, rest = set(padcomp[0]), padcomp[1:]
    for tgt in rest:
        ww, vd, vdr = w, (R.PVIA_D if pw else R.VIA_D), (R.PVIA_DRILL if pw else R.VIA_DRILL)
        path = R.astar(net, tree, tgt, ww, vd)
        if path is None and w > 0.25:
            ww, vd, vdr = 0.25, R.VIA_D, R.VIA_DRILL
            path = R.astar(net, tree, tgt, ww, vd)
        names = sorted({p["ref"] + "." + p["num"] for p in pads if R.pad_cells(p) & tgt})
        if path is None:
            failed.append((net, names)); continue
        R.commit(net, path, ww, vd, vdr, tracks, vias)
        tree |= set(path) | tgt
        print("joined", net, "island", names, "w", ww)

R.write_board(tracks, vias)
print("FAILED", failed)
