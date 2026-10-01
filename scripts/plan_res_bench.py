"""Resim plan tanıma — çözünürlük / ölçek ölçüm tablosu (geliştirme aracı, testler bunu çağırmaz).

  uv run python scripts/plan_res_bench.py [--scales 0.5,0.75,1,2] [--no-fixture] [--no-syn] [--given]

Satırlar: fikstür (tests/data/plan_3daire.jpg, varsa) ve ızgarasız kopyası; sentetik plan (make_test_plan DXF'inden
çizilen PNG, koyu + ızgarasız). Sütunlar: duvar isabet/kapsam, kapı eşleşen/ref, mahal, ölçek hatası, süre.
Çıktılar geçici dizine yazılır (references/ ve out/ değişmez).
"""

import argparse
import importlib.util
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="plan_bench_"))
os.environ.setdefault("ARCHAI_OUT", str(TMP / "out"))

import numpy as np  # noqa: E402
from PIL import Image  # noqa: E402

from archai import plan_eval as pe  # noqa: E402
from archai import plan_image as pi  # noqa: E402

PLAN = ROOT / "tests" / "data" / "plan_3daire.jpg"
TRUE_S, SYN_S = 46.2, 100.0


def scaled(src, f, out):
    im = Image.open(src).convert("RGB")
    if f != 1:
        im = im.resize((round(im.width * f), round(im.height * f)), Image.LANCZOS)
    im.save(out)
    return out


def degrid(src, out):
    """Fikstürün soluk arka plan ızgarasını sil: zemine yakın (kontrastı < 45) pikseller zemin rengine çekilir."""
    a = np.asarray(Image.open(src).convert("RGB")).astype(np.int16)
    bg = np.median(a.reshape(-1, 3), 0)
    faint = np.abs(a - bg).max(2) < 45
    a[faint] = bg
    Image.fromarray(a.astype(np.uint8)).save(out)
    return out


GIVEN = False   # --given: gerçek ölçek verilir (tanıma doğruluğu ölçek tahmininden ayrı ölçülür)


def row(name, path, true_s, ref_fn):
    t = time.perf_counter()
    els, rep = pi.recognize(path, px_per_m=true_s if GIVEN else None)
    dt = time.perf_counter() - t
    m = ref_fn(els, rep)
    err = rep["px_per_m"] / true_s - 1
    print(f"{name:<22} P={m['wall_precision']:.3f} R={m['wall_recall']:.3f} kapı {m['doors_matched']:>2}/{m['doors_ref']:<2}"
          f" (bulunan {m['doors_found']:>2}) mahal {m['rooms_found']:>2}/{m['rooms_ref']:<2} ölçek {100 * err:+6.2f}%"
          f" {dt:5.2f}s  [{rep['scale_method']}]", flush=True)
    return m, err, dt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scales", default="0.5,0.75,1,2")
    ap.add_argument("--no-fixture", action="store_true")
    ap.add_argument("--no-syn", action="store_true")
    ap.add_argument("--given", action="store_true")
    a = ap.parse_args()
    global GIVEN
    GIVEN = a.given
    fs = [float(x) for x in a.scales.split(",")]
    if PLAN.exists() and not a.no_fixture:
        H0 = Image.open(PLAN).height
        for tag, src in (("fikstür", PLAN), ("fikstür-ızgarasız", degrid(PLAN, TMP / "nogrid.png"))):
            for f in fs:
                p = scaled(src, f, TMP / f"{tag}_{f}.png")
                row(f"{tag} {f}×", p, TRUE_S * f,
                    lambda els, rep, f=f: pe.compare(els, pe.apartment_reference(rep["px_per_m"] / f, H0), "Zemin", "Normal Kat"))
    if not a.no_syn:
        d = TMP / "ref"
        subprocess.run([sys.executable, str(ROOT / "scripts" / "make_test_plan.py")], check=True, capture_output=True,
                       env={**os.environ, "ARCHAI_REF_OUT": str(d)})
        spec = importlib.util.spec_from_file_location("tpi", ROOT / "tests" / "test_plan_image.py")
        tpi = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tpi)
        from archai.dxf_import import import_dxf
        dxf = d / "test_plan_2+1.dxf"
        ref, _ = import_dxf(dxf, add_roof=False)

        def cmp(els, rep):
            al, _ = pe.align(els, ref, "Zemin", "Zemin")
            return pe.compare(al, ref, "Zemin", "Zemin")
        for tag, kw in (("sentetik", {}), ("sentetik-ızgarasız", {"dark": False, "grid": None})):
            src = tpi._render_dxf(dxf, TMP / f"{tag}.png", **kw)
            for f in fs:
                row(f"{tag} {f}×", scaled(src, f, TMP / f"{tag}_{f}.png"), SYN_S * f, cmp)


if __name__ == "__main__":
    main()
