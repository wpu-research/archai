"""Hareketli 3D sahneler: sanal saatle kare kare (24 fps) çekim.  kullanım: python motion.py <sahne> <ilk> <son>"""
import sys, os, math, time
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
FPS = 24
CENTER = (15.0, 17.0, 5.5)        # bina merkezi (plan x, y, z)
ease = lambda x: x * x * (3 - 2 * x)

def orbit_pose(az_deg, el_deg=24.0, R=38.0):
    a, e = math.radians(az_deg), math.radians(el_deg)
    cx, cy, cz = CENTER
    return (cx + R * math.cos(a) * math.cos(e), cy + R * math.sin(a) * math.cos(e), cz + R * math.sin(e)), CENTER

SET_CAM = """([c, t, fov]) => { const {V, toWorld} = window.ARCHAI; V.O.enableDamping = false; V.O.autoRotate = false;
  V.O.target.copy(toWorld(...t)); V.C.position.copy(toWorld(...c)); if (fov) { V.C.fov = fov; V.C.updateProjectionMatrix(); }
  V.C.lookAt(V.O.target); V.O.update(); V.C.updateMatrixWorld(); }"""
SET_LEVEL = "n => { const l = document.querySelector('#lv'); l.value = n < 0 ? l.max : n; l.dispatchEvent(new Event('input')); }"

# ---------------------------------------------------------------- YÜRÜYÜŞ yolu (t sn, x, y, yaw)
H = math.pi / 2
KEYS = [
    (0.0, 15.4, 6.0, 0.0), (2.8, 15.4, 13.4, 0.0), (3.8, 14.0, 14.75, H), (4.5, 13.0, 14.75, H), (6.5, 13.0, 14.75, H),
    (7.6, 11.35, 14.75, H), (8.2, 11.3, 14.0, math.pi), (9.8, 11.3, 10.1, math.pi), (10.6, 11.3, 8.6, math.pi),
    (11.8, 9.0, 7.4, yaw_to(-1, -0.2)), (13.0, 8.2, 7.3, yaw_to(-0.5, -1)), (14.2, 8.2, 7.3, yaw_to(-1, 0.8)),
    (15.4, 6.6, 8.7, 0.0), (16.6, 6.6, 10.5, yaw_to(1, 0.95)), (17.8, 6.6, 10.5, yaw_to(1, 0.95)),
]
WALK_N = int(KEYS[-1][0] * FPS) + 1
DOOR_T = (4.7, 5.7)            # kapıyı kapat, tekrar aç (F)

def unwrap_yaws(keys):
    out, prev = [], None
    for t, x, y, yaw in keys:
        if prev is not None:
            while yaw - prev > math.pi: yaw -= 2 * math.pi
            while yaw - prev < -math.pi: yaw += 2 * math.pi
        out.append((t, x, y, yaw)); prev = yaw
    return out
KEYS = unwrap_yaws(KEYS)

def catmull(vals, ts, t):
    """Düzgün olmayan zaman aralıklı Catmull-Rom (Hermite) — vals: [(x,y,yaw)]"""
    i = max(0, min(len(ts) - 2, next((k for k in range(len(ts) - 1) if ts[k] <= t < ts[k + 1]), len(ts) - 2)))
    t0, t1 = ts[i], ts[i + 1]; u = (t - t0) / (t1 - t0); u = min(1, max(0, u))
    p0, p1 = vals[i], vals[i + 1]
    def tan(k):
        a, b = max(0, k - 1), min(len(ts) - 1, k + 1)
        dt = ts[b] - ts[a] or 1
        return [(vals[b][j] - vals[a][j]) / dt for j in range(3)]
    m0, m1 = tan(i), tan(i + 1); h = t1 - t0
    h00, h10, h01, h11 = 2 * u**3 - 3 * u**2 + 1, u**3 - 2 * u**2 + u, -2 * u**3 + 3 * u**2, u**3 - u**2
    return [h00 * p0[j] + h10 * h * m0[j] + h01 * p1[j] + h11 * h * m1[j] for j in range(3)]

def walk_state(i):
    t = i / FPS
    x, y, yaw = catmull([(k[1], k[2], k[3]) for k in KEYS], [k[0] for k in KEYS], t)
    return t, x, y, yaw

# ---------------------------------------------------------------- sahne kurulumları
def open_page(pg, fullbleed_on=True):
    pg.goto(f"{BASE}/?vm=real&nointro=1#{HERO}")
    for _ in range(120):
        time.sleep(1)
        ok = pg.evaluate("() => !!(window.IN && window.IN.real && window.ARCHAI && window.ARCHAI.V.elements && document.querySelector('#hname').textContent.includes('Tanıtım'))")
        if ok: break
    time.sleep(9)                                   # mobilya/HDRI yüklensin
    if fullbleed_on: fullbleed(pg)
    pg.evaluate("ms => window.__adv(ms)", 5000)     # kat açılış animasyonu bitmiş sayılsın

def shot(pg, path):
    settle(pg, 2); pg.screenshot(path=path, type="jpeg", quality=92, timeout=180000)

def run(scene, a, b):
    out = f"{W}/frames/{scene}"; os.makedirs(out, exist_ok=True)
    with sync_playwright() as p:
        br = p.chromium.launch(args=ARGS)
        pg = br.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1.2)
        pg.add_init_script(VCLOCK)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        open_page(pg)
        adv = lambda: pg.evaluate("ms => window.__adv(ms)", 1000 / FPS)
        if scene == "intro":
            pg.evaluate(SET_LEVEL, -1)
            c, t = orbit_pose(-125)
            pg.evaluate(SET_CAM, [list(c), list(t), 34]); settle(pg, 2)
            pg.evaluate("() => window.ARCHAI.intro()")
            for i in range(0, b):                       # animasyonu a'ya kadar sessizce ilerlet
                if i >= a: shot(pg, f"{out}/{i:04d}.jpg")
                adv();
                if i < a: settle(pg, 1)
        elif scene == "orbit":
            pg.evaluate(SET_LEVEL, -1)
            for i in range(a, b):
                az = -125 + 75 * ease(i / (WALK_N * 0 + 95))
                c, t = orbit_pose(az, 24 + 4 * math.sin(math.pi * i / 95)); pg.evaluate(SET_CAM, [list(c), list(t), 34]); adv(); shot(pg, f"{out}/{i:04d}.jpg")
        elif scene == "modes":
            c, t = orbit_pose(-60); pg.evaluate(SET_LEVEL, -1); pg.evaluate(SET_CAM, [list(c), list(t), 34])
            for i, vm in enumerate(["wire", "xray", "solid", "real"]):
                if i < a or i >= b: continue
                pg.evaluate("v => document.querySelector(`[data-vm=${v}]`).click()", vm); time.sleep(3.5 if vm == "real" else 1.8); adv(); shot(pg, f"{out}/{i:04d}.jpg")
        elif scene == "floors":
            c, t = orbit_pose(-62, 30, 40); pg.evaluate(SET_CAM, [list(c), list(t), 34])
            for i in range(a, b):
                pg.evaluate(SET_LEVEL, i + 1); time.sleep(1.2); adv(); shot(pg, f"{out}/{i:04d}.jpg")
        elif scene == "walk":
            pg.evaluate(SET_LEVEL, 1); pg.evaluate("document.querySelector('#walk').click()"); time.sleep(3)
            door = pg.evaluate("""() => { let best = null; window.ARCHAI.V.root.traverse(o => { const d = o.userData.door; if (d && o.isGroup) {
                const dd = Math.hypot(d.hx - 11.9, d.hy - 14.75); if (!best || dd < best.dd) best = {dd, hx: d.hx, hy: d.hy, lw: d.lw, th0: d.th0, th1: d.th1}; } }); return best; }""")
            om = (door["hx"] + math.cos(door["th1"]) * door["lw"] / 2, door["hy"] + math.sin(door["th1"]) * door["lw"] / 2)   # açık kanat ortası
            cm = (door["hx"] + math.cos(door["th0"]) * door["lw"] / 2, door["hy"] + math.sin(door["th0"]) * door["lw"] / 2)   # kapalı kanat ortası
            print("kapı", door, flush=True)
            for i in range(a, b):
                t, x, y, yaw = walk_state(i)
                # kapı etkileşimi: bakışı kanada çevir
                if DOOR_T[0] - 0.5 <= t <= DOOR_T[1] + 0.9:
                    tgt = om if t < (DOOR_T[0] + DOOR_T[1]) / 2 else cm
                    aim = yaw_to(tgt[0] - x, tgt[1] - y)
                    while aim - yaw > math.pi: aim -= 2 * math.pi
                    while aim - yaw < -math.pi: aim += 2 * math.pi
                    w = ease(min(1, (t - (DOOR_T[0] - 0.5)) / 0.4)) * (1 - ease(min(1, max(0, (t - (DOOR_T[1] + 0.5)) / 0.4))))
                    yaw = yaw + (aim - yaw) * w
                pg.evaluate("([x, y, yaw]) => window.WALK_SET(x, y, yaw)", [x, y, yaw])
                adv(); settle(pg, 2)
                if abs(t - DOOR_T[0]) < 0.5 / FPS or abs(t - DOOR_T[1]) < 0.5 / FPS:
                    print("F tuşu", t, pg.evaluate("() => window.IN.toggleDoor()"), flush=True)
                shot(pg, f"{out}/{i:04d}.jpg")
        elif scene == "daynight":
            pg.evaluate(SET_LEVEL, 1)
            pg.evaluate(SET_CAM, [[15, -16, 25], [15, 14, 0], 36])
            for i in range(a, b):
                if i < 72:
                    h = 6.5 + 12.0 * i / 71
                    pg.evaluate("h => { const s = document.querySelector('#sunh'); s.value = h; s.dispatchEvent(new Event('input')); }", h)
                else:
                    if i == 72 or a > 72 and i == a:
                        pg.evaluate("() => { document.querySelector('#sunh').value = 19; const n = document.querySelector('#night'); if (!n.classList.contains('on')) n.click(); }")
                adv(); time.sleep(0.25); shot(pg, f"{out}/{i:04d}.jpg")
        print(scene, a, b, "bitti; hata:", errs[:2], flush=True)
        br.close()

if __name__ == "__main__":
    run(sys.argv[1], int(sys.argv[2]), int(sys.argv[3]))
