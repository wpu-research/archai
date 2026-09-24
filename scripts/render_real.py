"""Blender Cycles fotogerçekçi render: tarayıcıdaki sahne (GLB) → verilen kameradan fotoğraf.

    blender -b --factory-startup --python scripts/render_real.py -- job.json

job.json (koordinatlar three.js dünya uzayında, Y yukarı; burada Blender'a çevrilir):
  glb, hdri, out_dir, kind: "still"
  sun: {pos:[x,y,z], target:[x,y,z]}
  camera: {matrix:[16, sütun-öncelikli], fov: dikey derece, aspect}
  lights: [{pos:[x,y,z], w, d}]  — oda tavanı yumuşak alan ışıkları (opsiyonel)
  samples, width, exposure
Standart çıktıya ilerleme satırları yazar: ARCHAI_PROGRESS i n ad / ARCHAI_RESULT yol
"""

import json
import math
import os
import sys
import time

import bpy
from mathutils import Matrix, Vector

job = json.load(open(sys.argv[sys.argv.index("--") + 1]))
C4 = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))  # three (Y yukarı) → Blender (Z yukarı)
conv = lambda p: Vector((p[0], -p[2], p[1]))


def log(*a):
    print(*a, flush=True)


# ---------------------------------------------------------------- sahne
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=job["glb"])
for o in list(bpy.data.objects):  # glTF'ten gelen ışık/kamera varsa kaldır (ışığı burada kuruyoruz)
    if o.type in ("LIGHT", "CAMERA"):
        bpy.data.objects.remove(o, do_unlink=True)
sc = bpy.context.scene

# ---------------------------------------------------------------- GPU + Cycles
prefs = bpy.context.preferences.addons["cycles"].preferences
for t in ("OPTIX", "CUDA", "HIP", "METAL"):
    try:
        prefs.compute_device_type = t
        prefs.get_devices()
        if any(d.type == t for d in prefs.devices):
            for d in prefs.devices:
                d.use = d.type == t
            break
    except TypeError:
        continue
sc.render.engine = "CYCLES"
sc.cycles.device = "GPU" if any(d.use and d.type != "CPU" for d in prefs.devices) else "CPU"
sc.cycles.samples = int(job.get("samples", 128))
sc.cycles.use_adaptive_sampling = True
sc.cycles.adaptive_threshold = 0.02
sc.cycles.use_denoising = True
try:
    sc.cycles.denoiser = "OPTIX" if prefs.compute_device_type == "OPTIX" else "OPENIMAGEDENOISE"
except TypeError:
    pass
sc.cycles.max_bounces, sc.cycles.diffuse_bounces, sc.cycles.glossy_bounces = 12, 6, 4
sc.cycles.transmission_bounces, sc.cycles.transparent_max_bounces = 8, 16
sc.cycles.caustics_reflective = sc.cycles.caustics_refractive = False
sc.cycles.blur_glossy = 1.0
sc.cycles.sample_clamp_indirect = 8.0  # iç mekânda ateş böceği (firefly) gürültüsünü bastır
sc.view_settings.view_transform = "AgX"
sc.view_settings.exposure = float(job.get("exposure", 0.8))
sc.render.image_settings.file_format = "JPEG"
sc.render.image_settings.quality = 90
log("ARCHAI_DEVICE", sc.cycles.device, prefs.compute_device_type)

# ---------------------------------------------------------------- ışık: HDRI gökyüzü + güneş + tavan dolgu ışıkları
w = bpy.data.worlds.new("Sky")
sc.world = w
w.use_nodes = True
nt = w.node_tree
env = nt.nodes.new("ShaderNodeTexEnvironment")
env.image = bpy.data.images.load(job["hdri"])
nt.links.new(env.outputs["Color"], nt.nodes["Background"].inputs["Color"])
nt.nodes["Background"].inputs["Strength"].default_value = float(job.get("sky", 1.0))

sun_d = job.get("sun")
if sun_d:
    ld = bpy.data.lights.new("Gunes", "SUN")
    ld.energy = float(job.get("sun_energy", 4.0))
    ld.angle = math.radians(1.0)
    ld.color = (1.0, 0.95, 0.88)
    so = bpy.data.objects.new("Gunes", ld)
    sc.collection.objects.link(so)
    so.rotation_euler = (conv(sun_d["target"]) - conv(sun_d["pos"])).to_track_quat("-Z", "Y").to_euler()

for i, L in enumerate(job.get("lights", [])):
    ld = bpy.data.lights.new(f"Tavan{i}", "AREA")
    ld.shape = "RECTANGLE"
    ld.size, ld.size_y = max(0.6, L["w"] * 0.45), max(0.6, L["d"] * 0.45)
    ld.energy = float(job.get("room_light", 9.0)) * L["w"] * L["d"]
    ld.color = (1.0, 0.86, 0.72)  # ~3500 K sıcak beyaz
    lo = bpy.data.objects.new(f"Tavan{i}", ld)
    sc.collection.objects.link(lo)
    lo.location = conv(L["pos"])  # alan ışığı yerel -Z'ye bakar: tavandan aşağı

# ---------------------------------------------------------------- malzeme düzeltmeleri (glTF → fiziksel)
def principled(m):
    if not m.use_nodes:
        return None
    return next((n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)


for m in bpy.data.materials:
    b = principled(m)
    if not b:
        continue
    n = m.name.lower()
    if n.startswith("archai_glass"):
        b.inputs["Base Color"].default_value = (1, 1, 1, 1)
        b.inputs["Transmission Weight"].default_value = 1.0
        b.inputs["Roughness"].default_value = 0.0
        b.inputs["IOR"].default_value = 1.5
        b.inputs["Alpha"].default_value = 1.0
    elif n.startswith("archai_water"):
        b.inputs["Base Color"].default_value = (0.12, 0.55, 0.65, 1)
        b.inputs["Transmission Weight"].default_value = 0.85
        b.inputs["Roughness"].default_value = 0.02
        b.inputs["IOR"].default_value = 1.33
        b.inputs["Alpha"].default_value = 1.0
    elif n.startswith("archai_mirror"):
        b.inputs["Metallic"].default_value = 1.0
        b.inputs["Roughness"].default_value = 0.0
    elif n.startswith("archai_ground") or n.startswith("archai_site"):
        b.inputs["Alpha"].default_value = 1.0

out = job["out_dir"]
os.makedirs(out, exist_ok=True)
cam_d = bpy.data.cameras.new("Kamera")
cam = bpy.data.objects.new("Kamera", cam_d)
sc.collection.objects.link(cam)
sc.camera = cam
cam_d.clip_start = 0.05

# ---------------------------------------------------------------- render
c = job["camera"]
e = c["matrix"]
M = Matrix(((e[0], e[4], e[8], e[12]), (e[1], e[5], e[9], e[13]), (e[2], e[6], e[10], e[14]), (e[3], e[7], e[11], e[15])))
cam.matrix_world = C4 @ M
cam_d.sensor_fit = "VERTICAL"
cam_d.angle_y = math.radians(c["fov"])
W = int(job.get("width", 1920))
sc.render.resolution_x, sc.render.resolution_y = W, int(round(W / c["aspect"]))
path = os.path.join(out, "foto.jpg")
sc.render.filepath = path
t0 = time.time()
log("ARCHAI_PROGRESS", 0, 1, "foto")
bpy.ops.render.render(write_still=True)
log("ARCHAI_PROGRESS", 1, 1, "foto", round(time.time() - t0, 1))
log("ARCHAI_RESULT", path)
