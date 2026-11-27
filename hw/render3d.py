"""Populated 3D render of the board: KiCad VRML models where available, simple bodies for the rest.

usage: xvfb-run -a python3 render3d.py board.kicad_pcb top_texture.png out_prefix
Models come from a sparse checkout of kicad-packages3D (MODELS). Parts whose model is missing from that
mirror get a body sized from the footprint's F.Fab outline (PROC), coloured to suit the real part.
"""
import os
import re
import sys

import numpy as np
import pcbnew
import pyvista as pv
from PIL import Image

PCB, TEX, OUT = sys.argv[1:4]
MODELS = os.environ.get("KICAD_3D_DIRS", "/usr/share/kicad/3dmodels").split(":")  # e.g. KiCad 9 library first, then 7 for renamed models
THK = 1.6
OX = OY = 50.0  # board origin offset used by build_board (mm)
BW, BH = 120.0, 98.0

# parts whose exact model isn't in the KiCad 7 library: nearest real model, scaled to the footprint
#   fit = "body": model x/y scaled to the F.Fab body;  "all": to body + pads (leaded ICs);  None: as-is
SUBST = {
    "Fuse.3dshapes/Fuse_1812_4532Metric.wrl": ("Capacitor_SMD.3dshapes/C_1812_4532Metric.wrl", None, None),
    "Fuse.3dshapes/Fuse_2920_7451Metric.wrl": ("Capacitor_SMD.3dshapes/C_2816_7142Metric.wrl", "body", None),
    "Inductor_SMD.3dshapes/L_Bourns_SRP7028A_7.3x6.6mm.wrl": ("Inductor_SMD.3dshapes/L_Bourns_SRN6045TA.wrl", "body", 2.8),
    "Diode_SMD.3dshapes/D_SMA.wrl": ("Diode_SMD.3dshapes/D_SMB.wrl", "body", None),
    "Package_SON.3dshapes/VSON-8-1EP_3x3mm_P0.65mm_EP1.65x2.4mm.wrl": ("Package_SON.3dshapes/WSON-8-1EP_3x3mm_P0.5mm_EP1.6x2.0mm.wrl", None, None),
    "Capacitor_SMD.3dshapes/C_0603_1608Metric.wrl": ("Capacitor_SMD.3dshapes/C_0805_2012Metric.wrl", "body", 0.8),
    "Package_SO.3dshapes/SOIC-16W_7.5x10.3mm_P1.27mm.wrl": ("Package_SO.3dshapes/SOIC-18W_7.5x11.6mm_P1.27mm.wrl", "all", None),
    "Package_SO.3dshapes/VSSOP-8_2.3x2mm_P0.5mm.wrl": ("Package_SO.3dshapes/SOIC-8_3.9x4.9mm_P1.27mm.wrl", "all", 0.9),
    "Package_SO.3dshapes/SOP-4_3.8x4.1mm_P2.54mm.wrl": ("Package_SO.3dshapes/SOP-4_4.4x2.6mm_P1.27mm.wrl", "all", None),
    "Package_TO_SOT_SMD.3dshapes/SOT-353_SC-70-5.wrl": ("Package_TO_SOT_SMD.3dshapes/SOT-23-5.wrl", "all", 0.9),
    "ze2/ST_PowerSSO-16": ("Package_SO.3dshapes/TSSOP-16-1EP_4.4x5mm_Pitch0.65mm_EP3.4x5mm.wrl", "body", None),
    "ze2/PhotoMOS_DIP6_SMD": ("Package_DIP.3dshapes/SMDIP-6_W7.62mm.wrl", None, None),
    "ze2/Fuse_242": ("Resistor_SMD.3dshapes/R_2512_6332Metric.wrl", "body", 3.0),
}
FP_MODEL = {"ST_PowerSSO-16_3.9x4.9mm_P0.5mm_EP2.2x3.9mm": "ze2/ST_PowerSSO-16",  # custom footprints with no model
            "Panasonic_PhotoMOS_DIP6_SMD_W8.3mm": "ze2/PhotoMOS_DIP6_SMD",
            "Fuse_Littelfuse_242_SMD_L8.4mm_D3.0mm": "ze2/Fuse_242"}
BLACK, NYLON, METAL, TAN, DGREY = (0.09, 0.09, 0.10), (0.92, 0.89, 0.80), (0.78, 0.78, 0.80), (0.80, 0.68, 0.45), (0.22, 0.22, 0.24)
# procedural bodies: name fragment -> (height mm, colour, style)
PROC = {  # no Micro-Fit / Mini-Fit vertical headers in the KiCad 7 library: built from the real dimensions
    "Molex_Micro-Fit": (9.4, BLACK, "header"),
    "Molex_Mini-Fit": (9.6, NYLON, "header"),
}
LEAD = METAL


def parse_wrl(path):
    """KiCad StepUp VRML -> list of (colour, PolyData) in mm."""
    txt = open(path, errors="ignore").read()
    mats, out = {}, []
    for blk in re.split(r"\bShape\s*\{", txt)[1:]:
        m = re.search(r"material\s+DEF\s+(\S+)\s+Material\s*\{([^}]*)\}", blk)
        if m:
            c = re.search(r"diffuseColor\s+([\d.eE+-]+)\s+([\d.eE+-]+)\s+([\d.eE+-]+)", m.group(2))
            mats[m.group(1)] = tuple(float(v) for v in c.groups()) if c else (0.5, 0.5, 0.5)
            col = mats[m.group(1)]
        else:
            u = re.search(r"material\s+USE\s+(\S+)", blk)
            col = mats.get(u.group(1), (0.5, 0.5, 0.5)) if u else (0.5, 0.5, 0.5)
        pts = re.search(r"point\s*\[([^\]]*)\]", blk)
        idx = re.search(r"coordIndex\s*\[([^\]]*)\]", blk)
        if not (pts and idx):
            continue
        p = np.array(pts.group(1).replace(",", " ").split(), float).reshape(-1, 3) * 2.54
        ii = np.array(idx.group(1).replace(",", " ").split(), int)
        faces, cur = [], []
        for v in ii:
            if v < 0:
                if len(cur) >= 3:
                    faces += [len(cur)] + cur
                cur = []
            else:
                cur.append(int(v))
        if faces:
            out.append((col, pv.PolyData(p, np.array(faces))))
    return out


def fab_box(fp):
    xs, ys = [], []
    for g in fp.GraphicalItems():
        if g.GetLayer() in (pcbnew.F_Fab, pcbnew.B_Fab):
            bb = g.GetBoundingBox()
            xs += [bb.GetLeft(), bb.GetRight()]; ys += [bb.GetTop(), bb.GetBottom()]
    if not xs:
        bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
        xs, ys = [bb.GetLeft(), bb.GetRight()], [bb.GetTop(), bb.GetBottom()]
    mm = lambda v: pcbnew.ToMM(v)
    return mm(min(xs)) - OX, mm(min(ys)) - OY, mm(max(xs)) - OX, mm(max(ys)) - OY


def local_box(fp, mode, R, px, py):
    """Footprint body (or body+pads) bbox in the footprint's own frame, world orientation (y up)."""
    pts = []
    x0, y0, x1, y1 = fab_box(fp)
    pts += [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]
    if mode == "all":
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            for X, Y in ((bb.GetLeft(), bb.GetTop()), (bb.GetRight(), bb.GetBottom())):
                pts.append((pcbnew.ToMM(X) - OX, pcbnew.ToMM(Y) - OY))
    w = np.array([world(x, y)[:2] - world(px, py)[:2] for x, y in pts])
    loc = w @ R[:2, :2]  # inverse rotation
    return loc.min(0), loc.max(0)


def world(x, y, z=0.0):
    return np.array([x, BH - y, z])  # board y-down -> world y-up, board origin at bottom-left


def box(x0, y0, x1, y1, z0, z1):
    a, b = world(x0, y1, z0), world(x1, y0, z1)
    return pv.Box(bounds=(a[0], b[0], a[1], b[1], z0, z1))


def proc_meshes(fp, h, col, style):
    x0, y0, x1, y1 = fab_box(fp)
    z = THK
    if style == "chip":
        w = x1 - x0
        e = min(0.6, w * 0.18)
        return [(col, box(x0 + e, y0, x1 - e, y1, z, z + h)), (METAL, box(x0, y0, x0 + e, y1, z, z + h)),
                (METAL, box(x1 - e, y0, x1, y1, z, z + h))]
    if style == "ic":
        out = [(col, box(x0, y0, x1, y1, z + 0.1, z + h))]
        for pad in fp.Pads():
            bb = pad.GetBoundingBox()
            px0, py0 = pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY
            px1, py1 = pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY
            cx, cy = (px0 + px1) / 2, (py0 + py1) / 2
            if px1 - px0 > py1 - py0:  # lead runs in x towards the body
                xa, xb = (min(px0, x0), max(px1, x0)) if cx < x0 else (min(px0, x1), max(px1, x1))
                out.append((LEAD, box(xa, cy - 0.21, xb, cy + 0.21, z, z + 0.25)))
            else:
                ya, yb = (min(py0, y0), max(py1, y0)) if cy < y0 else (min(py0, y1), max(py1, y1))
                out.append((LEAD, box(cx - 0.21, ya, cx + 0.21, yb, z, z + 0.25)))
        out.append(((0.35, 0.35, 0.35), pv.Cylinder(center=world(x0 + 0.9, y0 + 0.9, z + h + 0.01), direction=(0, 0, 1), radius=0.35, height=0.02)))
        return out
    if style == "header":
        pins = []
        for pad in fp.Pads():
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_PTH:
                p = pad.GetPosition(); pins.append((pcbnew.ToMM(p.x) - OX, pcbnew.ToMM(p.y) - OY))
        pins = np.array(pins)
        xs, ys = np.unique(np.round(pins[:, 0], 2)), np.unique(np.round(pins[:, 1], 2))
        pitch = min(np.diff(xs).min() if len(xs) > 1 else 99, np.diff(ys).min() if len(ys) > 1 else 99)
        wall, floor = 0.55, z + 2.6
        dark = tuple(c * 0.55 for c in col)
        e = 0.01  # no coincident faces between the generated boxes (avoids z-fighting in the ray tracer)
        out = [(col, box(x0 + wall - e, y0 + wall - e, x1 - wall + e, y1 - wall + e, z, floor))]
        out += [(col, box(x0, y0, x1, y0 + wall, z, z + h)), (col, box(x0, y1 - wall, x1, y1, z, z + h)),
                (col, box(x0, y0 + wall + e, x0 + wall, y1 - wall - e, z + e, z + h - e)),
                (col, box(x1 - wall, y0 + wall + e, x1, y1 - wall - e, z + e, z + h - e))]
        for gx in (xs[:-1] + xs[1:]) / 2:  # cell walls between columns/rows (keyed cavities)
            out.append((col, box(gx - 0.25, y0 + wall + e, gx + 0.25, y1 - wall - e, floor - e, z + h - 0.4)))
        for gy in (ys[:-1] + ys[1:]) / 2:
            out.append((col, box(x0 + wall + e, gy - 0.25 + e, x1 - wall - e, gy + 0.25 - e, floor - 2 * e, z + h - 0.4 - e)))
        k = 0.9 * pitch / 3.0  # corner keys: alternate square / rounded (chamfer blocks) like the real housing
        for i, (cx, cy) in enumerate(pins):
            out.append(((0.85, 0.70, 0.25), box(cx - 0.32, cy - 0.32, cx + 0.32, cy + 0.32, floor, z + h - 1.6)))  # gold pin
            out.append((dark, box(cx - pitch / 2 + 0.25, cy - pitch / 2 + 0.25, cx + pitch / 2 - 0.25, cy + pitch / 2 - 0.25, floor, floor + 0.02)))
            if i % 2:
                for sx in (-1, 1):
                    out.append((col, box(cx + sx * (pitch / 2 - 0.25) - (k * 0.5 if sx > 0 else 0), cy - pitch / 2 + 0.25,
                                         cx + sx * (pitch / 2 - 0.25) + (0 if sx > 0 else k * 0.5), cy - pitch / 2 + 0.25 + k * 0.5,
                                         floor, z + h - 0.4)))
        # latch ramp on one long side, centred
        long_x = (x1 - x0) >= (y1 - y0)
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        if long_x:
            out.append((col, box(mx - 1.75, y0 - 1.1, mx + 1.75, y0 + e, z + h - 4.5, z + h - 0.6)))
        else:
            out.append((col, box(x0 - 1.1, my - 1.75, x0 + e, my + 1.75, z + h - 4.5, z + h - 0.6)))
        # PCB retention pegs are hidden under the body; nothing to draw
        return out
    return [(col, box(x0, y0, x1, y1, z, z + h))]


def board_mesh():
    img = np.array(Image.open(TEX).convert("RGB"))
    bg = np.array([32, 36, 42])
    mask = np.abs(img.astype(int) - bg).sum(2) > 12
    ys, xs = np.nonzero(mask)
    crop = img[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    tex = pv.numpy_to_texture(crop.copy())
    top = pv.Plane(center=(BW / 2, BH / 2, THK + 0.002), direction=(0, 0, 1), i_size=BW, j_size=BH)
    top.texture_map_to_plane(inplace=True)
    slab = pv.Box(bounds=(0, BW, 0, BH, 0, THK))
    return top, tex, slab


cache = {}
groups = {}  # colour -> list of meshes, merged per colour for speed
b = pcbnew.LoadBoard(PCB)
missing = []
for fp in b.GetFootprints():
    models = list(fp.Models())
    fn = FP_MODEL.get(str(fp.GetFPID().GetLibItemName()))
    if not models and not fn:
        continue
    fn = fn or re.sub(r"^\$\{KICAD\d_3DMODEL_DIR\}/", "", models[0].m_Filename)
    key = next((k for k in PROC if k in fn), None)
    path = None
    if key:
        meshes = proc_meshes(fp, *PROC[key])
    else:
        sub = SUBST.get(fn)
        src, fit, zt = sub if sub else (fn, None, None)
        path = next((os.path.join(d, src) for d in MODELS if os.path.exists(os.path.join(d, src))), None)
        if path is None:
            missing.append((fp.GetReference(), fn)); meshes = proc_meshes(fp, 1.5, DGREY, "box")
        else:
            if path not in cache:
                cache[path] = parse_wrl(path)
            pos = fp.GetPosition()
            px, py = pcbnew.ToMM(pos.x) - OX, pcbnew.ToMM(pos.y) - OY
            th = np.radians(fp.GetOrientationDegrees())
            R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
            parts = [(col, m.copy()) for col, m in cache[path]]
            if sub:  # scale/centre in footprint-local frame
                allp = np.vstack([q.points for _, q in parts])
                lo, hi = allp.min(0), allp.max(0)
                tl, th_ = local_box(fp, fit or "body", R, px, py)
                sc = np.ones(3)
                if fit:
                    sc[:2] = (th_ - tl) / np.maximum(hi[:2] - lo[:2], 1e-6)
                if zt:
                    sc[2] = zt / max(hi[2], 1e-6)
                ctr = (lo[:2] + hi[:2]) / 2
                for _, q in parts:
                    q.points[:, :2] = (q.points[:, :2] - ctr) * sc[:2] + (tl + th_) / 2
                    q.points[:, 2] *= sc[2]
            meshes = []
            for col, q in parts:
                q.points = q.points @ R.T + world(px, py, THK)
                meshes.append((col, q))
    kind = "proc" if (key or path is None) else "model"
    for col, m in meshes:
        groups.setdefault((tuple(round(c, 3) for c in col), kind), []).append(m.triangulate())
print("missing (generic body):", missing)

top, tex, slab = board_mesh()

if os.environ.get("EXPORT_DIR"):  # hand the populated scene to blender_render.py
    import json
    ed = os.environ["EXPORT_DIR"]; os.makedirs(ed, exist_ok=True)
    man = []
    for i, ((col, kind), ms) in enumerate(groups.items()):
        fn = os.path.join(ed, f"g{i:03d}.ply")
        pv.merge(ms).extract_surface().triangulate().save(fn)
        man.append({"file": fn, "color": col, "kind": kind})
    img = np.array(Image.open(TEX).convert("RGB"))
    mask = np.abs(img.astype(int) - np.array([32, 36, 42])).sum(2) > 12
    ys_, xs_ = np.nonzero(mask)
    Image.fromarray(img[ys_.min():ys_.max() + 1, xs_.min():xs_.max() + 1]).save(os.path.join(ed, "top.png"))
    slots = []
    for d in b.GetDrawings():  # interior Edge.Cuts = isolation slots, cut through the board in Blender
        if d.GetLayer() == pcbnew.Edge_Cuts:
            bb = d.GetBoundingBox()
            x0, y0 = pcbnew.ToMM(bb.GetLeft()) - OX, pcbnew.ToMM(bb.GetTop()) - OY
            x1, y1 = pcbnew.ToMM(bb.GetRight()) - OX, pcbnew.ToMM(bb.GetBottom()) - OY
            if x0 > 1 and y0 > 1 and x1 < BW - 1 and y1 < BH - 1:
                slots.append([x0, BH - y1, x1, BH - y0])  # world coords (y up)
    json.dump({"groups": man, "board": [BW, BH, THK], "top": os.path.join(ed, "top.png"), "slots": slots}, open(os.path.join(ed, "scene.json"), "w"))
    print("exported", len(man), "groups to", ed)
    sys.exit(0)


def shoot(name, cam, size=(2400, 2000), parallel=False):
    p = pv.Plotter(off_screen=True, window_size=size, lighting="three lights")
    p.set_background("white")
    p.add_mesh(slab, color=(0.08, 0.30, 0.16), smooth_shading=False)
    p.add_mesh(top, texture=tex, ambient=0.35, diffuse=0.7, specular=0.1)
    for (col, _kind), ms in groups.items():
        metal = min(col) > 0.6
        p.add_mesh(pv.merge(ms), color=col, smooth_shading=False, specular=0.6 if metal else 0.2,
                   specular_power=30, ambient=0.2, diffuse=0.85)
    p.camera_position = cam
    if parallel:
        p.enable_parallel_projection(); p.camera.parallel_scale = BH * 0.53
    p.enable_anti_aliasing("ssaa")
    p.screenshot(name)
    print("wrote", name)


c = (BW / 2, BH / 2, 0)
shoot(f"{OUT}_iso.png", [(BW / 2 - 45, -115, 165), (BW / 2 + 4, BH / 2 + 2, 0), (0, 0, 1)])
shoot(f"{OUT}_top.png", [(BW / 2, BH / 2, 400), c, (0, 1, 0)], size=(2400, 1960), parallel=True)
