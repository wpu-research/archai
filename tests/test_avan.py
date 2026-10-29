"""Avan programı: 1. bodrum + zemin katta işyeri + çatı katı (archai/avan.py)."""
import pytest

from archai import project
from archai.generate import generate

PARCEL = {"width": 32, "depth": 24}
ZONING = {"taks": 0.43, "kaks": 3.0, "front": 3, "side": 3.5, "rear": 3.5, "max_floors": 7, "floor_height": 2.75}
PROGRAM = {"unit_type": "1+1", "units_per_floor": 4, "avan": {"basement": True, "shops": 6, "attic_area": 74.5}}


@pytest.fixture(scope="module")
def avan():
    elements, report = generate(PARCEL, ZONING, PROGRAM)
    return project.avan.apply(elements, report, PARCEL, ZONING, PROGRAM)


def test_avan_olmadan_degismez():
    prog = {k: v for k, v in PROGRAM.items() if k != "avan"}
    els, rep = generate(PARCEL, ZONING, prog)
    els2, rep2 = project.avan.apply(els, rep, PARCEL, ZONING, prog)
    assert els2 is els and rep2 is rep and "avan" not in rep


def test_katlar_ve_bolumler(avan):
    els, rep = avan
    levels = {e["level"] for e in els}
    assert {"1. Bodrum", "Zemin Kat", "Kat 6", "Çatı Katı"} <= levels
    assert rep["floors"] == 7 and rep["units_per_floor"] == 4
    assert rep["unit_count"] == 24                       # 6 normal kat × 4 daire
    zemin_rooms = [e["name"] for e in els if e["type"] == "room" and e["level"] == "Zemin Kat" and e["role"] == "room"]
    assert len(zemin_rooms) == 6 and all("İşyeri" in n for n in zemin_rooms)
    assert not any("Daire" in e["name"] for e in els if e["type"] == "room" and e["level"] == "Zemin Kat")


def test_bodrum_ve_alanlar(avan):
    els, rep = avan
    b = rep["avan"]["basement"]
    assert b["rooms"]["Sığınak"] >= b["shelter_required"] and "Otopark" in b["rooms"]
    assert b["parking_required"] == 8                    # 24 konut / 3
    z = {e["level"]: e["z"] for e in els if e["type"] == "slab" and e["role"] == "floor"}
    assert z["1. Bodrum"] < z["Zemin Kat"] < z["Kat 1"]
    expect = rep["footprint_gross"] * 8 + rep["avan"]["attic_area"]     # 7 tipik kat + bodrum + çatı katı
    assert rep["gross_total"] == pytest.approx(expect, abs=0.1)


def test_uctan_uca_ve_cizimler(tmp_path):
    brief = {"name": "avan", "parcel": PARCEL, "zoning": ZONING, "program": PROGRAM}
    res, _ = project.run(brief, tmp_path / "p")
    names = {p.name for p in (tmp_path / "p" / "cizimler").glob("*.dxf")}
    assert {"02_zemin_kat_plani.dxf", "03_normal_kat_plani.dxf", "06_bodrum_kat_plani.dxf",
            "07_cati_kati_plani.dxf"} <= names
    assert "1. Bodrum" in res["summary"]["levels"]
