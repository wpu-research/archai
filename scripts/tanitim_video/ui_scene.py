"""Arayüz sahnesi: sıfırdan proje → özet/çizim/metraj/maliyet/belge → düzenleyici. Sahte imleç zaman çizelgesiyle kaydedilir."""
import sys, os, json, time, math
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
OUT = f"{W}/ui"; os.makedirs(OUT, exist_ok=True)
for f in os.listdir(OUT): os.remove(f"{OUT}/{f}")
ease = lambda x: x * x * (3 - 2 * x)

class Rec:
    def __init__(s, pg):
        s.pg, s.t, s.n, s.frames, s.knots, s.clicks, s.caps, s.pos, s.marks = pg, 0.0, 0, [], [], [], [], (800.0, 450.0), {}
    def snap(s):
        f = f"{OUT}/u{s.n:04d}.jpg"; s.n += 1
        s.pg.screenshot(path=f, type="jpeg", quality=92, timeout=120000); s.frames.append({"t": round(s.t, 3), "img": f})
    def wait(s, dt): s.t += dt
    def move(s, x, y, dur=0.55):
        s.knots.append([round(s.t, 3), s.pos[0], s.pos[1]]); s.t += dur; s.knots.append([round(s.t, 3), x, y]); s.pos = (x, y)
    def center(s, sel):
        loc = s.pg.locator(sel).first; loc.scroll_into_view_if_needed(timeout=20000)
        bb = loc.bounding_box(); return bb["x"] + bb["width"] / 2, bb["y"] + bb["height"] / 2
    def click(s, sel, pause=0.9, snap_after=True, delay=0.0):
        x, y = s.center(sel); s.move(x, y); s.clicks.append(round(s.t, 3)); s.pg.locator(sel).first.click()
        s.pg.wait_for_timeout(int(pause * 1000)); s.t += 0.12
        if snap_after: s.snap()
        s.t += 0.25 + delay
    def type(s, sel, text, per=0.055):
        x, y = s.center(sel); s.move(x, y); s.clicks.append(round(s.t, 3)); s.pg.locator(sel).first.click()
        s.pg.keyboard.press("Control+A"); s.pg.keyboard.press("Delete"); s.t += 0.15; s.snap()
        for ch in text:
            s.pg.keyboard.type(ch); s.t += per; s.snap()
        s.pg.keyboard.press("Tab"); s.t += 0.2
    def scroll_to(s, y, steps=0, per=0.055):
        cur = s.pg.evaluate("window.scrollY")
        if steps:
            for i in range(1, steps + 1):
                s.pg.evaluate("v => window.scrollTo(0, v)", cur + (y - cur) * ease(i / steps)); s.t += per; s.snap()
        else:
            s.pg.evaluate("v => window.scrollTo(0, v)", y)
    def tabs_y(s): return s.pg.evaluate("document.querySelector('#tabs').getBoundingClientRect().top + window.scrollY - 118")
    def cap(s, t0, t1, text): s.caps.append({"t0": round(t0, 3), "t1": round(t1, 3), "text": text})
    def mark(s, name): s.marks[name] = round(s.t, 3)
    def dump(s, name):
        json.dump({"frames": s.frames, "knots": s.knots, "clicks": s.clicks, "caps": s.caps, "marks": s.marks, "duration": round(s.t, 3)},
                  open(f"{W}/{name}.json", "w"), ensure_ascii=False)

def part1(pg):
    r = Rec(pg)
    pg.goto(f"{BASE}/"); pg.wait_for_timeout(5000); r.snap(); r.mark("form"); t0 = r.t; r.wait(0.9)
    r.type("#name", "ArchAI Tanıtım")
    r.type("#pd", "34"); r.type("#taks", "0.35"); r.type("#kaks", "1.6"); r.type("#mf", "4")
    x, y = r.center("#upf"); r.move(x, y); r.clicks.append(round(r.t, 3)); pg.select_option("#upf", "3"); r.t += 0.15; r.snap(); r.wait(0.8)
    r.cap(t0 + 0.2, r.t, "Sıfırdan başla: parsel, imar ve program")
    r.mark("go"); r.click("#go", pause=0.2, snap_after=False)
    pg.wait_for_function("document.querySelector('#hname').textContent.includes('Tanıtım')", timeout=180000); pg.wait_for_timeout(5000)
    r.scroll_to(0); r.snap(); r.mark("ozet"); r.wait(1.0)
    r.scroll_to(r.tabs_y(), steps=8); r.wait(2.4)
    return r

def part2(pg, r):
    def tab(name, pause=1.4):
        r.scroll_to(r.tabs_y()); r.click(f"#tabs [data-t={name}]", pause=pause)
    t0 = r.t
    tab("cizim"); r.wait(0.8); r.mark("cizim")
    r.click(".sheet img", pause=1.2); r.wait(1.4)
    pg.keyboard.press("Escape"); pg.mouse.click(5, 5); pg.wait_for_timeout(500)
    r.cap(t0, r.t, "Paftalar otomatik: plan, kesit, görünüş — DXF ve PDF")
    t1 = r.t
    tab("metraj", 1.2); r.wait(0.8); r.mark("metraj")
    tab("maliyet", 1.5); r.wait(0.7); r.mark("maliyet")
    r.scroll_to(r.pg.evaluate("window.scrollY") + 330, steps=7); r.wait(0.6)
    r.type("[data-pct=profit_pct]", "12"); r.wait(0.8); r.snap(); r.wait(1.0)
    r.cap(t1, r.t, "Metraj ve maliyet: kalem kalem, anında güncellenir")
    t2 = r.t
    tab("belge", 1.5); r.wait(1.4); r.mark("belge")
    r.cap(t2, r.t, "Teklif, teknik şartname ve Excel hazır")
    return r

def part3(pg, r):
    t0 = r.t
    r.scroll_to(0, steps=8); fullbleed(pg); r.snap()
    pg.evaluate("() => { const l = document.querySelector('#lv'); l.value = 1; l.dispatchEvent(new Event('input')); }"); pg.wait_for_timeout(800)
    r.click("[data-vm=real]", pause=7.0); r.wait(1.0); r.mark("real")
    r.click("#edit", pause=4.0); r.wait(0.6); r.mark("edit")
    r.click("#itabs [data-it=nesne]", pause=0.8)
    r.click("#iauto", pause=9.0); r.wait(1.0); r.mark("furnish")
    r.click("#idecor", pause=9.0); r.wait(1.2); r.mark("decor")
    r.cap(t0, r.t, "Düzenleyici: tek tıkla döşe ve dekor ekle")
    t1 = r.t
    r.click("#itabs [data-it=zemin]", pause=0.8)
    r.click("[data-f=herringbone_parquet]", pause=0.5, snap_after=False)
    r.click("#iall1", pause=3.0); r.wait(0.9); r.mark("floor")
    r.click("#itabs [data-it=duvar]", pause=0.8)
    r.click("[data-p=adacayi]", pause=1.5); r.wait(0.9); r.mark("paint")
    r.cap(t1, r.t, "Zemin kaplaması ve duvar boyası — metraj anında hesaplanır")
    t2 = r.t
    r.click("#idemo", pause=0.8); r.wait(0.4)
    # bölme duvarı (Daire 1 salon|mutfak) ekranda bul, üstüne gel, tıkla
    xy = pg.evaluate("""() => { const {V, toWorld} = window.ARCHAI; const p = toWorld(8.9, 9.45, 1.3).project(V.C);
      const r = document.querySelector('#cv').getBoundingClientRect(); return [r.left + (p.x + 1) / 2 * r.width, r.top + (1 - p.y) / 2 * r.height]; }""")
    r.move(xy[0], xy[1], 0.7); pg.mouse.move(xy[0], xy[1]); pg.wait_for_timeout(1200); r.snap(); r.wait(0.8); r.mark("hover")
    r.clicks.append(round(r.t, 3)); pg.mouse.click(xy[0], xy[1]); pg.wait_for_timeout(2500); r.t += 0.15; r.snap(); r.wait(1.8); r.mark("demolish")
    r.cap(t2, r.t, "Bölme duvarı yık — taşıyıcı duvar korunur")
    return r

if __name__ == "__main__":
    with sync_playwright() as p:
        b = p.chromium.launch(args=ARGS)
        pg = b.new_page(viewport={"width": 1600, "height": 900}, device_scale_factor=1.2)
        errs = []; pg.on("pageerror", lambda e: errs.append(str(e)))
        r = part1(pg); r = part2(pg, r); r = part3(pg, r)
        r.dump("ui_a"); print("süre", r.t, "kare", len(r.frames), "hata", errs[:3]); b.close()
