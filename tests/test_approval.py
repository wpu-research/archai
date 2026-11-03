"""Mimar / mühendis onayı: damga, parmak izi, değişiklikte geçersizlik, dosya bütünlüğü."""

import json

import pytest
from docx import Document
from openpyxl import load_workbook

from archai import approval as A
from archai import project

SIGNER = {"name": "Ayşe Yılmaz", "title": "Mimar", "chamber": "TMMOB Mimarlar Odası", "reg_no": "34-12345",
          "statement": True, "note": "Avan inceleme"}


def _footer(docx_path):
    d = Document(docx_path)
    return " ".join(p.text for s in d.sections for p in s.footer.paragraphs)


@pytest.fixture
def proj(tmp_path):
    project.run({"name": "Onay Test", "quick": {"gross_area": 450, "floors": 3, "unit_type": "2+1"}}, tmp_path)
    return tmp_path


def test_draft_stamp_by_default(proj):
    r = A.status(proj)
    assert r["status"] == "taslak" and "TASLAK" in r["text"]
    assert "TASLAK" in _footer(proj / "teklif.docx")


def test_approve_stamps_documents_and_writes_certificate(proj):
    res = A.approve(proj, SIGNER, project.redocument)
    st = A.status(proj)
    assert st["status"] == "onaylandi" and st["signer"]["name"] == "Ayşe Yılmaz"
    assert {d["key"] for d in st["documents"]} >= {"teklif_docx", "metraj_maliyet_xlsx", "sartname_docx", "kesif_xlsx"}
    assert all(d["ok"] for d in st["documents"])
    f = _footer(proj / "teklif.docx")
    assert "Ayşe Yılmaz" in f and st["code"] in f and "TASLAK" not in f
    assert "Ayşe Yılmaz" in load_workbook(proj / "metraj_maliyet.xlsx").active.oddFooter.left.text
    assert res["files"]["onay_tutanagi_docx"].endswith(A.CERT) and (proj / A.CERT).is_file()
    cert = " ".join(c.text for t in Document(proj / A.CERT).tables for row in t.rows for c in row.cells)
    assert "34-12345" in cert and st["documents"][0]["sha256"] in cert


def test_change_invalidates_and_restamps_draft(proj):
    A.approve(proj, SIGNER, project.redocument)
    project.readjust(proj, {"vat_pct": 10})
    st = A.status(proj)
    assert st["status"] == "gecersiz"
    assert "TASLAK" in _footer(proj / "teklif.docx")      # yeniden üretilen belge onay damgası taşımaz


@pytest.mark.parametrize("field", ["cost", "brief"])
def test_changed_project_invalidates_even_when_documents_unchanged(proj, field):
    A.approve(proj, SIGNER, project.redocument)
    path = proj / "project.json"
    result = json.loads(path.read_text())
    if field == "cost":
        result["cost"]["total"] += 1000
    else:
        result["brief"]["name"] = "Değişmiş proje"
    path.write_text(json.dumps(result, ensure_ascii=False))
    assert A.status(proj)["status"] == "gecersiz"


@pytest.mark.parametrize("already_approved", [False, True])
@pytest.mark.parametrize("legacy", [False, True])
def test_approval_rejects_unverified_quantities_before_writing(proj, already_approved, legacy):
    if already_approved:
        A.approve(proj, SIGNER, project.redocument)
    record = proj / A.FILE
    before = record.read_bytes() if record.exists() else None
    if legacy:
        path = proj / "project.json"
        result = json.loads(path.read_text())
        result.pop("quantities_fp")
        path.write_text(json.dumps(result))
    else:
        path = proj / "elements.json"
        elements = json.loads(path.read_text())
        elements.append({"type": "room", "name": "Extra Room", "level": "0",
                         "points": [[0, 0], [3, 0], [3, 3], [0, 3]], "height": 2.8})
        path.write_text(json.dumps(elements))
    with pytest.raises(RuntimeError, match="refinalize"):
        A.approve(proj, SIGNER, project.redocument)
    assert (record.read_bytes() if record.exists() else None) == before


def test_tampered_file_detected(proj):
    A.approve(proj, SIGNER, project.redocument)
    with open(proj / "kesif_ozeti.csv", "a", encoding="utf-8") as f:
        f.write("x;y\n")
    st = A.status(proj)
    assert st["status"] == "degistirilmis"
    assert [d["key"] for d in st["documents"] if not d["ok"]] == ["kesif_csv"]


@pytest.mark.parametrize("legacy", [False, True])
def test_revoke_checks_quantities_before_changing_record(proj, legacy):
    A.approve(proj, SIGNER, project.redocument)
    record_before = (proj / A.FILE).read_bytes()
    certificate_before = (proj / A.CERT).read_bytes()
    path = proj / "project.json"
    result = json.loads(path.read_text())
    if legacy:
        result.pop("quantities_fp")
    else:
        result["quantities_fp"] = "outdated"
    path.write_text(json.dumps(result))
    with pytest.raises(RuntimeError, match="refinalize"):
        A.revoke(proj, project.redocument, "test")
    assert (proj / A.FILE).read_bytes() == record_before
    assert (proj / A.CERT).read_bytes() == certificate_before
    project.refinalize(proj)
    A.revoke(proj, project.redocument, "test")
    assert A.status(proj)["status"] == "geri_alindi"
    assert not (proj / A.CERT).exists()


def test_revoke(proj):
    A.approve(proj, SIGNER, project.redocument)
    A.revoke(proj, project.redocument, "hata")
    assert A.status(proj)["status"] == "geri_alindi" and "TASLAK" in _footer(proj / "teklif.docx")
    assert not (proj / A.CERT).exists()
    with pytest.raises(ValueError):
        A.revoke(proj, project.redocument)


@pytest.mark.parametrize("bad,msg", [({"statement": False}, "beyan"), ({"name": "Ayşe"}, "tam"),
                                     ({"title": "Usta"}, "unvan"), ({"reg_no": "<x>"}, "sicil"),
                                     ({"chamber": "Başka"}, "oda")])
def test_signer_validation(bad, msg):
    with pytest.raises(ValueError, match=msg):
        A.validate_signer({**SIGNER, **bad})
