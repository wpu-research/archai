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


def test_amount_in_words():
    from archai.reports import amount_in_words, words_tr
    assert words_tr(1000) == "bin" and words_tr(1100) == "bin yüz" and words_tr(2001) == "iki bin bir"
    assert words_tr(36289874) == "otuz altı milyon iki yüz seksen dokuz bin sekiz yüz yetmiş dört"
    assert amount_in_words(1250.5) == "Yalnız bin iki yüz elli Türk Lirası elli Kuruş."


def test_formal_plan_is_true_scale_1_100():
    from archai import drawings
    parcel, zoning, program = CASES[1]
    els, rep = generate(parcel, zoning, program)
    sh = drawings.compose({"project": "t"}, "A-01", "ZEMİN KAT PLANI",
                          lambda s: drawings.draw_plan(s, els, "Zemin Kat", 10.0, "ZEMİN KAT PLANI"))
    assert sh.S == 100
    assert sh.doc.dimstyles.get("TR-CM").dxf.dimlfac == 100  # ölçüler cm


def test_cabin_scenario_valid():
    from archai import cabin
    from archai.layout_check import check
    els, rep, design = cabin.scenario()
    c = rep["checks"]
    assert c["taks"]["ok"] and c["kaks"]["ok"]
    sb = c["setbacks"]
    assert min(sb["front"], sb["rear"], sb["side_left"], sb["side_right"]) >= cabin.ZONING["side"]
    assert 95 <= rep["gross_total"] <= 105
    n = sum(len(e["openings"]) for e in els if e["type"] == "wall")
    assert n == len(cabin.ground_openings()) + len(cabin.loft_openings())
    assert check(els, design) == []
    assert {"klozet", "dus", "mutfak", "buzdolabi", "yatak_cift", "kanepe"} <= {o["kind"] for o in design["objects"]}
    assert set(design["floors"]) == {e["name"] for e in els if e["type"] == "room"}


def test_villa_scenario_valid():
    from archai import villa
    from archai.layout_check import check
    els, rep, design = villa.scenario()
    c = rep["checks"]
    assert c["taks"]["ok"] and c["kaks"]["ok"]
    sb = c["setbacks"]
    assert sb["front"] >= villa.ZONING["front"] and sb["rear"] >= villa.ZONING["rear"]
    assert min(sb["side_left"], sb["side_right"]) >= villa.ZONING["side"]
    # tanımlı her açıklık bir duvar parçasına oturmuş olmalı
    n = sum(len(e["openings"]) for e in els if e["type"] == "wall")
    assert n == len(villa.ground_openings()) + len(villa.first_openings())
    # nesneler odadan taşmıyor, çakışmıyor, kapı önlerini kapatmıyor
    assert check(els, design) == []
    kinds = {o["kind"] for o in design["objects"]}
    assert {"klozet", "lavabo", "dus", "kuvet", "mutfak", "yatak_cift", "kanepe_l", "sezlong"} <= kinds
    rooms = {e["name"] for e in els if e["type"] == "room"}
    assert set(design["floors"]) == rooms


def test_apartment_scenario_valid():
    from archai import apartment
    from archai.layout_check import check
    els, rep, design = apartment.scenario()
    assert rep["unit_count"] == 3 and 255 <= rep["gross_total"] <= 275
    walls = [e for e in els if e["type"] == "wall"]
    ops = [o for w in walls for o in w["openings"]]
    assert sum(o["kind"] == "door" for o in ops) == 19
    # her açıklık kendi duvarının içinde
    import math
    for w in walls:
        L = math.dist(w["start"], w["end"])
        assert all(0 <= o["offset"] and o["offset"] + o["width"] <= L + 1e-6 for o in w["openings"]), w["name"]
    # batı ve doğu daire birbirinin aynası: aynı mobilya, x'te simetrik
    rooms = [e["name"] for e in els if e["type"] == "room"]
    assert len(rooms) == 21
    n, objs = len(apartment.WEST_ITEMS), design["objects"]
    axis2 = 2 * apartment.OX + (apartment.MX - 2 * apartment.PX0) / apartment.S
    for a, b in zip(objs[:n], objs[n:2 * n]):
        assert a["kind"] == b["kind"] and abs(a["x"] + b["x"] - axis2) < 0.01 and a["y"] == b["y"]
    # çizimde lavabo banyo kapısının önünde; başka taşma/çakışma yok
    assert check(els, design) == ["Normal Kat/Daire 3 Banyo: lavabo bir kapı önünü kapatıyor"]
    assert set(design["floors"]) == set(rooms)


def test_ust_kat_cikmasi_ve_cati_geri():
    """Zemin oturumdur; üst katlar her kenardan 1,5 m taşar; çatı hattı (korkuluk) 1 m geri çekilir; çekmeler çıkmalı konturdan."""
    parcel = {"width": 24.0, "depth": 38.5}
    zon = {"taks": 0.25, "kaks": 2.0, "front": 5.0, "side": 3.0, "rear": 3.0, "max_floors": 3, "floor_height": 3.1}
    prog = {"unit_type": "2+1", "units_per_floor": "auto"}
    _, base = generate(parcel, zon, prog)
    els, rep = generate(parcel, zon, {**prog, "cikma": {"ust_kat": 1.5, "cati_geri": 1.0}})

    def bounds(name):
        pts = next(e["points"] for e in els if e["type"] == "slab" and e["name"] == name)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)
    z, k1, k2 = bounds("Zemin Kat/doseme"), bounds("Kat 1/doseme"), bounds("Kat 2/doseme")
    assert k1 == k2
    assert [round(k1[0] - z[0], 2), round(k1[1] - z[1], 2), round(z[2] - k1[2], 2), round(z[3] - k1[3], 2)] == [-1.5, -1.5, -1.5, -1.5]
    parapet = [e for e in els if e["name"].startswith("cati_parapet")]
    px = [e["origin"][0] for e in parapet] + [e["origin"][0] + e["size"][0] for e in parapet]
    py = [e["origin"][1] for e in parapet] + [e["origin"][1] + e["size"][1] for e in parapet]
    assert round(min(px) - k1[0], 2) == 1.0 and round(k1[2] - max(px), 2) == 1.0      # çatı hattı 1 m geride
    assert round(min(py) - k1[1], 2) == 1.0 and round(k1[3] - max(py), 2) == 1.0
    assert rep["checks"]["taks"]["value"] == base["checks"]["taks"]["value"]          # TAKS zemin oturumundan
    assert rep["gross_total"] > base["gross_total"] and rep["cikma"]["ust_kat"] == 1.5
    assert rep["checks"]["setbacks"]["side_left"] == pytest.approx(base["checks"]["setbacks"]["side_left"] - 1.5, abs=0.01)
    # çıkmasız üretim aynen kalır
    _, again = generate(parcel, zon, prog)
    assert again["gross_total"] == base["gross_total"] and "cikma" not in again
