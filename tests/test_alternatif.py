"""Kontrollü proje alternatifi: /api/projects/{pid}/alternatif endpoint testleri."""
import json
import pytest
from fastapi.testclient import TestClient

from archai import project as proj_mod
from archai import approval as A
from archai import quantities as Q
from webapp.app import app, PROJECTS

c = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
PARCEL = {"width": 24.0, "depth": 38.5}
ZON = {"taks": 0.25, "kaks": 2.0, "front": 5.0, "side": 3.0, "rear": 3.0, "max_floors": 3, "floor_height": 3.1}


def _new_arazi(name, **extra):
    r = c.post("/api/projects", json={"name": name, "parcel": PARCEL, "zoning": ZON,
                                      "program": {"unit_type": "2+1", "units_per_floor": "auto", **extra}})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _new_quick(name, **extra):
    r = c.post("/api/projects", json={"name": name, "quick": {"gross_area": 1800, "floors": 3, "unit_type": "2+1", **extra}})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _read_project(pid):
    r = c.get(f"/api/projects/{pid}")
    assert r.status_code == 200, r.text
    return r.json()


def test_alternatif_from_arazi_mode():
    """Arazi modu projesinden alternatif oluştur: kat sayısı ve daire tipi değiştir."""
    src = _new_arazi("kaynak arazi")
    src_data = _read_project(src)

    # Alternatif oluştur: 4 kat, 3+1 daire
    r = c.post(f"/api/projects/{src}/alternatif", json={
        "name": "4 Katlı 3+1 Alternatif",
        "floors": 4,
        "unit_type": "3+1",
        "acknowledgement": True,
    })
    assert r.status_code == 200, r.text
    alt = r.json()["alternative"]
    alt_id = alt["id"]

    # Kaynaktan farklı olmalı
    assert alt["name"] == "4 Katlı 3+1 Alternatif"
    assert alt["brief"].get("quick") is None  # arazi modu korundu
    assert alt["brief"]["program"]["unit_type"] == "3+1"
    assert alt["brief"]["zoning"]["max_floors"] == 4

    # Lineage bilgisi olmalı
    assert alt["brief"].get("lineage") is not None
    assert alt["brief"]["lineage"]["parent_id"] == src
    assert alt["brief"]["lineage"]["source_fingerprint"] is not None

    # Kaynak proje değişmemeli
    src_after = _read_project(src)
    assert src_after["brief"]["program"]["unit_type"] == "2+1"
    assert src_after["brief"]["zoning"]["max_floors"] == 3

    # Alternatif ayrı proje olarak erişilebilir olmalı
    alt_data = _read_project(alt_id)
    assert alt_data["name"] == "4 Katlı 3+1 Alternatif"


def test_alternatif_from_quick_mode():
    """Hızlı mod projesinden alternatif oluştur."""
    src = _new_quick("kaynak hızlı")
    src_data = _read_project(src)

    # Alternatif: 5 kat, 1+1 daire, 2 daire/kat
    r = c.post(f"/api/projects/{src}/alternatif", json={
        "name": "5 Katlı 1+1 Alternatif",
        "floors": 5,
        "unit_type": "1+1",
        "units_per_floor": 2,
        "acknowledgement": True,
    })
    assert r.status_code == 200, r.text
    alt = r.json()["alternative"]
    alt_id = alt["id"]

    assert alt["brief"]["quick"]["floors"] == 5
    assert alt["brief"]["quick"]["unit_type"] == "1+1"
    assert alt["brief"]["quick"]["units_per_floor"] == 2

    # Lineage
    assert alt["brief"]["lineage"]["parent_id"] == src


def test_alternatif_rejects_without_acknowledgement():
    """Onay kutusu olmadan alternatif oluşturma reddedilmeli."""
    src = _new_quick("kaynak")
    r = c.post(f"/api/projects/{src}/alternatif", json={
        "name": "Alternatif",
        "floors": 4,
        "acknowledgement": False,
    })
    assert r.status_code == 422
    assert "onaylamalısınız" in r.json()["detail"]


def test_alternatif_rejects_tablo_source():
    """Avan tablosu projesinden alternatif oluşturulamaz."""
    from archai import avan_tablo
    import tempfile

    with tempfile.TemporaryDirectory() as td:
        poly = [(0, 0), (31.8, 0), (31.8, 11.9), (0, 11.9)]
        # Tablo projesi oluştur
        brief = {
            "name": "Tablo Projesi",
            "parcel": {"polygon": poly, "front_edge": 0},
            "zoning": {"front": 0.5, "side": 0, "rear": 0.5},
            "tablo": True,
        }
        r = c.post("/api/projects", json=brief)
        assert r.status_code == 200, r.text
        pid = r.json()["id"]

    r = c.post(f"/api/projects/{pid}/alternatif", json={
        "name": "Alternatif",
        "acknowledgement": True,
    })
    assert r.status_code == 422
    assert "avan tablosu" in r.json()["detail"]


def test_alternatif_rejects_dxf_source():
    """DXF/resim planından üretilen projeden alternatif oluşturulamaz."""
    # DXF projesi simülasyonu (project.json'da dxf alanını set ederek)
    src = _new_quick("kaynak dxf simülasyonu")
    d = PROJECTS / src / "project.json"
    j = json.loads(d.read_text())
    j["brief"]["dxf"] = {"floors": 1, "floor_height": 3.0}
    d.write_text(json.dumps(j))

    r = c.post(f"/api/projects/{src}/alternatif", json={
        "name": "Alternatif",
        "acknowledgement": True,
    })
    assert r.status_code == 422
    assert "DXF/resim planından" in r.json()["detail"]


def test_alternatif_rejects_image_source():
    """Resim planından üretilen projeden alternatif oluşturulamaz."""
    src = _new_quick("kaynak image simülasyonu")
    d = PROJECTS / src / "project.json"
    j = json.loads(d.read_text())
    j["brief"]["image"] = {"floors": 1, "floor_height": 3.0}
    d.write_text(json.dumps(j))

    r = c.post(f"/api/projects/{src}/alternatif", json={
        "name": "Alternatif",
        "acknowledgement": True,
    })
    assert r.status_code == 422
    assert "resim planından" in r.json()["detail"]


def test_alternatif_rejects_demo_scenario():
    """Demo senaryo (villa/cabin/apartment) projelerinden alternatif oluşturulamaz."""
    # Villa demo
    r = c.post("/api/projects/villa", json={"name": "Villa Demo"})
    assert r.status_code == 200
    villa_id = r.json()["id"]

    r = c.post(f"/api/projects/{villa_id}/alternatif", json={
        "name": "Alternatif",
        "acknowledgement": True,
    })
    assert r.status_code == 422
    assert "demo senaryo" in r.json()["detail"]


def test_alternatif_source_unchanged():
    """Kaynak proje değiştirilmemeli (immutable)."""
    src = _new_quick("kaynak immutable test")
    src_before = _read_project(src)
    src_elements_before = (PROJECTS / src / "elements.json").read_bytes()
    src_fp_before = src_before.get("quantities_fp")

    r = c.post(f"/api/projects/{src}/alternatif", json={
        "name": "Alternatif",
        "floors": 5,
        "acknowledgement": True,
    })
    assert r.status_code == 200

    src_after = _read_project(src)
    src_elements_after = (PROJECTS / src / "elements.json").read_bytes()
    src_fp_after = src_after.get("quantities_fp")

    # Kaynak hiç değişmemeli
    assert src_after["brief"] == src_before["brief"]
    assert src_elements_after == src_elements_before
    assert src_fp_after == src_fp_before


def test_alternatif_no_approvals_scenarios_copied():
    """Onay, fizibilite senaryoları, tasarım setleri kopyalanmamalı."""
    src = _new_quick("kaynak approvals test")

    # Onay simülasyonu (manuel olarak ekle)
    d = PROJECTS / src / "project.json"
    j = json.loads(d.read_text())
    j["approval"] = {"status": "onaylandi", "signer": {"name": "Test"}}
    d.write_text(json.dumps(j))

    # Fizibilite senaryosu simülasyonu
    scenarios_dir = PROJECTS / src / "finance_scenarios"
    scenarios_dir.mkdir(exist_ok=True)
    (scenarios_dir / "senaryo1.json").write_text(json.dumps({"ad": "test"}))

    # Tasarım seti simülasyonu
    designs_dir = PROJECTS / src / "designs"
    designs_dir.mkdir(exist_ok=True)
    did = "240101120000-abcd"
    (designs_dir / did).mkdir()
    (designs_dir / did / "set.json").write_text(json.dumps({"id": did, "variants": []}))

    r = c.post(f"/api/projects/{src}/alternatif", json={
        "name": "Alternatif",
        "acknowledgement": True,
    })
    assert r.status_code == 200
    alt_id = r.json()["alternative"]["id"]

    # Alternatifte bu veriler YOK olmalı
    alt_d = PROJECTS / alt_id / "project.json"
    alt_j = json.loads(alt_d.read_text())
    assert "approval" not in alt_j
    assert not (PROJECTS / alt_id / "finance_scenarios").exists()
    assert not (PROJECTS / alt_id / "designs").exists()


def test_alternatif_geometry_regenerated_from_saved_inputs():
    """Manuel geometri düzenlemeleri (cephe düzeltmesi vb.) kopyalanmaz, kayıtlı girdilerden yeniden üretilir."""
    src = _new_quick("kaynak geometri test")

    # elements.json'ı manuel değiştir (cephe düzeltmesi simülasyonu)
    els_path = PROJECTS / src / "elements.json"
    els = json.loads(els_path.read_text())
    # Duvar ekle/sil simülasyonu - uzunluk değiştir
    wall = next(e for e in els if e.get("type") == "wall")
    wall["height"] = wall.get("height", 3.0) + 0.5
    els_path.write_text(json.dumps(els))

    # Source fingerprint hesapla (değişmiş haliyle)
    elements_modified = json.loads(els_path.read_text())
    q = Q.compute(elements_modified)
    modified_fp = A.quantities_fp(q)

    # Alternatif oluştur
    r = c.post(f"/api/projects/{src}/alternatif", json={
        "name": "Alternatif",
        "acknowledgement": True,
    })
    assert r.status_code == 200
    alt_id = r.json()["alternative"]["id"]

    # Lineage türetme anındaki kaynak geometriyi tanımlar;
    # yeni alternatif ise kayıtlı girdilerden yeniden üretilir.
    alt_d = PROJECTS / alt_id / "project.json"
    alt_j = json.loads(alt_d.read_text())

    # Orijinal project.json'daki quantities_fp (manuel değişiklik öncesi)
    orig_d = PROJECTS / src / "project.json"
    orig_j = json.loads(orig_d.read_text())
    orig_fp = orig_j.get("quantities_fp")

    assert modified_fp != orig_fp  # Manuel düzenlemenin gerçekten yapıldığını doğrula.
    assert alt_j["brief"]["lineage"]["source_fingerprint"] == modified_fp
    alt_elements = json.loads((PROJECTS / alt_id / "elements.json").read_text())
    assert A.quantities_fp(Q.compute(alt_elements)) == orig_fp
    assert json.loads(els_path.read_text()) == elements_modified


def test_alternatif_comparison_works():
    """Alternatif proje ile kaynak proje karşılaştırılabilmeli (mevcut /karsilastir endpoint)."""
    src = _new_quick("kaynak karşılaştırma")
    r = c.post(f"/api/projects/{src}/alternatif", json={
        "name": "Alternatif Karşılaştırma",
        "floors": 5,
        "acknowledgement": True,
    })
    assert r.status_code == 200
    alt_id = r.json()["alternative"]["id"]

    # Karşılaştırma endpoint'i çalışmalı
    cmp = c.get(f"/api/projects/{src}/karsilastir/{alt_id}")
    assert cmp.status_code == 200, cmp.text
    data = cmp.json()
    assert data["a"]["id"] == src
    assert data["b"]["id"] == alt_id
    # Kat sayısı farkı görülebilmeli
    gross = next(x for x in data["rapor"] if x["anahtar"] == "gross_total")
    assert gross["fark"] != 0 or gross["yuzde"] is not None


def test_alternatif_invalid_source_returns_404():
    """Olmayan kaynak projede 404 dönmeli."""
    r = c.post(f"/api/projects/20200101-000000-yok-abcd/alternatif", json={
        "name": "Alternatif",
        "acknowledgement": True,
    })
    assert r.status_code == 404


def test_alternatif_invalid_inputs():
    """Geçersiz girdilerde 422 dönmeli."""
    src = _new_quick("kaynak")

    # floors > 30
    r = c.post(f"/api/projects/{src}/alternatif", json={
        "name": "Alternatif",
        "floors": 31,
        "acknowledgement": True,
    })
    assert r.status_code == 422

    # name boş
    r = c.post(f"/api/projects/{src}/alternatif", json={
        "name": "",
        "acknowledgement": True,
    })
    assert r.status_code == 422

    # unit_type çok uzun
    r = c.post(f"/api/projects/{src}/alternatif", json={
        "name": "Alternatif",
        "unit_type": "x" * 21,
        "acknowledgement": True,
    })
    assert r.status_code == 422


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


def test_alternatif_does_not_carry_quantity_overrides():
    """Elle girilmiş miktar kaynak geometriye aittir; birim fiyat taşınır, miktar taşınmaz."""
    src = _new_quick("miktar kaynagi")
    r = c.put(f"/api/projects/{src}/adjust", json={"overrides": {"ZEM-01": 999.0}, "qty_overrides": {"ZEM-01": 12345.0}})
    assert r.status_code == 200, r.text
    r = c.post(f"/api/projects/{src}/alternatif", json={"name": "5 kat", "floors": 5, "acknowledgement": True})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["dropped_qty_overrides"] == ["ZEM-01"]
    adj = body["alternative"]["brief"].get("adjust") or {}
    assert "qty_overrides" not in adj and adj["overrides"] == {"ZEM-01": 999.0}
    row = next(x for x in _read_project(body["alternative"]["id"])["cost"]["rows"] if x["code"] == "ZEM-01")
    assert row["quantity"] != 12345.0 and row["unit_price"] == 999.0
