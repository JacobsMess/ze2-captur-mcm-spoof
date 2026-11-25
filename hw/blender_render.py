"""Ray-traced (Cycles) render of the populated board from the scene exported by render3d.py.

usage: EXPORT_DIR=scene xvfb-run -a python3 render3d.py board.kicad_pcb top.png x   (export)
       python3 blender_render.py scene/scene.json out_prefix [samples] [width]
Materials are chosen from each model colour: metals/gold get metallic BSDFs, everything else glossy plastic;
the board top is the KiCad layer composite (mask, silk, copper) on a glossy solder-mask material.
"""
import json
import math
import sys

import bpy
from mathutils import Vector

SCENE, OUT = sys.argv[1], sys.argv[2]
SAMPLES = int(sys.argv[3]) if len(sys.argv) > 3 else 96
WIDTH = int(sys.argv[4]) if len(sys.argv) > 4 else 2000
cfg = json.load(open(SCENE))
BW, BH, THK = cfg["board"]

bpy.ops.wm.read_factory_settings(use_empty=True)
sc = bpy.context.scene
sc.unit_settings.scale_length = 0.001  # model units are mm


def principled(name, color, metallic=0.0, rough=0.4, coat=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*color, 1)
    b.inputs["Metallic"].default_value = metallic
    b.inputs["Roughness"].default_value = rough
    if coat:
        b.inputs["Coat Weight"].default_value = coat
    return m, b


def material_for(col):
    r, g, bl = col
    if r > 0.7 and 0.5 < g < 0.85 and bl < 0.45:      # gold pins
        return principled("gold", (0.95, 0.72, 0.30), 1.0, 0.25)[0]
    if min(col) > 0.6 and max(col) - min(col) < 0.06:  # tin / steel / silver
        return principled(f"metal{col}", tuple(c * 0.95 for c in col), 1.0, 0.28)[0]
    if max(col) < 0.2:                                  # black epoxy / nylon
        return principled(f"black{col}", (0.03, 0.03, 0.035), 0.0, 0.45)[0]
    return principled(f"plastic{col}", tuple(c ** 2.2 for c in col), 0.0, 0.42)[0]  # sRGB -> linear


for gdef in cfg["groups"]:
    bpy.ops.wm.ply_import(filepath=gdef["file"])
    ob = bpy.context.selected_objects[0]
    ob.data.materials.clear()
    ob.data.materials.append(material_for(tuple(gdef["color"])))
    for p in ob.data.polygons:
        p.use_smooth = False
    if gdef.get("kind") == "proc":  # generated boxes already have outward normals
        continue
    # KiCad VRML faces have mixed winding (rendered double-sided in KiCad): make normals consistent/outward
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.mode_set(mode="EDIT")
    bpy.ops.mesh.select_all(action="SELECT")
    bpy.ops.mesh.remove_doubles(threshold=0.0005)
    bpy.ops.mesh.normals_make_consistent(inside=False)
    bpy.ops.object.mode_set(mode="OBJECT")

# board: FR4 slab + textured glossy top
bpy.ops.mesh.primitive_cube_add(size=1, location=(BW / 2, BH / 2, THK / 2))
slab = bpy.context.object; slab.scale = (BW, BH, THK)
slab.data.materials.append(principled("fr4", (0.02, 0.12, 0.05), 0.0, 0.5)[0])
bpy.ops.mesh.primitive_plane_add(size=1, location=(BW / 2, BH / 2, THK + 0.003))
top = bpy.context.object; top.scale = (BW, BH, 1)
m, bsdf = principled("mask", (1, 1, 1), 0.0, 0.32, coat=0.25)
nt = m.node_tree
tex = nt.nodes.new("ShaderNodeTexImage"); tex.image = bpy.data.images.load(cfg["top"])
nt.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
top.data.materials.append(m)
for i, (x0, y0, x1, y1) in enumerate(cfg.get("slots", [])):  # isolation slots through slab and top
    bpy.ops.mesh.primitive_cube_add(size=1, location=((x0 + x1) / 2, (y0 + y1) / 2, THK / 2))
    cut = bpy.context.object; cut.scale = (x1 - x0, y1 - y0, THK * 4); cut.hide_render = True
    for target_ob in (slab, top):
        mod = target_ob.modifiers.new(f"slot{i}", "BOOLEAN"); mod.operation = "DIFFERENCE"; mod.object = cut

# lighting: soft sky + key area light + low sun for crisp shadows
world = bpy.data.worlds.new("w"); sc.world = world; world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (1, 1, 1, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.55
bpy.ops.object.light_add(type="AREA", location=(BW * 0.3, BH * 0.2, 220))
key = bpy.context.object; key.data.size = 160; key.data.energy = 3.0e5
key.rotation_euler = (Vector((BW / 2, BH / 2, 0)) - key.location).to_track_quat("-Z", "Y").to_euler()
bpy.ops.object.light_add(type="SUN", location=(0, 0, 100), rotation=(math.radians(35), math.radians(-20), math.radians(30)))
sun = bpy.context.object; sun.data.energy = 2.2; sun.data.angle = math.radians(4)

target = bpy.data.objects.new("target", None); sc.collection.objects.link(target)


def camera(name, loc, look, ortho=None):
    cam = bpy.data.cameras.new(name)
    ob = bpy.data.objects.new(name, cam); sc.collection.objects.link(ob)
    ob.location = loc
    d = Vector(look) - Vector(loc)
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    cam.sensor_fit = "VERTICAL"
    cam.clip_start, cam.clip_end = 1, 2000
    if ortho:
        cam.type = "ORTHO"; cam.ortho_scale = ortho
    else:
        cam.angle_y = math.radians(30)
    return ob


sc.render.engine = "CYCLES"
sc.cycles.device = "CPU"
sc.cycles.samples = SAMPLES
sc.cycles.use_denoising = True
sc.cycles.max_bounces = 6
sc.view_settings.view_transform = "AgX"
sc.view_settings.look = "AgX - Medium High Contrast"
sc.render.film_transparent = True  # composited onto white below

views = [
    ("3d", camera("cam_iso", (BW / 2 - 45, -115, 165), (BW / 2 + 4, BH / 2 + 2, 0)), (WIDTH, int(WIDTH / 1.2))),
    ("top", camera("cam_top", (BW / 2, BH / 2, 400), (BW / 2, BH / 2, 0), ortho=BH * 1.06), (WIDTH, int(WIDTH * 0.8167))),
]
for name, cam, (w, h) in views:
    sc.camera = cam
    sc.render.resolution_x, sc.render.resolution_y = w, h
    sc.render.filepath = f"{OUT}_{name}.png"
    bpy.ops.render.render(write_still=True)
    from PIL import Image
    im = Image.open(sc.render.filepath).convert("RGBA")
    bg = Image.new("RGBA", im.size, (255, 255, 255, 255)); bg.alpha_composite(im)
    bg.convert("RGB").save(sc.render.filepath)
    print("wrote", sc.render.filepath)
