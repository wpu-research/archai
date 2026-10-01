"""Müşteri videosu: ayar doğrulama, sahne planlayıcı, yürüyüş yolu, kuyruk limitleri, uç noktalar.

Ağır uçtan uca test (Playwright + WebGL + ffmpeg) yalnız ARCHAI_VIDEO_E2E=1 ile çalışır.
Tüm çıktı conftest'in geçici ARCHAI_OUT dizinine yazılır.
"""
import json
import math
import os
import sys
import threading
import time
from pathlib import Path

import pytest
from pydantic import ValidationError
from shapely.geometry import LineString

from archai import project
from archai.video import facts as F, jobs as J, plan as P, walk as W
from archai.video.settings import VideoSettings

OUT = Path(os.environ["ARCHAI_OUT"])


# ------------------------------------------------------------------ yardımcılar
@pytest.fixture(scope="module")
def projects():
    out = {}
    for name, fn in (("villa", project.run_villa), ("apartment", project.run_apartment), ("cabin", project.run_cabin)):
        d = OUT / "projects" / f"20260101-000000-{name}-t{len(out)}"
        fn(d, {"name": name.title()})
        out[name] = d
    d = OUT / "projects" / "20260101-000000-hizli-t9"
    project.run({"name": "Hizli", "quick": {"gross_area": 450, "floors": 3, "unit_type": "2+1"}}, d)
    out["quick"] = d
    return out


def facts_of(d):
    return F.load_facts(d, OUT)


# ------------------------------------------------------------------ ayarlar
def test_settings_defaults_and_sizes():
    s = VideoSettings()
    assert s.profile == "standard" and s.cycles is False and s.music is True and s.size == (1920, 1080)
    assert VideoSettings(resolution="720p", profile="short").size == (1280, 720)


@pytest.mark.parametrize("bad", [{"profile": "uzun"}, {"resolution": "4k"}, {"cycles": "evet"}, {"cycles": 1},
                                 {"cycles_quality": "ultra"}, {"bilinmeyen": True}])
def test_settings_rejects_bad(bad):
    with pytest.raises(ValidationError):
        VideoSettings.model_validate(bad)


# ------------------------------------------------------------------ planlayıcı
def kinds(plan):
    return [s.kind for s in plan.scenes]


@pytest.mark.parametrize("name", ["villa", "apartment", "cabin", "quick"])
def test_plan_profiles_and_durations(projects, name):
    f = facts_of(projects[name])
    wk = W.plan_walk(f, budget_s=P.D["walk"][1] - 3.0)
    short = P.build_plan(f, VideoSettings(profile="short"), W.plan_walk(f, budget_s=P.D["walk"][0] - 3.0))
    std = P.build_plan(f, VideoSettings(profile="standard"), wk)
    assert 24 <= short.total <= 38, short.total
    assert 60 <= std.total <= 92, std.total
    for pl in (short, std):
        assert kinds(pl)[0] == "title" and kinds(pl)[-1] == "end"
        assert "orbit" in kinds(pl) and "maliyet" in kinds(pl)
        starts = [s.start for s in pl.scenes]
        assert starts == sorted(starts)
        # altyazılar: sahne içinde, aynı izde çakışmaz
        for track in ("main", "tag"):
            caps = pl.captions(track)
            for a, b in zip(caps, caps[1:]):
                assert a[1] <= b[0] + 1e-6, (track, a, b)
        for s in pl.scenes:
            for c in s.caps:
                assert 0 <= c.t0 < c.t1 <= s.dur + 1e-6


def test_plan_has_no_invented_company_or_cycles(projects):
    f = facts_of(projects["villa"])
    f.info = {}
    f.logo = None
    pl = P.build_plan(f, VideoSettings())
    assert "company" not in kinds(pl)            # firma bilgisi yoksa kare atlanır
    assert "cycles" not in kinds(pl)             # Cycles kapalı
    f.info = {"company": {"name": "Örnek Yapı", "phone": "0212"}}
    assert "company" in kinds(P.build_plan(f, VideoSettings()))
    assert F.contact_lines(f) == [("Telefon", "0212")]


def test_plan_cycles_and_skip(projects):
    f = facts_of(projects["villa"])
    wk = W.plan_walk(f)
    pl = P.build_plan(f, VideoSettings(cycles=True), wk)
    assert kinds(pl).count("cycles") >= 2
    pl2 = P.build_plan(f, VideoSettings(cycles=True), wk, cycles_ok=["dis"])
    assert kinds(pl2).count("cycles") == 1
    pl3 = P.build_plan(f, VideoSettings(), wk, skip=["walk"])
    assert "walk" not in kinds(pl3) and "end" in kinds(pl3)


def test_cards_use_only_project_numbers(projects):
    from archai.video import cards
    f = facts_of(projects["villa"])
    cd = cards.build_card_data(f)
    assert cd["cost"]["total"] == f.cost["total"]
    assert {t["value"] for t in cd["tiles"]} <= {float(v) for v in f.summary.values() if isinstance(v, (int, float))}
    c = cards.Cards(cd)
    for kind in ("title", "metraj", "maliyet", "end"):
        assert c.render(kind, 1.5, 3.0).size == (1920, 1080)
    # teklif şartları: yalnız kullanıcı girdiyse
    assert cd["offer_terms"] == []
    f.info = {"offer": {"months": 9}}
    assert cards.build_card_data(f)["offer_terms"] == [("Süre", "9 ay")]


def test_orbit_geometry_scales_with_building(projects):
    a = P.orbit_geometry(facts_of(projects["villa"]))
    b = P.orbit_geometry(facts_of(projects["cabin"]))
    assert a["radius"] > b["radius"] > 5
    x0, y0, x1, y1, _ = facts_of(projects["villa"]).bounds
    assert abs(a["center"][0] - (x0 + x1) / 2) < 1e-6


# ------------------------------------------------------------------ yürüyüş
def _door_spans(elements, level):
    """Her duvar için kapı açıklıkları (bağımsız doğrulama için)."""
    out = []
    for w in elements:
        if w.get("type") != "wall" or w.get("level") != level:
            continue
        (x0, y0), (x1, y1) = w["start"], w["end"]
        L = math.hypot(x1 - x0, y1 - y0)
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        t = (w.get("thickness") or 0.2) / 2
        poly = LineString([(x0, y0), (x1, y1)]).buffer(t, cap_style="flat")
        gaps = [LineString([(x0 + ux * o["offset"], y0 + uy * o["offset"]), (x0 + ux * (o["offset"] + o["width"]), y0 + uy * (o["offset"] + o["width"]))])
                .buffer(t + 0.01, cap_style="flat") for o in w.get("openings", []) if o["kind"] == "door"]
        out.append((poly, gaps))
    return out


@pytest.mark.parametrize("name", ["villa", "apartment", "cabin", "quick"])
def test_walk_never_crosses_walls(projects, name):
    f = facts_of(projects[name])
    wk = W.plan_walk(f, budget_s=24.0)
    assert wk is not None and wk.duration > 4 and len(wk.visited) >= 1
    crosses, clearance = W.validate(wk, f)
    assert not crosses and clearance >= 0.15, (crosses, clearance)
    # bağımsız: duvar gövdesine giren her adım bir kapı açıklığından geçmeli
    spans = _door_spans(f.elements, wk.level)
    pts = [(fr[1], fr[2]) for fr in wk.frames]
    for a, b in zip(pts, pts[1:]):
        seg = LineString([a, b]) if a != b else None
        if seg is None:
            continue
        for poly, gaps in spans:
            inter = seg.intersection(poly)
            if inter.is_empty or inter.length < 1e-9:
                continue
            assert any(g.buffer(0.02).contains(inter) for g in gaps), (name, a, b)
    # makul hız ve kare sürekliliği
    for p, q in zip(wk.frames, wk.frames[1:]):
        assert math.hypot(q[1] - p[1], q[2] - p[2]) / (q[0] - p[0]) < 4.0
        assert abs(W.wrap(q[3] - p[3])) < math.radians(12)         # tek karede ani dönüş yok


def test_walk_enters_through_exterior_door(projects):
    f = facts_of(projects["villa"])
    wk = W.plan_walk(f, budget_s=24.0)
    x0, y0, x1, y1, _ = f.bounds
    sx, sy = wk.frames[0][1], wk.frames[0][2]
    assert not (x0 <= sx <= x1 and y0 <= sy <= y1)               # başlangıç binanın dışında
    assert wk.door_open is not None and wk.door_open["t"] >= 0
    assert wk.tags and all(t[1] > t[0] for t in wk.tags)


def test_walk_respects_demolished_walls(projects):
    f = facts_of(projects["apartment"])
    base = W.Geometry(f.elements, f.floors[0], f.rooms)
    names = [w["name"] for w in f.elements if w.get("type") == "wall" and w["level"] == f.floors[0]][:1]
    dem = W.Geometry(f.elements, f.floors[0], f.rooms, demolished=names)
    assert len(dem.solids) < len(base.solids)


def test_no_walk_without_geometry():
    f = F.Facts("x", "x", [], {}, {}, {}, {}, {}, [], [], None, None)
    assert W.plan_walk(f) is None and not f.has_building


# ------------------------------------------------------------------ logo
def test_logo_only_from_out_dir_and_valid_image(tmp_path):
    from PIL import Image
    root = tmp_path / "out"
    root.mkdir()
    assert F.resolve_logo(root, {}) is None
    Image.new("RGB", (40, 20), "red").save(root / "logo.png")
    assert F.resolve_logo(root, {}) == (root / "logo.png").resolve()
    outside = tmp_path / "dis.png"
    Image.new("RGB", (4, 4)).save(outside)
    (root / "logo.png").unlink()
    assert F.resolve_logo(root, {"logo": str(outside)}) is None   # OUT dışı reddedilir
    (root / "logo.jpg").write_bytes(b"jpg degil")
    assert F.resolve_logo(root, {}) is None                       # bozuk resim reddedilir


# ------------------------------------------------------------------ kuyruk
def fake_runner(delay=0.0, fail=None):
    def run(j, jobs):
        jobs.update(j, stage="cekim", percent=40, message="x")
        t0 = time.time()
        while time.time() - t0 < delay:
            if j["id"] in jobs.cancel_flags:
                return
            time.sleep(0.02)
        if fail:
            raise RuntimeError(fail)
        (Path(j["dir"]) / "musteri_videosu.mp4").write_bytes(b"\x00" * 64)
    return run


def mk_jobs(tmp_path, **kw):
    root = tmp_path / "projects"
    (root / "20260101-000000-a-0001").mkdir(parents=True)
    (root / "20260101-000000-b-0002").mkdir(parents=True)
    kw.setdefault("check_env", False)
    kw.setdefault("min_free_gb", 0)
    return J.VideoJobs(root, **kw), root


def wait(jobs, jid, states, t=10):
    t0 = time.time()
    while time.time() - t0 < t:
        s = jobs.get(jid)["status"]
        if s in states:
            return s
        time.sleep(0.02)
    raise AssertionError(f"{jid} {states} durumuna gelmedi: {jobs.get(jid)}")


def test_queue_done_progress_and_durable_status(tmp_path):
    jobs, root = mk_jobs(tmp_path, runner=fake_runner())
    j = jobs.submit("20260101-000000-a-0001", VideoSettings(), "http://127.0.0.1:1")
    assert J.JID_RE.fullmatch(j["id"])
    assert wait(jobs, j["id"], ("done",)) == "done"
    pub = jobs.get(j["id"])
    assert pub["percent"] == 100.0 and pub["download"].endswith("/download") and "base" not in pub and "dir" not in pub
    disk = json.loads((root / "20260101-000000-a-0001" / "video" / j["id"] / "status.json").read_text())
    assert disk["status"] == "done"
    assert jobs.list_done("20260101-000000-a-0001")[0]["id"] == j["id"]
    # yeni yönetici (yeniden başlatma) diskten okur
    jobs2 = J.VideoJobs(root, runner=fake_runner(), check_env=False, min_free_gb=0)
    assert jobs2.get(j["id"])["status"] == "done"


def test_queue_error_message_and_work_cleanup(tmp_path):
    jobs, root = mk_jobs(tmp_path, runner=fake_runner(fail="patladı"))
    j = jobs.submit("20260101-000000-a-0001", VideoSettings(), "http://x")
    assert wait(jobs, j["id"], ("error",)) == "error"
    assert "patladı" in jobs.get(j["id"])["error"]
    assert not (root / "20260101-000000-a-0001" / "video" / j["id"] / "work").exists()


def test_queue_limits_duplicate_and_cancel(tmp_path):
    jobs, _ = mk_jobs(tmp_path, runner=fake_runner(delay=30), max_queued=1)
    a = jobs.submit("20260101-000000-a-0001", VideoSettings(), "http://x")
    wait(jobs, a["id"], ("running",))
    with pytest.raises(J.JobError) as e:                         # aynı proje: 409
        jobs.submit("20260101-000000-a-0001", VideoSettings(), "http://x")
    assert e.value.code == 409 and e.value.extra["job"]["id"] == a["id"]
    b = jobs.submit("20260101-000000-b-0002", VideoSettings(), "http://x")     # bekleyen 1
    assert jobs.get(b["id"])["status"] == "queued"
    jobs.root.joinpath("20260101-000000-c-0003").mkdir()
    with pytest.raises(J.JobError) as e:                         # kuyruk dolu: 429
        jobs.submit("20260101-000000-c-0003", VideoSettings(), "http://x")
    assert e.value.code == 429
    assert jobs.cancel(b["id"])["status"] == "cancelled"         # bekleyen iptal
    jobs.cancel(a["id"])                                         # çalışan iptal
    assert wait(jobs, a["id"], ("cancelled",)) == "cancelled"


def test_disk_guard_and_prune(tmp_path):
    jobs, root = mk_jobs(tmp_path, runner=fake_runner(), min_free_gb=10 ** 9)
    with pytest.raises(J.JobError) as e:
        jobs.submit("20260101-000000-a-0001", VideoSettings(), "http://x")
    assert e.value.code == 507
    jobs, root = mk_jobs(tmp_path / "p2", runner=fake_runner(), keep_per_project=2)
    ids = []
    for _ in range(4):
        j = jobs.submit("20260101-000000-a-0001", VideoSettings(), "http://x")
        wait(jobs, j["id"], ("done",))
        time.sleep(0.05)
        ids.append(j["id"])
    time.sleep(0.2)
    left = sorted(p.name for p in (root / "20260101-000000-a-0001" / "video").iterdir())
    assert len(left) == 2 and set(left) <= set(ids[-3:])


def test_restart_marks_running_as_error(tmp_path):
    root = tmp_path / "projects"
    jd = root / "20260101-000000-a-0001" / "video" / "vid-120000-abcdef"
    (jd / "work").mkdir(parents=True)
    (jd / "status.json").write_text(json.dumps({"id": "vid-120000-abcdef", "pid": "20260101-000000-a-0001", "status": "running", "dir": str(jd)}))
    jobs = J.VideoJobs(root, runner=fake_runner(), check_env=False)
    assert jobs.get("vid-120000-abcdef")["status"] == "error" and not (jd / "work").exists()


class SlowCmdJobs(J.VideoJobs):
    """Gerçek alt süreç yolunu (zaman aşımı + süreç grubu temizliği) uzun uyuyan bir komutla dener."""
    @staticmethod
    def _cmd(j):
        return [sys.executable, "-c", "import time, subprocess, sys; subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)']); print('ARCHAI_VIDEO_PROGRESS cekim 12.0 x', flush=True); time.sleep(60)"]


def _alive_sleepers():
    import subprocess
    out = subprocess.run(["pgrep", "-f", "import time; time.sleep\\(60\\)"], capture_output=True, text=True).stdout.split()
    return [p for p in out if int(p) != os.getpid()]


def test_subprocess_timeout_kills_process_group(tmp_path):
    root = tmp_path / "projects"
    (root / "20260101-000000-a-0001").mkdir(parents=True)
    jobs = SlowCmdJobs(root, timeout=1.5, check_env=False, min_free_gb=0)
    j = jobs.submit("20260101-000000-a-0001", VideoSettings(), "http://x")
    assert wait(jobs, j["id"], ("error",), t=20) == "error"
    assert "zaman aşımı" in jobs.get(j["id"])["error"]
    time.sleep(0.5)
    assert not _alive_sleepers()                                  # torun süreç de öldü


def test_subprocess_cancel_progress(tmp_path):
    root = tmp_path / "projects"
    (root / "20260101-000000-a-0001").mkdir(parents=True)
    jobs = SlowCmdJobs(root, timeout=60, check_env=False, min_free_gb=0)
    j = jobs.submit("20260101-000000-a-0001", VideoSettings(), "http://x")
    wait(jobs, j["id"], ("running",))
    t0 = time.time()
    while jobs.get(j["id"])["percent"] < 12 and time.time() - t0 < 10:
        time.sleep(0.05)
    assert jobs.get(j["id"])["percent"] == 12.0 and jobs.get(j["id"])["stage"] == "cekim"
    jobs.cancel(j["id"])
    assert wait(jobs, j["id"], ("cancelled",), t=15) == "cancelled"
    time.sleep(0.5)
    assert not _alive_sleepers()


# ------------------------------------------------------------------ uç noktalar
@pytest.fixture()
def client(tmp_path):
    from fastapi.testclient import TestClient
    import webapp.app as A
    import webapp.video_routes as V
    pid = "20260101-000000-rota-0001"
    (A.PROJECTS / pid).mkdir(parents=True, exist_ok=True)
    project.run_villa(A.PROJECTS / pid, {"name": "Rota Testi"})
    old = V._jobs
    V._jobs = J.VideoJobs(A.PROJECTS, runner=fake_runner(), check_env=False, min_free_gb=0)
    c = TestClient(A.app, base_url="http://127.0.0.1:8000", client=("127.0.0.1", 50000))
    yield c, pid, V
    V._jobs = old


def test_routes_flow_and_validation(client):
    c, pid, V = client
    assert c.get("/api/video-capabilities").json()["defaults"]["profile"] == "standard"
    assert c.post("/api/projects/20260101-000000-yok-0000/video", json={}).status_code == 404
    assert c.post("/api/projects/..%2F..%2Fx/video", json={}).status_code in (404, 405)
    assert c.post(f"/api/projects/{pid}/video", json={"profile": "uzun"}).status_code == 422
    assert c.post(f"/api/projects/{pid}/video", json={"cycles": "evet"}).status_code == 422
    assert c.post(f"/api/projects/{pid}/video", json={"x": 1}).status_code == 422
    r = c.post(f"/api/projects/{pid}/video", json={"profile": "short", "resolution": "720p"})
    assert r.status_code == 202, r.text
    jid = r.json()["id"]
    t0 = time.time()
    while c.get(f"/api/video-jobs/{jid}").json()["status"] != "done" and time.time() - t0 < 10:
        time.sleep(0.05)
    st = c.get(f"/api/video-jobs/{jid}").json()
    assert st["status"] == "done"
    d = c.get(st["download"])
    assert d.status_code == 200 and d.headers["content-type"] == "video/mp4"
    assert "rota-testi-musteri-videosu.mp4" in d.headers["content-disposition"]
    assert c.get(f"/api/video-jobs/{jid}/file/musteri_videosu.mp4", headers={"Range": "bytes=0-9"}).status_code == 206
    assert c.get(f"/api/video-jobs/{jid}/file/status.json").status_code == 404          # beyaz liste
    assert c.get(f"/api/video-jobs/{jid}/file/..%2Fstatus.json").status_code in (404, 422)
    assert c.get("/api/video-jobs/vid-000000-zzzzzz").status_code == 404
    assert c.get("/api/video-jobs/..%2F..%2Fetc").status_code == 404
    assert c.get(f"/api/projects/{pid}/video").json()[0]["id"] == jid


def test_routes_not_ready_and_host_guard(client):
    c, pid, V = client
    V._jobs.runner = fake_runner(delay=5)
    jid = c.post(f"/api/projects/{pid}/video", json={}).json()["id"]
    assert c.get(f"/api/video-jobs/{jid}/download").status_code == 409
    assert c.post(f"/api/projects/{pid}/video", json={}).status_code == 409             # aynı proje
    assert c.post(f"/api/video-jobs/{jid}/cancel").status_code == 200
    assert c.get("/api/video-capabilities", headers={"host": "evil.example"}).status_code == 400


def test_video_ui_wired():
    root = Path(__file__).resolve().parents[1] / "webapp" / "static"
    html = (root / "index.html").read_text()
    assert 'id="vidbtn"' in html and 'src="video.js"' in html
    js = (root / "video.js").read_text()
    for s in ("/api/video-capabilities", "/api/video-jobs/", "role=\"progressbar\"", "<video controls"):
        assert s in js


# ------------------------------------------------------------------ ağır uçtan uca (isteğe bağlı)
@pytest.mark.skipif(not os.environ.get("ARCHAI_VIDEO_E2E"), reason="ARCHAI_VIDEO_E2E=1 ile (Playwright+WebGL+ffmpeg)")
def test_e2e_short_video(projects, tmp_path):
    import socket
    import subprocess
    import uvicorn
    import webapp.app as A
    from archai.video import pipeline
    pid = "20260101-000000-e2e-0001"
    shutil_dir = A.PROJECTS / pid
    project.run_cabin(shutil_dir, {"name": "E2E"})
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = uvicorn.Server(uvicorn.Config(A.app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    time.sleep(2)
    try:
        jd = tmp_path / "job"
        jd.mkdir()
        res = pipeline.generate(shutil_dir, jd, VideoSettings(profile="short", resolution="720p", music=True), f"http://127.0.0.1:{port}", OUT)
    finally:
        srv.should_exit = True
    mp4 = jd / "musteri_videosu.mp4"
    assert mp4.stat().st_size > 100_000 and 24 <= res["duration"] <= 40
    pr = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_name,width,height", "-of", "csv=p=0", str(mp4)],
                        capture_output=True, text=True).stdout
    assert "h264,1280,720" in pr and "aac" in pr
