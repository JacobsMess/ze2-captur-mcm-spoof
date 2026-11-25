"""Silkscreen tidy: place every reference designator where it is readable and clear of pads, other silk,
the board edge and the slot; clip board-level outline boxes and footprint silk around obstacles.

usage: python3 tidy_silk.py in.kicad_pcb out.kicad_pcb
Works on a 0.05 mm raster of the top side. Hard obstacles: pads (+0.15), silk (+0.12), edges/slot (+0.4),
already-placed labels (+0.12). Soft obstacle: other footprints' courtyards (label would sit under a part).
"""
import sys

import numpy as np
import pcbnew
from PIL import Image, ImageDraw

SRC, DST = sys.argv[1], sys.argv[2]
OX = OY = 50.0
BW, BH = 120.0, 98.0
RES = 20  # px per mm
PAD_CLR, SILK_CLR, EDGE_CLR = 0.15, 0.12, 0.4
SIZES = [(0.8, 0.15)]  # (text height, stroke): 0.8 mm board minimum, JLC minimum stroke 0.15 mm

b = pcbnew.LoadBoard(SRC)
mm = lambda v: pcbnew.ToMM(v)
NX, NY = int(BW * RES), int(BH * RES)


def px(x, y):
    return ((x) * RES, (y) * RES)


def new_layer():
    return Image.new("1", (NX, NY), 0)


def seg_list(shape):
    """F.SilkS shape -> list of ((x0,y0),(x1,y1),width) in board mm."""
    w = mm(shape.GetWidth())
    st = shape.GetShape()
    if st == pcbnew.SHAPE_T_RECT:
        bb = shape.GetBoundingBox()
        x0, y0, x1, y1 = mm(bb.GetLeft()) - OX + w / 2, mm(bb.GetTop()) - OY + w / 2, mm(bb.GetRight()) - OX - w / 2, mm(bb.GetBottom()) - OY - w / 2
        c = [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
        return [(c[i], c[(i + 1) % 4], w) for i in range(4)]
    if st == pcbnew.SHAPE_T_SEGMENT:
        s, e = shape.GetStart(), shape.GetEnd()
        return [((mm(s.x) - OX, mm(s.y) - OY), (mm(e.x) - OX, mm(e.y) - OY), w)]
    if st in (pcbnew.SHAPE_T_POLY, pcbnew.SHAPE_T_ARC, pcbnew.SHAPE_T_CIRCLE):
        pts = []
        if st == pcbnew.SHAPE_T_POLY:
            ol = shape.GetPolyShape().Outline(0)
            pts = [(mm(ol.CPoint(i).x) - OX, mm(ol.CPoint(i).y) - OY) for i in range(ol.PointCount())]
            pts.append(pts[0])
        else:
            bb = shape.GetBoundingBox()
            x0, y0, x1, y1 = mm(bb.GetLeft()) - OX, mm(bb.GetTop()) - OY, mm(bb.GetRight()) - OX, mm(bb.GetBottom()) - OY
            pts = [(x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)]
        return [(pts[i], pts[i + 1], w) for i in range(len(pts) - 1)]
    return []


def draw_seg(img, a, c, w):
    d = ImageDraw.Draw(img)
    d.line([px(*a), px(*c)], fill=1, width=max(1, int(round(w * RES))))
    r = w / 2 * RES
    for p in (a, c):
        x, y = px(*p); d.ellipse([x - r, y - r, x + r, y + r], fill=1)


def draw_rect(img, x0, y0, x1, y1):
    ImageDraw.Draw(img).rectangle([px(x0, y0), px(x1, y1)], fill=1)


def bbox_mm(item):
    bb = item.GetBoundingBox()
    return mm(bb.GetLeft()) - OX, mm(bb.GetTop()) - OY, mm(bb.GetRight()) - OX, mm(bb.GetBottom()) - OY


# --- obstacle rasters -------------------------------------------------------------------------------
pads = new_layer()
for p in b.GetPads():
    if p.IsOnLayer(pcbnew.F_Cu) or p.IsOnLayer(pcbnew.F_Mask) or p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
        x0, y0, x1, y1 = bbox_mm(p)
        draw_rect(pads, x0 - PAD_CLR, y0 - PAD_CLR, x1 + PAD_CLR, y1 + PAD_CLR)
for v in b.GetTracks():  # vias are mask-tented, silk over them is fine; skip
    pass
edges = new_layer()
m = EDGE_CLR
draw_rect(edges, -1, -1, BW + 1, m); draw_rect(edges, -1, BH - m, BW + 1, BH + 1)
draw_rect(edges, -1, -1, m, BH + 1); draw_rect(edges, BW - m, -1, BW + 1, BH + 1)
for d in b.GetDrawings():  # interior Edge.Cuts (isolation slots)
    if d.GetLayer() == pcbnew.Edge_Cuts:
        x0, y0, x1, y1 = bbox_mm(d)
        if x0 > 1 and y0 > 1 and x1 < BW - 1 and y1 < BH - 1:
            draw_rect(edges, x0 - m, y0 - m, x1 + m, y1 + m)
for f in b.GetFootprints():  # mounting holes: keep labels off the hole and its ring
    for p in f.Pads():
        if p.GetAttribute() == pcbnew.PAD_ATTRIB_NPTH:
            x0, y0, x1, y1 = bbox_mm(p)
            draw_rect(edges, x0 - 0.5, y0 - 0.5, x1 + 0.5, y1 + 0.5)

hard_static = np.array(pads) | np.array(edges)


def clip_segments(segs, block, step=0.05):
    """Split segments into the runs whose centreline (+half width) stays out of `block` (bool raster)."""
    out = []
    for a, c, w in segs:
        L = np.hypot(c[0] - a[0], c[1] - a[1])
        n = max(2, int(L / step) + 1)
        t = np.linspace(0, 1, n)
        xs, ys = a[0] + (c[0] - a[0]) * t, a[1] + (c[1] - a[1]) * t
        ix = np.clip((xs * RES).astype(int), 0, NX - 1); iy = np.clip((ys * RES).astype(int), 0, NY - 1)
        ok = ~block[iy, ix]
        start = None
        for i in range(n + 1):
            if i < n and ok[i]:
                start = i if start is None else start
            elif start is not None:
                if i - 1 - start >= 3:  # keep runs > ~0.15 mm
                    out.append(((float(xs[start]), float(ys[start])), (float(xs[i - 1]), float(ys[i - 1])), float(w)))
                start = None
    return out


def grow(mask, r_mm):
    from scipy.ndimage import binary_dilation
    r = int(round(r_mm * RES))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    return binary_dilation(mask, structure=(xx * xx + yy * yy) <= r * r)


def sat(a):
    s = np.zeros((a.shape[0] + 1, a.shape[1] + 1), np.int32)
    s[1:, 1:] = a.astype(np.int32).cumsum(0).cumsum(1)
    return s


def hits(s, x0, y0, x1, y1):
    i0, j0 = max(0, int(y0 * RES)), max(0, int(x0 * RES))
    i1, j1 = min(NY, int(np.ceil(y1 * RES))), min(NX, int(np.ceil(x1 * RES)))
    if i1 <= i0 or j1 <= j0:
        return 10 ** 9
    return s[i1, j1] - s[i0, j1] - s[i1, j0] + s[i0, j0]


# --- 1. footprint silk: trim at board edge / slot / exposed pads ------------------------------------
pad_block = grow(np.array(pads), 0.08) | np.array(edges)
edge_block = np.array(edges)
fp_silk = new_layer()
trimmed = 0
for f in b.GetFootprints():
    for g in list(f.GraphicalItems()):
        if g.GetLayer() != pcbnew.F_SilkS or not isinstance(g, pcbnew.FP_SHAPE):
            continue
        segs = seg_list(g)
        if g.GetShape() not in (pcbnew.SHAPE_T_SEGMENT, pcbnew.SHAPE_T_RECT):
            x0, y0, x1, y1 = bbox_mm(g)  # arcs/circles (pin-1 notches): drop only if they reach an edge or slot
            if edge_block[max(0, int(y0 * RES)):int(y1 * RES) + 1, max(0, int(x0 * RES)):int(x1 * RES) + 1].any():
                f.Delete(g); trimmed += 1
                continue
            for a, c, w in segs:
                draw_seg(fp_silk, a, c, w + 2 * SILK_CLR)
            continue
        keep = clip_segments(segs, pad_block)
        whole = sum(np.hypot(c[0] - a[0], c[1] - a[1]) for a, c, _ in segs)
        kept = sum(np.hypot(c[0] - a[0], c[1] - a[1]) for a, c, _ in keep)
        if kept < whole - 0.06:
            f.Delete(g); trimmed += 1
            for a, c, w in keep:
                s = pcbnew.FP_SHAPE(f, pcbnew.SHAPE_T_SEGMENT)
                s.SetLayer(pcbnew.F_SilkS); s.SetWidth(pcbnew.FromMM(w))
                s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0] + OX), pcbnew.FromMM(a[1] + OY)))
                s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(c[0] + OX), pcbnew.FromMM(c[1] + OY)))
                s.SetLocalCoord()
                f.Add(s)
                draw_seg(fp_silk, a, c, w + 2 * SILK_CLR)
        else:
            for a, c, w in segs:
                draw_seg(fp_silk, a, c, w + 2 * SILK_CLR)
fp_silk = np.array(fp_silk)

# --- 2. board-level outline boxes: break them where they cross parts ------------------------------
crt = new_layer()
for f in b.GetFootprints():
    cy = f.GetCourtyard(pcbnew.F_CrtYd)
    if not cy.IsEmpty():
        x0, y0, x1, y1 = [mm(v) - o for v, o in ((cy.BBox().GetLeft(), OX), (cy.BBox().GetTop(), OY), (cy.BBox().GetRight(), OX), (cy.BBox().GetBottom(), OY))]
        draw_rect(crt, x0, y0, x1, y1)
crt = np.array(crt)
btext = new_layer()
for d in b.GetDrawings():
    if d.GetLayer() == pcbnew.F_SilkS and isinstance(d, pcbnew.PCB_TEXT):
        hs0 = sat(hard_static | fp_silk)
        x0, y0, x1, y1 = bbox_mm(d)
        p0 = d.GetPosition()
        best = None
        for dy in np.arange(-10, 10.01, 0.25):
            for dx in np.arange(-14, 14.01, 0.25):
                r = (x0 + dx - SILK_CLR, y0 + dy - SILK_CLR, x1 + dx + SILK_CLR, y1 + dy + SILK_CLR)
                if r[0] < 0 or r[1] < 0 or r[2] > BW or r[3] > BH or hits(hs0, *r):
                    continue
                if best is None or np.hypot(dx, dy) < best[0]:
                    best = (np.hypot(dx, dy), dx, dy)
        if best and best[0] > 0:
            d.SetPosition(pcbnew.VECTOR2I(p0.x + pcbnew.FromMM(float(best[1])), p0.y + pcbnew.FromMM(float(best[2]))))
        x0, y0, x1, y1 = bbox_mm(d)
        draw_rect(btext, x0 - 0.3, y0 - 0.3, x1 + 0.3, y1 + 0.3)
outline_block = grow(fp_silk, 0.1) | crt | grow(np.array(pads), 0.1) | np.array(edges) | np.array(btext)
board_silk = new_layer()
for d in list(b.GetDrawings()):
    if d.GetLayer() == pcbnew.F_SilkS and isinstance(d, pcbnew.PCB_SHAPE):
        keep = clip_segments(seg_list(d), outline_block)
        b.Delete(d)
        for a, c, w in keep:
            s = pcbnew.PCB_SHAPE(b, pcbnew.SHAPE_T_SEGMENT)
            s.SetLayer(pcbnew.F_SilkS); s.SetWidth(pcbnew.FromMM(w))
            s.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0] + OX), pcbnew.FromMM(a[1] + OY)))
            s.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(c[0] + OX), pcbnew.FromMM(c[1] + OY)))
            b.Add(s)
            draw_seg(board_silk, a, c, w + 2 * SILK_CLR)
    elif d.GetLayer() == pcbnew.F_SilkS and isinstance(d, pcbnew.PCB_TEXT):
        x0, y0, x1, y1 = bbox_mm(d)
        draw_rect(board_silk, x0 - SILK_CLR, y0 - SILK_CLR, x1 + SILK_CLR, y1 + SILK_CLR)
board_silk = np.array(board_silk)

# --- 3. reference designators ----------------------------------------------------------------------
hard = hard_static | fp_silk | board_silk
labels = np.zeros_like(hard)


def courtyard(f):
    cy = f.GetCourtyard(pcbnew.F_CrtYd)
    bb = cy.BBox() if not cy.IsEmpty() else f.GetBoundingBox(False, False)
    return mm(bb.GetLeft()) - OX, mm(bb.GetTop()) - OY, mm(bb.GetRight()) - OX, mm(bb.GetBottom()) - OY


def style(t, f, h, sw, ang):
    t.SetTextSize(pcbnew.VECTOR2I(pcbnew.FromMM(float(h)), pcbnew.FromMM(float(h))))
    t.SetTextThickness(pcbnew.FromMM(float(sw)))
    t.SetHorizJustify(pcbnew.GR_TEXT_H_ALIGN_CENTER); t.SetVertJustify(pcbnew.GR_TEXT_V_ALIGN_CENTER)
    t.SetKeepUpright(True)
    t.SetTextAngle(pcbnew.EDA_ANGLE(ang - f.GetOrientationDegrees(), pcbnew.DEGREES_T))  # FP text angle is parent-relative


def measure(t, f, h, sw, ang):
    style(t, f, h, sw, ang)
    bb = t.GetBoundingBox()
    return mm(bb.GetWidth()), mm(bb.GetHeight())


fps = [f for f in b.GetFootprints() if f.Reference().IsVisible()]
fps.sort(key=lambda f: (courtyard(f)[2] - courtyard(f)[0]) * (courtyard(f)[3] - courtyard(f)[1]))  # small parts first: least room
own_crt = {}
for f in fps:
    own_crt[f.GetReference()] = courtyard(f)
crt_sat = None
placed, failed, inside = 0, [], 0


def place(f, maxgap, clr):
    global placed, inside
    t = f.Reference()
    ref = f.GetReference()
    cx0, cy0, cx1, cy1 = own_crt[ref]
    ccx, ccy = (cx0 + cx1) / 2, (cy0 + cy1) / 2
    other = crt.copy()  # soft obstacle = everyone else's courtyard
    i0, i1, j0, j1 = int(cy0 * RES), int(np.ceil(cy1 * RES)), int(cx0 * RES), int(np.ceil(cx1 * RES))
    other[max(0, i0):i1, max(0, j0):j1] = False
    hs, ss = sat(hard | labels), sat(other)
    best = None
    for (h, sw) in SIZES:
        for ang in (0, 90):
            w_, h_ = measure(t, f, h, sw, ang)
            cands = [(ccx, ccy)]  # centre of own body (big parts)
            for gap in np.arange(0.05, maxgap, 0.15):
                for s_ in np.linspace(-0.5, 0.5, 9):
                    cands += [(ccx + s_ * (cx1 - cx0), cy0 - gap - h_ / 2), (ccx + s_ * (cx1 - cx0), cy1 + gap + h_ / 2),
                              (cx0 - gap - w_ / 2, ccy + s_ * (cy1 - cy0)), (cx1 + gap + w_ / 2, ccy + s_ * (cy1 - cy0))]
            for x, y in cands:
                r = (x - w_ / 2 - clr, y - h_ / 2 - clr, x + w_ / 2 + clr, y + h_ / 2 + clr)
                if r[0] < 0 or r[1] < 0 or r[2] > BW or r[3] > BH or hits(hs, *r):
                    continue
                under = hits(ss, *r) > 0
                score = np.hypot(x - ccx, y - ccy) + (6.0 if under else 0) + (0.3 if ang == 90 else 0) \
                    + (3.0 if (x, y) == (ccx, ccy) else 0)
                if best is None or score < best[0]:
                    best = (score, x, y, ang, h, sw)
    if best is None:
        return False
    _, x, y, ang, h, sw = best
    style(t, f, h, sw, ang)
    t.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(float(x + OX)), pcbnew.FromMM(float(y + OY))))
    x0, y0, x1, y1 = bbox_mm(t)  # rasterise the real bbox
    labels[max(0, int((y0 - clr) * RES)):int((y1 + clr) * RES) + 1, max(0, int((x0 - clr) * RES)):int((x1 + clr) * RES) + 1] = True
    placed += 1
    inside += (x, y) == (ccx, ccy)
    return True


for f in fps:
    if not place(f, 4.1, SILK_CLR):
        failed.append(f)
hidden = []
for f in failed:  # second pass: wider search, minimum DRC clearance
    if not place(f, 7.0, 0.03):
        f.Reference().SetVisible(False); hidden.append(f.GetReference())
failed = hidden
for f in b.GetFootprints():
    f.Value().SetVisible(False)
b.Save(DST)
print(f"placed {placed} labels ({inside} on own body), hidden {len(failed)}: {failed}; trimmed {trimmed} footprint silk shapes")
