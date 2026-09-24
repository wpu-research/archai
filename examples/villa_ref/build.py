"""references/villa_ref.png'den kurulan model (ajan çıktısı).

Koordinatlar: +y denize doğru (havuzun uzun ekseni), +x loggia/ev tarafı, z=0 teras kotu.

    uv run python examples/villa_ref/build.py [still|video]
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "mcp_server"))
import server as s  # noqa: E402

mode = sys.argv[1] if len(sys.argv) > 1 else "still"
OUT = ROOT / "out" / "villa_ref"


def pot_olive(name, x, y, h=2.2):
    return [
        {"type": "cylinder", "name": f"{name}_pot", "tag": "terracotta", "center": [x, y, 0.05],
         "radius": 0.35, "radius_top": 0.45, "height": 0.7},
        {"type": "cylinder", "name": f"{name}_trunk", "tag": "wood", "center": [x, y, 0.7], "radius": 0.05, "height": h * 0.5},
        {"type": "sphere", "name": f"{name}_crown", "tag": "tree", "center": [x, y, 0.7 + h * 0.6], "radius": h * 0.3,
         "scale": [1, 1, 0.9]},
    ]


def shrub(name, x, y, z, r=0.8):
    return {"type": "sphere", "name": name, "tag": "vegetation", "center": [x, y, z + r * 0.4], "radius": r,
            "scale": [1.2, 1, 0.6]}


els = []

# --- Arazi: üst plato (villa), alt bahçe terası, uçurum, deniz, uzak tepeler
els += [
    {"type": "slab", "name": "plateau", "tag": "terrain", "points": [[-2.2, -4], [35, -4], [35, 30], [-2.2, 30]], "z": -0.05, "thickness": 3},
    # havuzun solunda yamaç: denize doğru alçalan kaba kademeler
    {"type": "slab", "name": "slope1", "tag": "terrain", "points": [[-12, -4], [-2.2, -4], [-2.2, 30], [-12, 30]], "z": -4, "thickness": 2},
    {"type": "slab", "name": "slope2", "tag": "hill", "points": [[-60, -30], [-12, -30], [-12, 34], [-60, 34]], "z": -12, "thickness": 58},
    {"type": "slab", "name": "garden_low", "tag": "terrain", "points": [[-25, -30], [35, -30], [35, -4], [-25, -4]], "z": -2.6, "thickness": 1},
    {"type": "box", "name": "retaining_wall", "tag": "stone", "origin": [-6, -4.6, -2.6], "size": [26, 0.6, 2.6]},
    {"type": "slab", "name": "sea", "tag": "sea", "points": [[-3000, 30], [3000, 30], [3000, 4000], [-3000, 4000]], "z": -70, "thickness": 1},
    {"type": "slab", "name": "cliff", "tag": "hill", "points": [[-25, 30], [35, 30], [35, 34], [-25, 34]], "z": -3, "thickness": 67},
    *[{"type": "sphere", "name": f"hill{i}", "tag": "hill", "center": [x, y, -70], "radius": r, "scale": sc}
      for i, (x, y, r, sc) in enumerate([(-2600, 2600, 400, [3, 1, 0.3]), (-1500, 3000, 450, [3.5, 1, 0.28]),
                                         (-300, 3300, 380, [3, 1, 0.25])])],
]

# --- Teras ve sonsuzluk havuzu (x 0..5, y 0..15)
els += [
    {"type": "slab", "name": "terrace", "tag": "stone", "points": [[-1.2, -1.5], [13.5, -1.5], [13.5, 18], [-1.2, 18]], "z": 0.05, "thickness": 0.1},
    {"type": "slab", "name": "pool_water", "tag": "water", "points": [[0, 0], [5, 0], [5, 15], [0, 15]], "z": 0.07, "thickness": 0.02},
]

# --- Loggia: 4 kolon (x=8.4), kalın saçaklı düz çatı
cols = [1.0, 4.8, 8.6, 12.4]
els += [{"type": "box", "name": f"loggia_col{i}", "tag": "wall", "origin": [8.2, y, 0.05], "size": [0.55, 0.55, 3.2]}
        for i, y in enumerate(cols)]
els += [
    {"type": "slab", "name": "loggia_roof", "tag": "roof", "points": [[8.0, 0.6], [14, 0.6], [14, 16.5], [8.0, 16.5]], "z": 3.7, "thickness": 0.12},
    {"type": "box", "name": "loggia_fascia_front", "tag": "wall", "origin": [7.9, 0.5, 3.25], "size": [0.4, 16.1, 0.5]},
    {"type": "box", "name": "loggia_fascia_end", "tag": "wall", "origin": [7.9, 0.5, 3.25], "size": [6.1, 0.4, 0.5]},
    # iç mekân: arka duvar, kanepe, yemek masası, perdeler
    {"type": "wall", "name": "loggia_back", "start": [13.6, 0.8], "end": [13.6, 16.4], "height": 3.2, "base_z": 0.05, "thickness": 0.3},
    {"type": "box", "name": "sofa", "tag": "fabric", "origin": [12.2, 8.5, 0.05], "size": [1.0, 4.0, 0.8]},
    {"type": "box", "name": "sofa_l", "tag": "fabric", "origin": [10.0, 12.0, 0.05], "size": [3.0, 1.0, 0.8]},
    {"type": "box", "name": "dining_table", "tag": "wood", "origin": [10.0, 3.5, 0.8], "size": [1.1, 3.2, 0.08]},
    *[{"type": "box", "name": f"dining_leg{i}", "tag": "wood", "origin": [x, y, 0.05], "size": [0.1, 0.1, 0.75]}
      for i, (x, y) in enumerate([(10.05, 3.6), (10.95, 3.6), (10.05, 6.55), (10.95, 6.55)])],
    *[{"type": "box", "name": f"chair{i}", "tag": "furniture", "origin": [x, y, 0.05], "size": [0.5, 0.5, 0.9]}
      for i, (x, y) in enumerate([(9.3, 4.0), (9.3, 5.5), (11.3, 4.0), (11.3, 5.5)])],
    *[{"type": "box", "name": f"curtain{i}", "tag": "fabric", "origin": [8.3, y, 0.05], "size": [0.08, 0.9, 3.1]}
      for i, y in enumerate([1.6, 11.5])],
]

# --- Ana ev: loggia arkasında, daha yüksek çatı + baca
els += [
    {"type": "wall", "name": "house_s", "start": [13.6, -0.5], "end": [21, -0.5], "height": 4.3, "base_z": 0.05, "thickness": 0.35,
     "openings": [{"offset": 2.5, "width": 1.4, "kind": "window", "sill": 1.0, "height": 1.6}]},
    {"type": "wall", "name": "house_e", "start": [21, -0.5], "end": [21, 17], "height": 4.3, "base_z": 0.05, "thickness": 0.35},
    {"type": "wall", "name": "house_n", "start": [21, 17], "end": [13.6, 17], "height": 4.3, "base_z": 0.05, "thickness": 0.35,
     "openings": [{"offset": 2.0, "width": 2.6, "kind": "window", "sill": 0.1, "height": 2.6}]},
    {"type": "slab", "name": "house_roof", "tag": "roof", "points": [[13.3, -0.8], [21.3, -0.8], [21.3, 17.3], [13.3, 17.3]], "z": 4.55, "thickness": 0.25},
    {"type": "box", "name": "house_parapet", "tag": "wall", "origin": [13.2, -0.9, 4.3], "size": [8.3, 18.3, 0.35]},
    {"type": "box", "name": "chimney", "tag": "wall", "origin": [15.0, 12.5, 4.5], "size": [1.1, 1.1, 2.4]},
    {"type": "box", "name": "chimney_cap", "tag": "stone", "origin": [14.9, 12.4, 6.9], "size": [1.3, 1.3, 0.15]},
]

# --- Havuz kenarı: şemsiye, 2 şezlong, saksılı zeytinler
els += [
    {"type": "cylinder", "name": "umbrella_pole", "tag": "metal", "center": [6.2, 7.2, 0.05], "radius": 0.03, "height": 2.4},
    {"type": "cylinder", "name": "umbrella", "tag": "fabric", "center": [6.2, 7.2, 2.1], "radius": 1.5, "radius_top": 0.05, "height": 0.5},
    *[{"type": "box", "name": f"lounger{i}", "tag": "fabric", "origin": [5.5 + i * 0.3, y, 0.05], "size": [0.75, 2.0, 0.35], "rotation_z": -20}
      for i, y in enumerate([4.2, 5.8])],
    *pot_olive("pot1", 7.2, 1.5), *pot_olive("pot2", 7.3, 13.8, 2.6), *pot_olive("pot3", 6.8, 16.8),
    *pot_olive("pot4", 12.8, -1.0, 2.4), *pot_olive("pot5", -0.6, 16.5, 1.8),
]

# --- Peyzaj: servi, fıstık çamları, zeytin, alt bahçe çalıları
els += [
    {"type": "tree", "name": "cypress", "position": [-3.0, 19], "base_z": -4, "height": 11, "crown_scale": [0.28, 0.28, 2.1]},
    *[{"type": "tree", "name": f"pine{i}", "position": p, "height": h, "crown_scale": [1.8, 1.8, 0.35]}
      for i, (p, h) in enumerate([([-12, 26], 12), ([4, 28], 10), ([18, 27], 13), ([28, 22], 11), ([-20, 12], 9)])],
    # kadrajın üstünü çerçeveleyen fıstık çamı (kameranın arkasında, tacı öne uzanır)
    {"type": "sphere", "name": "pine_frame_crown", "tag": "tree", "center": [6.5, -6.0, 10.2], "radius": 7.5,
     "scale": [1.3, 1.1, 0.28]},
    {"type": "cylinder", "name": "pine_frame_trunk", "tag": "wood", "center": [6, -9, -2.6], "radius": 0.35, "height": 13.5},
    {"type": "tree", "name": "olive_front", "position": [-6.0, -4.8], "height": 5, "base_z": -2.6, "crown_scale": [1.2, 1.2, 0.8]},
    *[shrub(f"shrub{i}", x, y, -2.6, r) for i, (x, y, r) in enumerate(
        [(1, -7, 1.0), (5, -8, 0.9), (9, -6.5, 1.1), (13, -7.5, 1.0), (16, -6, 0.9), (3, -11, 1.2), (11, -11, 1.0), (-1, -6, 0.8)])],
    *[shrub(f"lush{i}", x, y, -2.6, r) for i, (x, y, r) in enumerate(
        [(-1.5, -8, 1.3), (2, -6, 1.0), (6.5, -5.5, 1.2), (7.5, -9, 1.4), (-3, -11, 1.1), (1, -13, 1.3), (5, -12, 1.2), (9, -13, 1.1)])],
    *[shrub(f"slope_sh{i}", x, y, -4, r) for i, (x, y, r) in enumerate([(-4, 2, 1.4), (-5, 8, 1.6), (-3.5, 11, 1.2), (-6, 22, 1.8)])],
    *[shrub(f"bed{i}", x, y, 0.05, 0.7) for i, (x, y) in enumerate([(-1.0, -2.3), (2.5, -2.4), (11.5, -2.4), (15, -2.2)])],
]

print(s.blender_status())
s.reset_scene()
r = s.build(els)
print("build:", r["created"], "obje, hatalar:", r["errors"])
print("tags:", s.scene_info(limit=0)["tags"])

# Referans kadrajı: bahçeden yüksek, aşağı ve denize doğru. Video için yavaş yükselen dolly.
frames = 120 if mode == "video" else 2
print(s.camera_path(mode="flythrough", frames=frames, lens=23,
                    points=[[-5, -10, 7.5], [-3.8, -8.8, 8.2]],
                    targets=[[7, 10, -1.2], [7, 11, -0.8]]))

res = [1080, 1920] if mode == "video" else [540, 960]
print(s.render(kind="colormap", still=1, resolution=res, out_dir=str(OUT)))
print(s.render(kind="preview", still=1, resolution=res, out_dir=str(OUT)))
if mode == "video":
    print(s.render(kind="colormap", resolution=res, out_dir=str(OUT)))
    job = s.prepare_video_job(
        name="villa_ref", source_dir=str(OUT),
        style_prompt=("Photorealistic cinematic architectural film of a Mediterranean clifftop villa above the sea "
                      "near Saint-Tropez, late morning sun, crisp shadows, warm stone tones, 35mm film look."),
        materials={
            "wall": "warm off-white lime plaster, thick square columns and fascia",
            "roof": "flat roof of weathered timber planks and reed shading",
            "stone": "pale travertine paving and dry-laid limestone retaining walls",
            "water": "clear turquoise infinity pool water with caustics",
            "sea": "deep blue Mediterranean sea with sun glints",
            "hill": "distant hazy rocky coastline and headlands",
            "terrain": "dry mediterranean garden: lavender, rosemary, gravel paths",
            "vegetation": "dense lavender and rosemary shrubs",
            "tree": "umbrella pines, olive trees and a slim Italian cypress",
            "wood": "tree trunks and teak furniture",
            "terracotta": "large terracotta planters",
            "fabric": "off-white linen cushions, parasol and curtains",
            "furniture": "woven rattan dining chairs",
            "metal": "thin parasol pole",
            "glass": "dark glazed windows with reflections",
            "frame": "slim bronze window frames",
        },
        camera_note="slow forward push-in with a gentle crane up, high vantage point from the garden")
    print(job["job_dir"], "eksik malzeme:", job["missing_materials"])
s.save_blend(str(OUT / "villa_ref.blend"))
