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


def test_imar_read_text_and_consent():
    txt = ("İl: Ankara İlçe: Çankaya\nAda: 5021 Parsel: 7\nParsel Alanı: 864,50 m²\nTAKS: 0,30 KAKS: 1,50\n"
           "Kat Adedi: 5 Hmax: 15,50 m\nÖn bahçe mesafesi: 5 m\nYan bahçe mesafesi: 3 m\nArka bahçe mesafesi: 3 m\n")
    r = c.post("/api/imar/read", files={"file": ("imar.txt", txt.encode())})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["method"] == "metin" and j["zoning"] == {"taks": 0.3, "kaks": 1.5, "front": 5.0, "side": 3.0, "rear": 3.0,
                                                      "max_floors": 5, "max_height": 15.5}
    assert j["site"]["ada"] == "5021" and j["values"]["parcel_area"] == 864.5 and not j["missing"]
    # metinsiz görsel + onay yok → Claude çağrılmaz, uyarı döner
    from PIL import Image
    import io
    buf = io.BytesIO()
    Image.new("RGB", (40, 40), "white").save(buf, "PNG")
    r2 = c.post("/api/imar/read", files={"file": ("tarama.png", buf.getvalue())}).json()
    assert r2["method"] == "yok" and any("onay" in w for w in r2["warnings"])
    assert c.post("/api/imar/read", files={"file": ("x.docx", b"PK")}).status_code == 422


@pytest.mark.parametrize("action", ["approve", "revoke"])
def test_onay_quantity_conflict_returns_actionable_409(monkeypatch, tmp_path, action):
    from archai import approval
    from webapp import muteahhit_routes as routes

    monkeypatch.setattr(routes, "_project", lambda pid: (tmp_path, {}))

    def reject(*args, **kwargs):
        raise approval.QuantitiesMismatchError("Metraj değişmiş; refinalize ile yeniden üretin.")

    monkeypatch.setattr(approval, action, reject)
    signer = {"name": "Ali Kaya", "title": "İnşaat Mühendisi",
              "chamber": "TMMOB İnşaat Mühendisleri Odası", "reg_no": "12345", "statement": True}
    suffix = "/revoke" if action == "revoke" else ""
    response = c.post(f"/api/projects/test/onay{suffix}",
                      json={"reason": "test"} if action == "revoke" else signer)
    assert response.status_code == 409
    assert "refinalize" in response.json()["detail"]


def test_onay_flow(pid):
    u = f"/api/projects/{pid}/onay"
    assert c.get(u).json()["status"] == "taslak"
    signer = {"name": "Ali Kaya", "title": "İnşaat Mühendisi", "chamber": "TMMOB İnşaat Mühendisleri Odası",
              "reg_no": "12345", "statement": True}
    assert c.post(u, json={**signer, "statement": False}).status_code == 422
    r = c.post(u, json=signer)
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["status"] == "onaylandi" and j["files"]["onay_tutanagi_docx"].startswith(f"/files/{pid}/")
    assert c.get(j["files"]["onay_tutanagi_docx"]).status_code == 200
    c.put(f"/api/projects/{pid}/adjust", json={"profit_pct": 12})
    assert c.get(u).json()["status"] == "gecersiz"
    r2 = c.post(u + "/revoke", json={"reason": "fiyat değişti"})
    assert r2.status_code == 200 and r2.json()["status"] == "geri_alindi"


def test_refinalize_endpoint(pid):
    """POST /api/projects/{pid}/refinalize calls project.refinalize and returns updated project + onay status."""
    u = f"/api/projects/{pid}/onay"
    # First approve to get onaylandi status
    signer = {"name": "Ali Kaya", "title": "İnşaat Mühendisi", "chamber": "TMMOB İnşaat Mühendisleri Odası",
              "reg_no": "12345", "statement": True}
    r = c.post(u, json=signer)
    assert r.status_code == 200
    # Change adjust to invalidate approval (gecersiz)
    r2 = c.put(f"/api/projects/{pid}/adjust", json={"profit_pct": 15})
    assert r2.status_code == 200
    assert c.get(u).json()["status"] == "gecersiz"
    # Call refinalize
    r3 = c.post(f"/api/projects/{pid}/refinalize")
    assert r3.status_code == 200, r3.text
    data = r3.json()
    assert "project" in data and data["project"]["id"] == pid
    # Status remains gecersiz because cost changed (profit_pct) → fingerprint mismatch → re-approval needed
    assert "status" in data and data["status"] == "gecersiz"
    assert "files" in data and "onay_tutanagi_docx" not in data["files"]  # certificate removed


def test_refinalize_updates_quantities_fp_and_regenerates_documents(pid):
    """After refinalize, quantities_fp is updated and all documents are regenerated with current cost."""
    u = f"/api/projects/{pid}/onay"
    signer = {"name": "Ali Kaya", "title": "İnşaat Mühendisi", "chamber": "TMMOB İnşaat Mühendisleri Odası",
              "reg_no": "12345", "statement": True}
    c.post(u, json=signer)
    # Get initial project state
    proj_before = c.get(f"/api/projects/{pid}").json()
    qfp_before = proj_before["quantities_fp"]
    cost_before = proj_before["cost"]["total"]
    # Invalidate by changing profit
    c.put(f"/api/projects/{pid}/adjust", json={"profit_pct": 20})
    assert c.get(u).json()["status"] == "gecersiz"
    # Refinalize
    r = c.post(f"/api/projects/{pid}/refinalize")
    assert r.status_code == 200
    # Verify project updated
    proj_after = c.get(f"/api/projects/{pid}").json()
    qfp_after = proj_after["quantities_fp"]
    cost_after = proj_after["cost"]["total"]
    # quantities_fp should remain the same (geometry unchanged)
    assert qfp_after == qfp_before, "quantities_fp should not change when only adjust changes"
    # Cost should change due to profit_pct change
    assert cost_after != cost_before, "cost should change after adjust + refinalize"
    # Approval status remains gecersiz because fingerprint (cost + brief) changed → re-approval needed
    assert c.get(u).json()["status"] == "gecersiz"
    # Certificate should be removed
    onay = c.get(u).json()
    assert "onay_tutanagi_docx" not in onay.get("files", {})


def test_refinalize_preserves_price_adjustment(pid):
    """Regeneration preserves the selected profit adjustment."""
    u = f"/api/projects/{pid}/onay"
    signer = {"name": "Ali Kaya", "title": "İnşaat Mühendisi", "chamber": "TMMOB İnşaat Mühendisleri Odası",
              "reg_no": "12345", "statement": True}
    c.post(u, json=signer)
    # Get initial cost
    cost_before = c.get(f"/api/projects/{pid}").json()["cost"]["total"]
    # Invalidate approval
    c.put(f"/api/projects/{pid}/adjust", json={"profit_pct": 10})
    assert c.get(u).json()["status"] == "gecersiz"
    # Refinalize
    r = c.post(f"/api/projects/{pid}/refinalize")
    assert r.status_code == 200
    cost_after = c.get(f"/api/projects/{pid}").json()["cost"]["total"]
    # Cost should be recalculated (may be same if no catalog selected, but endpoint works)
    assert "cost" in r.json()["project"]
    assert r.json()["project"]["brief"]["adjust"]["profit_pct"] == 10


@pytest.mark.parametrize("legacy", [False, True], ids=["changed-elements", "legacy-project"])
def test_refinalize_recovers_blocked_approval(legacy):
    """Real API recovery: reject stale input, regenerate, then allow reapproval."""
    import json
    from archai import approval, costing, quantities
    from webapp import muteahhit_routes as routes

    created = c.post("/api/projects", json={"name": "Yenileme kurtarma testi",
                     "quick": {"gross_area": 300, "floors": 2, "unit_type": "2+1"}})
    assert created.status_code == 200, created.text
    project_id = created.json()["id"]
    url = f"/api/projects/{project_id}"
    signer = {"name": "Ali Kaya", "title": "İnşaat Mühendisi",
              "chamber": "TMMOB İnşaat Mühendisleri Odası", "reg_no": "12345", "statement": True}
    approved = c.post(url + "/onay", json=signer)
    assert approved.status_code == 200, approved.text
    directory, saved = routes._project(project_id)
    elements_path = directory / "elements.json"
    elements = json.loads(elements_path.read_text())
    if legacy:
        saved.pop("quantities_fp")
        (directory / "project.json").write_text(json.dumps(saved))
    else:
        elements.append({"type": "room", "name": "Ek Mahal", "level": "Zemin Kat",
                         "points": [[0, 0], [3, 0], [3, 3], [0, 3]], "height": 2.8})
        elements_path.write_text(json.dumps(elements))

    approval_before = (directory / "onay.json").read_bytes()
    blocked = c.post(url + "/onay", json=signer)
    assert blocked.status_code == 409, blocked.text
    assert (directory / "onay.json").read_bytes() == approval_before

    renewed = c.post(url + "/refinalize")
    assert renewed.status_code == 200, renewed.text
    refreshed = renewed.json()["project"]
    current_elements = json.loads(elements_path.read_text())
    q = quantities.compute(current_elements)
    assert current_elements == elements  # use edited elements, not the original brief
    assert refreshed["quantities_fp"] == approval.quantities_fp(q)
    assert refreshed["summary"] == q["summary"]
    assert refreshed["rooms"] == q["rooms"]
    assert refreshed["cost"] == costing.estimate(q, adjust=saved["brief"].get("adjust"))
    if not legacy:
        assert renewed.json()["status"] == "gecersiz"
        assert refreshed["cost"]["total"] != saved["cost"]["total"]
    for key in ("teklif_docx", "metraj_maliyet_xlsx", "cizim_pdf"):
        assert c.get(refreshed["files"][key]).status_code == 200

    reapproved = c.post(url + "/onay", json=signer)
    assert reapproved.status_code == 200, reapproved.text
    assert reapproved.json()["status"] == "onaylandi"
    assert all(doc["ok"] for doc in reapproved.json()["documents"])
    assert c.get(reapproved.json()["files"]["onay_tutanagi_docx"]).status_code == 200


def test_refinalize_requires_valid_project():
    """A missing project is rejected by the actual path lookup."""
    r = c.post("/api/projects/missing-refinalize-project/refinalize")
    assert r.status_code == 404


def test_refinalize_internal_error_does_not_leak(monkeypatch, tmp_path):
    from webapp import muteahhit_routes as routes
    monkeypatch.setattr(routes, "_project", lambda pid: (tmp_path, {}))

    def fail(out):
        raise RuntimeError("gizli /home/private/project.json")

    monkeypatch.setattr(routes.project, "refinalize", fail)
    r = c.post("/api/projects/test/refinalize")
    assert r.status_code == 500
    assert r.json() == {"detail": "yeniden üretim sırasında iç hata"}


def test_refinalize_requires_authentication(monkeypatch):
    monkeypatch.setenv("ARCHAI_TOKEN", "refinalize-test-secret")
    r = c.post("/api/projects/test/refinalize")
    assert r.status_code == 401
