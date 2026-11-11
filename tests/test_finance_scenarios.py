import copy
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient

from archai import approval, finance_scenarios as scenarios, fizibilite, quantities
from webapp.app import app

INPUT = {"arsa_bedeli_tl": 500, "satis_m2_fiyati_tl": 20,
         "satilabilir_alan_m2": 100, "ek_gider_pct": 10}


@pytest.fixture
def record():
    return {"cost": {"total": 1000}, "brief": {},
            "quantities_fp": approval.quantities_fp(quantities.compute([]))}


def test_immutable_snapshots_and_freshness(tmp_path, record):
    result = fizibilite.compute(record, [], **INPUT)
    before = copy.deepcopy(result)
    assert scenarios.list_saved(tmp_path, record, [])["senaryolar"] == []
    assert not (tmp_path / scenarios.DB_NAME).exists()
    a = scenarios.save(tmp_path, "Temkinli", result)
    b = scenarios.save(tmp_path, "İyimser", fizibilite.compute(record, [], **{**INPUT, "satis_m2_fiyati_tl": 30}))
    assert a["id"] != b["id"]
    rows = scenarios.list_saved(tmp_path, record, [])["senaryolar"]
    assert [r["ad"] for r in rows] == ["İyimser", "Temkinli"]
    assert all(r["guncel"] for r in rows)
    record["cost"]["total"] = 2000
    rows = scenarios.list_saved(tmp_path, record, [])["senaryolar"]
    assert not any(r["guncel"] for r in rows)
    assert rows[1]["hesap"] == before
    record["cost"]["total"] = 1000
    record.pop("quantities_fp")
    assert not scenarios.list_saved(tmp_path, record, [])["senaryolar"][0]["guncel"]


@pytest.mark.parametrize("name", ["", "   ", "x" * 81, "hello\nworld"])
def test_invalid_names(tmp_path, record, name):
    with pytest.raises(ValueError):
        scenarios.save(tmp_path, name, fizibilite.compute(record, [], **INPUT))
    assert not (tmp_path / scenarios.DB_NAME).exists()


def test_limit_is_atomic_across_writers(tmp_path, record, monkeypatch):
    monkeypatch.setattr(scenarios, "LIMIT", 2)
    result = fizibilite.compute(record, [], **INPUT)

    def save(i):
        try:
            scenarios.save(tmp_path, f"Senaryo {i}", result)
            return True
        except ValueError:
            return False

    with ThreadPoolExecutor(max_workers=4) as pool:
        assert sum(pool.map(save, range(6))) == 2
    assert len(scenarios.list_saved(tmp_path, record, [])["senaryolar"]) == 2


@pytest.fixture
def client(monkeypatch, tmp_path, record):
    from webapp import araclar_routes as routes
    monkeypatch.setattr(routes, "_load", lambda pid: (tmp_path, record, []))
    return TestClient(app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))


def test_save_recomputes_server_side_and_detects_changed_project(client, record):
    url = "/api/projects/test/fizibilite"
    calculation = client.post(url, json=INPUT).json()
    payload = {**INPUT, "ad": "Temel", "proje_parmak_izi": calculation["kaynak"]["proje_parmak_izi"]}
    assert client.post(url + "/senaryolar", json={**payload, "sonuc": {"tahmini_kar_tl": 99999}}).status_code == 422
    saved = client.post(url + "/senaryolar", json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["senaryo"]["hesap"]["sonuc"]["tahmini_kar_tl"] == 400
    record["cost"]["total"] = 2000
    assert client.post(url + "/senaryolar", json=payload).status_code == 409
    rows = client.get(url + "/senaryolar").json()["senaryolar"]
    assert len(rows) == 1 and not rows[0]["guncel"]
    assert rows[0]["hesap"]["sonuc"]["tahmini_kar_tl"] == 400


def test_stale_quantities_cannot_be_saved(client, record):
    payload = {**INPUT, "ad": "Eski", "proje_parmak_izi": "a" * 64}
    record.pop("quantities_fp")
    assert client.post("/api/projects/test/fizibilite/senaryolar", json=payload).status_code == 409
    assert client.get("/api/projects/test/fizibilite/senaryolar").json()["senaryolar"] == []


def test_export_and_delete_scenario(client, record):
    url = "/api/projects/test/fizibilite/senaryolar"
    calculation = client.post("/api/projects/test/fizibilite", json=INPUT).json()
    saved = client.post(url, json={**INPUT, "ad": "Temel",
                                   "proje_parmak_izi": calculation["kaynak"]["proje_parmak_izi"]}).json()["senaryo"]
    item = f"{url}/{saved['id']}"
    exported = client.get(item + "/export")
    assert exported.status_code == 200
    assert exported.headers["content-disposition"] == f'attachment; filename="fizibilite-{saved["id"]}.json"'
    assert exported.json()["hesap"] == saved["hesap"]
    assert exported.json()["guncel"] is True

    record["cost"]["total"] = 2000
    stale_export = client.get(item + "/export")
    assert stale_export.json()["hesap"] == saved["hesap"]
    assert stale_export.json()["guncel"] is False
    assert client.delete(item).json() == {"ok": True, "id": saved["id"]}
    assert client.get(item + "/export").status_code == 404
    assert client.delete(item).status_code == 404
    assert client.get(url).json()["senaryolar"] == []


def test_export_and_delete_missing_scenario_do_not_create_database(client, tmp_path):
    url = "/api/projects/test/fizibilite/senaryolar/" + "a" * 32
    assert client.get(url + "/export").status_code == 404
    assert client.delete(url).status_code == 404
    assert not (tmp_path / scenarios.DB_NAME).exists()
    assert client.get(url + "bad/export").status_code == 404


def test_scenarios_authentication(client, monkeypatch):
    monkeypatch.setenv("ARCHAI_TOKEN", "scenario-test-token")
    url = "/api/projects/test/fizibilite/senaryolar"
    assert client.get(url).status_code == 401
    assert client.post(url, json=INPUT).status_code == 401
    assert client.get(url + "/" + "a" * 32 + "/export").status_code == 401
    assert client.delete(url + "/" + "a" * 32).status_code == 401
