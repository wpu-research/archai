"""İç mekân varlıklarını Poly Haven'dan indirir (hepsi CC0 — atıf gerekmez, ticari kullanım serbest).

    uv run python scripts/fetch_assets.py

webapp/static/assets/{tex,models,hdri}/ altına yazar ve LICENSES.json üretir.
"""

import json
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "webapp" / "static" / "assets"
API = "https://api.polyhaven.com/files/"
UA = {"User-Agent": "archai-asset-fetch/1.0"}

TEXTURES = ["laminate_floor_02", "herringbone_parquet", "oak_wood_planks", "wood_floor", "marble_tiles",
            "large_grey_tiles", "terrazzo_tiles", "painted_plaster_wall", "long_white_tiles"]
MAPS = {"diff": "Diffuse", "nor_gl": "nor_gl", "rough": "Rough"}
MODELS = ["sofa_03", "ArmChair_01", "CoffeeTable_01", "WoodenTable_01", "WoodenChair_01", "Television_01",
          "modern_wooden_cabinet", "side_table_01", "Ottoman_01", "potted_plant_02"]
HDRI = "kloofendal_48d_partly_cloudy_puresky"


def get(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read()


def save(url, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_bytes(get(url))
    return path.stat().st_size


def main():
    total, lic = 0, {}
    for tid in TEXTURES:
        files = json.loads(get(API + tid))
        for key, name in MAPS.items():
            node = files.get(name) or files.get(key)
            if not node:
                continue
            f = node["1k"]["jpg"]
            total += save(f["url"], ROOT / "tex" / tid / f"{key}.jpg")
        lic[tid] = {"source": f"https://polyhaven.com/a/{tid}", "license": "CC0"}
    for mid in MODELS:
        files = json.loads(get(API + mid))
        g = files["gltf"]["1k"]["gltf"]
        total += save(g["url"], ROOT / "models" / mid / f"{mid}.gltf")
        base = None
        for rel, inc in g.get("include", {}).items():
            total += save(inc["url"], ROOT / "models" / mid / rel)
            base = inc["url"].rsplit("/", 1)[0]
        # API "include" listesi bazen eksik: gltf'in başvurduğu tüm dokuları tamamla
        doc = json.loads((ROOT / "models" / mid / f"{mid}.gltf").read_text())
        for img in doc.get("images", []):
            rel = img.get("uri", "")
            if rel and not (ROOT / "models" / mid / rel).exists() and base:
                total += save(f"{base}/{rel.rsplit('/', 1)[-1]}", ROOT / "models" / mid / rel)
        lic[mid] = {"source": f"https://polyhaven.com/a/{mid}", "license": "CC0"}
    files = json.loads(get(API + HDRI))
    total += save(files["hdri"]["1k"]["hdr"]["url"], ROOT / "hdri" / "sky_1k.hdr")
    lic[HDRI] = {"source": f"https://polyhaven.com/a/{HDRI}", "license": "CC0"}
    (ROOT / "LICENSES.json").write_text(json.dumps(lic, indent=1))
    print(f"toplam {total / 1e6:.1f} MB")


if __name__ == "__main__":
    main()
