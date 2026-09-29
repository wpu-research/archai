"""Resim plan tanıma: test planı (3 daireli kat, tests/data/plan_3daire.jpg) elle kurulmuş modelle
(archai/apartment.py) karşılaştırılır. Eşikler, bugünkü doğruluğun biraz altında regresyon bekçisidir."""

from pathlib import Path

import pytest
from PIL import Image, ImageOps

from archai import plan_eval as pe
from archai import plan_image as pi

PLAN = "tests/data/plan_3daire.jpg"
TRUE_S = 46.2   # arka plan ızgarası 23,1 px = 0,5 m
# görsel repoda değil (üçüncü taraf çizim, .gitignore); yoksa testler atlanır
pytestmark = pytest.mark.skipif(not Path(PLAN).exists(), reason="test planı görseli yerelde yok")


def _metrics(path):
    els, rep = pi.recognize(path)
    ref = pe.apartment_reference(rep["px_per_m"], Image.open(path).height)
    return rep, pe.compare(els, ref, "Zemin", "Normal Kat")


def test_recognize_plan_without_hints():
    rep, m = _metrics(PLAN)
    assert abs(rep["px_per_m"] - TRUE_S) / TRUE_S < 0.01, rep["scale_method"]   # ölçek ipucusuz bulunur
    assert m["wall_precision"] >= 0.95 and m["wall_recall"] >= 0.95, m
    assert m["doors_matched"] >= 14 and m["doors_found"] <= m["doors_ref"] + 3, m
    assert m["rooms_found"] >= 15, m


def test_light_background_same_result(tmp_path):
    inv = tmp_path / "inv.png"
    ImageOps.invert(Image.open(PLAN).convert("RGB")).save(inv)   # beyaz zemin, siyah çizgi
    rep, m = _metrics(inv)
    assert abs(rep["px_per_m"] - TRUE_S) / TRUE_S < 0.01
    assert m["wall_precision"] >= 0.95 and m["wall_recall"] >= 0.95, m


def test_given_scale_is_used():
    els, rep = pi.recognize(PLAN, px_per_m=50.0)
    assert rep["px_per_m"] == 50.0 and rep["scale_method"] == "verilen ölçek"


def test_image_project_end_to_end(tmp_path):
    from archai import project
    res, els = project.run_image(PLAN, {"name": "Resim Plan", "image": {}}, tmp_path)
    assert res["report"]["source"] == "image" and res["report"]["walls"] > 20
    assert (tmp_path / "tanima_onay.png").exists() and "tanima_onay_png" in res["files"]
    assert res["summary"]["gross_floor_area"] > 200 and res["cost"]["total"] > 0


def test_villa_sheet_roundtrip(tmp_path):
    """Farklı stil: ArchAI'nin kendi 1/100 paftası (taralı duvar, ölçü zinciri, aks, antet, kapı yayı).
    Resimden okunan 1. kat, paftanın üretildiği modelle karşılaştırılır. Görsel repoya gerekmez."""
    from archai import project
    res, els = project.run_villa(tmp_path)
    png = tmp_path / "cizimler" / "03_normal_kat_plani.png"
    found, rep = pi.recognize(png)
    lv = next(e["level"] for e in els if e["type"] == "slab" and e.get("role") == "floor" and e["z"] > 1)
    al, k = pe.align(found, els, "Zemin", lv)
    assert abs(k - 1) < 0.05, k                                   # kapı genişliğinden ölçek ≈ doğru
    m = pe.compare(al, els, "Zemin", lv, tol=0.2)
    assert m["wall_precision"] >= 0.9 and m["wall_recall"] >= 0.9, m
    assert m["rooms_found"] >= m["rooms_ref"] - 1, m
    assert pe.windows(found, "Zemin") >= pe.windows(els, lv) - 1
