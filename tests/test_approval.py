"""Mimar / mühendis onayı: damga, parmak izi, değişiklikte geçersizlik, dosya bütünlüğü."""

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


def test_tampered_file_detected(proj):
    A.approve(proj, SIGNER, project.redocument)
    with open(proj / "kesif_ozeti.csv", "a", encoding="utf-8") as f:
        f.write("x;y\n")
    st = A.status(proj)
    assert st["status"] == "degistirilmis"
    assert [d["key"] for d in st["documents"] if not d["ok"]] == ["kesif_csv"]


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
