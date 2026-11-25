import pcbnew, sys, re, collections
b = pcbnew.LoadBoard(sys.argv[1])
if len(sys.argv) > 2:
    pcbnew.ZONE_FILLER(b).Fill(b.Zones())
pcbnew.WriteDRCReport(b, "/tmp/drc.txt", pcbnew.EDA_UNITS_MILLIMETRES, True)
t = open("/tmp/drc.txt").read()
print(collections.Counter(re.findall(r"^\[(\w+)\]", t, re.M)))
for blk in re.split(r"\n(?=\[)", t):
    if blk.startswith(("[unconnected", "[clearance", "[shorting", "[tracks_crossing", "[hole_clearance", "[copper_edge")):
        print(blk.strip().replace("\n", " | ")[:260])
