from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from webapp.app import app

ROOT = Path(__file__).resolve().parents[1]
c = TestClient(app)


def test_quick_project_and_adjust():
    r = c.post("/api/projects", json={"name": "api test", "quick": {"gross_area": 450, "floors": 3, "unit_type": "2+1"}})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["cost"]["total"] > 0 and len(p["sheets"]) >= 4
    for key in ("teklif_docx", "metraj_maliyet_xlsx", "sartname_docx", "cizim_pdf"):
        assert c.get(p["files"][key]).status_code == 200, key
    r2 = c.put(f"/api/projects/{p['id']}/adjust", json={"variants": {"ZEM-01": "traverten"}, "vat_pct": 10})
    assert r2.status_code == 200 and r2.json()["cost"]["vat_pct"] == 10
    assert r2.json()["cost"]["total"] != p["cost"]["total"]


def test_dxf_upload():
    with open(ROOT / "references" / "test_plan_2+1.dxf", "rb") as f:
        r = c.post("/api/projects/dxf", files={"file": ("plan.dxf", f)}, data={"name": "dxf api", "floors": "2"})
    assert r.status_code == 200, r.text
    assert r.json()["report"]["walls"] == 7


def test_bad_input_and_path_traversal():
    assert c.post("/api/projects", json={"name": "x"}).status_code == 422
    r = c.post("/api/projects", json={"name": "x", "parcel": {"width": 10, "depth": 10},
                                      "zoning": {"taks": 0.4, "kaks": 1, "front": 5, "side": 3, "rear": 3}})
    assert r.status_code == 422  # çekmelerden sonra alan yok
    assert c.get("/files/../../pyproject.toml").status_code == 404


def test_interior_roundtrip():
    r = c.post("/api/projects", json={"name": "ic mekan", "quick": {"gross_area": 300, "floors": 2, "unit_type": "2+1"}})
    pid = r.json()["id"]
    assert c.get(f"/api/projects/{pid}/interior").json() == {"floors": {}, "paint": "kirik_beyaz", "objects": []}
    design = {"floors": {"Zemin Kat/Daire A/Salon": "marble_tiles"}, "paint": "bej",
              "objects": [{"id": "a1", "kind": "klozet", "level": "Zemin Kat", "x": 1.5, "y": 2.0, "rot": 1.57, "evil": "x"}]}
    assert c.put(f"/api/projects/{pid}/interior", json=design).json()["objects"] == 1
    got = c.get(f"/api/projects/{pid}/interior").json()
    assert got["floors"]["Zemin Kat/Daire A/Salon"] == "marble_tiles" and got["paint"] == "bej"
    assert "evil" not in got["objects"][0]  # yalnız izinli alanlar saklanır
    assert c.put("/api/projects/yok/interior", json=design).status_code == 404
    assert c.put(f"/api/projects/{pid}/interior", json={"objects": "x"}).status_code == 422


def test_cabin_endpoint():
    r = c.post("/api/projects/cabin", json={})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["name"] == "Dağ Evi Demo" and p["report"]["floors"] == 2 and len(p["sheets"]) >= 4
    inter = c.get(f"/api/projects/{p['id']}/interior").json()
    assert len(inter["objects"]) > 15 and inter["floors"]


def test_apartment_endpoint():
    r = c.post("/api/projects/apartment", json={})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["name"] == "Apartman Katı" and p["report"]["unit_count"] == 3 and len(p["sheets"]) >= 4
    inter = c.get(f"/api/projects/{p['id']}/interior").json()
    assert len(inter["objects"]) == 72
    # parametrik ölçüler kaydetme sonrası korunur, tür dışı değerler atılır
    inter["objects"][0].update(w=2.6, kitap=True, side="x", orta=1, decor=True)
    assert c.put(f"/api/projects/{p['id']}/interior", json=inter).status_code == 200
    o = c.get(f"/api/projects/{p['id']}/interior").json()["objects"][0]
    assert o["w"] == 2.6 and o["kitap"] is True and o["decor"] is True and "side" not in o and "orta" not in o


def test_villa_endpoint():
    r = c.post("/api/projects/villa", json={})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["name"] == "Villa Demo" and p["report"]["floors"] == 2 and len(p["sheets"]) >= 4
    inter = c.get(f"/api/projects/{p['id']}/interior").json()
    assert len(inter["objects"]) > 50 and inter["floors"]
    assert any(r["code"] == "HAV-01" and r["quantity"] > 0 for r in p["cost"]["rows"])  # havuz maliyete girdi


@pytest.mark.skipif(not (ROOT / "tests/data/plan_3daire.jpg").exists(), reason="test planı görseli yerelde yok")
def test_image_plan_upload():
    with open("tests/data/plan_3daire.jpg", "rb") as f:
        r = c.post("/api/projects/dxf", files={"file": ("plan.jpg", f, "image/jpeg")}, data={"name": "Resim Plan"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["report"]["source"] == "image" and p["files"]["tanima_onay_png"].endswith("tanima_onay.png")
    assert c.get(p["files"]["tanima_onay_png"]).status_code == 200
    bad = c.post("/api/projects/dxf", files={"file": ("plan.pdf", b"%PDF", "application/pdf")}, data={"name": "x"})
    assert bad.status_code == 422
