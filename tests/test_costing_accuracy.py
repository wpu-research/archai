"""Konsey bulguları (B: maliyet/metraj/imar doğruluğu) için regresyon testleri.

Önceki değerler (düzeltme öncesi, aynı örnek 22×30 / 3+1 → 2+1, 4 kat):
  DUV-01/YAL-01/SIV-02 = 991,32 m² (dış 568 + çekirdek 423), ZEM-01 = 849,96 m² (ortak alan + asansör kuyusu dahil),
  merdiven 9 × 0,17 = 1,53 m, ön çekme dış yüzden 4,975 m.
"""

import math
from pathlib import Path

import pytest
from docx import Document

from archai import costing, project, quantities as Q, reports
from archai.dxf_import import import_dxf
from archai.generate import generate

ROOT = Path(__file__).resolve().parents[1]
C22 = ({"width": 22, "depth": 30}, {"taks": 0.4, "kaks": 1.6, "front": 5, "side": 3, "rear": 3, "max_floors": 5},
       {"unit_type": "3+1"})


def _rows(els):
    Q.mark_exterior(els)
    q = Q.compute(els)
    return q, {r["code"]: r for r in costing.estimate(q)["rows"]}


@pytest.fixture(scope="module")
def c22():
    els, rep = generate(*C22)
    q, rows = _rows(els)
    return els, rep, q, rows


# ---------------------------------------------------------------- 1. dış duvar kalemleri
def test_interior_walls_not_in_exterior_items(c22):
    els, rep, q, rows = c22
    walls = [e for e in els if e["type"] == "wall"]
    assert all("exterior" in w for w in walls)
    lines = Q.select(q["lines"], type="wall", exterior=False, legacy={"min_thickness": 0.2}, tag=["wall", None])
    assert lines and sum(l["metrics"]["net_area"] for l in lines if l["exterior"]) == 0
    # dış duvar = aks çevresi × duvar yüksekliği − dış duvar açıklıkları
    (w, d), fl = rep["footprint"], rep["floors"]
    h = walls[0]["height"]
    ext_open = sum(o["width"] * o["height"] for e in walls if e["exterior"] for o in e["openings"])
    expected = 2 * (w + d) * h * fl - ext_open
    for code in ("DUV-01", "YAL-01", "SIV-02"):
        assert rows[code]["quantity"] == pytest.approx(expected, abs=0.1), code
    assert rows["DUV-01"]["quantity"] < 600          # önce 991,32
    assert rows["DUV-04"]["quantity"] > 400          # çekirdek duvarları kendi kalemine


def test_mark_exterior_matches_generator(c22):
    els = generate(*C22)[0]
    truth = {e["name"]: e["exterior"] for e in els if e["type"] == "wall"}
    for e in els:
        e.pop("exterior", None)
    Q.mark_exterior(els)
    assert {e["name"]: e["exterior"] for e in els if e["type"] == "wall"} == truth


def test_legacy_elements_fall_back_to_thickness():
    els, _ = import_dxf(ROOT / "references" / "test_plan_2+1.dxf", floors=1, add_roof=False)
    legacy = {r["code"]: r["quantity"] for r in costing.estimate(Q.compute(els))["rows"]}
    marked = {r["code"]: r["quantity"] for r in _rows(els)[1].values()}
    assert legacy["DUV-01"] == pytest.approx(marked["DUV-01"]) and legacy["DUV-01"] > 90   # 4 dış duvar, 25 cm
    assert marked["DUV-02"] == pytest.approx(legacy["DUV-02"])


@pytest.mark.parametrize("name,lo,hi", [("villa", 250, 320), ("cabin", 0, 0.01), ("apartment", 140, 175)])
def test_scenario_exterior_totals(name, lo, hi):
    import importlib
    els = importlib.import_module(f"archai.{name}").scenario()[0]
    _, rows = _rows(els)
    assert lo <= rows["DUV-01"]["quantity"] <= hi   # cabin tomruk: DUV-03


# ---------------------------------------------------------------- 2–3. ortak alan, asansör, sıva açıklığı
def test_common_areas_and_shaft(c22):
    els, rep, q, rows = c22
    rl = [l for l in q["lines"] if l["type"] == "room"]
    lift = sum(l["metrics"]["area"] for l in rl if l["kind"] == "lift")
    common = sum(l["metrics"]["area"] for l in rl if l["kind"] == "common")
    unit = sum(l["metrics"]["area"] for l in rl if l["kind"] == "room")
    assert lift > 0 and common > 0
    assert rows["ZEM-01"]["quantity"] == pytest.approx(unit, abs=0.05)
    assert rows["ORT-01"]["quantity"] == pytest.approx(common, abs=0.05)
    for code in ("SIV-01", "TAV-01", "SAP-01", "SUP-01"):
        rule = next(it for it in costing.load_prices()["items"] if it["code"] == code)["qty"]
        assert "lift" not in rule["kind"] and "shaft" not in rule["kind"], code
    assert rows["ASN-01"]["quantity"] == rep["floors"]       # durak


def test_wall_finish_deducts_openings():
    wall = lambda n, a, b, ops, t=0.2: {"type": "wall", "name": n, "level": "K", "start": a, "end": b, "thickness": t,
                                         "height": 2.8, "openings": ops}
    els = [wall("S", [0, 0], [8, 0], [{"offset": 1, "width": 1.0, "height": 1.4, "kind": "window"}]),
           wall("N", [0, 4], [8, 4], []), wall("W", [0, 0], [0, 4], []), wall("E", [8, 0], [8, 4], []),
           wall("I", [4, 0], [4, 4], [{"offset": 1, "width": 0.9, "height": 2.1, "kind": "door"}], 0.1),
           {"type": "room", "name": "K/A", "level": "K", "height": 2.8,
            "points": [[0.1, 0.1], [3.95, 0.1], [3.95, 3.9], [0.1, 3.9]]},
           {"type": "room", "name": "K/B", "level": "K", "height": 2.8,
            "points": [[4.05, 0.1], [7.9, 0.1], [7.9, 3.9], [4.05, 3.9]]}]
    rooms = {l["element"]: l["metrics"] for l in Q.compute(els)["lines"] if l["type"] == "room"}
    a, b = rooms["K/A"], rooms["K/B"]
    assert a["wall_finish_gross"] - a["wall_finish_area"] == pytest.approx(1.4 + 0.9 * 2.1, abs=1e-3)  # pencere + kapı
    assert b["wall_finish_gross"] - b["wall_finish_area"] == pytest.approx(0.9 * 2.1, abs=1e-3)        # kapının öbür yüzü
    assert b["skirting_length"] == pytest.approx(b["perimeter"] - 0.9, abs=1e-3)


# ---------------------------------------------------------------- 4. yaklaşık taşıyıcı kalemler
def test_structural_items_present_and_flagged(c22):
    els, rep, q, rows = c22
    for code in ("HAF-01", "TEM-01", "KOL-01", "MER-01", "ASN-01"):
        assert rows[code]["quantity"] > 0 and rows[code]["approx"], code
    gfa = q["summary"]["gross_floor_area"]
    assert rows["KOL-01"]["quantity"] == pytest.approx(0.12 * gfa, abs=0.05)
    # m² maliyeti: önce 22.779 TL/m² (KDV dahil); taşıyıcı kalemler eklendi, dış duvar fazlası düştü → ±%25 içinde
    per_m2 = costing.estimate(q)["per_m2"]
    assert 22779 * 0.75 <= per_m2 <= 22779 * 1.25


def test_cabin_uses_pier_foundation():
    from archai import cabin
    _, rows = _rows(cabin.scenario()[0])
    assert rows["TEM-01"]["quantity"] == 0 and rows["TEM-02"]["quantity"] > 60 and rows["KOL-01"]["quantity"] == 0


# ---------------------------------------------------------------- 5. teklif şartları
def _offer_text(tmp_path, info, adjust=None):
    els, rep = generate(*C22)
    q = Q.compute(els)
    cost = costing.estimate(q, adjust=adjust)
    p = reports.write_offer_docx(tmp_path / "t.docx", "T", rep, q, cost, info=info)
    return "\n".join(par.text for par in Document(p).paragraphs)


def test_offer_terms_default_marked_draft(tmp_path):
    txt = _offer_text(tmp_path, {})
    assert txt.count(reports.DRAFT.strip()) >= 5
    assert "anahtar teslim" in txt and "kesin statik/temel projesine göre" in txt
    assert "%20'si sözleşme imzasında" in txt and "%30'u kaba inşaat" in txt


def test_offer_terms_from_info(tmp_path):
    offer = {"months": 14, "payment": [{"pct": 25, "desc": "avans"}, {"pct": 75, "desc": "teslimde"}],
             "court": "İzmir (Merkez) Mahkemeleri", "validity_days": 45, "price_diff_pct": 5}
    txt = _offer_text(tmp_path, {"offer": offer})
    assert reports.DRAFT.strip() not in txt
    assert "14 (on dört) aydır" in txt and "%25'i avans" in txt and "45 (kırk beş) gün" in txt
    assert "%5'i aşan" in txt and "İzmir (Merkez) Mahkemeleri yetkilidir" in txt


def test_offer_scope_without_structure_is_not_turnkey(tmp_path):
    txt = _offer_text(tmp_path, {}, adjust={"disabled": ["KOL-01", "TEM-01", "TEM-02"]})
    assert "anahtar teslim değildir" in txt


def test_offer_key_in_info_keys():
    assert "offer" in project.INFO_KEYS


# ---------------------------------------------------------------- 6. hızlı mod / KAKS
@pytest.mark.parametrize("area,floors,ut", [(5000, 10, "2+1"), (600, 2, "1+1"), (2100, 5, "1+1"), (600, 3, "2+1")])
def test_quick_mode_area(area, floors, ut):
    parcel, zoning, program = project.quick_brief({"gross_area": area, "floors": floors, "unit_type": ut})
    els, rep = generate(parcel, zoning, program)
    assert abs(rep["area_deviation_pct"]) <= 3 and rep["gross_total"] == pytest.approx(area, rel=0.03)  # önce −%37…−%45
    assert rep["unit_type"] == ut and rep["virtual_parcel"]
    assert all("parsel" not in w.replace("sanal parsel", "") for w in rep["warnings"])


def test_quick_mode_error_wording():
    parcel, zoning, program = project.quick_brief({"gross_area": 90, "floors": 3, "unit_type": "2+1"})
    with pytest.raises(ValueError) as ex:
        generate(parcel, zoning, program)
    assert "parsel" not in str(ex.value).replace("sanal parsel", "")


def test_kaks_usage_reported():
    els, rep = generate({"width": 60, "depth": 40}, {"taks": 0.4, "kaks": 2.0, "front": 5, "side": 3, "rear": 3,
                                                     "max_floors": 6}, {"unit_type": "2+1"})
    assert rep["kaks_used_pct"] >= 85                  # önce 1371,5 / 4800 = %29 (tek çekirdeğe kırpılıyordu)
    assert rep["checks"]["kaks"]["ok"] and rep["checks"]["taks"]["ok"]


# ---------------------------------------------------------------- 7. çekme dış yüzden
def test_setbacks_from_outer_face(c22):
    els, rep, q, rows = c22
    c = rep["checks"]
    parcel, zoning, _ = C22
    ox, oy = rep["origin"]
    assert c["setbacks"]["front"] == pytest.approx(oy - 0.125, abs=1e-3)     # önce aks: 5,1 (dış yüz 4,975)
    assert c["setback_ok"] and all(v["ok"] for v in c["setbacks_detail"].values())
    for k, lim in (("front", 5), ("side_left", 3), ("side_right", 3), ("rear", 3)):
        assert c["setbacks"][k] >= lim and c["setbacks_detail"][k]["limit"] == lim


@pytest.mark.parametrize("name", ["villa", "cabin", "apartment"])
def test_scenario_setback_format(name):
    import importlib
    rep = importlib.import_module(f"archai.{name}").scenario()[1]
    c = rep["checks"]
    assert set(c["setbacks"]) == {"front", "side_left", "side_right", "rear"}
    assert all(isinstance(v, float) for v in c["setbacks"].values())
    assert c["setback_ok"], c["setbacks_detail"]


# ---------------------------------------------------------------- 8. merdiven kat yüksekliğine ulaşır
def test_stairs_reach_floor_height(c22):
    els, rep, q, rows = c22
    lvl = "Zemin Kat"
    st = [e for e in els if e["type"] == "stairs" and e["level"] == lvl]
    assert len(st) == 2
    assert sum(s["steps"] * s["rise"] for s in st) == pytest.approx(3.0, abs=0.01)   # önce 9 × 0,17 = 1,53 m
    assert rows["MER-01"]["quantity"] == pytest.approx(rep["floors"] * sum(s["steps"] * s["width"] for s in st))


# ---------------------------------------------------------------- 9. fiyat ayarı doğrulaması
@pytest.mark.parametrize("adj", [
    {"profit_pct": -50}, {"overhead_pct": 150}, {"vat_pct": "20"}, {"overrides": {"KAP-01": -1}},
    {"overrides": ["KAP-01"]}, {"variants": {"ZEM-01": "mermer"}}, {"variants": {"KAP-01": "x"}},
    {"extra_items": [{"name": "", "quantity": 1, "unit_price": 1}]},
    {"extra_items": [{"name": "x", "quantity": -1, "unit_price": 1}]}, {"disabled": "KAP-01"}, {"bilinmeyen": 1},
])
def test_validate_adjust_rejects(adj):
    with pytest.raises(ValueError):
        costing.validate_adjust(adj)
    with pytest.raises(ValueError):
        costing.estimate({"lines": [], "summary": {"gross_floor_area": 0}}, adjust=adj)


def test_validate_adjust_accepts_and_enabled_wins(c22):
    q = c22[2]
    adj = {"profit_pct": 0, "vat_pct": 10, "overrides": {"KAP-01": 0}, "variants": {"ZEM-01": "seramik"},
           "disabled": ["KOL-01"], "enabled": ["KOL-01"], "extra_items": [{"name": "x", "quantity": 0, "unit_price": 5}]}
    assert costing.validate_adjust(adj) is adj
    c = costing.estimate(q, adjust=adj)
    assert c["total"] > 0 and next(r for r in c["rows"] if r["code"] == "KOL-01")["enabled"]
    assert costing.validate_adjust(None) == {}
    assert not math.isnan(c["total"])
