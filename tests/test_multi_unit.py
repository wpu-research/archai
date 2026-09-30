"""Kat başına 3 ve 4 daireli tek çekirdekli yerleşim (archai/generate.py `multi_plan`)."""

import copy
import math

import pytest

from archai import costing, generate as G, project, quantities as Q

Q3 = {"gross_area": 1000, "floors": 4, "unit_type": "1+1", "units_per_floor": 3}
Q4 = {"gross_area": 1600, "floors": 4, "unit_type": "2+1", "units_per_floor": 4}
CASES = {"3x1+1": Q3, "4x2+1": Q4, "600/2/1+1": {"gross_area": 600, "floors": 2, "unit_type": "1+1"},
         "3x2+1": {"gross_area": 1200, "floors": 4, "unit_type": "2+1", "units_per_floor": 3},
         "3x3+1": {"gross_area": 2000, "floors": 4, "unit_type": "3+1", "units_per_floor": 3}}
LAND4 = ({"width": 30, "depth": 32}, {"taks": 0.4, "kaks": 1.6, "front": 5, "side": 3, "rear": 3, "max_floors": 4},
         {"unit_type": "1+1", "units_per_floor": 4})


def _gen(q):
    return G.generate(*project.quick_brief(q))


@pytest.fixture(scope="module", params=list(CASES))
def case(request):
    q = CASES[request.param]
    els, rep = _gen(q)
    return q, els, rep


def test_unit_and_room_counts(case):
    q, els, rep = case
    n = rep["units_per_floor"]
    assert n == q.get("units_per_floor", 4) and rep["layout"] == f"core{n}"
    assert rep["unit_count"] == n * q["floors"]
    nb = G.UNIT_TYPES[rep["unit_type"]][1]
    rooms = [e["name"].split("/", 1)[1] for e in els if e["type"] == "room" and e["level"] == "Zemin Kat"]
    for i in range(1, n + 1):
        mine = [r for r in rooms if r.startswith(f"Daire {i}/")]
        short = {r.split("/")[1] for r in mine}
        assert {"Salon", "Hol", "Mutfak", "Banyo"} <= short, mine
        assert sum(s.startswith("Yatak Odası") for s in short) == nb
    common = [e for e in els if e["type"] == "room" and e["level"] == "Zemin Kat" and e["role"] == "common"]
    assert sorted(e["name"].split("/", 1)[1] for e in common) == ["Asansör/Şaft", "Kat Holü", "Merdiven"]
    assert {Q.room_kind(e) for e in common} == {"lift", "stair", "common"}


def test_zoning_and_area(case):
    q, els, rep = case
    c = rep["checks"]
    assert c["taks"]["ok"] and c["kaks"]["ok"] and c["floors"]["ok"] and c["setback_ok"]
    assert abs(rep["area_deviation_pct"]) <= 3
    assert Q.compute(els)["summary"]["gross_floor_area"] == pytest.approx(rep["gross_total"], abs=0.05)
    assert not any("sapma" in w for w in rep["warnings"])


def test_openings_inside_walls_and_all_placed(case):
    q, els, rep = case
    walls = [e for e in els if e["type"] == "wall"]
    for w in walls:
        L = math.dist(w["start"], w["end"])
        assert all(o["offset"] >= -1e-6 and o["offset"] + o["width"] <= L + 1e-6 for o in w["openings"]), w["name"]
    # üreticinin koyduğu her açıklık bir duvar parçasına oturmuş olmalı (sessizce düşen yok)
    m = G.massing(*project.quick_brief(q))
    rects, cores = G.floor_plan(*m["footprint"], G.UNIT_TYPES[m["unit_type"]][1], m["layout"], m["units_per_floor"],
                                1, m["geom"])
    for lvl, ground in (("Zemin Kat", True), ("Kat 1", False)):
        placed = sum(len(w["openings"]) for w in walls if w["level"] == lvl)
        assert placed == len(G._openings(rects, *m["footprint"], cores, ground)), lvl


def test_room_rules(case):
    """Her mahalin kapısı var; salon / yatak odası / mutfak cepheli; giriş kapısı kat holüne; alan ve oran makul."""
    q, els, rep = case
    m = G.massing(*project.quick_brief(q))
    rects, cores = G.floor_plan(*m["footprint"], G.UNIT_TYPES[m["unit_type"]][1], m["layout"], m["units_per_floor"],
                                1, m["geom"])
    ops = G._openings(rects, *m["footprint"], cores, ground=False)
    doors = [o for o in ops if o[4] == "door"]

    def on_edge(r, o):
        orient, c, a, b, _ = o
        if orient == "h":
            return c in (r.y0, r.y1) and r.x0 - 1e-6 <= a and b <= r.x1 + 1e-6
        return c in (r.x0, r.x1) and r.y0 - 1e-6 <= a and b <= r.y1 + 1e-6

    halls = [r for r in rects if r.name == "Kat Holü"]
    for r in rects:
        short = r.name.split("/")[-1]
        if r.kind == "room" or short == "Merdiven" or short.startswith("Asansör"):
            assert any(on_edge(r, d) for d in doors), f"kapısız mahal: {r.name}"
        if r.kind == "room" and short.startswith(("Salon", "Yatak", "Mutfak")):
            assert G._ext_edges(r, rects), f"cephesiz mahal: {r.name}"
        if r.kind == "room" and short != "Hol":
            assert min(r.w, r.d) >= 1.75 and max(r.w, r.d) / min(r.w, r.d) <= 3.2, (r.name, r.w, r.d)
        if short == "Hol":   # daire girişi: hol ↔ kat holü ortak kenarında kapı
            assert any(on_edge(r, d) and any(on_edge(h, d) for h in halls) for d in doors), r.name
    for x in Q.compute(els)["rooms"]:
        n = x["name"]
        if "Yatak" in n:
            assert x["area"] >= 9.0, n
        if "Salon" in n:
            assert x["area"] >= 16.0, n
        if n.endswith("/Mutfak") or n.endswith("/Banyo"):
            assert x["area"] >= 3.5, n


def test_exterior_flags(case):
    q, els, rep = case
    walls = [e for e in els if e["type"] == "wall"]
    truth = {w["name"]: w["exterior"] for w in walls}
    assert all(w["exterior"] == (w["thickness"] == G.EXT_T) for w in walls)
    e2 = copy.deepcopy(els)
    for e in e2:
        e.pop("exterior", None)
    Q.mark_exterior(e2)
    assert {e["name"]: e["exterior"] for e in e2 if e["type"] == "wall"} == truth
    q2 = Q.compute(els)
    lines = Q.select(q2["lines"], type="wall", exterior=False, legacy={"min_thickness": 0.2}, tag=["wall", None])
    assert lines and sum(l["metrics"]["net_area"] for l in lines if l["exterior"]) == 0
    # dış duvar = kontur çevresi (aks) × yükseklik − dış açıklıklar
    per = sum(math.dist(w["start"], w["end"]) for w in walls if w["exterior"] and w["level"] == "Zemin Kat")
    ol = [tuple(p) for p in next(e for e in els if e.get("name") == "Zemin Kat/doseme")["points"]]
    assert per == pytest.approx(Q.polygon_perimeter(ol) - 8 * G.EXT_T / 2, abs=0.05)   # kontur aksın 12,5 cm dışında


def test_three_unit_is_t_shaped_and_four_is_rect():
    els3, rep3 = _gen(Q3)
    els4, rep4 = _gen(Q4)
    ol3 = next(e for e in els3 if e.get("name") == "Zemin Kat/doseme")["points"]
    ol4 = next(e for e in els4 if e.get("name") == "Zemin Kat/doseme")["points"]
    assert len(ol3) == 8 and len(ol4) == 4
    assert rep3["footprint_gross"] < (rep3["footprint"][0] + 0.25) * (rep3["footprint"][1] + 0.25)


def test_600_two_floor_1plus1_hits_target():
    """Önce: 2 daire/kat, daire ≈ 96–101 m² net ve 'hedefin çok üzerinde' uyarısı. Şimdi 4 daire/kat."""
    els, rep = _gen({"gross_area": 600, "floors": 2, "unit_type": "1+1"})
    assert rep["units_per_floor"] == 4 and rep["unit_type"] == "1+1" and rep["unit_count"] == 8
    assert all(45 <= v <= 70 for v in rep["unit_net_area"].values()), rep["unit_net_area"]
    assert 60 <= rep["gross_total"] / rep["unit_count"] <= 80
    assert rep["warnings"] == []


def test_auto_unit_count_from_area():
    assert G.units_for(300, "1+1", "auto") == 4 and G.units_for(300, "2+1", "auto") == 3
    assert G.units_for(200, "2+1", "auto") is None and G.units_for(1000, "2+1", "auto") is None
    assert G.units_for(300, "4+1", "auto") is None and G.units_for(150, "1+1", 3) == 3


def test_land_mode_four_units():
    els, rep = G.generate(*LAND4)
    assert rep["units_per_floor"] == 4 and rep["unit_count"] == 16
    c = rep["checks"]
    assert c["taks"]["ok"] and c["kaks"]["ok"] and c["setback_ok"]
    assert rep["kaks_used_pct"] >= 85


@pytest.mark.parametrize("parcel,taks,upf", [({"width": 20, "depth": 40}, 0.3, 3),    # 14 m genişlik < ≈18 m
                                              ({"width": 60, "depth": 21}, 0.25, 4)])  # 13 m derinlik < ≈16,5 m
def test_narrow_parcel_rejected_in_turkish(parcel, taks, upf):
    zoning = {"taks": taks, "kaks": taks * 4, "front": 5, "side": 3, "rear": 3, "max_floors": 4}
    with pytest.raises(ValueError) as ex:
        G.generate(parcel, zoning, {"unit_type": "1+1", "units_per_floor": upf})
    msg = str(ex.value)
    assert f"kat başına {upf} daire için yapılaşma alanı yetmiyor" in msg and "en az" in msg and "çekirdek" in msg, msg


def test_too_small_floor_rejected():
    with pytest.raises(ValueError) as ex:
        _gen({"gross_area": 400, "floors": 4, "unit_type": "1+1", "units_per_floor": 3})
    assert "kat başına 3 daire" in str(ex.value) and "parsel" not in str(ex.value)


def test_unsupported_unit_count():
    with pytest.raises(ValueError, match="desteklenmiyor"):
        _gen({"gross_area": 600, "floors": 2, "unit_type": "1+1", "units_per_floor": 6})


def test_quantities_four_floor_three_units():
    """4 katlı, kat başına 3 daireli örnekte metraj makul aralıkta."""
    els, rep = _gen({"gross_area": 1200, "floors": 4, "unit_type": "2+1", "units_per_floor": 3})
    Q.mark_exterior(els)
    q = Q.compute(els)
    s = q["summary"]
    net = sum(r["area"] for r in q["rooms"])
    assert 0.78 <= net / s["gross_floor_area"] <= 0.9
    walls = [l for l in q["lines"] if l["type"] == "wall"]
    wl = sum(l["metrics"]["length"] for l in walls)
    assert 0.45 <= wl / s["gross_floor_area"] <= 0.85         # m duvar / m² brüt (2 daireli kat ≈ 0,59)
    ops = [l for l in q["lines"] if l["type"] == "opening"]
    doors = sum(l["kind"] == "door" for l in ops)
    wins = sum(l["kind"] == "window" for l in ops)
    per_floor_rooms = sum(1 for r in q["rooms"] if r["level"] == "Kat 1")
    assert (per_floor_rooms - 4) * 4 <= doors <= (per_floor_rooms + 4) * 4   # hol/kat holü hariç her mahale bir kapı + girişler
    assert 3 * 4 * 4 <= wins <= 3 * 4 * 8     # daire başına salon 2 + mutfak + yatak odaları (banyolar iç)
    cost = costing.estimate(q)
    assert cost["total"] > 0


@pytest.mark.parametrize("q", [Q3, Q4], ids=["3daire", "4daire"])
def test_project_run_end_to_end(q, tmp_path):
    res, els = project.run({"name": "çok daire", "quick": q}, tmp_path)
    assert res["report"]["units_per_floor"] == q["units_per_floor"]
    for k in ("metraj_maliyet_xlsx", "sartname_docx", "teklif_docx", "cizim_pdf", "cizim_03_normal_kat_plani",
              "cizim_04_kesit_AA", "cizim_05_on_gorunus"):
        assert (tmp_path / res["files"][k]).exists(), k
    assert (tmp_path / "cizimler" / "03_normal_kat_plani.png").exists()
