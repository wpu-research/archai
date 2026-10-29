"""Çokgen (yamuk) parsel: yerleştirme, imar kontrolü, web uçları."""
import math
from pathlib import Path

import ezdxf
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Polygon

from archai import parcel
from archai.generate import generate
from webapp.app import app

c = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
TRAPEZ = [(0, 0), (32, 0), (29, 26), (2, 23)]
ZON = {"taks": 0.43, "kaks": 3.0, "front": 3, "side": 3.5, "rear": 3.5, "max_floors": 7, "floor_height": 2.75}
PROG = {"unit_type": "1+1", "units_per_floor": 4}


def test_dikdortgen_cokgen_dikdortgenle_ayni_sonucu_verir():
    rect = [(0, 0), (32, 0), (32, 24), (0, 24)]
    zon = {**ZON, "side": 3.5}
    e1, r1 = generate({"width": 32, "depth": 24}, zon, PROG)
    e2, r2 = parcel.generate_on_polygon({"polygon": rect}, zon, PROG)
    assert r2["footprint"] == r1["footprint"] and r2["floors"] == r1["floors"]
    assert r2["gross_total"] == pytest.approx(r1["gross_total"], abs=0.5)
    assert r2["checks"]["taks"]["value"] == pytest.approx(r1["checks"]["taks"]["value"], abs=0.01)


def test_yamuk_parsel_bina_sinirlar_icinde_ve_cekmeler_saglanir():
    els, rep = parcel.generate_on_polygon({"polygon": TRAPEZ}, ZON, PROG)
    poly = Polygon(rep["parcel_geom"]["polygon"])
    floor = next(e for e in els if e["type"] == "slab" and e.get("role") == "floor")
    assert poly.buffer(1e-6).contains(Polygon([tuple(p[:2]) for p in floor["points"]]))
    assert rep["parcel_area"] == pytest.approx(Polygon(TRAPEZ).area, abs=0.1)
    assert rep["checks"]["setback_ok"] and rep["checks"]["taks"]["ok"] and rep["checks"]["kaks"]["ok"]
    assert rep["checks"]["setbacks"]["front"] >= 3 - 1e-6
    assert next(e for e in els if e.get("name") == "parsel")["points"] == [list(map(float, p)) for p in TRAPEZ]


def test_donuk_parsel_on_kenar_x_eksenine_gelir():
    ang = math.radians(35)
    rot = [(x * math.cos(ang) - y * math.sin(ang) + 500, x * math.sin(ang) + y * math.cos(ang) - 80) for x, y in TRAPEZ]
    f = parcel.fit(rot, ZON, front_edge=0)
    assert f["rotation_deg"] == pytest.approx(-35, abs=0.1)
    assert min(y for _, y in f["pts"]) == pytest.approx(0, abs=1e-6)
    assert f["area"] == pytest.approx(Polygon(TRAPEZ).area, abs=0.1)


def test_dar_parselde_anlamli_hata():
    with pytest.raises(ValueError, match="yapılaşma alanı|dikdörtgen"):
        parcel.generate_on_polygon({"polygon": [(0, 0), (12, 0), (12, 30), (0, 30)]},
                                   {**ZON, "side": 5}, PROG)


def _derece_dxf(path):
    doc = ezdxf.new("R2000")
    pts = [(28.86189, 41.01303), (28.86194, 41.01293), (28.86229, 41.01304), (28.86224, 41.01314)]
    doc.modelspace().add_lwpolyline(pts, close=True)
    doc.saveas(path)


def test_dxf_derece_metreye_cevrilir(tmp_path):
    p = tmp_path / "parsel.dxf"
    _derece_dxf(p)
    pts, info = parcel.polygon_from_dxf(p)
    assert info["geographic"] and len(pts) == 4
    assert 100 < Polygon(pts).area < 2000


def test_web_parsel_dxf_ve_cokgen_proje(tmp_path):
    p = tmp_path / "parsel.dxf"
    _derece_dxf(p)
    r = c.post("/api/parcel/dxf", files={"file": ("parsel.dxf", p.read_bytes())})
    assert r.status_code == 200, r.text
    d = r.json()
    assert len(d["polygon"]) == 4 and d["area"] > 100
    assert c.post("/api/parcel/dxf", files={"file": ("x.txt", b"x")}).status_code == 422
    r = c.post("/api/projects", json={"name": "yamuk", "parcel": {"polygon": [list(p) for p in TRAPEZ]},
                                      "zoning": ZON, "program": PROG})
    assert r.status_code == 200, r.text
    pr = r.json()
    assert pr["report"]["parcel_geom"]["front_edge"] == 0 and any(s for s in pr["sheets"])
    assert c.post("/api/projects", json={"name": "x", "parcel": {"width": 10}, "zoning": ZON}).status_code == 422


def test_emsal_yok_dar_seritte_dort_daire():
    """TKGM şeridi gibi dar parsel (≈32 × 11,9 m), TAKS/KAKS sınırı yok, ön/arka 0,5 m, yan 0: kat başı 4 daire."""
    strip = [(0, 0), (31.8, 0), (31.8, 11.9), (0, 11.9)]
    zon = {"emsal_yok": True, "front": 0.5, "side": 0, "rear": 0.5, "max_floors": 7, "floor_height": 2.75}
    els, rep = parcel.generate_on_polygon({"polygon": strip}, zon, {"unit_type": "1+1", "units_per_floor": "auto"})
    assert rep["units_per_floor"] == 4 and rep["floors"] == 7
    assert rep["checks"]["taks"]["limit"] is None and rep["checks"]["taks"]["ok"]
    assert rep["checks"]["setback_ok"]


def test_geojson_ve_kml_parsel(tmp_path):
    import json as _j
    ring = [[28.86189, 41.01303], [28.86194, 41.01293], [28.86229, 41.01304], [28.86224, 41.01314], [28.86189, 41.01303]]
    gj = tmp_path / "p.geojson"
    gj.write_text(_j.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "properties": {},
                                                                       "geometry": {"type": "Polygon", "coordinates": [ring]}}]}))
    kml = tmp_path / "p.kml"
    kml.write_text("<kml><Placemark><Polygon><outerBoundaryIs><LinearRing><coordinates>"
                   + " ".join(f"{x},{y},0" for x, y in ring) + "</coordinates></LinearRing></outerBoundaryIs></Polygon></Placemark></kml>")
    for f in (gj, kml):
        pts, info = parcel.polygon_from_file(f)
        assert info["geographic"] and len(pts) == 4 and 50 < Polygon(pts).area < 2000
    r = c.post("/api/parcel/dxf", files={"file": ("p.geojson", gj.read_bytes())})
    assert r.status_code == 200 and len(r.json()["polygon"]) == 4
    assert c.post("/api/parcel/dxf", files={"file": ("p.txt", b"x")}).status_code == 422
    import pytest as _p
    with _p.raises(ValueError):
        parcel.polygon_from_geojson('{"type": "Point", "coordinates": [1, 2]}')
