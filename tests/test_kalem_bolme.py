"""Kalem bölme + eksiksiz iş kalemi kataloğu (katalog v2) testleri."""

import importlib
from pathlib import Path

import pytest

from archai import costing, quantities as Q, spec
from archai.dxf_import import import_dxf
from archai.generate import generate

ROOT = Path(__file__).resolve().parents[1]
C22 = ({"width": 22, "depth": 30}, {"taks": 0.4, "kaks": 1.6, "front": 5, "side": 3, "rear": 3, "max_floors": 5},
       {"unit_type": "3+1"})
PRICES = costing.load_prices()
ITEMS = {it["code"]: it for it in PRICES["items"]}


def _cost(els, adjust=None):
    Q.mark_exterior(els)
    q = Q.compute(els)
    c = costing.estimate(q, adjust=adjust)
    return q, c, {r["code"]: r for r in c["rows"]}


@pytest.fixture(scope="module")
def c22():
    els, rep = generate(*C22)
    q, c, rows = _cost(els)
    return els, rep, q, c, rows


@pytest.fixture(scope="module")
def scenarios():
    out = {n: importlib.import_module(f"archai.{n}").scenario()[0] for n in ("villa", "cabin", "apartment")}
    out["dxf"] = import_dxf(ROOT / "references" / "test_plan_2+1.dxf", floors=3, add_roof=True)[0]
    return out


# ---------------------------------------------------------------- katalog bütünlüğü
def test_catalog_integrity():
    codes = [it["code"] for it in PRICES["items"]]
    assert len(codes) == len(set(codes)) and len(codes) >= 90
    groups = []                                  # raporlar grup başlığını satır değişince yazar: gruplar bitişik olmalı
    for it in PRICES["items"]:
        if not groups or groups[-1] != it["group"]:
            assert it["group"] not in groups, f"{it['group']} bölünmüş"
            groups.append(it["group"])
        assert it["unit_price"] > 0 and it["unit"] and it["qty"].get("metric")
        for v in it.get("variants", []):
            assert v["unit_price"] > 0
        assert not it.get("variants") or it["selected"] in {v["id"] for v in it["variants"]}
    assert groups[0] == "Genel giderler" and groups[-1] == "Teklif dışı hizmetler"


def test_every_item_has_spec_text():
    assert set(spec.ITEMS) == set(ITEMS)
    for code, t in spec.ITEMS.items():
        assert all(isinstance(t[k], str) and len(t[k]) > 15 for k in ("malzeme", "uygulama", "olcum")), code


def test_every_metric_exists_on_real_lines(c22, scenarios):
    seen = {}
    for q in [c22[2]] + [Q.compute(Q.mark_exterior(e)) for e in scenarios.values()]:
        for l in q["lines"]:
            seen.setdefault(l["type"], set()).update(l["metrics"])
    for code, it in ITEMS.items():
        r = it["qty"]
        types = r["type"] if isinstance(r["type"], list) else [r["type"]]
        assert any(r["metric"] in seen.get(t, ()) for t in types), f"{code}: {r['metric']} hiçbir {types} satırında yok"


@pytest.mark.parametrize("name", ["villa", "cabin", "apartment", "dxf"])
def test_all_scenarios_cost_without_errors(scenarios, name):
    q, c, rows = _cost(scenarios[name])
    assert c["total"] > 0 and set(rows) == set(ITEMS)
    assert all(r["quantity"] >= 0 and r["amount"] >= 0 for r in rows.values())


# ---------------------------------------------------------------- ıslak hacim sınıfı
@pytest.mark.parametrize("name,expect", [
    ("Zemin Kat/Daire 1/Banyo", "bath"), ("Ebeveyn Banyosu", "bath"), ("Misafir Banyosu", "bath"),
    ("K/Misafir WC", "wc"), ("Lavabo", "wc"), ("Çamaşır Odası", "wc"), ("Küçük Sauna", "spa"), ("Hamam", "spa"),
    ("Daire 1/Mutfak ve Yemek", "kitchen"), ("Amerikan Mutfak ve Salon", "kitchen"), ("Balkon", "balcony"),
    ("Salon", None), ("Yatak Odası", None), ("Antre", None), ("Giriş Holü", None),
])
def test_room_wet_classification(name, expect):
    assert Q.room_wet({"name": name, "role": "room"}) == expect


def test_common_rooms_are_never_wet():
    assert Q.room_wet({"name": "Kat Holü/WC", "role": "common"}) is None
    assert Q.room_wet({"name": "Asansör/Şaft", "role": "common"}) is None


# ---------------------------------------------------------------- bölme tutarlılığı (hiçbir yüzey iki kez / hiç sayılmaz)
def test_floor_finishes_partition_room_area(c22):
    els, rep, q, c, rows = c22
    total = sum(l["metrics"]["area"] for l in q["lines"] if l["type"] == "room" and l["kind"] == "room")
    got = rows["ZEM-01"]["quantity"] + rows["SER-01"]["quantity"] + rows["BAL-01"]["quantity"]
    assert got == pytest.approx(total, abs=0.05)


def test_wall_finishes_partition_wall_area(c22):
    """Sıva her mahalde; boya+alçı banyo/WC dışında; seramik banyo/WC'de — boya + seramik = sıva."""
    rows = c22[4]
    assert rows["ALC-01"]["quantity"] == pytest.approx(rows["BOY-01"]["quantity"])
    assert rows["BOY-01"]["quantity"] + rows["SER-02"]["quantity"] == pytest.approx(rows["SIV-01"]["quantity"], abs=0.05)
    assert 0 < rows["SER-02"]["quantity"] < rows["SIV-01"]["quantity"]
    assert rows["TAV-01"]["quantity"] == pytest.approx(rows["TAV-02"]["quantity"])


def test_exterior_finish_layers_share_one_area(c22):
    rows = c22[4]
    for code in ("YAL-01", "YAL-04", "SIV-02", "BOY-02"):
        assert rows[code]["quantity"] == pytest.approx(rows["DUV-01"]["quantity"], abs=0.01), code
    assert rows["GEN-03"]["quantity"] > rows["DUV-01"]["quantity"]       # iskele brüt alan (boşluklar düşülmemiş)


def test_doors_partition_into_three_kinds(c22, scenarios):
    for q, rows in [(c22[2], c22[4])] + [(lambda r: (r[0], r[2]))(_cost(e)) for e in scenarios.values()]:
        n = rows["KAP-01"]["quantity"] + rows["KAP-02"]["quantity"] + rows["KAP-03"]["quantity"]
        assert n == q["summary"]["door_count"]
        assert rows["KAP-04"]["quantity"] == pytest.approx(
            sum(l["metrics"]["width"] for l in q["lines"] if l["type"] == "opening" and l["kind"] == "door"), abs=0.01)


def test_window_split_into_frame_and_glass(c22):
    rows = c22[4]
    assert rows["PEN-03"]["quantity"] == pytest.approx(0.85 * rows["PEN-01"]["quantity"], abs=0.02)
    assert [v["id"] for v in rows["PEN-01"]["variants"]] == ["pvc", "alu"]
    assert [v["id"] for v in rows["PEN-03"]["variants"]] == ["cift_cam", "low_e", "uclu_cam"]
    q = c22[2]
    base = costing.estimate(q)["subtotal"]
    tri = costing.estimate(q, adjust={"variants": {"PEN-01": "alu", "PEN-03": "uclu_cam"}})["subtotal"]
    area, glass = rows["PEN-01"]["quantity"], rows["PEN-03"]["quantity"]
    assert tri - base == pytest.approx(area * (8200 - 4600) + glass * (4100 - 1900), rel=1e-3)   # satır miktarları 2 haneye yuvarlı


def test_concrete_is_itemized_into_concrete_steel_formwork(c22):
    rows = c22[4]
    for c in ("BET-01", "DON-01", "KAL-01", "KOL-01", "DON-02", "KAL-02", "TEM-01", "DON-03", "KAL-03"):
        assert rows[c]["quantity"] > 0, c
    assert rows["DON-01"]["unit"] == "ton" and rows["DON-01"]["quantity"] == pytest.approx(rows["BET-01"]["quantity"] * 0.085, abs=0.01)
    assert rows["DON-03"]["quantity"] == pytest.approx(rows["TEM-01"]["quantity"] * 0.11, abs=0.01)
    assert rows["GRO-01"]["quantity"] == pytest.approx(rows["YAL-03"]["quantity"] * 0.10, abs=0.01)


def test_dwelling_units_and_unit_based_items(c22, scenarios):
    rows = c22[4]
    assert c22[2]["lines"] and rows["ISI-02"]["quantity"] == rows["DOG-01"]["quantity"] == rows["ELK-03"]["quantity"] == 8
    assert Q.dwelling_units(c22[0]) == 8                              # 4 kat × 2 daire
    assert Q.dwelling_units(scenarios["villa"]) == 1 and Q.dwelling_units(scenarios["apartment"]) == 3
    assert Q.dwelling_units([{"type": "slab", "role": "floor"}]) == 0   # daire içi mahal yoksa birim yok


def test_wet_room_items_follow_room_names(scenarios):
    _, c, rows = _cost(scenarios["villa"])
    assert rows["VIT-01"]["quantity"] == 3 and rows["VIT-02"]["quantity"] == 1       # 3 banyo + misafir WC
    assert rows["MUT-01"]["quantity"] == pytest.approx(4.5) and rows["SIH-01"]["quantity"] == 5   # 3 banyo + WC + mutfak
    _, c, cab = _cost(scenarios["cabin"])
    assert cab["VIT-01"]["quantity"] == 1 and cab["SER-01"]["quantity"] > 0       # sauna: kaplama var, takım yok


def test_stair_rail_and_common_area_items(c22):
    rows = c22[4]
    assert rows["KRK-01"]["quantity"] > 0 and rows["YAN-01"]["quantity"] > 0 and rows["ASN-01"]["quantity"] == 4


def test_landscape_area_is_site_minus_footprint_and_paving():
    els = [{"type": "slab", "role": "site", "name": "p", "points": [[0, 0], [20, 0], [20, 20], [0, 20]], "level": "Arsa"},
           {"type": "slab", "role": "paving", "name": "y", "points": [[0, 0], [5, 0], [5, 4], [0, 4]], "level": "Arsa"},
           {"type": "slab", "role": "floor", "tag": "concrete", "name": "d", "level": "K",
            "points": [[5, 5], [15, 5], [15, 15], [5, 15]], "z": 0, "thickness": 0.2}]
    rows = {r["code"]: r for r in costing.estimate(Q.compute(els))["rows"]}
    assert rows["CEV-02"]["quantity"] == pytest.approx(400 - 100 - 20)
    assert rows["CEV-01"]["quantity"] == pytest.approx(80) and not rows["CEV-01"]["enabled"]      # opsiyonel


# ---------------------------------------------------------------- opsiyonel / teklif dışı kalemler
def test_optional_items_off_by_default_and_enabled_on_request(c22):
    q, c, rows = c22[2], c22[3], c22[4]
    optional = [code for code, it in ITEMS.items() if it.get("default_enabled") is False]
    assert {"CEV-01", "CEP-01", "PEN-04", "TAV-03"} <= set(optional) and len([o for o in optional if o.startswith("HIZ-")]) == 6
    assert all(not rows[o]["enabled"] and rows[o]["amount"] == 0 and rows[o]["default_enabled"] is False for o in optional)
    on = costing.estimate(q, adjust={"enabled": ["HIZ-04", "PEN-04"]})
    r = {x["code"]: x for x in on["rows"]}
    assert r["HIZ-04"]["enabled"] and r["HIZ-04"]["amount"] == pytest.approx(r["HIZ-04"]["quantity"] * 520)
    assert on["subtotal"] - c["subtotal"] == pytest.approx(r["HIZ-04"]["amount"] + r["PEN-04"]["amount"], abs=0.5)
    off = costing.estimate(q, adjust={"enabled": ["HIZ-04"], "disabled": ["HIZ-04"]})   # enabled kazanır (eski sözleşme)
    assert next(x for x in off["rows"] if x["code"] == "HIZ-04")["enabled"]


def test_optional_items_not_in_offer_or_spec(c22):
    from archai import spec as S
    q, c = c22[2], c22[3]
    names = {i["code"] for i in S.build_spec("T", q, c)["items"]}
    assert not names & {"HIZ-01", "HIZ-04", "CEV-01", "PEN-04"} and {"BET-01", "DON-01", "PEN-03"} <= names


# ---------------------------------------------------------------- eski kayıtlar
def test_legacy_window_variant_migrates(c22):
    q = c22[2]
    legacy = costing.estimate(q, adjust={"variants": {"PEN-01": "alu_triple"}})
    new = costing.estimate(q, adjust={"variants": {"PEN-01": "alu", "PEN-03": "uclu_cam"}})
    assert legacy["subtotal"] == pytest.approx(new["subtotal"])
    assert costing.validate_adjust({"variants": {"PEN-01": "alu_triple"}})["variants"] == {"PEN-01": "alu", "PEN-03": "uclu_cam"}
    with pytest.raises(ValueError):
        costing.validate_adjust({"variants": {"PEN-01": "bambu"}})


def test_catalog_total_is_anchored_to_approx_unit_cost(c22):
    c = c22[3]
    anchor = c["approx"]["classes"]["IV-A"]
    assert anchor * 0.85 <= c["per_m2_before_vat"] <= anchor * 1.15
