"""Grid A* maze router with exact-geometry clearance (KiCad 7 pcbnew).

Routing layers F.Cu / In2.Cu / B.Cu; In1.Cu is the GND / ISLGND plane layer (plane nets get pad stub + via).
Obstacles are stored as exact shapes (pad rectangles, track capsules, via discs) with a per-obstacle
distance field over a local window, so fine-pitch pads (0.5 mm MSOP / USB-C) can escape on a 0.2 mm grid.
Multi-pass: nets that fail are routed first on the next pass; best pass is written to the output board.
"""
import heapq
import math
import sys

import numpy as np
import pcbnew

G = 0.2
LAYERS = [pcbnew.F_Cu, pcbnew.In2_Cu, pcbnew.B_Cu]
PLANE = {"GND", "ISLGND"}
CLS = {"Default": (0.15, 0.15), "Power": (0.5, 0.2), "HV": (0.25, 0.6), "HVLOW": (0.2, 0.2)}  # width, clearance
VIA_D, VIA_DRILL, PVIA_D, PVIA_DRILL = 0.6, 0.3, 0.8, 0.4
VIA_COST, BEND_COST, LAYER_W = 12.0, 0.4, (1.0, 1.15, 1.05)
INFL = 1.2  # mm: max influence radius of any obstacle (w/2 + clr, incl. vias)
SRC, DST = sys.argv[1], sys.argv[2]

board = pcbnew.LoadBoard(SRC)
eb = board.GetBoardEdgesBoundingBox()
ox, oy = pcbnew.ToMM(eb.GetX()), pcbnew.ToMM(eb.GetY())
BW, BH = pcbnew.ToMM(eb.GetWidth()), pcbnew.ToMM(eb.GetHeight())
NX, NY = int(BW / G) + 1, int(BH / G) + 1
XC = ox + np.arange(NX) * G
YC = oy + np.arange(NY) * G

POWER_P = ("VBAT_P", "VIG_", "VCOIL", "COIL_", "BMS12V", "PUMP_N", "BUCK_SW", "+5V", "LM_GATE")
HV_P = ("BUS_P", "DIV", "TAP", "VHB", "SNS")
HVLOW_P = ("BUS_N", "SENSE_MID", "HV5V")  # within a few volts of pack negative


def cls_name(net):
    if any(net == p or net.startswith(p) for p in POWER_P):
        return "Power"
    if any(net == p or net.startswith(p) for p in HV_P):
        return "HV"
    if any(net == p or net.startswith(p) for p in HVLOW_P):
        return "HVLOW"
    return "Default"


def cls_of(net):
    return CLS[cls_name(net)]


def to_grid(x, y):
    return int(round((x - ox) / G)), int(round((y - oy) / G))


# ---------------------------------------------------------------- static blocks
XX, YY = np.meshgrid(XC, YC, indexing="ij")
static = (XX < ox + 0.4) | (XX > ox + BW - 0.4) | (YY < oy + 0.4) | (YY > oy + BH - 0.4)
for d in board.GetDrawings():
    if d.GetLayer() == pcbnew.Edge_Cuts and d.GetShape() == pcbnew.SHAPE_T_RECT:
        bb = d.GetBoundingBox()
        x0, y0 = pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY())
        x1, y1 = x0 + pcbnew.ToMM(bb.GetWidth()), y0 + pcbnew.ToMM(bb.GetHeight())
        if x1 - x0 < BW - 1:
            static |= (XX > x0 - 0.4) & (XX < x1 + 0.4) & (YY > y0 - 0.4) & (YY < y1 + 0.4)
for z in board.Zones():
    if z.GetIsRuleArea():
        bb = z.GetBoundingBox()
        x0, y0 = pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY())
        static |= (XX >= x0) & (XX <= x0 + pcbnew.ToMM(bb.GetWidth())) & (YY >= y0) & (YY <= y0 + pcbnew.ToMM(bb.GetHeight()))
# reinforced isolation band (no routing, any net) between LV and HV regions, full board height
static |= (XX > ox + 85.4) & (XX < ox + 91.0)
STATIC = [static.copy() for _ in range(3)]
# footprint-embedded keepout rule areas (e.g. ESP32 antenna, isolated DC-DC body)
for fp in board.GetFootprints():
    for z in fp.Zones():
        if z.GetIsRuleArea() and (z.GetDoNotAllowTracks() or z.GetDoNotAllowVias()):
            for li, L in enumerate(LAYERS):
                if z.GetLayerSet().Contains(L):
                    bb = z.GetBoundingBox()
                    x0, y0 = pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY())
                    x1, y1 = x0 + pcbnew.ToMM(bb.GetWidth()), y0 + pcbnew.ToMM(bb.GetHeight())
                    win = (XX >= x0 - 0.2) & (XX <= x1 + 0.2) & (YY >= y0 - 0.2) & (YY <= y1 + 0.2)
                    ys_, xs_ = np.nonzero(win.T)
                    for gx, gy in zip(xs_, ys_):
                        if z.Outline().Contains(pcbnew.VECTOR2I(pcbnew.FromMM(float(XC[gx])), pcbnew.FromMM(float(YC[gy]))), -1, pcbnew.FromMM(0.4)):
                            STATIC[li][gx, gy] = True

# ---------------------------------------------------------------- obstacles
NET_ID = {}


def nid(n):
    return NET_ID.setdefault(n, len(NET_ID))


class Obs:
    __slots__ = ("net", "sl", "dist", "clr", "trk")


def window(x0, y0, x1, y1):
    gx0, gy0 = to_grid(x0 - INFL, y0 - INFL)
    gx1, gy1 = to_grid(x1 + INFL, y1 + INFL)
    gx0, gy0, gx1, gy1 = max(0, gx0), max(0, gy0), min(NX - 1, gx1), min(NY - 1, gy1)
    return slice(gx0, gx1 + 1), slice(gy0, gy1 + 1)


def rect_obs(net, x0, y0, x1, y1, clr):
    o = Obs(); o.net, o.clr, o.trk = net, clr, False
    o.sl = window(x0, y0, x1, y1)
    xs, ys = XX[o.sl], YY[o.sl]
    dx = np.maximum(np.maximum(x0 - xs, xs - x1), 0)
    dy = np.maximum(np.maximum(y0 - ys, ys - y1), 0)
    o.dist = np.hypot(dx, dy)
    return o


def capsule_obs(net, ax, ay, bx, by, r, clr):
    o = Obs(); o.net, o.clr, o.trk = net, clr, True
    o.sl = window(min(ax, bx) - r, min(ay, by) - r, max(ax, bx) + r, max(ay, by) + r)
    xs, ys = XX[o.sl], YY[o.sl]
    vx, vy = bx - ax, by - ay
    L2 = vx * vx + vy * vy
    t = np.clip(((xs - ax) * vx + (ys - ay) * vy) / L2, 0, 1) if L2 > 0 else 0
    o.dist = np.maximum(np.hypot(xs - (ax + t * vx), ys - (ay + t * vy)) - r, 0)
    return o


BASE_OBS = [[], [], []]
pads_by_net = {}
for fp in board.GetFootprints():
    for p in fp.Pads():
        net = p.GetNetname()
        bb = p.GetBoundingBox()
        x0, y0 = pcbnew.ToMM(bb.GetX()), pcbnew.ToMM(bb.GetY())
        x1, y1 = x0 + pcbnew.ToMM(bb.GetWidth()), y0 + pcbnew.ToMM(bb.GetHeight())
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            for li in range(3):
                BASE_OBS[li].append(rect_obs(-1, x0, y0, x1, y1, 0.3))
            continue
        on = [i for i, l in enumerate(LAYERS) if p.IsOnLayer(l)]
        n = nid(net) if net else -1
        clr = cls_of(net)[1] if net else 0.2
        for li in on:
            BASE_OBS[li].append(rect_obs(n, x0, y0, x1, y1, clr))
        if net:
            pc = p.GetPosition()
            inside = []
            gx0, gy0 = int(math.ceil((x0 - ox) / G)), int(math.ceil((y0 - oy) / G))
            gx1, gy1 = int(math.floor((x1 - ox) / G)), int(math.floor((y1 - oy) / G))
            for gx in range(gx0, gx1 + 1):
                for gy in range(gy0, gy1 + 1):
                    pt = pcbnew.VECTOR2I(pcbnew.FromMM(ox + gx * G), pcbnew.FromMM(oy + gy * G))
                    if p.HitTest(pt, -pcbnew.FromMM(0.02)):
                        inside.append((gx, gy))
            has_vias = any(q.GetNumber() == p.GetNumber() and q.GetAttribute() == pcbnew.PAD_ATTRIB_PTH
                           for q in fp.Pads()) and p.GetAttribute() != pcbnew.PAD_ATTRIB_PTH
            pads_by_net.setdefault(net, []).append(dict(ref=fp.GetReference(), num=p.GetNumber(), x=pcbnew.ToMM(pc.x),
                                                        y=pcbnew.ToMM(pc.y), box=(x0, y0, x1, y1), layers=on,
                                                        tht=p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH, inside=inside,
                                                        thermal_vias=has_vias))
    if fp.GetReference().startswith("H"):
        pc = fp.GetPosition()
        cx, cy = pcbnew.ToMM(pc.x), pcbnew.ToMM(pc.y)
        for li in range(3):
            STATIC[li] |= np.hypot(XX - cx, YY - cy) < 3.6
for n in pads_by_net:
    nid(n)

OBS = [list(l) for l in BASE_OBS]


from scipy.ndimage import binary_dilation

_STATIC_D = {}


def static_dilated(li, width):
    k = (li, round(width, 3))
    if k not in _STATIC_D:
        r = width / 2 / G
        rr = int(math.ceil(r))
        yy_, xx_ = np.ogrid[-rr:rr + 1, -rr:rr + 1]
        _STATIC_D[k] = binary_dilation(STATIC[li], structure=(xx_ * xx_ + yy_ * yy_) <= r * r + 1e-6) if rr else STATIC[li]
    return _STATIC_D[k]


def blocked(net, li, width):
    me, myclr = NET_ID[net], cls_of(net)[1]
    m = static_dilated(li, width).copy()
    half = width / 2
    for o in OBS[li]:
        if o.net != me:
            m[o.sl] |= o.dist < half + max(o.clr, myclr) + 0.03
    return m


def pad_cells(p):
    """Grid cells whose centres lie on the pad copper (exact HitTest), per pad layer."""
    cells = set()
    pts = p["inside"] or [to_grid(p["x"], p["y"])]
    for li in p["layers"]:
        for gx, gy in pts:
            cells.add((li, gx, gy))
    return cells


DIRS = [(1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)]


def astar(net, sources, targets, width, via_d, layers=(0, 1, 2), limit=900000):
    masks = [blocked(net, li, width) if li in layers else np.ones((NX, NY), bool) for li in range(3)]
    vmask = np.zeros((NX, NY), bool)
    for li in range(3):
        vmask |= blocked(net, li, via_d)
    for (li, x, y) in sources | targets:
        masks[li][x, y] = False
    me = NET_ID[net]
    pw = 3.0 if cls_name(net) == "Power" else 0.6
    pens = []
    for li in range(3):
        pen = np.zeros((NX, NY), bool)
        for o in BASE_OBS[li]:
            if o.net != me and o.net >= 0:
                pen[o.sl] |= o.dist < 1.0
        pens.append(pen)
    tset = targets
    tpts = np.array([(t[1], t[2]) for t in targets])
    tmin, tmax = tpts.min(0), tpts.max(0)

    def h(x, y):
        dx = max(tmin[0] - x, 0, x - tmax[0]); dy = max(tmin[1] - y, 0, y - tmax[1])
        return max(dx, dy) + 0.414 * min(dx, dy)
    openq, best, came = [], {}, {}
    for s in sources:
        best[(s, -1)] = 0.0
        heapq.heappush(openq, (h(s[1], s[2]), 0.0, s, -1, None))
    n = 0
    while openq:
        f, g, node, d, par = heapq.heappop(openq)
        if (node, d) in came:
            continue
        came[(node, d)] = par
        n += 1
        if n > limit:
            return None
        if node in tset:
            path, k = [], (node, d)
            while k is not None:
                path.append(k[0]); k = came[k]
            return path[::-1]
        li, x, y = node
        ml = masks[li]
        for di, (dx, dy) in enumerate(DIRS):
            nx_, ny_ = x + dx, y + dy
            if not (0 <= nx_ < NX and 0 <= ny_ < NY) or ml[nx_, ny_]:
                continue
            if dx and dy and (ml[x + dx, y] or ml[x, y + dy]):
                continue
            ng = g + (1.4142 if dx and dy else 1.0) * LAYER_W[li] + (BEND_COST if d not in (-1, di) else 0) \
                + (pw if pens[li][nx_, ny_] else 0.0)
            nn = (li, nx_, ny_)
            if best.get((nn, di), 1e18) <= ng:
                continue
            best[(nn, di)] = ng
            heapq.heappush(openq, (ng + h(nx_, ny_), ng, nn, di, (node, d)))
        if not vmask[x, y]:
            for l2 in layers:
                if l2 != li and not masks[l2][x, y]:
                    nn, ng = (l2, x, y), g + VIA_COST
                    if best.get((nn, -1), 1e18) <= ng:
                        continue
                    best[(nn, -1)] = ng
                    heapq.heappush(openq, (ng + h(x, y), ng, nn, -1, (node, d)))
    return None


def simplify(seg):
    if len(seg) < 3:
        return seg
    out = [seg[0]]
    for i in range(1, len(seg) - 1):
        a, b, c = out[-1], seg[i], seg[i + 1]
        if (b[0] - a[0]) * (c[1] - b[1]) != (b[1] - a[1]) * (c[0] - b[0]):
            out.append(b)
    out.append(seg[-1])
    return out


def gxy(x, y):
    return ox + x * G, oy + y * G


def commit(net, path, width, via_d, via_drill, tracks, vias):
    me, clr = NET_ID[net], cls_of(net)[1]
    segs, cur, curl = [], [], path[0][0]
    for li, x, y in path:
        if li != curl:
            segs.append((curl, cur)); cur = []
            vias.append((net, x, y, via_d, via_drill))
            for l2 in range(3):
                OBS[l2].append(capsule_obs(me, *gxy(x, y), *gxy(x, y), via_d / 2, clr))
            curl = li
        cur.append((x, y))
    segs.append((curl, cur))
    for li, cells in segs:
        pts = simplify(cells)
        tracks.append((net, li, pts, width))
        if len(pts) == 1:
            continue
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            OBS[li].append(capsule_obs(me, *gxy(ax, ay), *gxy(bx, by), width / 2, clr))


def route_net(net, tracks, vias, failed):
        w, _ = cls_of(net)
        vd, vdr = (PVIA_D, PVIA_DRILL) if cls_name(net) == "Power" else (VIA_D, VIA_DRILL)
        pads = sorted(pads_by_net[net], key=lambda p: (not p["tht"], -(p["box"][2] - p["box"][0]) * (p["box"][3] - p["box"][1])))
        tree = pad_cells(pads[0])
        done, todo = [pads[0]], pads[1:]
        roots_tried = 1
        while todo:
            todo.sort(key=lambda p: min((p["x"] - q["x"]) ** 2 + (p["y"] - q["y"]) ** 2 for q in done))
            p = todo.pop(0)
            tgt = pad_cells(p)
            path = astar(net, tree, tgt, w, vd)
            ww, vvd, vvdr = w, vd, vdr
            if path is None and w > 0.25:
                ww, vvd, vvdr = 0.25, VIA_D, VIA_DRILL
                path = astar(net, tree, tgt, ww, vvd)
            if path is None and len(done) == 1 and roots_tried < 4 and todo:
                # root pad may be boxed in: restart this net from another pad
                todo.append(done[0]); done = [p]; tree = tgt; roots_tried += 1
                continue
            if path is None:
                failed.append((net, p["ref"], p["num"])); continue
            commit(net, path, ww, vvd, vvdr, tracks, vias)
            tree |= set(path) | tgt
            done.append(p)


def route_all(priority):
    for li in range(3):
        OBS[li] = list(BASE_OBS[li])
    tracks, vias, failed = [], [], []
    for net in sorted(PLANE):
        for p in pads_by_net.get(net, []):
            if p["tht"] or len(p["layers"]) == 3 or p.get("thermal_vias"):
                continue
            vm = np.zeros((NX, NY), bool)
            roomy = np.zeros((NX, NY), bool)
            for li in range(3):
                vm |= blocked(net, li, VIA_D)
                roomy |= blocked(net, li, VIA_D + 1.2)
            cx, cy = to_grid(p["x"], p["y"])
            src = pad_cells(p)
            cand = [(p["layers"][0], cx + dx, cy + dy) for dx in range(-12, 13) for dy in range(-12, 13)
                    if 0 <= cx + dx < NX and 0 <= cy + dy < NY and not vm[cx + dx, cy + dy] and (dx, dy) != (0, 0)]
            cand.sort(key=lambda c: ((0 if not roomy[c[1], c[2]] else 25) + math.hypot(c[1] - cx, c[2] - cy)))
            path = astar(net, src, set(cand[:20]), 0.2, VIA_D, layers=(p["layers"][0],), limit=40000) if cand else None
            if not path:
                failed.append((net, p["ref"], p["num"])); continue
            commit(net, path, 0.2, VIA_D, VIA_DRILL, tracks, vias)
            li, x, y = path[-1]
            vias.append((net, x, y, VIA_D, VIA_DRILL))
            for l2 in range(3):
                OBS[l2].append(capsule_obs(NET_ID[net], *gxy(x, y), *gxy(x, y), VIA_D / 2, cls_of(net)[1]))
    order = sorted([n for n in pads_by_net if n not in PLANE and len(pads_by_net[n]) > 1],
                   key=lambda n: (0 if n in priority else 1, 0 if cls_name(n) == "Power" else 1, len(pads_by_net[n])))
    for net in order:
        route_net(net, tracks, vias, failed)
    return tracks, vias, failed


def write_board(tracks, vias):
    bd = pcbnew.LoadBoard(SRC)
    nets = bd.GetNetsByName()
    for net, li, pts, w in tracks:
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(bd)
            t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(ox + ax * G), pcbnew.FromMM(oy + ay * G)))
            t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(ox + bx * G), pcbnew.FromMM(oy + by * G)))
            t.SetWidth(pcbnew.FromMM(w)); t.SetLayer(LAYERS[li]); t.SetNet(nets[net])
            bd.Add(t)
    kept = []
    for net, x, y, d, drill in vias:
        near = next(((kx, ky) for (kn, kx, ky) in kept if kn == net and (net in PLANE or (kx, ky) == (x, y))
                     and math.hypot(kx - x, ky - y) * G < 0.9), None)
        if near is not None:
            if near != (x, y):  # merge: bridge to the kept via on every routing layer
                for li in (0,):
                    t = pcbnew.PCB_TRACK(bd)
                    t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(ox + x * G), pcbnew.FromMM(oy + y * G)))
                    t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(ox + near[0] * G), pcbnew.FromMM(oy + near[1] * G)))
                    t.SetWidth(pcbnew.FromMM(0.2)); t.SetLayer(LAYERS[li]); t.SetNet(nets[net])
                    bd.Add(t)
            continue
        kept.append((net, x, y))
        v = pcbnew.PCB_VIA(bd)
        v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(ox + x * G), pcbnew.FromMM(oy + y * G)))
        v.SetWidth(pcbnew.FromMM(d)); v.SetDrill(pcbnew.FromMM(drill)); v.SetNet(nets[net])
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        bd.Add(v)
    bd.Save(DST)


def rip(net, tracks, vias):
    me = NET_ID[net]
    for li in range(3):
        OBS[li] = [o for o in OBS[li] if not (o.trk and o.net == me)]
    tracks[:] = [t for t in tracks if t[0] != net]
    vias[:] = [v for v in vias if v[0] != net]


def nets_near(x, y, r, tracks, vias):
    out = set()
    for net, li, pts, w in tracks:
        if net in PLANE:
            continue
        for (ax, ay) in pts:
            if math.hypot(ox + ax * G - x, oy + ay * G - y) < r:
                out.add(net); break
    for net, vx, vy, d, dr in vias:
        if net not in PLANE and math.hypot(ox + vx * G - x, oy + vy * G - y) < r:
            out.add(net)
    return out


def repair(tracks, vias, failed, rounds=12):
    import random
    rnd = random.Random(1)
    for it in range(rounds):
        if not failed:
            break
        fnets = list(dict.fromkeys(f[0] for f in failed if f[0] not in PLANE))
        victims = set()
        for net, ref, num in failed:
            p = next(q for q in pads_by_net[net] if q["ref"] == ref and q["num"] == num)
            victims |= nets_near(p["x"], p["y"], 2.5 + it * 0.5, tracks, vias)
        victims -= set(fnets)
        victims = set(rnd.sample(sorted(victims), min(len(victims), 6 + it)))
        for n in fnets + sorted(victims):
            rip(n, tracks, vias)
        newfailed = [f for f in failed if f[0] in PLANE]
        others = sorted(victims)
        rnd.shuffle(others)
        for n in fnets + others:
            route_net(n, tracks, vias, newfailed)
        # keep any old failures of nets we did not touch
        newfailed += [f for f in failed if f[0] not in fnets and f[0] not in victims and f[0] not in PLANE]
        failed = newfailed
        print("  repair", it, "failed", len(failed), failed, flush=True)
    return tracks, vias, failed


if __name__ == "__main__":
    tracks, vias, failed = route_all(["USB_DN", "USB_DP", "DASH_CANL", "DASH_CANH", "IMA_CANH", "IMA_CANL", "MCM_CANH", "MCM_CANL", "CAN1H", "CAN1L"])
    print("PASS 0 failed", len(failed), failed, flush=True)
    write_board(tracks, vias)
    tracks, vias, failed = repair(tracks, vias, failed)
    write_board(tracks, vias)
    print("FINAL failed", len(failed), failed, flush=True)
    raise SystemExit(0)


if False:
    priority, best = [], None
    for PASS in range(int(sys.argv[3]) if len(sys.argv) > 3 else 4):
        tracks, vias, failed = route_all(priority)
        print("PASS", PASS, "failed", len(failed), failed, flush=True)
        if best is None or len(failed) < len(best[2]):
            best = (tracks, vias, failed)
            write_board(tracks, vias)
            print("saved", len(failed), flush=True)
        if not failed:
            break
        priority = list(dict.fromkeys([f[0] for f in failed if f[0] not in PLANE] + priority))
