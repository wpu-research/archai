"""Tedarikçi kataloğu: okuma, uygulanmış fiyat, maliyete bağlama, varyant değişiminde düşme, web API."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from archai import catalog, costing
from archai import quantities as Q
from webapp.app import app

ROOT = Path(__file__).resolve().parents[1]
EX = ROOT / "examples" / "katalog_ornek.csv"
c = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))


@pytest.fixture(scope="module")
def cat():
    return catalog.read_catalog(EX.name, EX.read_bytes(), costing.load_prices())


def test_read_example(cat):
    assert cat["supplier"] == "Örnek Yapı Market" and len(cat["items"]) == 9 and not cat["warnings"]
    lam = next(p for p in cat["items"] if p["sku"] == "LAM-8-MESE")
    assert lam["material"] == round(520 / 1.2, 2) and lam["labor"] == 180 and lam["variant"] == "laminat"
    assert catalog.unit_price(lam) == round(lam["material"] * 1.08 + 180, 2)


def test_bad_rows_skipped(tmp_path):
    p = tmp_path / "k.csv"
    p.write_text("Ürün Adı;Birim;Fiyat;Kalem\nA;m2;100;YOK-01\nB;adet;50;ZEM-01\nC;m2;90;ZEM-01\n", encoding="utf-8")
    r = catalog.read_catalog("k.csv", p.read_bytes(), costing.load_prices())
    assert len(r["items"]) == 1 and r["skipped"] == 2 and r["items"][0]["labor"] is None
    assert any("YOK-01" in w for w in r["warnings"]) and any("birim" in w for w in r["warnings"])
    with pytest.raises(ValueError, match="geçerli ürün yok"):
        catalog.read_catalog("k.csv", b"a;b\n1;2\n", costing.load_prices())


def test_selection_drives_cost_and_drops_on_variant_change(cat):
    els = __import__("archai.generate", fromlist=["generate"])
    from archai.project import quick_brief
    parcel, zoning, program = quick_brief({"gross_area": 450, "floors": 3, "unit_type": "2+1"})
    elements, _ = els.generate(parcel, zoning, program)
    q = Q.compute(elements)
    por = next(p for p in cat["items"] if p["sku"] == "POR-60120-BEJ")
    adj = {"catalog": {"ZEM-01": catalog.selection(por)}, "variants": {"ZEM-01": "seramik"}}
    row = next(r for r in costing.estimate(q, adjust=adj)["rows"] if r["code"] == "ZEM-01")
    assert row["unit_price"] == catalog.unit_price(por) and "Porselen seramik 60x120 bej" in row["name"]
    adj["variants"]["ZEM-01"] = "masif"
    row = next(r for r in costing.estimate(q, adjust=adj)["rows"] if r["code"] == "ZEM-01")
    assert row["catalog"] is None and row["unit_price"] == 2600


def test_web_catalog_flow():
    r = c.post("/api/catalogs", files={"file": (EX.name, EX.read_bytes())})
    assert r.status_code == 200, r.text
    sid = r.json()["catalog"]["id"]
    p = c.post("/api/projects", json={"name": "katalog", "quick": {"gross_area": 450, "floors": 3, "unit_type": "2+1"}}).json()
    rows = {x["code"]: x for x in c.get(f"/api/projects/{p['id']}/catalog").json()["rows"]}
    assert "ZEM-01" in rows and rows["ZEM-01"]["products"][0]["variant"] == "laminat"   # mevcut varyant: laminat
    pid8 = rows["ZEM-01"]["products"][0]["id"]
    r2 = c.put(f"/api/projects/{p['id']}/catalog", json={"select": {"ZEM-01": {"catalog": sid, "product": pid8}}})
    assert r2.status_code == 200, r2.text
    z = next(x for x in r2.json()["project"]["cost"]["rows"] if x["code"] == "ZEM-01")
    assert z["catalog"]["sku"] == "LAM-8-MESE" and z["unit_price"] == z["catalog"]["unit_price"]
    assert c.put(f"/api/projects/{p['id']}/catalog", json={"select": {"ZEM-01": {"catalog": sid, "product": "999"}}}).status_code == 422
    r3 = c.put(f"/api/projects/{p['id']}/catalog", json={"select": {"ZEM-01": None}})
    assert next(x for x in r3.json()["project"]["cost"]["rows"] if x["code"] == "ZEM-01")["catalog"] is None
    assert c.delete(f"/api/catalogs/{sid}").status_code == 200
    assert c.delete("/api/catalogs/../x").status_code in (404, 405)
