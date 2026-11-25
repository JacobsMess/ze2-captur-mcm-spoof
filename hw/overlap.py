import pcbnew, sys
b = pcbnew.LoadBoard(sys.argv[1])
fps = list(b.GetFootprints())
cy = {f.GetReference(): f.GetCourtyard(pcbnew.F_CrtYd) for f in fps}
bad = []
for i, a in enumerate(fps):
    for c in fps[i + 1:]:
        pa, pc = cy[a.GetReference()], cy[c.GetReference()]
        if pa.OutlineCount() and pc.OutlineCount() and pa.Collide(pc):
            bad.append((a.GetReference(), c.GetReference()))
print(bad)
