"""ArchAI Bridge — LLM ajanlarının Blender'ı kullanabilmesi için yerel köprü.

İki şekilde çalışır:
  * GUI: Blender'da eklenti olarak kurulur, açılışta 127.0.0.1:9876'yı dinler.
  * Headless: blender -b --python archai_bridge.py -- --serve

Protokol: tek satırlık JSON istek {"cmd": str, "args": {...}} → tek satırlık JSON yanıt
{"ok": bool, "result": ..., "error": str}. Her istek için yeni bağlantı açılır.
"""

bl_info = {
    "name": "ArchAI Bridge",
    "author": "wpu-research",
    "version": (0, 1, 0),
    "blender": (4, 2, 0),
    "category": "System",
    "description": "LLM ajanları için mimari modelleme + colormap render köprüsü",
}

import io
import json
import math
import os
import queue
import shutil
import socket
import subprocess
import sys
import threading
import traceback
from contextlib import redirect_stdout

import bmesh
import bpy
from mathutils import Vector

HOST = "127.0.0.1"
PORT = int(os.environ.get("ARCHAI_PORT", "9876"))
COLLECTION = "ArchAI"

# Colormap paleti: semantik etiket → düz sRGB renk. Video modeline "hangi renk hangi
# malzeme" rehberi olarak verilir; renkler birbirinden uzak seçildi.
PALETTE = {
    "wall": (0.90, 0.25, 0.25),
    "concrete": (0.92, 0.92, 0.92),
    "floor": (0.98, 0.85, 0.20),
    "roof": (0.55, 0.30, 0.80),
    "glass": (0.25, 0.85, 1.00),
    "frame": (0.10, 0.10, 0.45),
    "wood": (0.85, 0.50, 0.15),
    "stone": (0.55, 0.50, 0.40),
    "metal": (0.30, 0.40, 1.00),
    "water": (0.10, 1.00, 0.75),
    "vegetation": (0.20, 0.75, 0.20),
    "tree": (0.05, 0.45, 0.10),
    "fabric": (1.00, 0.55, 0.80),
    "furniture": (1.00, 0.45, 0.00),
    "ground": (0.70, 0.70, 0.65),
    "terrain": (0.45, 0.60, 0.30),
    "sea": (0.05, 0.15, 0.55),
    "hill": (0.80, 0.70, 0.45),
    "terracotta": (0.55, 0.18, 0.00),
    "sky": (0.85, 0.93, 1.00),
}

# Önizleme (preview) render'ı için kaba PBR değerleri: (renk, roughness, metallic, transmission)
PREVIEW = {
    "wall": ((0.93, 0.90, 0.85), 0.9, 0.0, 0.0),
    "concrete": ((0.75, 0.75, 0.73), 0.8, 0.0, 0.0),
    "floor": ((0.80, 0.75, 0.68), 0.6, 0.0, 0.0),
    "roof": ((0.35, 0.33, 0.32), 0.7, 0.0, 0.0),
    "glass": ((0.85, 0.95, 1.00), 0.02, 0.0, 1.0),
    "frame": ((0.12, 0.12, 0.12), 0.4, 1.0, 0.0),
    "wood": ((0.45, 0.28, 0.15), 0.6, 0.0, 0.0),
    "stone": ((0.62, 0.57, 0.48), 0.9, 0.0, 0.0),
    "metal": ((0.70, 0.70, 0.72), 0.3, 1.0, 0.0),
    "water": ((0.10, 0.45, 0.60), 0.02, 0.0, 0.8),
    "vegetation": ((0.20, 0.40, 0.12), 0.8, 0.0, 0.0),
    "tree": ((0.15, 0.35, 0.10), 0.8, 0.0, 0.0),
    "fabric": ((0.90, 0.88, 0.82), 0.95, 0.0, 0.0),
    "furniture": ((0.55, 0.45, 0.35), 0.6, 0.0, 0.0),
    "ground": ((0.60, 0.58, 0.52), 0.9, 0.0, 0.0),
    "terrain": ((0.35, 0.42, 0.22), 0.95, 0.0, 0.0),
    "sea": ((0.02, 0.12, 0.30), 0.05, 0.0, 0.0),
    "hill": ((0.45, 0.42, 0.30), 0.95, 0.0, 0.0),
    "terracotta": ((0.60, 0.30, 0.18), 0.8, 0.0, 0.0),
    "sky": ((0.85, 0.93, 1.00), 1.0, 0.0, 0.0),
}


# ---------------------------------------------------------------- yardımcılar

def _collection():
    col = bpy.data.collections.get(COLLECTION)
    if col is None:
        col = bpy.data.collections.new(COLLECTION)
        bpy.context.scene.collection.children.link(col)
    return col


def _srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def _material(tag, mode):
    """mode: 'CM' (colormap, düz renk) veya 'PV' (önizleme PBR)."""
    if tag not in PALETTE:
        raise ValueError(f"bilinmeyen etiket '{tag}'. Geçerli: {sorted(PALETTE)}")
    name = f"{mode}_{tag}"
    mat = bpy.data.materials.get(name)
    if mat:
        return mat
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new("ShaderNodeOutputMaterial")
    if mode == "CM":
        rgb = tuple(_srgb_to_linear(c) for c in PALETTE[tag])
        em = nt.nodes.new("ShaderNodeEmission")
        em.inputs["Color"].default_value = (*rgb, 1.0)
        nt.links.new(em.outputs[0], out.inputs["Surface"])
        mat.diffuse_color = (*rgb, 1.0)  # Workbench bu rengi kullanır
    else:
        col, rough, metal, trans = PREVIEW[tag]
        bsdf = nt.nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.inputs["Base Color"].default_value = (*col, 1.0)
        bsdf.inputs["Roughness"].default_value = rough
        bsdf.inputs["Metallic"].default_value = metal
        key = "Transmission Weight" if "Transmission Weight" in bsdf.inputs else "Transmission"
        bsdf.inputs[key].default_value = trans
        nt.links.new(bsdf.outputs[0], out.inputs["Surface"])
        mat.diffuse_color = (*col, 1.0)
    return mat


def _finish(obj, tag, name=None):
    if name:
        obj.name = name
    obj["archai_tag"] = tag
    for c in obj.users_collection:
        c.objects.unlink(obj)
    _collection().objects.link(obj)
    obj.data.materials.clear()
    obj.data.materials.append(_material(tag, "PV"))
    return obj


def _mesh_obj(name, bm):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(obj)
    return obj


def _box_bm(sx, sy, sz):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co.x = (v.co.x + 0.5) * sx
        v.co.y = (v.co.y + 0.5) * sy
        v.co.z = (v.co.z + 0.5) * sz
    return bm


def _box(name, origin, size, tag, rot_z=0.0):
    """origin: min köşe [x,y,z], size: [sx,sy,sz], rot_z: derece (origin etrafında)."""
    obj = _mesh_obj(name, _box_bm(*size))
    obj.location = Vector(origin)
    obj.rotation_euler.z = math.radians(rot_z)
    return _finish(obj, tag, name)


# ---------------------------------------------------------------- elemanlar

def el_box(e):
    return [_box(e.get("name", "box"), e["origin"], e["size"], e.get("tag", "concrete"),
                 e.get("rotation_z", 0.0))]


def el_wall(e):
    """Duvar: start→end çizgisi, thickness çizginin soluna doğru değil ortalanır.
    openings: [{offset, width, sill, height, kind: window|door}] — offset start'tan
    açıklığın başlangıcına mesafe (m). Pencerelere otomatik cam + kasa eklenir."""
    (x0, y0), (x1, y1) = e["start"], e["end"]
    L = math.hypot(x1 - x0, y1 - y0)
    if L < 1e-6:
        raise ValueError("duvar uzunluğu sıfır")
    H = e.get("height", 3.0)
    T = e.get("thickness", 0.2)
    z0 = e.get("base_z", 0.0)
    tag = e.get("tag", "wall")
    name = e.get("name", "wall")
    ang = math.degrees(math.atan2(y1 - y0, x1 - x0))
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    nx, ny = -uy, ux  # sol normal
    ox, oy = x0 - nx * T / 2, y0 - ny * T / 2  # kalınlığı ortala

    def seg(a, b, zb, zt, suffix, t=tag, thick=T, inset=0.0):
        if b - a < 1e-4 or zt - zb < 1e-4:
            return None
        px = ox + ux * a + nx * inset
        py = oy + uy * a + ny * inset
        return _box(f"{name}{suffix}", [px, py, z0 + zb], [b - a, thick, zt - zb], t, ang)

    out, cursor = [], 0.0
    ops = sorted(e.get("openings", []), key=lambda o: o["offset"])
    for i, o in enumerate(ops):
        a, w = o["offset"], o["width"]
        b = a + w
        kind = o.get("kind", "window")
        sill = 0.0 if kind == "door" else o.get("sill", 0.9)
        top = sill + o.get("height", 2.1 if kind == "door" else 1.4)
        if a < cursor - 1e-6 or b > L + 1e-6 or top > H + 1e-6:
            raise ValueError(f"{name}: açıklık {i} duvar dışına taşıyor/çakışıyor")
        out += [seg(cursor, a, 0, H, f"_p{i}"), seg(a, b, 0, sill, f"_s{i}"),
                seg(a, b, top, H, f"_h{i}")]
        if kind == "window":
            out.append(seg(a, b, sill, top, f"_glass{i}", "glass", 0.02, T / 2 - 0.01))
            f = 0.05
            out += [seg(a, a + f, sill, top, f"_fl{i}", "frame", 0.08, T / 2 - 0.04),
                    seg(b - f, b, sill, top, f"_fr{i}", "frame", 0.08, T / 2 - 0.04)]
        elif o.get("leaf", False):
            out.append(seg(a, b, 0, top, f"_door{i}", o.get("leaf_tag", "wood"), 0.05, T / 2 - 0.025))
        cursor = b
    out.append(seg(cursor, L, 0, H, "_end"))
    return [o for o in out if o]


def el_slab(e):
    """Poligon döşeme/çatı/havuz: points [[x,y],...], z (üst yüz), thickness."""
    pts = e["points"]
    z = e.get("z", 0.0)
    t = e.get("thickness", 0.2)
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, z - t)) for x, y in pts]
    f = bm.faces.new(vs)
    bmesh.ops.recalc_face_normals(bm, faces=[f])
    if f.normal.z > 0:
        f.normal_flip()
    ext = bmesh.ops.extrude_face_region(bm, geom=[f])
    moved = [g for g in ext["geom"] if isinstance(g, bmesh.types.BMVert)]
    bmesh.ops.translate(bm, vec=(0, 0, t), verts=moved)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    name = e.get("name", "slab")
    return [_finish(_mesh_obj(name, bm), e.get("tag", "floor"), name)]


def el_cylinder(e):
    """Kolon/gövde: center [x,y,z-alt], radius, height."""
    bm = bmesh.new()
    r, h = e["radius"], e["height"]
    bmesh.ops.create_cone(bm, cap_ends=True, segments=e.get("segments", 24),
                          radius1=r, radius2=e.get("radius_top", r), depth=h)
    bmesh.ops.translate(bm, vec=(0, 0, h / 2), verts=bm.verts)
    name = e.get("name", "cylinder")
    obj = _mesh_obj(name, bm)
    obj.location = Vector(e["center"])
    return [_finish(obj, e.get("tag", "concrete"), name)]


def el_sphere(e):
    """Ağaç tacı vb.: center [x,y,z], radius, scale [sx,sy,sz] opsiyonel."""
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=16, v_segments=10, radius=e["radius"])
    name = e.get("name", "sphere")
    obj = _mesh_obj(name, bm)
    obj.location = Vector(e["center"])
    obj.scale = Vector(e.get("scale", (1, 1, 1)))
    return [_finish(obj, e.get("tag", "tree"), name)]


def el_tree(e):
    """Basit ağaç: gövde + taç. position [x,y], height, base_z (zemin kotu)."""
    x, y = e["position"]
    h = e.get("height", 5.0)
    z = e.get("base_z", 0.0)
    name = e.get("name", "tree")
    trunk = el_cylinder({"name": f"{name}_trunk", "center": [x, y, z], "radius": h * 0.03,
                         "height": h * 0.55, "tag": "wood"})
    crown = el_sphere({"name": f"{name}_crown", "center": [x, y, z + h * 0.65], "radius": h * 0.3,
                       "scale": e.get("crown_scale", [1, 1, 0.8]), "tag": "tree"})
    return trunk + crown


def el_stairs(e):
    """Düz merdiven: origin [x,y,z], width, steps, rise, run, rotation_z."""
    name = e.get("name", "stairs")
    rot = e.get("rotation_z", 0.0)
    ox, oy, oz = e["origin"]
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    out = []
    for i in range(e.get("steps", 10)):
        dx = i * e.get("run", 0.28)
        out.append(_box(f"{name}_{i}", [ox + c * dx, oy + s * dx, oz],
                        [e.get("run", 0.28), e.get("width", 1.2), (i + 1) * e.get("rise", 0.17)],
                        e.get("tag", "stone"), rot))
    return out


ELEMENTS = {"box": el_box, "wall": el_wall, "slab": el_slab, "cylinder": el_cylinder,
            "sphere": el_sphere, "tree": el_tree, "stairs": el_stairs}


# ---------------------------------------------------------------- komutlar

def cmd_ping(_):
    return {"blender": bpy.app.version_string, "file": bpy.data.filepath or None,
            "background": bpy.app.background}


def cmd_reset_scene(_):
    # read_factory_settings GUI'de eklentiyi/timer'ı düşürür; veriyi elle temizle.
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials, bpy.data.cameras,
                 bpy.data.lights, bpy.data.actions, bpy.data.collections):
        for item in list(coll):
            coll.remove(item)
    sc = bpy.context.scene
    sc.unit_settings.system = "METRIC"
    sc.camera = None
    if sc.world is None:
        sc.world = bpy.data.worlds.new("World")
    return "boş sahne hazır"


def cmd_build(args):
    """elements: [{type, ...}] — her eleman ELEMENTS'teki bir tip."""
    made, errors = [], []
    for i, e in enumerate(args["elements"]):
        try:
            fn = ELEMENTS[e["type"]]
            made += [o.name for o in fn(e)]
        except Exception as ex:  # tek hatalı eleman tüm partiyi düşürmesin
            errors.append(f"#{i} ({e.get('type')}/{e.get('name')}): {ex}")
    return {"created": len(made), "objects": made[:50], "errors": errors}


def cmd_delete(args):
    """names: silinecek obje adları; prefix: bu önekle başlayanların hepsi."""
    names = set(args.get("names", []))
    prefix = args.get("prefix")
    gone = []
    for o in list(bpy.data.objects):
        if o.name in names or (prefix and o.name.startswith(prefix)):
            gone.append(o.name)
            bpy.data.objects.remove(o, do_unlink=True)
    return {"deleted": gone}


def _bbox(objs):
    bpy.context.view_layer.update()  # yeni objelerin matrix_world'ü yoksa bayat kalır
    pts =[o.matrix_world @ Vector(c) for o in objs for c in o.bound_box]
    if not pts:
        return None
    mn = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
    mx = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
    return mn, mx


def cmd_scene_info(args):
    objs = [o for o in bpy.data.objects if o.type == "MESH"]
    tags = {}
    for o in objs:
        t = o.get("archai_tag", "?")
        tags[t] = tags.get(t, 0) + 1
    bb = _bbox(objs)
    limit = args.get("limit", 200)
    return {
        "object_count": len(objs),
        "tags": tags,
        "bbox": [list(map(lambda v: round(v, 3), bb[0])), list(map(lambda v: round(v, 3), bb[1]))] if bb else None,
        "objects": [{"name": o.name, "tag": o.get("archai_tag"),
                     "loc": [round(v, 3) for v in o.location],
                     "dim": [round(v, 3) for v in o.dimensions]} for o in objs[:limit]],
        "camera": bool(bpy.data.objects.get("ArchAI_Cam")),
        "frames": [bpy.context.scene.frame_start, bpy.context.scene.frame_end],
        "palette": PALETTE,
    }


def cmd_exec_python(args):
    """Serbest bpy kodu — yüksek seviyeli araçların yetmediği durumlar için."""
    buf = io.StringIO()
    ns = {"bpy": bpy, "bmesh": bmesh, "Vector": Vector, "math": math,
          "tag_object": lambda obj, tag: _finish(obj, tag)}
    with redirect_stdout(buf):
        exec(args["code"], ns)
    return {"stdout": buf.getvalue()[-8000:]}


# ---- kamera

def _catmull(pts, t):
    """pts boyunca 0..1 parametresiyle Catmull-Rom interpolasyonu."""
    if len(pts) == 1:
        return Vector(pts[0])
    P = [Vector(p) for p in pts]
    P = [P[0] * 2 - P[1]] + P + [P[-1] * 2 - P[-2]]
    n = len(pts) - 1
    f = min(t * n, n - 1e-9)
    i = int(f)
    u = f - i
    p0, p1, p2, p3 = P[i], P[i + 1], P[i + 2], P[i + 3]
    return 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
                  + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3)


def _ease(t):
    return t * t * (3 - 2 * t)


def cmd_camera_path(args):
    """mode:
       orbit      — sahne merkezinde yörünge (radius, height, degrees)
       flythrough — points listesi boyunca; targets verilmezse ileri bakar
       dolly      — points[0]→points[-1], sabit target
    Ortak: frames, fps, lens (mm), ease (bool)."""
    sc = bpy.context.scene
    frames = int(args.get("frames", 120))
    sc.render.fps = int(args.get("fps", 24))
    sc.frame_start, sc.frame_end = 1, frames

    cam = bpy.data.objects.get("ArchAI_Cam")
    if cam is None:
        cam = bpy.data.objects.new("ArchAI_Cam", bpy.data.cameras.new("ArchAI_Cam"))
        sc.collection.objects.link(cam)
    tgt = bpy.data.objects.get("ArchAI_Target")
    if tgt is None:
        tgt = bpy.data.objects.new("ArchAI_Target", None)
        sc.collection.objects.link(tgt)
    cam.data.lens = args.get("lens", 24)
    cam.data.clip_end = 2000
    cam.animation_data_clear()
    tgt.animation_data_clear()
    for c in list(cam.constraints):
        cam.constraints.remove(c)
    tc = cam.constraints.new("TRACK_TO")
    tc.target, tc.track_axis, tc.up_axis = tgt, "TRACK_NEGATIVE_Z", "UP_Y"
    sc.camera = cam

    mode = args.get("mode", "orbit")
    ease = args.get("ease", True)
    objs = [o for o in bpy.data.objects if o.type == "MESH" and o.get("archai_tag") not in ("ground", "terrain", "sea", "hill")]
    bb = _bbox(objs) or (Vector((-5, -5, 0)), Vector((5, 5, 3)))
    center = (bb[0] + bb[1]) / 2

    if mode == "orbit":
        r = args.get("radius", (bb[1] - bb[0]).length * 0.9)
        h = args.get("height", center.z + (bb[1].z - bb[0].z) * 0.6)
        deg = args.get("degrees", 90)
        start = args.get("start_angle", -45)
        target = Vector(args.get("target", center))
        cam_at = lambda t: Vector((center.x + r * math.cos(math.radians(start + deg * t)),
                                   center.y + r * math.sin(math.radians(start + deg * t)), h))
        tgt_at = lambda t: target
    else:
        pts = args["points"]
        cam_at = lambda t: _catmull(pts, t)
        if args.get("targets"):
            tgt_at = lambda t: _catmull(args["targets"], t)
        elif args.get("target") is not None:
            tgt_at = lambda t: Vector(args["target"])
        else:  # ileri bak
            tgt_at = lambda t: _catmull(pts, min(t + 0.05, 1.0)) + (
                _catmull(pts, min(t + 0.05, 1.0)) - _catmull(pts, max(t - 0.05, 0))).normalized() * 2

    for f in range(frames):
        t = f / max(frames - 1, 1)
        t = _ease(t) if ease else t
        cam.location = cam_at(t)
        tgt.location = tgt_at(t)
        cam.keyframe_insert("location", frame=f + 1)
        tgt.keyframe_insert("location", frame=f + 1)
    for ob in (cam, tgt):
        for fc in ob.animation_data.action.fcurves:
            for kp in fc.keyframe_points:
                kp.interpolation = "LINEAR"
    return {"mode": mode, "frames": frames, "fps": sc.render.fps,
            "start": [round(v, 2) for v in cam_at(0)], "end": [round(v, 2) for v in cam_at(1)]}


# ---- render

def _set_materials(mode):
    for o in bpy.data.objects:
        if o.type == "MESH" and "archai_tag" in o and o.data.materials:
            o.data.materials[0] = _material(o["archai_tag"], mode)


def _setup_world(mode):
    sc = bpy.context.scene
    w = sc.world or bpy.data.worlds.new("World")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes.get("Background")
    if mode == "CM":
        rgb = tuple(_srgb_to_linear(c) for c in PALETTE["sky"])
        bg.inputs["Color"].default_value = (*rgb, 1)
        bg.inputs["Strength"].default_value = 1.0
        w.color = rgb
    else:
        bg.inputs["Color"].default_value = (0.55, 0.70, 0.95, 1)
        bg.inputs["Strength"].default_value = 0.6
        sun = bpy.data.objects.get("ArchAI_Sun")
        if sun is None:
            sun = bpy.data.objects.new("ArchAI_Sun", bpy.data.lights.new("ArchAI_Sun", "SUN"))
            sc.collection.objects.link(sun)
            sun.rotation_euler = (math.radians(50), 0, math.radians(35))
        sun.data.energy = 4.0
        sun.data.angle = math.radians(1.5)


def _set_engine(kind, samples):
    sc = bpy.context.scene
    if kind == "colormap":
        sc.render.engine = "BLENDER_WORKBENCH"
        sc.display.shading.light = "FLAT"
        sc.display.shading.color_type = "MATERIAL"
        sc.display.shading.show_shadows = False
        sc.display.shading.show_cavity = False
        sc.display.shading.show_object_outline = False
        sc.display.shading.background_type = "WORLD"
        sc.display.render_aa = "OFF"  # sınırlar net kalsın: saf renk segmentasyonu
        sc.render.dither_intensity = 0.0  # piksel renkleri paletle birebir eşleşsin
        sc.view_settings.view_transform = "Standard"
        return "BLENDER_WORKBENCH"
    sc.view_settings.view_transform = "AgX" if "AgX" in [i.identifier for i in
        sc.view_settings.bl_rna.properties["view_transform"].enum_items] else "Filmic"
    if kind == "preview_cycles":
        sc.render.engine = "CYCLES"
        sc.cycles.samples = samples
        sc.cycles.use_denoising = True
        try:
            prefs = bpy.context.preferences.addons["cycles"].preferences
            for dev_type in ("OPTIX", "CUDA"):
                try:
                    prefs.compute_device_type = dev_type
                    prefs.get_devices()
                    if any(d.type == dev_type for d in prefs.devices):
                        for d in prefs.devices:
                            d.use = d.type == dev_type
                        sc.cycles.device = "GPU"
                        break
                except TypeError:
                    continue
        except Exception:
            pass
        return f"CYCLES/{sc.cycles.device}"
    for eng in ("BLENDER_EEVEE_NEXT", "BLENDER_EEVEE"):
        try:
            sc.render.engine = eng
            break
        except TypeError:
            continue
    return sc.render.engine


def cmd_render(args):
    """kind: colormap | preview (EEVEE) | preview_cycles
       still: kare no (tek PNG) — verilmezse tüm animasyon + mp4.
       out_dir, resolution [w,h], samples."""
    sc = bpy.context.scene
    if sc.camera is None:
        raise RuntimeError("kamera yok — önce camera_path çağır")
    kind = args.get("kind", "colormap")
    out_dir = os.path.abspath(os.path.expanduser(args.get("out_dir", "~/archai_out")))
    os.makedirs(out_dir, exist_ok=True)
    w, h = args.get("resolution", [1280, 720])
    sc.render.resolution_x, sc.render.resolution_y = int(w), int(h)
    sc.render.resolution_percentage = 100
    sc.render.image_settings.file_format = "PNG"
    sc.render.film_transparent = False

    mode = "CM" if kind == "colormap" else "PV"
    _set_materials(mode)
    _setup_world(mode)
    engine = _set_engine(kind, int(args.get("samples", 64)))

    still = args.get("still")
    if still is not None:
        sc.frame_set(int(still))
        path = os.path.join(out_dir, f"{kind}_f{int(still):04d}.png")
        sc.render.filepath = path
        bpy.ops.render.render(write_still=True)
        return {"image": path, "engine": engine}

    frames_dir = os.path.join(out_dir, f"{kind}_frames")
    shutil.rmtree(frames_dir, ignore_errors=True)
    os.makedirs(frames_dir)
    sc.render.filepath = os.path.join(frames_dir, "f_")
    bpy.ops.render.render(animation=True)
    video = os.path.join(out_dir, f"{kind}.mp4")
    ff = shutil.which("ffmpeg")
    if ff:
        subprocess.run([ff, "-loglevel", "error", "-y", "-framerate", str(sc.render.fps),
                        "-start_number", str(sc.frame_start), "-i", os.path.join(frames_dir, "f_%04d.png"),
                        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", video], check=True)
    return {"video": video if ff else None, "frames_dir": frames_dir, "engine": engine,
            "frames": sc.frame_end - sc.frame_start + 1}


def cmd_save(args):
    path = os.path.abspath(os.path.expanduser(args["path"]))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=path)
    return {"saved": path}


def cmd_open(args):
    bpy.ops.wm.open_mainfile(filepath=os.path.abspath(os.path.expanduser(args["path"])))
    return {"opened": bpy.data.filepath}


COMMANDS = {n[4:]: f for n, f in globals().items() if n.startswith("cmd_")}


def dispatch(req):
    try:
        fn = COMMANDS[req["cmd"]]
        return {"ok": True, "result": fn(req.get("args") or {})}
    except Exception as ex:
        return {"ok": False, "error": f"{type(ex).__name__}: {ex}",
                "trace": traceback.format_exc()[-2000:]}


# ---------------------------------------------------------------- ağ katmanı

def _read_request(conn):
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = conn.recv(65536)
        if not chunk:
            break
        buf += chunk
    return json.loads(buf.decode("utf-8"))


def _send(conn, resp):
    conn.sendall((json.dumps(resp, ensure_ascii=False, default=str) + "\n").encode("utf-8"))


def serve_blocking():
    """Headless mod: ana thread'de sırayla istek işler (bpy ana thread ister)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(4)
    print(f"[archai] headless dinleniyor {HOST}:{PORT}", flush=True)
    while True:
        conn, _ = srv.accept()
        with conn:
            try:
                req = _read_request(conn)
            except Exception as ex:
                _send(conn, {"ok": False, "error": f"bad request: {ex}"})
                continue
            if req.get("cmd") == "shutdown":
                _send(conn, {"ok": True, "result": "bye"})
                break
            _send(conn, dispatch(req))
    srv.close()


# GUI modu: thread bağlantı kabul eder, iş kuyruğa girer, timer ana thread'de çalıştırır.
_jobs = queue.Queue()
_server_thread = None
_stop = threading.Event()


def _accept_loop():
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind((HOST, PORT))
    srv.listen(4)
    srv.settimeout(0.5)
    while not _stop.is_set():
        try:
            conn, _ = srv.accept()
        except socket.timeout:
            continue
        try:
            conn.settimeout(None)
            req = _read_request(conn)
        except Exception as ex:
            _send(conn, {"ok": False, "error": f"bad request: {ex}"})
            conn.close()
            continue
        done = threading.Event()
        box = {}
        _jobs.put((req, box, done))
        done.wait()
        try:
            _send(conn, box["resp"])
        finally:
            conn.close()
    srv.close()


def _pump():
    while not _jobs.empty():
        req, box, done = _jobs.get()
        box["resp"] = dispatch(req)
        done.set()
    return 0.05


def register():
    global _server_thread
    _stop.clear()
    _server_thread = threading.Thread(target=_accept_loop, daemon=True)
    _server_thread.start()
    bpy.app.timers.register(_pump, persistent=True)
    print(f"[archai] GUI köprüsü dinleniyor {HOST}:{PORT}")


def unregister():
    _stop.set()
    if bpy.app.timers.is_registered(_pump):
        bpy.app.timers.unregister(_pump)


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    if "--serve" in argv:
        if bpy.app.background:
            serve_blocking()
        else:
            register()
