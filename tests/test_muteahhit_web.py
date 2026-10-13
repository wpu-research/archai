"""Müteahhit katmanı API'si: poz listesi, proje eşlemesi."""

import pytest
from fastapi.testclient import TestClient

from webapp.app import app

c = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))

CSV = ("Poz No;Tanımı;Birimi;Birim Fiyatı\n"
       "15.150.1006;C 30/37 hazır beton dökülmesi;m3;3.950,25\n"
       "15.275.1101;Kireç çimento harçlı iç sıva yapılması;m2;241,10\n")


@pytest.fixture
def plist():
    r = c.post("/api/poz/list", files={"file": ("liste.csv", CSV.encode("utf-8"))}, data={"year": "2026"})
    assert r.status_code == 200, r.text
    yield r.json()["list"]
    c.delete("/api/poz/list")


@pytest.fixture(scope="module")
def pid():
    r = c.post("/api/projects", json={"name": "poz web", "quick": {"gross_area": 450, "floors": 3, "unit_type": "2+1"}})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_list_upload_info_delete(plist):
    assert plist["count"] == 2 and plist["year"] == 2026
    assert c.get("/api/poz/list").json()["list"]["count"] == 2
    bad = c.post("/api/poz/list", files={"file": ("x.pdf", b"%PDF-1.4")})
    assert bad.status_code == 422 and "desteklenen" in bad.json()["detail"]


def test_project_poz_match_and_apply(pid, plist):
    d = c.get(f"/api/projects/{pid}/poz").json()
    rows = {r["code"]: r for r in d["rows"]}
    assert rows["BET-01"]["durum"] == "eslesti" and d["summary"]["eslesti"] >= 1
    assert d["files"]["kesif_xlsx"].endswith("kesif_ozeti.xlsx")
    r = c.put(f"/api/projects/{pid}/poz", json={"poz": {"SIV-01": "15.275.1101"}, "apply_prices": True})
    assert r.status_code == 200, r.text
    p = r.json()["project"]
    row = {x["code"]: x for x in p["cost"]["rows"]}
    assert row["SIV-01"]["unit_price"] == 241.10 and row["SIV-01"]["poz"] == "15.275.1101"
    assert row["BET-01"]["unit_price"] == 3950.25 and r.json()["applied"] >= 2
    assert p["brief"]["adjust"]["poz"] == {"SIV-01": "15.275.1101"}
    # poz silme
    r2 = c.put(f"/api/projects/{pid}/poz", json={"poz": {"SIV-01": None}})
    assert "SIV-01" not in r2.json()["project"]["brief"]["adjust"]["poz"]


def test_project_poz_validation(pid):
    assert c.put(f"/api/projects/{pid}/poz", json={"poz": {"YOK-99": "15.1"}}).status_code == 422
    assert c.put(f"/api/projects/{pid}/poz", json={"poz": {"SIV-01": "=cmd|x"}}).status_code == 422
    c.delete("/api/poz/list")
    r = c.put(f"/api/projects/{pid}/poz", json={"poz": {}, "apply_prices": True})
    assert r.status_code == 422 and "liste" in r.json()["detail"]
    assert c.get("/api/projects/../poz").status_code == 404
