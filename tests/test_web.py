from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from webapp.app import app

ROOT = Path(__file__).resolve().parents[1]
# yerel istemci: token yokken yalnız loopback'e izin verilir (erişim koruması)
LOCAL = dict(base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
c = TestClient(app, **LOCAL)


def test_quick_project_and_adjust():
    r = c.post("/api/projects", json={"name": "api test", "quick": {"gross_area": 450, "floors": 3, "unit_type": "2+1"}})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["cost"]["total"] > 0 and len(p["sheets"]) >= 4
    for key in ("teklif_docx", "metraj_maliyet_xlsx", "sartname_docx", "cizim_pdf"):
        assert c.get(p["files"][key]).status_code == 200, key
    r2 = c.put(f"/api/projects/{p['id']}/adjust", json={"variants": {"ZEM-01": "traverten"}, "vat_pct": 10})
    assert r2.status_code == 200 and r2.json()["cost"]["vat_pct"] == 10
    assert r2.json()["cost"]["total"] != p["cost"]["total"]


def test_optional_items_toggle_through_api():
    """Opsiyonel / teklif dışı kalemler `enabled` ile açılır, `disabled` listesine alınınca kapanır; belgelerde görünür."""
    p = c.post("/api/projects", json={"name": "opsiyon", "quick": {"gross_area": 450, "floors": 3, "unit_type": "2+1"}}).json()
    u = f"/api/projects/{p['id']}/adjust"
    row = lambda pr, code: next(x for x in pr["cost"]["rows"] if x["code"] == code)
    assert row(p, "HIZ-04")["default_enabled"] is False and not row(p, "HIZ-04")["enabled"]
    on = c.put(u, json={"enabled": ["HIZ-04"]}).json()
    assert row(on, "HIZ-04")["enabled"] and row(on, "HIZ-04")["amount"] > 0 and on["cost"]["total"] > p["cost"]["total"]
    assert on["brief"]["adjust"]["enabled"] == ["HIZ-04"]
    off = c.put(u, json={"disabled": ["HIZ-04"]}).json()                 # arayüz kapatınca enabled'ı da boşaltır
    assert not row(off, "HIZ-04")["enabled"] and off["cost"]["total"] == p["cost"]["total"]


def test_dxf_upload(test_dxf):
    with open(test_dxf, "rb") as f:
        r = c.post("/api/projects/dxf", files={"file": ("plan.dxf", f)}, data={"name": "dxf api", "floors": "2"})
    assert r.status_code == 200, r.text
    assert r.json()["report"]["walls"] == 7


def test_bad_input_and_path_traversal():
    assert c.post("/api/projects", json={"name": "x"}).status_code == 422
    r = c.post("/api/projects", json={"name": "x", "parcel": {"width": 10, "depth": 10},
                                      "zoning": {"taks": 0.4, "kaks": 1, "front": 5, "side": 3, "rear": 3}})
    assert r.status_code == 422  # çekmelerden sonra alan yok
    assert c.get("/files/../../pyproject.toml").status_code == 404


def test_interior_roundtrip():
    r = c.post("/api/projects", json={"name": "ic mekan", "quick": {"gross_area": 300, "floors": 2, "unit_type": "2+1"}})
    pid = r.json()["id"]
    assert c.get(f"/api/projects/{pid}/interior").json() == {"floors": {}, "paint": "kirik_beyaz", "objects": []}
    design = {"floors": {"Zemin Kat/Daire A/Salon": "marble_tiles"}, "paint": "bej",
              "objects": [{"id": "a1", "kind": "klozet", "level": "Zemin Kat", "x": 1.5, "y": 2.0, "rot": 1.57, "evil": "x"}]}
    assert c.put(f"/api/projects/{pid}/interior", json=design).json()["objects"] == 1
    got = c.get(f"/api/projects/{pid}/interior").json()
    assert got["floors"]["Zemin Kat/Daire A/Salon"] == "marble_tiles" and got["paint"] == "bej"
    assert "evil" not in got["objects"][0]  # yalnız izinli alanlar saklanır
    assert c.put("/api/projects/yok/interior", json=design).status_code == 404
    assert c.put(f"/api/projects/{pid}/interior", json={"objects": "x"}).status_code == 422


def test_cabin_endpoint():
    r = c.post("/api/projects/cabin", json={})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["name"] == "Dağ Evi Demo" and p["report"]["floors"] == 2 and len(p["sheets"]) >= 4
    inter = c.get(f"/api/projects/{p['id']}/interior").json()
    assert len(inter["objects"]) > 15 and inter["floors"]


def test_apartment_endpoint():
    r = c.post("/api/projects/apartment", json={})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["name"] == "Apartman Katı" and p["report"]["unit_count"] == 3 and len(p["sheets"]) >= 4
    inter = c.get(f"/api/projects/{p['id']}/interior").json()
    assert len(inter["objects"]) == 72
    # parametrik ölçüler kaydetme sonrası korunur, tür dışı değerler atılır
    inter["objects"][0].update(w=2.6, kitap=True, side="x", orta=1, decor=True)
    assert c.put(f"/api/projects/{p['id']}/interior", json=inter).status_code == 200
    o = c.get(f"/api/projects/{p['id']}/interior").json()["objects"][0]
    assert o["w"] == 2.6 and o["kitap"] is True and o["decor"] is True and "side" not in o and "orta" not in o


def test_villa_endpoint():
    r = c.post("/api/projects/villa", json={})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["name"] == "Villa Demo" and p["report"]["floors"] == 2 and len(p["sheets"]) >= 4
    inter = c.get(f"/api/projects/{p['id']}/interior").json()
    assert len(inter["objects"]) > 50 and inter["floors"]
    assert any(r["code"] == "HAV-01" and r["quantity"] > 0 for r in p["cost"]["rows"])  # havuz maliyete girdi


@pytest.mark.skipif(not (ROOT / "tests/data/plan_3daire.jpg").exists(), reason="test planı görseli yerelde yok")
def test_image_plan_upload():
    with open("tests/data/plan_3daire.jpg", "rb") as f:
        r = c.post("/api/projects/dxf", files={"file": ("plan.jpg", f, "image/jpeg")}, data={"name": "Resim Plan"})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["report"]["source"] == "image" and p["files"]["tanima_onay_png"].endswith("tanima_onay.png")
    assert c.get(p["files"]["tanima_onay_png"]).status_code == 200
    bad = c.post("/api/projects/dxf", files={"file": ("plan.pdf", b"%PDF", "application/pdf")}, data={"name": "x"})
    assert bad.status_code == 422


# ================================================================== güvenlik / doğrulama / kuyruk
import json  # noqa: E402
import time  # noqa: E402

import webapp.app as W  # noqa: E402
from archai import project as PRJ  # noqa: E402

QUICK = {"gross_area": 300, "floors": 2, "unit_type": "2+1"}


def _dirs():
    return {p.name for p in W.PROJECTS.iterdir()}


@pytest.fixture(scope="module")
def pid():
    r = c.post("/api/projects", json={"name": "guvenlik", "quick": QUICK})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def test_remote_without_token_is_refused():
    remote = TestClient(app, base_url="http://127.0.0.1:8000")  # istemci adresi "testclient" (uzak)
    for url in ("/", "/api/projects", "/index.html"):
        r = remote.get(url)
        assert r.status_code == 403 and "ARCHAI_TOKEN" in r.json()["detail"], url
    assert c.get("/").status_code == 200  # loopback: arayüz açılır


def test_host_allow_list(monkeypatch):
    assert c.get("/api/projects", headers={"host": "evil.example.com"}).status_code == 400
    assert c.get("/api/projects", headers={"host": "localhost:8000"}).status_code == 200
    assert c.get("/api/projects", headers={"host": "[::1]:8000"}).status_code == 200
    assert c.get("/api/projects", headers={"host": "192.168.1.20:8000"}).status_code == 200  # IP literal: rebinding yok
    assert c.get("/api/projects", headers={"host": "archai.lan"}).status_code == 400
    monkeypatch.setenv("ARCHAI_ALLOWED_HOSTS", "ofis.local, archai.lan")
    assert c.get("/api/projects", headers={"host": "archai.lan:8000"}).status_code == 200


def test_origin_must_match_host_on_writes():
    body = {"architect": "Y. Mimar"}
    assert c.put("/api/settings", json=body, headers={"origin": "http://evil.example.com"}).status_code == 403
    assert c.put("/api/settings", json=body, headers={"origin": "null"}).status_code == 403
    assert c.put("/api/settings", json=body, headers={"origin": "http://127.0.0.1:8000"}).status_code == 200
    assert c.get("/api/settings", headers={"origin": "http://evil.example.com"}).status_code == 200  # GET etkilenmez


def test_token_modes(monkeypatch):
    monkeypatch.setenv("ARCHAI_TOKEN", "s3cr3t-anahtar")
    remote = TestClient(app, base_url="http://192.168.1.20:8000")
    assert remote.get("/api/projects").status_code == 401
    assert c.get("/api/projects").status_code == 401  # token ayarlıysa loopback da token ister
    assert remote.get("/api/projects", headers={"authorization": "Bearer yanlis"}).status_code == 401
    assert remote.get("/api/projects", headers={"authorization": "Bearer s3cr3t-anahtar"}).status_code == 200
    assert remote.get("/api/projects", headers={"x-archai-token": "s3cr3t-anahtar"}).status_code == 200
    r = remote.get("/?token=s3cr3t-anahtar&x=1", headers={"accept": "text/html"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/?x=1"        # anahtar adresten atılır
    assert r.headers["referrer-policy"] == "no-referrer"
    remote.cookies.clear()
    api = remote.get("/api/projects?token=s3cr3t-anahtar")                  # sayfa dışı istek yönlendirilmez
    assert api.status_code == 200 and "archai_token" in api.headers.get("set-cookie", "")
    remote.cookies.clear()
    r = remote.get("/?token=s3cr3t-anahtar", headers={"accept": "text/html"})   # yönlendirme izlenir → sayfa açılır
    assert r.status_code == 200 and "<html" in r.text.lower()
    sc = r.history[0].headers["set-cookie"].lower()
    assert "archai_token=s3cr3t-anahtar" in sc and "httponly" in sc and "samesite=strict" in sc
    assert remote.get("/api/projects").status_code == 200  # çerezle sonraki istekler
    fresh = TestClient(app, base_url="http://192.168.1.20:8000", cookies={"archai_token": "yanlis"})
    assert fresh.get("/api/projects").status_code == 401


def test_pid_validation_everywhere(pid):
    bad = ["..", "%2e%2e", "%2E%2E", "yok", "20260101-000000-X", "20260101-000000-a%2f..", pid + "%00"]
    for b in bad:
        for method, url, kw in [("get", f"/api/projects/{b}", {}), ("get", f"/api/projects/{b}/elements", {}),
                                ("get", f"/api/projects/{b}/interior", {}), ("put", f"/api/projects/{b}/interior", {"json": {}}),
                                ("put", f"/api/projects/{b}/adjust", {"json": {}}), ("post", f"/api/projects/{b}/render", {}),
                                ("get", f"/api/projects/{b}/real", {}), ("get", f"/files/{b}/project.json", {})]:
            r = getattr(c, method)(url, **kw)
            # düz ".." istemcide normalize edilir (başka bir yola gider): orada da proje verisine ulaşılamaz
            assert r.status_code in ((404, 405) if b == ".." or "%2f" in b else (404,)), (method, url, r.status_code)
    # geçerli biçim ama olmayan proje
    assert c.get("/api/projects/20260101-000000-yok-0000").status_code == 404
    assert c.get(f"/files/{pid}/%2e%2e/%2e%2e/pyproject.toml").status_code == 404
    assert c.get(f"/files/{pid}/project.json").status_code == 200


def _detail(r):
    d = r.json()["detail"]
    assert isinstance(d, str), d  # arayüz tek satırlık mesaj gösterir
    return d


def test_brief_schema():
    land = {"parcel": {"width": 20, "depth": 30}, "zoning": {"taks": 0.4, "kaks": 1.2}}
    cases = [
        ({"parcel": {"width": 2, "depth": 30}, "zoning": {"taks": 0.4}}, "parcel.width"),
        ({"parcel": {"width": 20, "depth": 501}, "zoning": {"taks": 0.4}}, "parcel.depth"),
        ({"parcel": {"width": "20", "depth": 30}, "zoning": {"taks": 0.4}}, "parcel.width"),  # metin sayı reddedilir
        ({**land, "zoning": {"taks": 1.5}}, "zoning.taks"),
        ({**land, "zoning": {"taks": 0}}, "zoning.taks"),
        ({**land, "zoning": {"kaks": 11}}, "zoning.kaks"),
        ({**land, "zoning": {"front": -1}}, "zoning.front"),
        ({**land, "zoning": {"max_floors": 31}}, "zoning.max_floors"),
        ({**land, "zoning": {"floor_height": 1.5}}, "zoning.floor_height"),
        ({"quick": {"gross_area": 10, "floors": 2}}, "quick.gross_area"),
        ({"quick": {"gross_area": 300, "floors": 31}}, "quick.floors"),
        ({"quick": {"gross_area": 300, "floors": 2.5}}, "quick.floors"),
        ({"quick": {"gross_area": 300, "floors": 2, "floor_height": 9}}, "quick.floor_height"),
        ({"quick": {"gross_area": 300}}, "quick.floors"),
        ({"quick": QUICK, "adjust": {"vat_pct": 150}}, "adjust.vat_pct"),
        ({"quick": QUICK, "name": 5}, "name"),
    ]
    for body, where in cases:
        r = c.post("/api/projects", json=body)
        assert r.status_code == 422, (body, r.text)
        assert where in _detail(r), (where, r.text)
    assert "zorunlu" in _detail(c.post("/api/projects", json={"quick": {"gross_area": 300}}))


def test_adjust_schema(pid):
    u = f"/api/projects/{pid}/adjust"
    for body in [{"overrides": {"KAP-01": "20000"}}, {"overrides": {"KAP-01": -1}}, {"vat_pct": 101},
                 {"overhead_pct": -5}, {"bilinmeyen": 1}, {"disabled": "HAV-01"},
                 {"extra_items": [{"name": "x" * 81, "quantity": 1, "unit_price": 1}]},
                 {"extra_items": [{"name": "Kalem", "quantity": -1, "unit_price": 1}]},
                 {"extra_items": [{"name": "Kalem", "quantity": 1}]},
                 {"extra_items": [{"name": "Kalem", "quantity": 1, "unit_price": 1}] * 201}]:
        r = c.put(u, json=body)
        assert r.status_code == 422, (body, r.text)
        _detail(r)
    r = c.put(u, json={"kdv_pct": 10, "disabled": ["HAV-01", "PEY-01"], "enabled": ["PEY-01"],
                       "extra_items": [{"name": "Proje çizimi", "quantity": 1, "unit_price": 5000}]})
    assert r.status_code == 200, r.text
    p = r.json()
    assert p["cost"]["vat_pct"] == 10 and p["brief"]["adjust"]["disabled"] == ["HAV-01"]
    assert any(x["name"] == "Proje çizimi" for x in p["cost"]["rows"])


def test_internal_error_does_not_leak(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("gizli-ayrinti /home/kullanici/sir")
    monkeypatch.setattr(PRJ, "run", boom)
    before = _dirs()
    safe = TestClient(app, raise_server_exceptions=False, **LOCAL)
    r = safe.post("/api/projects", json={"name": "patlak", "quick": QUICK})
    assert r.status_code == 500 and r.json() == {"detail": "iç hata"} and "gizli" not in r.text
    assert _dirs() == before  # yarım proje klasörü kalmaz


def test_value_error_is_422_and_cleans_up(monkeypatch):
    before = _dirs()
    r = c.post("/api/projects", json={"name": "x", "parcel": {"width": 10, "depth": 10},
                                      "zoning": {"taks": 0.4, "kaks": 1, "front": 5, "side": 3, "rear": 3}})
    assert r.status_code == 422 and _dirs() == before


def test_name_sanitized():
    r = c.post("/api/projects", json={"name": "Ev\x00\x1b[31m‮Adı " + "x" * 200, "quick": QUICK})
    assert r.status_code == 200, r.text
    n = r.json()["name"]
    assert len(n) <= 80 and n.startswith("Ev[31mAdı") and not any(ord(ch) < 32 or 0x202A <= ord(ch) <= 0x202E for ch in n)


def test_upload_limits_and_meta(monkeypatch, test_dxf):
    data = test_dxf.read_bytes()
    before = _dirs()
    # meta dosya yazılmadan önce doğrulanır, klasör açılmaz
    for meta in ("{bozuk", "[]", '{"px_per_m": "12"}', '{"vision": "evet"}', '{"company": "metin"}'):
        r = c.post("/api/projects/dxf", files={"file": ("plan.dxf", data)}, data={"name": "m", "meta": meta})
        assert r.status_code == 422, (meta, r.text)
        assert "meta" in _detail(r)
    assert c.post("/api/projects/dxf", files={"file": ("plan.dxf", data)}, data={"floors": "99"}).status_code == 422
    assert c.post("/api/projects/dxf", files={"file": ("plan.dxf", b"")}).status_code == 422
    # boyut sınırı (akışta sayılır)
    monkeypatch.setattr(W, "MAX_PLAN_BYTES", 1000)
    r = c.post("/api/projects/dxf", files={"file": ("plan.dxf", data)}, data={"name": "buyuk"})
    assert r.status_code == 413 and "MB" in _detail(r)
    monkeypatch.setattr(W, "MAX_PLAN_BYTES", 25 * W.MB)
    # bozuk DXF: hata döner, proje klasörü kalmaz
    safe = TestClient(app, raise_server_exceptions=False, **LOCAL)
    r = safe.post("/api/projects/dxf", files={"file": ("plan.dxf", b"bu bir dxf degil\n" * 50)}, data={"name": "bozuk"})
    assert r.status_code in (422, 500) and "Traceback" not in r.text
    assert _dirs() == before


def test_vision_flag_contract(monkeypatch):
    seen = []

    def fake_run_image(src, brief, d, render_3d=False):
        seen.append(brief["image"])
        raise ValueError("test: durdur")
    monkeypatch.setattr(PRJ, "run_image", fake_run_image)
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    before = _dirs()
    for meta, want in (("{}", False), ('{"vision": true, "px_per_m": 50}', True), ('{"vision": false}', False)):
        r = c.post("/api/projects/dxf", files={"file": ("plan.png", png, "image/png")}, data={"meta": meta})
        assert r.status_code == 422
        assert seen[-1]["vision"] is want
    assert seen[1]["px_per_m"] == 50
    assert _dirs() == before


def test_archive_skips_corrupt_records():
    good = c.post("/api/projects", json={"name": "saglam", "quick": QUICK}).json()["id"]
    bad1, bad2 = W.PROJECTS / "20200101-000000-bozuk-json", W.PROJECTS / "20200101-000001-eksik-alan"
    bad1.mkdir()
    (bad1 / "project.json").write_text("{bozuk")
    bad2.mkdir()
    (bad2 / "project.json").write_text(json.dumps({"name": "eksik"}))
    try:
        r = c.get("/api/projects")
        assert r.status_code == 200
        ids = {p["id"] for p in r.json()}
        assert good in ids and bad1.name not in ids and bad2.name not in ids
        assert c.get(f"/api/projects/{bad1.name}").status_code == 422
        assert c.get(f"/api/projects/{bad2.name}").status_code == 422
    finally:
        import shutil
        shutil.rmtree(bad1)
        shutil.rmtree(bad2)


# ------------------------------------------------------------------ render kuyruğu (sahte Blender)
CAM = {"matrix": [1.0, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 1.6, 5, 1], "fov": 50, "aspect": 1.5}


def _fake_blender(tmp_path, body):
    s = tmp_path / "blender.sh"
    s.write_text("#!/bin/sh\nJD=$(dirname \"$6\")\n" + body)
    s.chmod(0o755)
    return str(s)


def _wait(jid, timeout=20):
    t0 = time.time()
    while time.time() - t0 < timeout:
        j = c.get(f"/api/jobs/{jid}").json()
        if j["status"] in ("done", "error"):
            return j
        time.sleep(0.1)
    raise AssertionError("iş bitmedi")


def _submit(pid, job, scene=b"glTF" + b"0" * 64):
    return c.post(f"/api/projects/{pid}/real", files={"scene": ("scene.glb", scene, "model/gltf-binary")},
                  data={"job": json.dumps(job)})


def test_real_job_validation(pid, monkeypatch):
    ok = {"kind": "still", "camera": CAM, "lights": []}
    for job in [{"kind": "still"}, {**ok, "kind": "video"}, {**ok, "camera": {**CAM, "matrix": [0] * 15}},
                {**ok, "camera": {**CAM, "fov": 200}}, {**ok, "camera": {**CAM, "aspect": 0}},
                {**ok, "lights": [{"pos": [0, 0, 0], "w": 1, "d": 1}] * 201}]:
        r = _submit(pid, job)
        assert r.status_code == 422, (job, r.text)
        assert "job" in _detail(r)
    assert c.post(f"/api/projects/{pid}/real", files={"scene": ("s.glb", b"x")}, data={"job": "{"}).status_code == 422
    monkeypatch.setattr(W, "MAX_SCENE_BYTES", 10)
    n = len(list((W.PROJECTS / pid).glob("real/*")))
    assert _submit(pid, ok).status_code == 413
    assert len(list((W.PROJECTS / pid).glob("real/*"))) == n  # iş klasörü kalmaz
    monkeypatch.setattr(W, "MAX_QUEUE", 0)
    monkeypatch.setattr(W, "MAX_SCENE_BYTES", 300 * W.MB)
    assert _submit(pid, ok).status_code == 429


def test_real_job_lifecycle(pid, tmp_path, monkeypatch):
    monkeypatch.setattr(W, "BLENDER", _fake_blender(tmp_path, 'echo "ARCHAI_PROGRESS 1 1 foto"\n'
                                                              'touch "$JD/foto.png"\necho "ARCHAI_RESULT $JD/foto.png"\n'))
    r = _submit(pid, {"kind": "still", "camera": CAM, "lights": [{"pos": [1, 2, 3], "w": 2, "d": 3}], "glb": "/etc/passwd"})
    assert r.status_code == 200, r.text
    jid = r.json()["id"]
    jd = W.PROJECTS / pid / "real" / jid
    assert json.loads((jd / "status.json").read_text())["status"] in ("queued", "running", "done")  # submit anında yazılır
    assert json.loads((jd / "job.json").read_text())["glb"] == str(jd / "scene.glb")  # istemci yolu ezilemez
    j = _wait(jid)
    assert j["status"] == "done" and j["urls"][0].endswith("/foto.png")
    assert c.get(j["urls"][0]).status_code == 200
    # bellekten düşse de diskten okunur
    W.JOBS.pop(jid)
    assert c.get(f"/api/jobs/{jid}").json()["status"] == "done"
    assert any(x["id"] == jid for x in c.get(f"/api/projects/{pid}/real").json())
    assert c.get("/api/jobs/still-000000-zzzz").status_code == 404
    assert c.get("/api/jobs/still-000000-..").status_code == 404
    assert "root:" not in c.get("/api/jobs/..%2f..%2f..%2f..%2fetc%2fpasswd").text


def test_real_job_timeout(pid, tmp_path, monkeypatch):
    monkeypatch.setattr(W, "BLENDER", _fake_blender(tmp_path, "exec sleep 30\n"))
    monkeypatch.setattr(W, "RENDER_TIMEOUT", 1)
    r = _submit(pid, {"kind": "still", "camera": CAM})
    assert r.status_code == 200, r.text
    j = _wait(r.json()["id"], timeout=15)
    assert j["status"] == "error" and "zaman aşımı" in j["error"]


def test_restart_marks_running_jobs(pid):
    jid = "still-000001-abcd"
    jd = W.PROJECTS / pid / "real" / jid
    jd.mkdir(parents=True)
    (jd / "status.json").write_text(json.dumps({"id": jid, "pid": pid, "kind": "still", "status": "running", "results": []}))
    W._recover_jobs()
    j = c.get(f"/api/jobs/{jid}").json()
    assert j["status"] == "error" and j["error"] == "sunucu yeniden başladı"


def test_jobs_memory_is_bounded(monkeypatch):
    monkeypatch.setattr(W, "JOBS", {f"j{i}": {"status": "done" if i < 250 else "running"} for i in range(260)})
    W._prune_jobs()
    assert len(W.JOBS) == W.MAX_JOBS and all(f"j{i}" in W.JOBS for i in range(250, 260))


def test_xlsx_formula_injection(tmp_path):
    from openpyxl import load_workbook

    from archai import reports
    evil = '=HYPERLINK("https:kotu.example","tikla")'
    qres = {"lines": [{"level": "+Kat", "element": "a/-eleman", "type": "wall", "kind": None, "role": "@rol", "tag": None,
                       "metrics": {"length": 3.0}}],
            "rooms": [{"level": "Zemin", "name": f"Zemin/{evil}", "area": 12.0, "perimeter": 14.0}]}
    cost = {"rows": [{"enabled": True, "code": "EK", "name": "=1+2", "unit": "\tadet", "quantity": 2, "unit_price": 3}],
            "overhead_pct": 5, "profit_pct": 10, "vat_pct": 20, "gross_floor_area": 100, "note": None}
    info = {"company": {"name": "=cmd|' /C calc'!A0"}, "drawn_by": "-2+3", "checked_by": "\r=X"}
    path = reports.write_xlsx(tmp_path / "m.xlsx", "=proje", qres, cost, info)
    wb = load_workbook(path)
    ok_prefix = ("=E", "=SUM(", "=G", "=(G", "=IF(")
    for ws in wb:
        for row in ws.iter_rows():
            for cell in row:
                if cell.data_type == "f":
                    assert str(cell.value).startswith(ok_prefix), (ws.title, cell.coordinate, cell.value)
    ms = wb["Mahal Listesi"]
    assert ms["B6"].value == "'" + evil
    bf = wb["Birim Fiyat Cetveli"]
    assert bf["C6"].value == "'=1+2" and bf["G6"].data_type == "f" and bf["G6"].value == "=E6*F6"
    assert bf["A1"].value.startswith("'=")


def test_index_escapes_html():
    html = (ROOT / "webapp/static/index.html").read_text()
    assert "const esc=" in html and "${p.name}" not in html and "${x}</div>" not in html


def test_offer_terms_via_api():
    """Firma teklif şartları API'den verilebilir; taslak işareti yalnız verilmeyen maddelerde kalır."""
    body = {"name": "Şartlı Teklif", "quick": {"gross_area": 450, "floors": 3},
            "offer": {"months": 14, "court": "Ankara Mahkemeleri", "validity_days": 15,
                      "payment": [{"pct": 30, "desc": "peşin"}, {"pct": 70, "desc": "hakedişle"}]}}
    r = c.post("/api/projects", json=body)
    assert r.status_code == 200, r.text
    from docx import Document
    url = r.json()["files"]["teklif_docx"]                      # /files/<pid>/teklif.docx
    path = W.PROJECTS / url.removeprefix("/files/")
    text = "\n".join(p.text for p in Document(path).paragraphs)
    assert "14 (" in text and "Ankara Mahkemeleri" in text and "15 (" in text
    bad = c.post("/api/projects", json={**body, "offer": {"months": 0}})
    assert bad.status_code == 422


def test_legacy_project_migration(tmp_path):
    """Eski biçimli klasör (kimlik kuralına uymayan ad) betikle taşınır, API'den açılır, dosya bağlantıları çalışır."""
    import importlib.util, json, shutil
    spec = importlib.util.spec_from_file_location("migrate_projects", ROOT / "scripts" / "migrate_projects.py")
    mig = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mig)
    r = c.post("/api/projects", json={"name": "Eski", "quick": {"gross_area": 450, "floors": 3}})
    assert r.status_code == 200, r.text
    src = W.PROJECTS / r.json()["id"]
    out = tmp_path / "out"
    (out / "projects").mkdir(parents=True)
    old = out / "projects" / "Kadıköy Demo"                   # büyük harf + Türkçe karakter + boşluk
    shutil.copytree(src, old)
    pj = json.loads((old / "project.json").read_text())
    old_abs = str((src).resolve())
    (old / "project.json").write_text((old / "project.json").read_text().replace(old_abs, str(old.resolve())))
    (out / "projects" / "bos-klasor").mkdir()
    assert mig.main(["--out", str(out)]) == 0 and old.exists()          # önizleme değiştirmez
    assert mig.main(["--out", str(out), "--apply"]) == 0
    assert not old.exists() and (out / "projects" / "bos-klasor").exists()   # boş klasör atlandı
    new = next(p for p in (out / "projects").iterdir() if p.name != "bos-klasor")
    assert W.PID_RE.fullmatch(new.name) and new.name.endswith("kadikoy-demo")
    assert str(old.resolve()) not in (new / "project.json").read_text()
    assert pj["name"] == "Eski"
    assert mig.main(["--out", str(out), "--apply"]) == 0                   # yeniden çalıştırma zararsız
