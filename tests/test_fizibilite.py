import copy

import pytest
from fastapi.testclient import TestClient

from archai import approval, fizibilite, quantities
from webapp.app import app

INPUT = {"arsa_bedeli_tl": 500, "satis_m2_fiyati_tl": 20,
         "satilabilir_alan_m2": 100, "ek_gider_pct": 10}


@pytest.fixture
def record():
    return {"cost": {"total": 1000}, "brief": {},
            "quantities_fp": approval.quantities_fp(quantities.compute([]))}


def test_finance_formulas_and_source(record):
    before = copy.deepcopy(record)
    result = fizibilite.compute(record, [], **INPUT)
    assert result["sonuc"] == {
        "insaat_bedeli_tl": 1000, "ek_gider_tl": 100, "toplam_gider_tl": 1600,
        "satis_geliri_tl": 2000, "tahmini_kar_tl": 400, "kar_marji_pct": 20,
        "maliyet_getirisi_pct": 25, "basabas_m2_fiyati_tl": 16}
    assert result["kaynak"]["maliyet_alani"] == "cost.total"
    assert len(result["kaynak"]["proje_parmak_izi"]) == 64
    assert record == before


def test_loss_and_break_even(record):
    loss = fizibilite.compute(record, [], **{**INPUT, "satis_m2_fiyati_tl": 10})
    assert loss["sonuc"]["tahmini_kar_tl"] == -600
    balanced = fizibilite.compute(record, [], **{**INPUT, "satis_m2_fiyati_tl": 16})
    assert balanced["sonuc"]["tahmini_kar_tl"] == 0


@pytest.mark.parametrize("field,value", [
    ("arsa_bedeli_tl", -1), ("satis_m2_fiyati_tl", 0), ("satilabilir_alan_m2", 0),
    ("ek_gider_pct", 101), ("ek_gider_pct", float("nan")),
    ("satis_m2_fiyati_tl", float("inf")), ("arsa_bedeli_tl", True),
    ("satilabilir_alan_m2", 1e-300), ("satis_m2_fiyati_tl", 1e10),
])
def test_invalid_assumptions(record, field, value):
    with pytest.raises(ValueError):
        fizibilite.compute(record, [], **{**INPUT, field: value})


@pytest.mark.parametrize("legacy", [False, True])
def test_unverified_quantities_rejected(record, legacy):
    record["quantities_fp"] = None if legacy else "stale"
    with pytest.raises(approval.QuantitiesMismatchError):
        fizibilite.compute(record, [], **INPUT)


def test_saved_price_change_updates_source(record):
    a = fizibilite.compute(record, [], **INPUT)
    record["cost"]["total"] = 2000
    b = fizibilite.compute(record, [], **INPUT)
    assert a["kaynak"]["proje_parmak_izi"] != b["kaynak"]["proje_parmak_izi"]
    assert b["sonuc"]["toplam_gider_tl"] == 2700


@pytest.fixture
def client(monkeypatch, tmp_path, record):
    from webapp import araclar_routes as routes
    monkeypatch.setattr(routes, "_load", lambda pid: (tmp_path, record, []))
    return TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))


def test_finance_api(client, record):
    response = client.post("/api/projects/test/fizibilite", json=INPUT)
    assert response.status_code == 200, response.text
    assert response.json()["sonuc"]["tahmini_kar_tl"] == 400
    record.pop("quantities_fp")
    response = client.post("/api/projects/test/fizibilite", json=INPUT)
    assert response.status_code == 409
    assert "ONAY" in response.json()["detail"]


@pytest.mark.parametrize("change", [{"satilabilir_alan_m2": 0}, {"arsa_bedeli_tl": True},
                                    {"ek_gider_pct": 101}, {"unexpected": 1}])
def test_api_validation(client, change):
    assert client.post("/api/projects/test/fizibilite", json={**INPUT, **change}).status_code == 422


def test_api_auth(client, monkeypatch):
    monkeypatch.setenv("ARCHAI_TOKEN", "finance-test-token")
    assert client.post("/api/projects/test/fizibilite", json=INPUT).status_code == 401
