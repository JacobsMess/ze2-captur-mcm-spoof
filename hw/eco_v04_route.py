"""Incremental router for the v0.4 ECO: keeps every existing track/via as an obstacle and only routes
the new termination nets plus the stubs that join new pads onto existing nets.
usage: python3 route_v04.py patched.kicad_pcb routed.kicad_pcb
"""
import math
import sys

import numpy as np
import pcbnew

SRC, DST = sys.argv[1], sys.argv[2]
TMP = "/tmp/v04_pre.kicad_pcb"
NEW_NETS = ["K4_NO1", "K4_NO2", "TERM3", "TERM2", "TERM2_SW", "TERM2_LED"]
JOIN_NETS = ["MCM_CANH", "MCM_CANL", "K4_COIL", "+5V"]
# +5V feed into K4 pin 1 ran straight through the new termination parts: rip it (board mm, origin = board corner)
RIP = [("+5V", (71.35, 67.55), (76.15, 72.35)), ("+5V", (76.15, 72.35), (76.15, 75.15)),
       ("+5V", (71.35, 65.35), (71.35, 67.55)), ("+5V", (71.35, 67.55), None)]


def rip(b, net, a, c):
    mmxy = lambda v: (round(pcbnew.ToMM(v.x) - 50, 2), round(pcbnew.ToMM(v.y) - 50, 2))
    for t in list(b.GetTracks()):
        if t.GetNetname() != net:
            continue
        if c is None and t.Type() == pcbnew.PCB_VIA_T and mmxy(t.GetPosition()) == a:
            b.Delete(t); return
        if c is not None and t.Type() != pcbnew.PCB_VIA_T and {mmxy(t.GetStart()), mmxy(t.GetEnd())} == {a, c}:
            b.Delete(t); return
    raise SystemExit(f"rip target not found: {net} {a} {c}")


b = pcbnew.LoadBoard(SRC)
for item in RIP:
    rip(b, *item)
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
