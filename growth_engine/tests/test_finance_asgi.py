"""Exercise real core routes through HTTPX ASGI transport, without network calls."""
import asyncio
import importlib
import json

import httpx
import pytest

from archai import approval, fizibilite, quantities
from growth_engine import server

PID = "20261103-120000-finance"
INPUT = dict(arsa_bedeli_tl=500, satis_m2_fiyati_tl=20,
             satilabilir_alan_m2=800, ek_gider_pct=10)


@pytest.fixture
def core(monkeypatch, tmp_path):
    web = importlib.import_module("webapp.app")
    monkeypatch.setattr(web, "PROJECTS", tmp_path)
    monkeypatch.setenv("ARCHAI_TOKEN", "test-core-api-token")
    record = {
        "name": "Offline finance fixture", "files": {}, "brief": {},
        "cost": {"total": 1000},
        "summary": {"gross_floor_area": 1000},
        "rooms": [{"name": "Kat 1/Daire 1/Hol", "area": 40},
                  {"name": "Kat 1/Daire 2/Hol", "area": 40},
                  {"name": "Ortak hol", "area": 20}],
        "quantities_fp": approval.quantities_fp(quantities.compute([])),
    }
    directory = tmp_path / PID
    directory.mkdir()
    (directory / "elements.json").write_text("[]")
    path = directory / "project.json"
    path.write_text(json.dumps(record))
    client_class = httpx.AsyncClient
    transport = httpx.ASGITransport(app=web.app, client=("127.0.0.1", 50000))
    monkeypatch.setattr(server.httpx, "AsyncClient", lambda **kwargs: client_class(
        transport=transport, **kwargs))
    return record, path


@pytest.mark.parametrize("explicit", [False, True])
def test_profit_matches_actual_core_calculation(core, explicit):
    record, _ = core
    expected = fizibilite.compute(record, [], **INPUT)
    result = asyncio.run(server.karlilik(
        PID, 500, 20, 10, satilabilir_alan_m2=800 if explicit else None))
    assert result["uyarilar"] == expected["uyarilar"]
    assert result["kar_tl"] == expected["sonuc"]["tahmini_kar_tl"]
    assert result["toplam_yatirim_tl"] == expected["sonuc"]["toplam_gider_tl"]
    assert result["satilabilir_brut_m2"] == 800
    assert result["_kaynak"]["core_fingerprint"] == expected["kaynak"]["proje_parmak_izi"]


def test_land_share_uses_real_routes(core):
    result = asyncio.run(server.kat_karsiligi(PID, 20, 50, 20, 10))
    assert result["daire_sayisi"] == 2
    assert result["_kaynak"]["core_fingerprint"]


@pytest.mark.parametrize("explicit", [False, True])
def test_core_rejects_stale_quantities(core, explicit):
    record, path = core
    record["quantities_fp"] = "stale"
    path.write_text(json.dumps(record))
    with pytest.raises(ValueError, match="Metraj"):
        asyncio.run(server.karlilik(PID, 500, 20, 10,
                    satilabilir_alan_m2=800 if explicit else None))
    assert not server.KAYIT.exists()


@pytest.mark.parametrize("explicit", [False, True])
def test_core_rejects_wrong_token(core, monkeypatch, explicit):
    monkeypatch.setattr(server, "ARCHAI_TOKEN", "wrong-token")
    with pytest.raises(ValueError, match="401|yetkisiz"):
        asyncio.run(server.karlilik(PID, 500, 20, 10,
                    satilabilir_alan_m2=800 if explicit else None))
    assert not server.KAYIT.exists()


def test_exact_target_margin_allows_zero_landowner_units(core):
    # 800 × 1.71875 = 1375 revenue; 1100 cost yields exactly 20% margin.
    result = asyncio.run(server.kat_karsiligi(PID, 1.71875, 0, 20, 10))
    assert result["onerilen"]["arsa_sahibi_daire"] == 0
    assert result["onerilen"]["muteahhit_marj_pct"] == 20
    assert result["uyari"] is None


@pytest.mark.parametrize("field", ["arsa_sahibi_payi_pct", "hedef_marj_pct"])
@pytest.mark.parametrize("value", [-1, 101, float("inf"), float("nan"), True])
def test_invalid_shares_rejected_before_http(core, monkeypatch, field, value):
    def unexpected_request(**kwargs):
        pytest.fail("Invalid shares must be rejected before HTTP")
    monkeypatch.setattr(server.httpx, "AsyncClient", unexpected_request)
    with pytest.raises(ValueError, match=field):
        asyncio.run(server.kat_karsiligi(PID, 20, **{field: value}))
    assert not server.KAYIT.exists()


def test_updated_saved_cost_changes_profit_and_source(core):
    record, path = core
    before = asyncio.run(server.karlilik(PID, 500, 20, 10))
    record["cost"]["total"] = 2000
    path.write_text(json.dumps(record))
    after = asyncio.run(server.karlilik(PID, 500, 20, 10))
    assert after["toplam_yatirim_tl"] == 2700
    assert after["kar_tl"] == before["kar_tl"] - 1100
    assert after["_kaynak"]["core_fingerprint"] != before["_kaynak"]["core_fingerprint"]
    saved = json.loads(server.KAYIT.read_text())
    assert saved[PID]["karlilik"] == after


def test_unreachable_land_share_margin_returns_no_recommendation(core):
    result = asyncio.run(server.kat_karsiligi(PID, 1, 50, 20, 10))
    assert result["onerilen"] is None
    assert result["uyari"]
    assert result["istenen_pay"]["muteahhit_kar_tl"] < 0


def test_core_validates_explicit_area(core):
    with pytest.raises(ValueError, match="Geçersiz girdi"):
        asyncio.run(server.karlilik(PID, 500, 20, 10, satilabilir_alan_m2=0))
    assert not server.KAYIT.exists()
