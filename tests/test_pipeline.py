import json
from pathlib import Path

import pytest

from archai import costing, quantities as Q
from archai.dxf_import import import_dxf

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def imported(test_dxf):
    # plan conftest'te geçici dizine üretilir (ARCHAI_REF_OUT) — references/ değişmez
    els, rep = import_dxf(test_dxf, floors=1, floor_height=3.0, slab_thickness=0.2, add_roof=False)
    return els, rep


def test_import_matches_truth(imported):
    els, rep = imported
    truth = json.loads((ROOT / "references" / "test_plan_2+1.truth.json").read_text())
    a, b = Q.compute(els)["summary"], Q.compute(truth)["summary"]
    for k in ("gross_floor_area", "net_room_area", "wall_length", "wall_net_area", "wall_volume",
              "window_count", "window_area", "door_count", "door_area"):
        assert a[k] == pytest.approx(b[k], abs=0.01), k
    assert rep["walls"] == 7 and rep["openings"] == 13 and rep["rooms"] == 5


def test_room_names_and_areas(imported):
    rooms = {r["name"].split("/")[-1]: r["area"] for r in Q.compute(imported[0])["rooms"]}
    assert rooms["Salon"] == pytest.approx((7 - 0.125 - 0.05) * (5 - 0.125 - 0.05), abs=0.01)
    assert set(rooms) == {"Salon", "Mutfak", "Yatak Odası 1", "Banyo", "Yatak Odası 2"}


def test_multi_floor_scales(imported, test_dxf):
    els3, _ = import_dxf(test_dxf, floors=3, floor_height=3.0, add_roof=True)
    s1, s3 = Q.compute(imported[0])["summary"], Q.compute(els3)["summary"]
    assert s3["gross_floor_area"] == pytest.approx(3 * s1["gross_floor_area"], abs=0.01)
    assert s3["window_count"] == 3 * s1["window_count"]
    assert s3["roof_area"] == pytest.approx(s1["gross_floor_area"], abs=0.01)
    assert s3["levels"] == ["Kat 0", "Kat 1", "Kat 2", "Çatı"]


def test_cost_adjustments(imported):
    q = Q.compute(imported[0])
    base = costing.estimate(q)
    assert base["total"] > 0 and base["per_m2"] > 0
    row = next(r for r in base["rows"] if r["code"] == "ZEM-01")
    wet = sum(l["metrics"]["area"] for l in q["lines"] if l["type"] == "room" and l["wet"] in ("bath", "wc", "balcony"))
    assert row["quantity"] == pytest.approx(q["summary"]["net_room_area"] - wet, abs=0.01)   # banyo/WC/balkon ayrı kalem
    # varyant: seramik > laminat
    cer = costing.estimate(q, adjust={"variants": {"ZEM-01": "seramik"}})
    assert cer["subtotal"] - base["subtotal"] == pytest.approx(row["quantity"] * (1350 - 950), abs=1)
    # override + kapatma + ek kalem + oran
    adj = costing.estimate(q, adjust={"overrides": {"KAP-01": 20000}, "disabled": ["HAV-01", "PEY-01"],
                                      "extra_items": [{"name": "Proje çizimi", "quantity": 1, "unit_price": 50000}],
                                      "vat_pct": 10})
    kap = next(r for r in adj["rows"] if r["code"] == "KAP-01")
    assert kap["amount"] == pytest.approx(kap["quantity"] * 20000)
    assert adj["vat"] == pytest.approx(adj["total_before_vat"] * 0.10, abs=0.1)
    assert any(r["name"] == "Proje çizimi" for r in adj["rows"])
