"""İmar kuralları: yençok/saçak sınırı, emsal dışı ortak alan payı, imar özeti ve imar notu."""

import pytest
from docx import Document
from openpyxl import load_workbook

from archai import project
from archai.generate import generate
from archai.notice import IMAR_NOTE, IMAR_SHORT

PARCEL = {"width": 30, "depth": 28}
BASE = {"taks": 0.4, "kaks": 2.0, "front": 5, "side": 3, "rear": 3, "max_floors": 6, "floor_height": 3.0}
PROG = {"unit_type": "3+1"}


def test_max_height_limits_floor_count():
    _, rep = generate(PARCEL, {**BASE, "max_height": 9.0}, PROG)
    assert rep["floors"] <= 3
    h = rep["checks"]["height"]
    assert h["ok"] and h["value"] <= 9.0 and h["limit"] == 9.0
    assert any("yençok" in w for w in rep["warnings"])
    # kat sayısı düşünce KAKS sapması da uyarıya yansır
    assert rep["checks"]["kaks"]["ok"]


def test_max_height_not_binding_leaves_floors_unchanged():
    _, free = generate(PARCEL, BASE, PROG)
    _, high = generate(PARCEL, {**BASE, "max_height": 60.0}, PROG)
    assert high["floors"] == free["floors"]
    assert not any("yençok" in w for w in high["warnings"])
    assert high["checks"]["height"]["ok"]


def test_max_height_too_low_is_rejected():
    with pytest.raises(ValueError, match="tek kat bile"):
        generate(PARCEL, {**BASE, "max_height": 2.5}, PROG)


def test_no_new_keys_means_no_height_check():
    _, rep = generate(PARCEL, BASE, PROG)
    assert "height" not in rep["checks"] and "emsal_disi" not in rep["checks"]


def test_emsal_disi_allows_more_gross_and_keeps_kaks_ok():
    _, base = generate(PARCEL, {**BASE, "max_floors": 3}, PROG)
    _, ex = generate(PARCEL, {**BASE, "max_floors": 3, "emsal_disi_pct": 20}, PROG)
    assert ex["gross_total"] >= base["gross_total"] - 1e-6
    c = ex["checks"]
    assert c["kaks"]["ok"] and c["emsal_disi"]["value"] == pytest.approx(ex["gross_total"] * 0.20, abs=0.05)
    assert c["emsal_disi"]["unit"] == "m²"
    # brüt alan KAKS sınırını aşabilir ama emsale girenler aşmaz
    assert c["kaks"]["value"] <= BASE["kaks"] + 1e-3


def test_emsal_disi_m2():
    """Emsal dışı alan m² girilir: izin verilen brüt alan KAKS×A + m² olur, KAKS yalnız emsale girenle hesaplanır."""
    _, base = generate(PARCEL, {**BASE, "max_floors": 3}, PROG)
    _, ex = generate(PARCEL, {**BASE, "max_floors": 3, "emsal_disi_m2": 60}, PROG)
    c = ex["checks"]
    assert ex["gross_total"] >= base["gross_total"] - 1e-6
    assert c["emsal_disi"]["value"] == 60 and c["emsal_disi"]["unit"] == "m²" and c["emsal_disi"]["ok"]
    A = PARCEL["width"] * PARCEL["depth"]
    assert c["kaks"]["value"] == pytest.approx((ex["gross_total"] - 60) / A, abs=1e-3) and c["kaks"]["ok"]
    row = next(r for r in ex["imar_ozeti"]["rows"] if r["key"] == "emsal_disi")
    assert row["unit"] == "m²" and row["value"] == 60


def test_imar_summary_rows_and_note():
    _, rep = generate(PARCEL, {**BASE, "max_height": 12.0, "emsal_disi_pct": 10}, PROG)
    s = rep["imar_ozeti"]
    keys = {r["key"] for r in s["rows"]}
    assert {"taks", "kaks", "floors", "height", "emsal_disi", "front", "side_left", "side_right", "rear"} <= keys
    assert all(isinstance(r["ok"], bool) for r in s["rows"])
    assert s["note"] == IMAR_NOTE


def test_imar_note_in_outputs(tmp_path):
    res, _ = project.run_apartment(tmp_path)
    f = res["files"]
    for key in ("teklif_docx", "sartname_docx"):
        d = Document(f[key])
        text = "\n".join(p.text for p in d.paragraphs) + "\n".join(c.text for t in d.tables for r in t.rows for c in r.cells)
        assert IMAR_NOTE in text, key
    wb = load_workbook(f["metraj_maliyet_xlsx"])
    for ws in wb.worksheets:
        assert IMAR_NOTE in (ws["A4"].value or ""), ws.title
    import ezdxf
    dxfs = [v for k, v in f.items() if k.startswith("cizim_") and str(v).endswith(".dxf")]
    assert dxfs
    for p in dxfs:
        txt = " ".join(e.dxf.text for e in ezdxf.readfile(p).modelspace().query("TEXT"))
        assert IMAR_SHORT in txt, p


def test_api_validates_new_zoning_fields():
    from fastapi.testclient import TestClient
    from webapp.app import app
    c = TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    body = {"name": "imar", "parcel": PARCEL, "zoning": {**BASE, "max_height": 9.0, "emsal_disi_pct": 10},
            "program": PROG}
    for bad in ({"max_height": -3}, {"max_height": 1}, {"emsal_disi_pct": 45}, {"emsal_disi_pct": -1}, {"emsal_disi_m2": -5}):
        r = c.post("/api/projects", json={**body, "zoning": {**body["zoning"], **bad}})
        assert r.status_code == 422, (bad, r.text)
    r = c.post("/api/projects", json=body)
    assert r.status_code == 200, r.text
    ch = r.json()["report"]["checks"]
    assert ch["height"]["ok"] and ch["height"]["limit"] == 9.0
