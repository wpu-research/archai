"""Proje → metraj → maliyet → belge veri sözleşmesi.

Gerçek geometri ve hesaplama kullanılır. Dosya biçimleyicileri izole edilir;
bu testler DOCX/DXF içeriğinin veya tarayıcı akışının doğruluğunu kanıtlamaz.
"""

import json

import pytest

from archai import costing, project
from archai import quantities as Q


@pytest.fixture
def document_calls(monkeypatch):
    calls = []

    def write_documents(out, name, brief, report, q, cost, info=None):
        calls.append({"summary": q["summary"], "rooms": q["rooms"], "cost": cost})
        return {}

    monkeypatch.setattr(project, "write_documents", write_documents)
    monkeypatch.setattr(project.drawings, "export_all", lambda *args, **kwargs: {})
    monkeypatch.setattr(project, "load_settings", lambda: {})
    return calls


def read_json(path):
    return json.loads(path.read_text())


def assert_pipeline_consistent(out, result, document_calls):
    persisted = read_json(out / "project.json")
    elements = read_json(out / "elements.json")
    quantities = Q.compute(elements)
    expected_cost = costing.estimate(quantities, adjust=persisted["brief"].get("adjust"))
    assert persisted["summary"] == quantities["summary"]
    assert persisted["rooms"] == quantities["rooms"]
    assert persisted["cost"] == expected_cost
    assert result["summary"] == persisted["summary"]
    assert result["cost"] == persisted["cost"]
    assert document_calls[-1] == {
        "summary": quantities["summary"],
        "rooms": quantities["rooms"],
        "cost": expected_cost,
    }


@pytest.mark.parametrize("floors", [1, 3])
def test_generated_project_uses_same_quantities_for_documents_and_storage(
    tmp_path, document_calls, floors
):
    brief = {
        "name": "Entegrasyon referansı",
        "quick": {"gross_area": 200 * floors, "floors": floors, "unit_type": "auto"},
    }
    result, elements = project.run(brief, tmp_path)
    assert elements
    assert len(document_calls) == 1
    assert_pipeline_consistent(tmp_path, result, document_calls)


def test_price_recalculation_preserves_geometry_and_document_consistency(
    tmp_path, document_calls
):
    brief = {"name": "Fiyat referansı", "quick": {"gross_area": 600, "floors": 3}}
    project.run(brief, tmp_path)
    original_elements = (tmp_path / "elements.json").read_bytes()
    result = project.readjust(tmp_path, {})
    assert (tmp_path / "elements.json").read_bytes() == original_elements
    assert len(document_calls) == 2
    assert_pipeline_consistent(tmp_path, result, document_calls)


def test_readjust_refreshes_stale_summary_and_rooms(tmp_path, document_calls):
    brief = {"name": "Eski özet", "quick": {"gross_area": 600, "floors": 3}}
    result, _ = project.run(brief, tmp_path)
    original_elements = (tmp_path / "elements.json").read_bytes()
    result["summary"]["gross_floor_area"] = -1
    result["rooms"] = []
    (tmp_path / "project.json").write_text(json.dumps(result, ensure_ascii=False))

    refreshed = project.readjust(tmp_path, {})

    assert refreshed["summary"]["gross_floor_area"] > 0
    assert refreshed["rooms"]
    assert (tmp_path / "elements.json").read_bytes() == original_elements
    assert_pipeline_consistent(tmp_path, refreshed, document_calls)


def test_refinalize_preserves_project_metadata_and_recomputes_outputs(
    tmp_path, document_calls
):
    brief = {"name": "Yenileme referansı", "quick": {"gross_area": 600, "floors": 3}}
    result, _ = project.run(brief, tmp_path)
    result["integration_note"] = "korunacak proje notu"
    (tmp_path / "project.json").write_text(json.dumps(result, ensure_ascii=False))
    refreshed = project.refinalize(tmp_path)
    assert refreshed["integration_note"] == "korunacak proje notu"
    assert read_json(tmp_path / "project.json")["integration_note"] == refreshed["integration_note"]
    assert refreshed["brief"] == brief
    assert len(document_calls) == 2
    assert_pipeline_consistent(tmp_path, refreshed, document_calls)


def test_redocument_refreshes_stale_summary_and_rooms(tmp_path, document_calls):
    """redocument (onay akışı) güncel elemanlardan özet ve mahalleri yenilemelidir.
    Maliyet değişmez (sadece onay damgası güncellenir), bu yüzden cost tutarlılığı test edilmez.
    """
    brief = {"name": "Onay akışı", "quick": {"gross_area": 600, "floors": 3}}
    result, _ = project.run(brief, tmp_path)
    original_elements = json.loads((tmp_path / "elements.json").read_text())
    original_cost = result["cost"]
    # Geometri ve maliyet aynı; yalnız önbelleklenmiş özet/mahal bilgileri eskimiş.
    elements = original_elements
    result["summary"]["gross_floor_area"] = -1
    result["rooms"] = []
    (tmp_path / "project.json").write_text(json.dumps(result, ensure_ascii=False))

    refreshed = project.redocument(tmp_path)

    fresh_q = Q.compute(elements)
    assert refreshed["summary"] == fresh_q["summary"]
    assert refreshed["rooms"] == fresh_q["rooms"]
    # Maliyet korunmalı (redocument sadece onay damgası için belgeleri yeniden yazar)
    assert refreshed["cost"] == original_cost
    # elements.json redocument tarafından yazılmaz; içerik değişmemeli
    assert json.loads((tmp_path / "elements.json").read_text()) == elements
    assert len(document_calls) == 2
    # summary ve rooms tutarlılığı (cost hariç)
    persisted = read_json(tmp_path / "project.json")
    assert persisted["summary"] == fresh_q["summary"]
    assert persisted["rooms"] == fresh_q["rooms"]
    assert refreshed["summary"] == persisted["summary"]
    assert refreshed["rooms"] == persisted["rooms"]
    assert document_calls[-1] == {
        "summary": fresh_q["summary"],
        "rooms": fresh_q["rooms"],
        "cost": original_cost,  # redocument eski maliyeti kullanır
    }


@pytest.mark.parametrize("legacy", [False, True])
def test_redocument_rejects_unverified_draft_without_writing(tmp_path, document_calls, legacy):
    brief = {"quick": {"gross_area": 600, "floors": 3}}
    result, elements = project.run(brief, tmp_path)
    if legacy:
        result.pop("quantities_fp")
        (tmp_path / "project.json").write_text(json.dumps(result))
    else:
        elements.append({"type": "room", "name": "Extra Room", "level": "0",
                         "points": [[0, 0], [3, 0], [3, 3], [0, 3]], "height": 2.8})
        (tmp_path / "elements.json").write_text(json.dumps(elements))
    before = (tmp_path / "project.json").read_bytes()
    with pytest.raises(RuntimeError, match="refinalize"):
        project.redocument(tmp_path)
    assert (tmp_path / "project.json").read_bytes() == before
    assert len(document_calls) == 1
    project.refinalize(tmp_path)
    refreshed = project.redocument(tmp_path)
    assert_pipeline_consistent(tmp_path, refreshed, document_calls)


def test_redocument_rejects_changed_geometry_after_approval(tmp_path, document_calls):
    """Onaylı projede geometri değişince redocument hata vermeli (tutarsız metraj–maliyet önlenir).
    Kullanıcı önce readjust/refinalize ile maliyeti yenilemelidir.
    """
    from archai import approval as A
    SIGNER = {"name": "Ayşe Yılmaz", "title": "Mimar", "chamber": "TMMOB Mimarlar Odası",
              "reg_no": "34-12345", "statement": True, "note": "test"}

    brief = {"name": "Koruma testi", "quick": {"gross_area": 600, "floors": 3}}
    project.run(brief, tmp_path)
    A.approve(tmp_path, SIGNER, project.redocument)

    # Onay sonrası eleman değiştir (geometri değişimi simülasyonu)
    elements = json.loads((tmp_path / "elements.json").read_text())
    elements.append({"type": "room", "name": "Extra Room", "level": "0",
                     "points": [[0, 0], [3, 0], [3, 3], [0, 3]], "height": 2.8})
    (tmp_path / "elements.json").write_text(json.dumps(elements, ensure_ascii=False))

    # redocument artık hata vermeli (eski maliyet + yeni geometri = tutarsız)
    import pytest
    with pytest.raises(RuntimeError, match="geometri.*değişmiş"):
        project.redocument(tmp_path)

    # Doğru yol: refinalize ile maliyet de yeniden hesaplanır
    refreshed = project.refinalize(tmp_path)
    fresh_q = Q.compute(elements)
    expected_cost = costing.estimate(fresh_q, adjust=brief.get("adjust"))
    assert refreshed["summary"] == fresh_q["summary"]
    assert refreshed["rooms"] == fresh_q["rooms"]
    assert refreshed["cost"] == expected_cost
    assert_pipeline_consistent(tmp_path, refreshed, document_calls)

    # refinalize sonrası maliyet güncel, redocument artık çalışmalı (tutarsızlık yok)
    # Onay yine "gecersiz" kalır (yeniden onay gerekir), ama belge tutarlı üretilir.
    result = project.redocument(tmp_path)
    assert result["cost"] == expected_cost
    assert result["summary"] == fresh_q["summary"]
    assert result["rooms"] == fresh_q["rooms"]
    assert A.status(tmp_path)["status"] == "gecersiz"  # onay hala geçersiz
    assert len(document_calls) == 4  # run + redocument (approve) + refinalize + redocument
