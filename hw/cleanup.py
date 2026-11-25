"""Remove dangling vias and track ends left by ECO steps, only where KiCad connectivity shows nothing loses a connection.

usage: python3 cleanup.py board.kicad_pcb   (in place; run until it prints nothing)
"""
import sys, pcbnew
b=pcbnew.LoadBoard(sys.argv[1])
def unc(): b.BuildConnectivity(); return b.GetConnectivity().GetUnconnectedCount(False)
for it in range(30):
    base=unc(); done=False
    for t in list(b.GetTracks()):
        if t.Type()==pcbnew.PCB_VIA_T: continue
        v=pcbnew.VECTOR2I()
        if b.GetConnectivity().TestTrackEndpointDangling(t,False,v):
            k=t.Duplicate(); b.Delete(t)
            if unc()>base: b.Add(k)
            else: print('deleted', k.GetNetname()); done=True; break
    if not done: break
b.Save(sys.argv[1])
import re, math
pcbnew.ZONE_FILLER(b).Fill(b.Zones())
for it in range(10):
    pcbnew.WriteDRCReport(b, "/tmp/dg.txt", pcbnew.EDA_UNITS_MILLIMETRES, True)
    hits = re.findall(r"\[via_dangling\].*?@\(([\d.]+) mm, ([\d.]+) mm\): Via \[([^\]]*)\]", open("/tmp/dg.txt").read(), re.S)
    if not hits: break
    base = unc()
    for x, y, n in hits:
        for t in list(b.GetTracks()):
            if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == n and math.dist((pcbnew.ToMM(t.GetPosition().x), pcbnew.ToMM(t.GetPosition().y)), (float(x), float(y))) < 0.01:
                k = t.Duplicate(); b.Delete(t)
                if unc() > base: b.Add(k)
                else: print("deleted via", n)
                break
b.Save(sys.argv[1])
