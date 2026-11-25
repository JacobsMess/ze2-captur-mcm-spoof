"""v0.4 ECO on the routed v0.3 board: relay-gated IMA terminations.

Removes the always-on CAN3 split termination (R86/R87/JP13/C93 + their copper), then places the new
termination parts from build_board.PARTS with their nets. Routing of the new connections is done by
route_v04.py so the rest of the proven v0.3 layout is untouched.
usage: python3 patch_v04.py routed_v03.kicad_pcb patched.kicad_pcb
"""
import math
import sys

import pcbnew

sys.argv, SRC, DST = sys.argv[:1], sys.argv[1], sys.argv[2]
import build_board as BB  # noqa: E402  (PARTS is the netlist source of truth)

REMOVE = ["R86", "R87", "JP13", "C93"]
ADD = ["R86", "JP13", "R96", "JP12", "U22", "R97"]
DEAD_NETS = {"TERM3", "TERM3_MID"}
PRUNE_NETS = {"IMA_CANH", "IMA_CANL"}

b = pcbnew.LoadBoard(SRC)
for ref in REMOVE:
    b.Delete(b.FindFootprintByReference(ref))
for t in list(b.GetTracks()):
    if t.GetNetname() in DEAD_NETS:
        b.Delete(t)


def net(name):
    n = b.FindNet(name)
    if n is None:
        n = pcbnew.NETINFO_ITEM(b, name)
        b.Add(n)
    return n


for ref in ADD:
    p = BB.PARTS[ref]
    fp = pcbnew.FootprintLoad(BB.FP + p["fp"][0] + ".pretty", p["fp"][1])
    fp.SetReference(ref); fp.SetValue(p["val"]); fp.SetPosition(BB.mm(*p["pos"]))
    b.Add(fp)
    fp.SetOrientationDegrees(p["rot"])
    fp.Reference().SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(0.8), pcbnew.FromMM(0.8)))
    fp.Reference().SetTextThickness(pcbnew.FromMM(0.12))
    fp.Value().SetVisible(False)
    fp.SetLocalClearance(0)
    for pad in fp.Pads():
        pad.SetLocalClearance(0)
        pad.SetNet(net(p["nets"][pad.GetNumber()]))
k4 = b.FindFootprintByReference("K4")
for pad in k4.Pads():
    if pad.GetNumber() in ("4", "5"):
        pad.SetNet(net(BB.PARTS["K4"]["nets"][pad.GetNumber()]))


# prune IMA_CAN stubs that used to run to the old termination (track ends touching nothing)
def anchored(pt, item, net_items, pads):
    for pd in pads:
        if pd.HitTest(pt):
            return True
    for o in net_items:
        if o is item:
            continue
        if o.Type() == pcbnew.PCB_VIA_T:
            if math.dist((pt.x, pt.y), (o.GetPosition().x, o.GetPosition().y)) <= o.GetWidth() / 2:
                return True
        elif (o.IsOnLayer(item.GetLayer()) if item.Type() != pcbnew.PCB_VIA_T else True) and o.HitTest(pt, 1000):
            return True
    return False


changed = True
while changed:
    changed = False
    for name in PRUNE_NETS:
        items = [t for t in b.GetTracks() if t.GetNetname() == name]
        pads = [pd for pd in b.GetPads() if pd.GetNetname() == name]
        for t in items:
            ends = [t.GetPosition()] if t.Type() == pcbnew.PCB_VIA_T else [t.GetStart(), t.GetEnd()]
            if t.Type() == pcbnew.PCB_VIA_T:
                touching = sum(1 for o in items if o is not t and o.Type() != pcbnew.PCB_VIA_T and o.HitTest(t.GetPosition(), 1000))
                if touching < 2 and not any(pd.HitTest(t.GetPosition()) for pd in pads):
                    b.Delete(t); changed = True; break
            elif not all(anchored(e, t, items, pads) for e in ends):
                b.Delete(t); changed = True; break
b.Save(DST)
print("patched ->", DST)
