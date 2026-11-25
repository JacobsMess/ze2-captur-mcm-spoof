"""Finish routing on an already-routed board: import its tracks/vias as obstacles, then route any
unconnected pads of the given nets with fine rules (0.12 mm width / 0.12 mm clearance, within JLCPCB 4-layer
capability). Reports KiCad's own unconnected-item count before and after."""
import math
import sys

src_code = open("route.py").read()
src_code = src_code[:src_code.index('def rip(net')]
sys.argv = ["route.py", sys.argv[1], sys.argv[2]] + sys.argv[3:]
exec(src_code)  # noqa: S102 - our own router module

FINE_W, FINE_CLR = 0.12, 0.12
bd = pcbnew.LoadBoard(SRC)
bd.BuildConnectivity()
print("unconnected before:", bd.GetConnectivity().GetUnconnectedCount(True))

tracks, vias = [], []
li_of = {pcbnew.F_Cu: 0, pcbnew.In2_Cu: 1, pcbnew.B_Cu: 2}
for t in bd.GetTracks():
    net = t.GetNetname()
    if net not in NET_ID:
        continue
    me, clr = NET_ID[net], cls_of(net)[1]
    if t.GetClass() == "PCB_VIA":
        x, y = pcbnew.ToMM(t.GetPosition().x), pcbnew.ToMM(t.GetPosition().y)
        for l2 in range(3):
            OBS[l2].append(capsule_obs(me, x, y, x, y, pcbnew.ToMM(t.GetWidth()) / 2, clr))
    else:
        li = li_of.get(t.GetLayer())
        if li is None:
            continue
        a, b = t.GetStart(), t.GetEnd()
        OBS[li].append(capsule_obs(me, pcbnew.ToMM(a.x), pcbnew.ToMM(a.y), pcbnew.ToMM(b.x), pcbnew.ToMM(b.y),
                                   pcbnew.ToMM(t.GetWidth()) / 2, clr))

_blocked = blocked


def blocked_fine(net, li, width):
    me = NET_ID[net]
    m = STATIC[li].copy()
    for o in OBS[li]:
        if o.net != me:
            m[o.sl] |= o.dist < width / 2 + max(o.clr, FINE_CLR) + 0.03
    return m


globals()["blocked"] = blocked_fine


def pad_connected_cells(net):
    """Cells already belonging to the net: its pads + its existing copper (for tree growth)."""
    cells = set()
    for p in pads_by_net[net]:
        cells |= pad_cells(p)
    return cells


new_tracks, new_vias = [], []
for net in sys.argv[3:]:
    # Group pads by KiCad connectivity cluster: route each unconnected pad to the rest of the net
    conn = bd.GetConnectivity()
    items = [p for f in bd.GetFootprints() for p in f.Pads() if p.GetNetname() == net]
    clusters, seen = [], set()
    for p in items:
        key = (p.GetParent().GetReference(), p.GetNumber())
        if key in seen:
            continue
        grp = [p] + [q for q in conn.GetConnectedPads(p) if q.GetNetname() == net]
        grp = list({(q.GetParent().GetReference(), q.GetNumber()): q for q in grp}.values())
        seen |= {(q.GetParent().GetReference(), q.GetNumber()) for q in grp}
        clusters.append(grp)
    clusters.sort(key=len, reverse=True)
    print(net, "pad clusters:", [[(q.GetParent().GetReference(), q.GetNumber()) for q in c] for c in clusters])
    padinfo = {(q["ref"], q["num"]): q for q in pads_by_net[net]}
    main = set()
    for q in clusters[0]:
        main |= pad_cells(padinfo[(q.GetParent().GetReference(), q.GetNumber())])
    for c in clusters[1:]:
        tgt = set()
        for q in c:
            tgt |= pad_cells(padinfo[(q.GetParent().GetReference(), q.GetNumber())])
        path = astar(net, main, tgt, FINE_W, VIA_D, limit=2000000)
        if path is None:
            path = astar(net, tgt, main, FINE_W, VIA_D, limit=2000000)
        print("  cluster", [(q.GetParent().GetReference(), q.GetNumber()) for q in c], "->", "ok" if path else "FAILED")
        if path:
            commit(net, path, FINE_W, VIA_D, VIA_DRILL, new_tracks, new_vias)
            main |= set(path) | tgt

nets = bd.GetNetsByName()
for net, li, pts, w in new_tracks:
    for (ax, ay), (bx, by) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(bd)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(ox + ax * G), pcbnew.FromMM(oy + ay * G)))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(ox + bx * G), pcbnew.FromMM(oy + by * G)))
        t.SetWidth(pcbnew.FromMM(w)); t.SetLayer(LAYERS[li]); t.SetNet(nets[net])
        bd.Add(t)
for net, x, y, d, drill in new_vias:
    v = pcbnew.PCB_VIA(bd)
    v.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(ox + x * G), pcbnew.FromMM(oy + y * G)))
    v.SetWidth(pcbnew.FromMM(d)); v.SetDrill(pcbnew.FromMM(drill)); v.SetNet(nets[net])
    v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
    bd.Add(v)
bd.BuildConnectivity()
print("unconnected after:", bd.GetConnectivity().GetUnconnectedCount(True))
bd.Save(DST)
