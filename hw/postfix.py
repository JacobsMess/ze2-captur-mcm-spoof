"""Post-route fixes: restore vias at same-net layer changes that lack one."""
import sys
from collections import defaultdict

import pcbnew

b = pcbnew.LoadBoard(sys.argv[1])
ends = defaultdict(set)   # (net, x, y) -> layers with a track end there
vias = set()
pads = set()
for t in b.GetTracks():
    if t.GetClass() == "PCB_VIA":
        p = t.GetPosition(); vias.add((t.GetNetname(), p.x, p.y))
    else:
        for p in (t.GetStart(), t.GetEnd()):
            ends[(t.GetNetname(), p.x, p.y)].add(t.GetLayer())
for f in b.GetFootprints():
    for p in f.Pads():
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
            q = p.GetPosition(); pads.add((p.GetNetname(), q.x, q.y))
nets = b.GetNetsByName()
added = 0
for (net, x, y), layers in ends.items():
    if len(layers) > 1 and (net, x, y) not in vias:
        # skip if inside a through-hole pad of the same net
        if any(n == net and abs(px - x) < pcbnew.FromMM(0.8) and abs(py - y) < pcbnew.FromMM(0.8) for n, px, py in pads):
            continue
        v = pcbnew.PCB_VIA(b)
        v.SetPosition(pcbnew.VECTOR2I(x, y))
        big = net in ("VBAT_P", "+5V") or net.startswith(("VIG_", "VCOIL", "COIL_", "BMS12V", "PUMP_N", "BUCK_SW", "LM_GATE"))
        v.SetWidth(pcbnew.FromMM(0.8 if big else 0.6)); v.SetDrill(pcbnew.FromMM(0.4 if big else 0.3))
        v.SetNet(nets[net]); v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        b.Add(v); added += 1
print("vias restored:", added)
b.Save(sys.argv[2])
