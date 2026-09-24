from pathlib import Path

import pytest

from archai import project, quantities as Q
from archai.generate import generate

CASES = [
    ({"width": 22, "depth": 30}, {"taks": 0.4, "kaks": 1.6, "front": 5, "side": 3, "rear": 3, "max_floors": 5}, {"unit_type": "3+1"}),
    ({"width": 30, "depth": 28}, {"taks": 0.4, "kaks": 2.0, "front": 5, "side": 3, "rear": 3, "max_floors": 6}, {"unit_type": "3+1"}),
    ({"width": 18, "depth": 25}, {"taks": 0.35, "kaks": 1.05, "front": 5, "side": 3, "rear": 3, "max_floors": 3}, {"unit_type": "auto"}),
    ({"width": 40, "depth": 35}, {"taks": 0.3, "kaks": 1.5, "front": 5, "side": 5, "rear": 5, "max_floors": 5}, {"unit_type": "4+1"}),
]


@pytest.mark.parametrize("parcel,zoning,program", CASES)
def test_zoning_respected(parcel, zoning, program):
    els, rep = generate(parcel, zoning, program)
    c = rep["checks"]
    assert c["taks"]["ok"] and c["kaks"]["ok"] and c["floors"]["ok"]
    sb = c["setbacks"]
    assert sb["front"] >= zoning["front"] - 1e-6 and sb["side_left"] >= zoning["side"] - 1e-6
    assert sb["side_right"] >= zoning["side"] - 1e-6 and sb["rear"] >= zoning["rear"] - 1e-6
    # metraj brüt alanı = rapor brüt alanı
    assert Q.compute(els)["summary"]["gross_floor_area"] == pytest.approx(rep["gross_total"], abs=0.05)


@pytest.mark.parametrize("parcel,zoning,program", CASES)
def test_rooms_usable(parcel, zoning, program):
    els, rep = generate(parcel, zoning, program)
    q = Q.compute(els)
    for r in q["rooms"]:
        n = r["name"]
        if "Yatak" in n:
            assert r["area"] >= 9.0, n  # yatak odası min ~9 m²
        if "Salon" in n:
            assert r["area"] >= 16.0, n
    # her odanın en az bir kapısı var: kapı sayısı ≥ oda sayısı (hol hariç)
    lvl = next(l for l in q["summary"]["levels"] if l.startswith("Zemin"))
    doors = sum(1 for l in q["lines"] if l["type"] == "opening" and l["kind"] == "door" and l["level"] == lvl)
    rooms = sum(1 for r in q["rooms"] if r["level"] == lvl and not r["name"].endswith("/Hol") and "Kat Holü" not in r["name"]
                and "Şaft" not in r["name"])
    assert doors >= rooms


def test_quick_mode_hits_area(tmp_path):
    res, _ = project.run({"name": "t", "quick": {"gross_area": 600, "floors": 3, "unit_type": "2+1"}}, tmp_path)
    assert res["report"]["gross_total"] == pytest.approx(600, rel=0.03)
    assert res["report"]["unit_type"] == "2+1"
    for k in ("metraj_maliyet_xlsx", "sartname_docx", "teklif_docx", "cizim_pdf"):
        assert Path(res["files"][k]).exists(), k
