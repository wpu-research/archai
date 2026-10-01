#!/usr/bin/env python3
"""Playwright çekim işçisi: ArchAI görüntüleyicisini sanal saatle kare kare kaydeder.

YALNIZ standart kütüphane + playwright gerektirir (archai içe aktarmaz); Playwright'ın kurulu olduğu Python ile
çalıştırılır:  python capture_worker.py prep|capture <manifest.json>

Çıktı protokolü (stdout, satır satır): `RENDERER <ad>`, `WARN <metin>`, `PROGRESS <aşama> <0..1> [metin]`,
`SCENE <id> ok|fail <kare>`, `DONE`.  Kareler: <workdir>/frames/<sahne>/NNNN.jpg, Cycles: <workdir>/cycles/<ad>.jpg.
GPU: önce ANGLE-GL (NVIDIA/AMD), sonra gl-egl (Mesa iGPU), son çare SwiftShader (çok yavaş; adım atlanır, uyarı verilir).
"""
import json
import math
import os
import sys
import time
import urllib.error
import urllib.request

GL_SETS = [
    ("angle-gl", ["--use-gl=angle", "--use-angle=gl", "--ignore-gpu-blocklist", "--disable-gpu-sandbox", "--enable-gpu-rasterization"]),
    ("angle-gl-egl", ["--use-gl=angle", "--use-angle=gl-egl", "--ignore-gpu-blocklist", "--disable-gpu-sandbox", "--enable-gpu-rasterization"]),
    ("swiftshader", ["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"]),
]
SOFT_WORDS = ("swiftshader", "llvmpipe", "software", "swangle")
RENDERER_JS = """() => { const c = document.createElement('canvas'); const g = c.getContext('webgl2'); if (!g) return 'webgl yok';
  const e = g.getExtension('WEBGL_debug_renderer_info'); return e ? g.getParameter(e.UNMASKED_RENDERER_WEBGL) : g.getParameter(g.RENDERER); }"""
# sanal saat: animasyonlar performance.now() ile ilerler; kare kare çekimde elle ilerletilir
VCLOCK = "(() => { let t = 0; performance.now = () => t; window.__adv = ms => { t += ms; return t; }; })();"
HIDE_CSS = (".hud,.whud,#whud,.hud *{display:none!important}"
            ".vp{position:fixed!important;left:0!important;top:0!important;width:100vw!important;height:100vh!important;"
            "z-index:60!important;border-radius:0!important;margin:0!important}")
SET_CAM = """([c, t, fov]) => { const {V, toWorld} = window.ARCHAI; V.O.enableDamping = false; V.O.autoRotate = false;
  V.O.target.copy(toWorld(...t)); V.C.position.copy(toWorld(...c)); if (fov) { V.C.fov = fov; V.C.updateProjectionMatrix(); }
  V.C.lookAt(V.O.target); V.O.update(); V.C.updateMatrixWorld(); }"""
SET_LEVEL = "n => { const l = document.querySelector('#lv'); l.value = n < 0 ? l.max : n; l.dispatchEvent(new Event('input')); }"
SETTLE = "n => new Promise(r => { let k = n; const f = () => --k <= 0 ? r() : requestAnimationFrame(f); requestAnimationFrame(f); })"
SUBMIT = """async ({hq}) => {
  const out = await window.IN.exportForRender('still', {maket: false});
  const job = {...out.job, hq};
  const fd = new FormData(); fd.append('scene', new Blob([out.glb], {type: 'model/gltf-binary'}), 'scene.glb'); fd.append('job', JSON.stringify(job));
  const r = await fetch(`/api/projects/${location.hash.slice(1)}/real`, {method: 'POST', body: fd});
  return {status: r.status, body: await r.json().catch(() => ({}))}; }"""
CLOSE_DOORS = """() => { const seen = new Set(); window.ARCHAI.V.root.traverse(o => { const d = o.userData.door;
  if (d && o.isGroup && !seen.has(d)) { seen.add(d); d.cur = d.tgt = d.th0; o.rotation.y = d.th0; } }); return seen.size; }"""
FIND_DOOR = """([x, y]) => { let best = null; window.ARCHAI.V.root.traverse(o => { const d = o.userData.door; if (d && o.isGroup) {
  const dd = Math.hypot(d.hx - x, d.hy - y); if (!best || dd < best.dd) best = {dd, d}; } });
  if (!best || best.dd > 1.6) return false; window.__door = best.d; return true; }"""

ease = lambda x: (lambda u: u * u * (3 - 2 * u))(min(1.0, max(0.0, x)))


def say(*a):
    print(*a, flush=True)


class Worker:
    def __init__(self, M):
        self.M = M
        self.base = M["base"].rstrip("/")
        self.pid = M["pid"]
        self.work = M["workdir"]
        self.fps = M.get("fps", 24)
        self.token = os.environ.get("ARCHAI_TOKEN") or ""
        self.soft = False
        self.step = 1
        self.done = 0
        self.total = 1

    # ------------------------------------------------------------------ tarayıcı
    def launch(self, p):
        last = None
        for name, args in GL_SETS:
            try:
                b = p.chromium.launch(args=args, timeout=90000)
                pg = b.new_page()
                pg.goto("about:blank")
                r = str(pg.evaluate(RENDERER_JS))
                pg.close()
            except Exception as ex:  # noqa: BLE001
                last = ex
                continue
            soft = any(w in r.lower() for w in SOFT_WORDS) or r == "webgl yok"
            if not soft or name == "swiftshader":
                self.soft = soft
                say("RENDERER", f"{name}: {r}")
                if soft:
                    say("WARN", "GPU bulunamadı: yazılım çizimi (SwiftShader) kullanılıyor; çekim çok yavaş, kare sıklığı düşürüldü")
                    self.step = 4
                return b
            b.close()
        raise RuntimeError(f"tarayıcı/WebGL başlatılamadı: {last}")

    def context(self, b, fresh=True):
        w, h = self.M["size"]
        vw, vh, dsf = (1600, 900, 1.2) if w >= 1920 else (1280, 720, 1.0)
        ctx = b.new_context(viewport={"width": vw, "height": vh}, device_scale_factor=dsf)
        if self.token:
            ctx.add_cookies([{"name": "archai_token", "value": self.token, "url": self.base}])
        self.puts = []
        override = os.path.join(self.work, "interior_auto.json")

        def route(r, req):
            if req.method == "PUT":
                try:
                    self.puts.append(req.post_data)
                except Exception:  # noqa: BLE001
                    pass
                r.fulfill(status=200, content_type="application/json", body='{"ok": true}')
            elif req.method == "GET" and os.path.exists(override):
                r.fulfill(status=200, content_type="application/json", body=open(override, encoding="utf-8").read())
            else:
                r.continue_()
        ctx.route("**/api/projects/*/interior", route)       # kullanıcının projesi DEĞİŞMEZ
        return ctx

    def open_page(self, pg, vclock=True):
        pg.goto(f"{self.base}/?vm=real&nointro=1#{self.pid}")
        pg.wait_for_function("() => !!(window.IN && window.IN.real && window.ARCHAI && window.ARCHAI.V.elements && "
                             "window.ARCHAI.V.elements.length && document.querySelector('#hname').textContent.trim().length > 1 && "
                             "document.querySelector('#hname').textContent.trim() !== '—')", timeout=240000)
        try:
            pg.wait_for_load_state("networkidle", timeout=60000)
        except Exception:  # noqa: BLE001
            pass
        time.sleep(18 if self.soft else 8)                     # mobilya / HDRI yüklensin
        pg.add_style_tag(content=HIDE_CSS)
        pg.wait_for_timeout(600)
        if vclock:
            pg.evaluate("ms => window.__adv(ms)", 5000)        # kat açılış animasyonu bitmiş sayılsın

    def settle(self, pg, n=2):
        pg.evaluate(SETTLE, n)

    def adv(self, pg, ms=None):
        pg.evaluate("ms => window.__adv(ms)", ms if ms is not None else 1000 / self.fps)

    def shot(self, pg, path):
        self.settle(pg, 2)
        pg.screenshot(path=path, type="jpeg", quality=90, timeout=240000)
        self.done += 1
        if self.done % 6 == 0:
            say("PROGRESS", "capture", round(min(1.0, self.done / self.total), 4))

    # ------------------------------------------------------------------ hazırlık: boş iç mekânı otomatik döşe
    def prep(self):
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            b = self.launch(p)
            ctx = self.context(b)
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: say("WARN", f"sayfa hatası: {str(e)[:160]}"))
            self.open_page(pg, vclock=False)
            for lv in self.M.get("floors", []):
                pg.evaluate("async lv => { await window.IN.autoFurnish(lv); await window.IN.autoDecor(lv); }", lv)
                say("PROGRESS", "prep", 0.5, lv)
            time.sleep(2.0)                                     # save() 400 ms gecikmeli
            if self.puts:
                with open(os.path.join(self.work, "interior_auto.json"), "w", encoding="utf-8") as f:
                    f.write(self.puts[-1])
                say("INTERIOR", "ok")
            b.close()
        say("DONE")

    # ------------------------------------------------------------------ çekim
    def out_dir(self, sid):
        d = os.path.join(self.work, "frames", sid)
        os.makedirs(d, exist_ok=True)
        return d

    @staticmethod
    def cam_pose(M, az, el, R, center):
        a, e = math.radians(az), math.radians(el)
        cx, cy, cz = center
        return [cx + R * math.cos(a) * math.cos(e), cy + R * math.sin(a) * math.cos(e), cz + R * math.sin(e)], list(center)

    def count_total(self):
        n = 0
        for s in self.M["scenes"]:
            k = s["kind"]
            if k in ("modes",):
                n += len(s["modes"])
            elif k == "floors":
                n += len(s["levels"])
            else:
                n += len(range(0, s["frames"], self.step))
        return max(1, n)

    def capture(self):
        from playwright.sync_api import sync_playwright
        info = {"scenes": {}}
        with sync_playwright() as p:
            b = self.launch(p)
            self.total = self.count_total()
            ctx = self.context(b)
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)))
            pg.add_init_script(VCLOCK)
            self.open_page(pg)
            order = {"intro": 0, "orbit": 1, "modes": 2, "floors": 3, "daynight": 4, "walk": 6}
            scenes = sorted(self.M["scenes"], key=lambda s: order.get(s["kind"], 9))
            cyc = self.M.get("cycles", {}).get("shots", [])
            jobs = {}
            for s in scenes:
                if s["kind"] == "walk" and cyc:
                    jobs.update(self.cycles_submit(pg, [c for c in cyc if c.get("walk") is None]))
                try:
                    n = getattr(self, "scene_" + s["kind"])(pg, s)
                    info["scenes"][s["id"]] = {"ok": True, "frames": n}
                    say("SCENE", s["id"], "ok", n)
                except Exception as ex:  # noqa: BLE001
                    info["scenes"][s["id"]] = {"ok": False, "error": str(ex)[:200]}
                    say("SCENE", s["id"], "fail", str(ex)[:160].replace("\n", " "))
            if cyc:
                if not any(s["kind"] == "walk" for s in scenes):
                    jobs.update(self.cycles_submit(pg, [c for c in cyc if c.get("walk") is None]))
                jobs.update(self.cycles_interior(pg, [c for c in cyc if c.get("walk") is not None]))
            b.close()
        if jobs:
            info["cycles"] = self.cycles_collect(jobs)
        info.update(step=self.step, soft=self.soft, errors=errs[:3])
        with open(os.path.join(self.work, "capture_info.json"), "w", encoding="utf-8") as f:
            json.dump(info, f, ensure_ascii=False)
        say("DONE")

    # ---- sahneler
    def level_max(self, pg):
        pg.evaluate(SET_LEVEL, -1)
        self.settle(pg, 2)

    def put_cam(self, pg, az, el, R, center, fov):
        c, t = self.cam_pose(self.M, az, el, R, center)
        pg.evaluate(SET_CAM, [c, t, fov])

    def scene_intro(self, pg, s):
        out = self.out_dir(s["id"])
        self.level_max(pg)
        self.put_cam(pg, s["az"], s["el"], s["radius"], s["center"], s["fov"])
        self.settle(pg, 2)
        pg.evaluate("() => window.ARCHAI.intro()")
        n = 0
        for i in range(s["frames"]):
            if i % self.step == 0:
                self.shot(pg, f"{out}/{i:04d}.jpg")
                n += 1
            self.adv(pg)
            if i % self.step:
                self.settle(pg, 1)
        return n

    def scene_orbit(self, pg, s):
        out = self.out_dir(s["id"])
        self.level_max(pg)
        N = s["frames"]
        n = 0
        for i in range(N):
            u = i / max(1, N - 1)
            az = s["az0"] + (s["az1"] - s["az0"]) * ease(u)
            self.put_cam(pg, az, s["el"] + 4 * math.sin(math.pi * u), s["radius"], s["center"], s["fov"])
            self.adv(pg)
            if i % self.step == 0:
                self.shot(pg, f"{out}/{i:04d}.jpg")
                n += 1
        return n

    def scene_modes(self, pg, s):
        out = self.out_dir(s["id"])
        self.level_max(pg)
        n = 0
        for i, vm in enumerate(s["modes"]):
            pg.evaluate("v => document.querySelector(`[data-vm=${v}]`).click()", vm)
            self.level_max(pg)
            self.put_cam(pg, s["az"], s["el"], s["radius"], s["center"], s["fov"])
            time.sleep((10 if self.soft else 3.5) if vm == "real" else 1.8)
            self.adv(pg)
            self.put_cam(pg, s["az"], s["el"], s["radius"], s["center"], s["fov"])
            self.shot(pg, f"{out}/{i:04d}.jpg")
            n += 1
        return n

    def scene_floors(self, pg, s):
        out = self.out_dir(s["id"])
        n = 0
        for i, lv in enumerate(s["levels"]):
            pg.evaluate(SET_LEVEL, lv)
            time.sleep(1.2)
            self.adv(pg)
            self.put_cam(pg, s["az"], s["el"], s["radius"], s["center"], s["fov"])        # fitVisible kadrajı bozmasın
            self.shot(pg, f"{out}/{i:04d}.jpg")
            n += 1
        return n

    def scene_daynight(self, pg, s):
        out = self.out_dir(s["id"])
        self.level_max(pg)
        N = s["frames"]
        n = 0
        night_at = int(N * 0.72)
        for i in range(N):
            u = i / max(1, N - 1)
            az = s["az0"] + (s["az1"] - s["az0"]) * u
            self.put_cam(pg, az, s["el"], s["radius"], s["center"], s["fov"])
            if i < night_at:
                h = s["h0"] + (s["h1"] - s["h0"]) * i / max(1, night_at - 1)
                pg.evaluate("h => { const e = document.querySelector('#sunh'); e.value = h; e.dispatchEvent(new Event('input')); }", h)
            elif i == night_at:
                pg.evaluate("() => { document.querySelector('#sunh').value = 19; const n = document.querySelector('#night');"
                            " if (!n.classList.contains('on')) n.click(); }")
            self.adv(pg)
            if not self.soft:
                time.sleep(0.12)
            if i % self.step == 0:
                self.shot(pg, f"{out}/{i:04d}.jpg")
                n += 1
        # sonraki sahneler gündüz görsün
        pg.evaluate("() => { const n = document.querySelector('#night'); if (n.classList.contains('on')) n.click();"
                    " const e = document.querySelector('#sunh'); e.value = 11; e.dispatchEvent(new Event('input')); }")
        return n

    def scene_walk(self, pg, s):
        out = self.out_dir(s["id"])
        pg.evaluate(SET_LEVEL, s["level_index"])
        pg.evaluate("document.querySelector('#walk').click()")
        time.sleep(3)
        door = s.get("door_open")
        have_door = False
        if door:
            pg.evaluate(CLOSE_DOORS)
            have_door = bool(pg.evaluate(FIND_DOOR, [door["x"], door["y"]]))
        opened = False
        n = 0
        for i, (t, x, y, yaw) in enumerate(s["samples"]):
            pg.evaluate("([x, y, yaw]) => window.WALK_SET(x, y, yaw)", [x, y, yaw])
            if have_door and not opened and t >= door["t"]:
                pg.evaluate("() => { window.__door.tgt = window.__door.th1; }")
                opened = True
            self.adv(pg)
            if i % self.step == 0:
                self.shot(pg, f"{out}/{i:04d}.jpg")
                n += 1
            else:
                self.settle(pg, 1)
        return n

    # ---- Cycles
    def http(self, path, data=None, headers=None, method=None):
        req = urllib.request.Request(self.base + path, data=data, headers=headers or {}, method=method)
        if self.token:
            req.add_header("Authorization", "Bearer " + self.token)
        return urllib.request.urlopen(req, timeout=60)

    def submit(self, pg, hq):
        for attempt in range(40):
            r = pg.evaluate(SUBMIT, {"hq": hq})
            if r["status"] == 200:
                return r["body"]["id"]
            if r["status"] == 429:
                say("PROGRESS", "cycles", 0.0, "render kuyruğu dolu, bekleniyor")
                time.sleep(15)
                continue
            raise RuntimeError(f"Cycles gönderimi reddedildi ({r['status']}): {str(r['body'])[:120]}")
        raise RuntimeError("render kuyruğu uzun süre doluydu")

    def cycles_submit(self, pg, shots):
        jobs = {}
        hq = bool(self.M["cycles"].get("hq"))
        if not shots:
            return jobs
        pg.evaluate("() => { const n = document.querySelector('#night'); if (n.classList.contains('on')) n.click(); }")
        for sh in shots:
            try:
                self.level_max(pg)
                c = sh["cam"]
                pg.evaluate(SET_CAM, [c["pos"], c["target"], c["fov"]])
                time.sleep(2)
                self.settle(pg, 3)
                jobs[sh["name"]] = self.submit(pg, hq)
                say("PROGRESS", "cycles", 0.0, f"{sh['name']} sıraya alındı")
            except Exception as ex:  # noqa: BLE001
                say("WARN", f"Cycles '{sh['name']}' gönderilemedi: {str(ex)[:140]}")
        return jobs

    def cycles_interior(self, pg, shots):
        jobs = {}
        if not shots:
            return jobs
        hq = bool(self.M["cycles"].get("hq"))
        try:
            pg.evaluate(CLOSE_DOORS)
        except Exception:  # noqa: BLE001
            pass
        for sh in shots:
            try:
                x, y, yaw = sh["walk"]
                pg.evaluate("([x,y,yaw]) => window.WALK_SET(x,y,yaw)", [x, y, yaw])
                time.sleep(1)
                self.settle(pg, 3)
                jobs[sh["name"]] = self.submit(pg, hq)
                say("PROGRESS", "cycles", 0.0, f"{sh['name']} sıraya alındı")
            except Exception as ex:  # noqa: BLE001
                say("WARN", f"Cycles '{sh['name']}' gönderilemedi: {str(ex)[:140]}")
        return jobs

    def cycles_collect(self, jobs):
        os.makedirs(os.path.join(self.work, "cycles"), exist_ok=True)
        res = {}
        limit = float(os.environ.get("ARCHAI_VIDEO_CYCLES_TIMEOUT", 1500))
        pending = dict(jobs)
        t0 = time.time()
        total = len(jobs)
        while pending and time.time() - t0 < limit * total:
            for name, jid in list(pending.items()):
                try:
                    j = json.load(self.http(f"/api/jobs/{jid}"))
                except (urllib.error.URLError, ValueError, OSError):
                    continue
                if j.get("status") == "done" and j.get("urls"):
                    url = next((u for u in j["urls"] if u.lower().endswith((".jpg", ".png"))), j["urls"][0])
                    data = self.http(url).read()
                    with open(os.path.join(self.work, "cycles", name + ".jpg"), "wb") as f:
                        f.write(data)
                    res[name] = True
                    pending.pop(name)
                elif j.get("status") == "error":
                    res[name] = False
                    say("WARN", f"Cycles '{name}' hata: {str(j.get('error'))[:140]}")
                    pending.pop(name)
                else:
                    frac = (j.get("done") or 0) / max(1, j.get("total") or 1)
                    say("PROGRESS", "cycles", round((len(res) + frac) / total, 4), f"{name}: Blender çalışıyor")
            time.sleep(3)
        for name in pending:
            res[name] = False
            say("WARN", f"Cycles '{name}' zaman aşımı")
        say("PROGRESS", "cycles", 1.0)
        return res


def main():
    mode, path = sys.argv[1], sys.argv[2]
    with open(path, encoding="utf-8") as f:
        M = json.load(f)
    w = Worker(M)
    getattr(w, mode)()


if __name__ == "__main__":
    main()
