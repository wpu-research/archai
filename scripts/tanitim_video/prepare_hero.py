import os
import time, json
from playwright.sync_api import sync_playwright
W = os.environ.get("ARCHAI_PROMO_DIR") or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "out", "promo")); ID = open(f"{W}/hero_id").read().strip()
with sync_playwright() as p:
    b = p.chromium.launch(args=["--use-angle=swiftshader", "--enable-unsafe-swiftshader", "--ignore-gpu-blocklist"])
    pg = b.new_page(viewport={"width": 1600, "height": 900}); errs = []
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(f"http://localhost:8070/?vm=real&nointro=1#{ID}"); time.sleep(12)
    info = pg.evaluate("""() => { const V = window.ARCHAI.V;
      const lv = V.nLv; const rooms = V.elements.filter(e => e.type === 'room').map(r => ({n: r.name, lv: r.level, pts: r.points}));
      return {lv, nrooms: rooms.length, names: rooms.filter(r => r.lv === lv[0]).map(r => r.n), zs: lv.map(n => V.elements.find(e => e.type==='slab' && e.role==='floor' && e.level===n)?.z)}; }""")
    print(json.dumps(info, ensure_ascii=False)[:1500])
    for lv in info["lv"]:
        if lv in ("Arsa", "Çatı"): continue
        n = pg.evaluate("async (lv) => { const a = await window.IN.autoFurnish(lv); const d = await window.IN.autoDecor(lv); return d; }", lv)
        print("döşendi", lv, "dekor:", n)
    time.sleep(3)
    print("hatalar:", errs[:3]); b.close()
