"""Uçtan uca smoke test: villa kur → kamera → colormap + preview → video paketi.

    uv run python scripts/demo_villa.py [--full]   # --full: tüm animasyonu da render et
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "mcp_server"))
import server as s  # noqa: E402

full = "--full" in sys.argv

print(s.blender_status())
s.reset_scene()

# Ev: 14 x 8 m, 3.2 m tek kat, güney cephesi (y=0) büyük açıklıklı
W, D, H = 14.0, 8.0, 3.2
els = [
    {"type": "slab", "name": "ground", "tag": "terrain", "points": [[-30, -30], [40, -30], [40, 30], [-30, 30]], "z": 0, "thickness": 0.1},
    {"type": "slab", "name": "terrace", "tag": "stone", "points": [[-4, -9], [W + 4, -9], [W + 4, D], [-4, D]], "z": 0.3, "thickness": 0.3},
    {"type": "slab", "name": "floor", "tag": "floor", "points": [[0, 0], [W, 0], [W, D], [0, D]], "z": 0.35, "thickness": 0.05},
    {"type": "wall", "name": "w_south", "start": [0, 0], "end": [W, 0], "height": H, "base_z": 0.3,
     "openings": [{"offset": 1.0, "width": 3.0, "kind": "window", "sill": 0.1, "height": 2.6},
                  {"offset": 5.5, "width": 3.0, "kind": "window", "sill": 0.1, "height": 2.6},
                  {"offset": 10.0, "width": 3.0, "kind": "window", "sill": 0.1, "height": 2.6}]},
    {"type": "wall", "name": "w_north", "start": [W, D], "end": [0, D], "height": H, "base_z": 0.3,
     "openings": [{"offset": 3.0, "width": 1.2, "kind": "window"}, {"offset": 6.5, "width": 1.0, "kind": "door", "leaf": True},
                  {"offset": 10.0, "width": 1.2, "kind": "window"}]},
    {"type": "wall", "name": "w_east", "start": [W, 0], "end": [W, D], "height": H, "base_z": 0.3,
     "openings": [{"offset": 3.0, "width": 2.0, "kind": "window"}]},
    {"type": "wall", "name": "w_west", "start": [0, D], "end": [0, 0], "height": H, "base_z": 0.3},
    {"type": "slab", "name": "roof", "tag": "roof", "points": [[-0.4, -0.4], [W + 0.4, -0.4], [W + 0.4, D + 0.4], [-0.4, D + 0.4]], "z": H + 0.55, "thickness": 0.25},
    # Pergola: 4 kolon + kirişler
    *[{"type": "box", "name": f"perg_col{i}", "tag": "wall", "origin": [x, -4.2, 0.6], "size": [0.35, 0.35, 2.8]}
      for i, x in enumerate([0.5, 4.8, 9.1, 13.2])],
    {"type": "box", "name": "perg_beam", "tag": "wood", "origin": [0.3, -4.3, 3.4], "size": [13.4, 0.5, 0.25]},
    *[{"type": "box", "name": f"perg_slat{i}", "tag": "wood", "origin": [0.4 + i * 0.7, -4.3, 3.65], "size": [0.12, 4.3, 0.1]}
      for i in range(19)],
    # Havuz
    {"type": "slab", "name": "pool_edge", "tag": "stone", "points": [[1, -18], [13, -18], [13, -10], [1, -10]], "z": 0.35, "thickness": 0.35},
    {"type": "slab", "name": "pool_water", "tag": "water", "points": [[1.4, -17.6], [12.6, -17.6], [12.6, -10.4], [1.4, -10.4]], "z": 0.38, "thickness": 0.05},
    # Mobilya
    *[{"type": "box", "name": f"lounger{i}", "tag": "fabric", "origin": [2 + i * 3, -8.7, 0.6], "size": [0.8, 2.0, 0.35]} for i in range(4)],
    {"type": "box", "name": "sofa", "tag": "fabric", "origin": [3.5, -3.5, 0.6], "size": [5.0, 0.9, 0.7]},
    {"type": "box", "name": "table", "tag": "wood", "origin": [5.0, -2.2, 0.6], "size": [2.0, 1.0, 0.4]},
    # Peyzaj
    *[{"type": "tree", "name": f"tree{i}", "position": p, "height": h}
      for i, (p, h) in enumerate([([-6, -4], 7), ([-7, 4], 9), ([19, -2], 8), ([20, 6], 6), ([-5, -15], 6), ([18, -15], 7)])],
    {"type": "box", "name": "garden_wall", "tag": "stone", "origin": [-4, -20.5, 0], "size": [22, 0.6, 1.0]},
]
r = s.build(els)
print("build:", r["created"], "obje, hata:", r["errors"])
assert not r["errors"], r["errors"]

info = s.scene_info(limit=0)
print("tags:", info["tags"], "bbox:", info["bbox"])

# Havuzun güneyinden eve doğru yavaş dolly + hafif yükselme
print(s.camera_path(mode="flythrough", frames=96 if full else 24, lens=28,
                    points=[[-2, -24, 2.0], [4, -19, 2.4], [9, -14, 2.8]],
                    targets=[[7, 0, 1.8], [7, 0, 2.0], [7, 2, 1.8]]))

print(s.render(kind="colormap", still=1))
print(s.render(kind="preview", still=1, samples=32))
if full:
    print(s.render(kind="colormap"))
    print(s.prepare_video_job(
        name="villa_demo",
        style_prompt="Cinematic architectural film of a Mediterranean villa in Saint-Tropez, golden hour, soft shadows, photorealistic, 35mm.",
        materials={"wall": "white lime-washed stucco", "floor": "light travertine", "roof": "flat roof with thin stone coping",
                   "glass": "large frameless glass doors with reflections", "frame": "slim black steel frames",
                   "wood": "weathered oak beams with reed shading", "stone": "warm beige limestone paving",
                   "water": "turquoise infinity pool water", "tree": "olive and umbrella pine trees",
                   "fabric": "off-white linen cushions", "terrain": "dry mediterranean garden with lavender"},
        camera_note="slow forward dolly with slight crane up"))
s.save_blend(str(s.OUT / "villa_demo.blend"))
print("OK")
