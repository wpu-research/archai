"""Teslim videosu 4K (3840×2160): Chrome CDP ekran yayınından kareler → teslim/kareler/ + zaman damgaları.

Sahne sınırları (altyazı için) teslim/sahneler.json'a yazılır. Birleştirme: scripts/video4k.sh
"""
import asyncio
import base64
import json
import time
from pathlib import Path

from playwright.async_api import async_playwright

KOK = Path(__file__).resolve().parent.parent
OUT = KOK / "teslim" / "kareler"


async def main():
    d = json.loads((KOK / "demo/demo.json").read_text())
    OUT.mkdir(parents=True, exist_ok=True)
    for f in OUT.glob("*.jpg"):
        f.unlink()
    kareler, sahne, t0, bosluk = [], [], [None], []
    kayit = [True]

    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required", "--enable-gpu", "--ignore-gpu-blocklist"])
        ctx = await b.new_context(viewport={"width": 1920, "height": 1080}, device_scale_factor=2)
        pg = await ctx.new_page()
        cdp = await ctx.new_cdp_session(pg)

        async def on_frame(ev):
            try:
                await cdp.send("Page.screencastFrameAck", {"sessionId": ev["sessionId"]})
            except Exception:
                pass
            if not kayit[0]:
                return
            ts = ev["metadata"]["timestamp"]
            t0[0] = t0[0] or ts
            n = len(kareler)
            (OUT / f"{n:06d}.jpg").write_bytes(base64.b64decode(ev["data"]))
            kareler.append(ts)

        cdp.on("Page.screencastFrame", lambda ev: asyncio.ensure_future(on_frame(ev)))

        async def yayin():
            await cdp.send("Page.startScreencast", {"format": "jpeg", "quality": 92, "maxWidth": 3840,
                                                    "maxHeight": 2160, "everyNthFrame": 1})

        def isaret(ad):
            sahne.append({"ad": ad, "t": time.time()})

        await pg.goto("http://127.0.0.1:8765/demo?hiz=1.4"); await pg.wait_for_timeout(1500)
        await yayin(); isaret("acilis")
        await pg.wait_for_timeout(3500)
        await pg.select_option("#semt", "Kartal"); await pg.wait_for_timeout(600)
        isaret("arama"); await pg.locator("#go").click()
        await pg.wait_for_selector("#repbtn", state="visible", timeout=60000)
        isaret("sonuc"); await pg.wait_for_timeout(2500)
        await pg.locator("#kart1").scroll_into_view_if_needed(); await pg.wait_for_timeout(1200)
        isaret("film"); await pg.locator("#kart1 .fb").click(); await pg.wait_for_timeout(13000)
        await pg.locator("#vmodal .x").click(); await pg.wait_for_timeout(600)
        isaret("kampanya"); await pg.locator("#kart1 .kb").click(); await pg.wait_for_timeout(2500)
        await pg.mouse.move(960, 600); await pg.mouse.wheel(0, 500); await pg.wait_for_timeout(2200)
        await pg.locator(".post .yay").click(); await pg.wait_for_timeout(2200)
        await pg.locator("#kmodal .x").click(); await pg.wait_for_timeout(500)
        isaret("rapor"); await pg.locator("#repbtn").click(); await pg.wait_for_timeout(3000)
        await pg.mouse.wheel(0, 700); await pg.wait_for_timeout(3200)
        await pg.mouse.wheel(0, 900); await pg.wait_for_timeout(2800)
        await pg.locator("#rmodal .x").click()
        # 3D: yükleme sırasında kayıt durur
        kayit[0] = False; bosluk.append(len(kareler) - 1)  # bu karenin süresi kısa tutulacak
        await pg.goto(d["kartlar"][1]["model_3d"]); await pg.wait_for_timeout(9000)
        await yayin(); kayit[0] = True
        isaret("model"); await pg.wait_for_timeout(4500)
        isaret("yuru"); await pg.locator("#walk").click(); await pg.wait_for_timeout(2000)
        await pg.keyboard.down("KeyW"); await pg.wait_for_timeout(1100); await pg.keyboard.up("KeyW")
        for _ in range(25):
            await pg.mouse.move(960 + 5, 540); await pg.wait_for_timeout(80)
        await pg.keyboard.down("KeyW"); await pg.wait_for_timeout(900); await pg.keyboard.up("KeyW")
        await pg.wait_for_timeout(2500)
        isaret("son")
        await cdp.send("Page.stopScreencast"); await b.close()

    # kayıt dışı aralığı (3D yükleme) zaman çizgisinden çıkar: kare süreleri ardışık farklardan
    sure = []
    for i, ts in enumerate(kareler):
        dt = (kareler[i + 1] - ts) if i + 1 < len(kareler) else 0.5
        sure.append(0.04 if i in bosluk else dt)  # yalnız 3D yükleme boşluğu atlanır; sabit sahneler gerçek süresinde
    (OUT.parent / "kareler.txt").write_text("".join(f"file 'kareler/{i:06d}.jpg'\nduration {s:.4f}\n"
                                                    for i, s in enumerate(sure)) + f"file 'kareler/{len(sure) - 1:06d}.jpg'\n")
    # sahne zamanlarını video zamanına çevir (kare zaman damgası → kümülatif süre)
    birikim, t = [], 0.0
    for s in sure:
        birikim.append(t); t += s
    def vzaman(gercek):
        i = min(range(len(kareler)), key=lambda j: abs(kareler[j] - gercek))
        return round(birikim[i], 2)
    (OUT.parent / "sahneler.json").write_text(json.dumps(
        [{"ad": s["ad"], "t": vzaman(s["t"])} for s in sahne] + [{"ad": "toplam", "t": round(t, 2)}], indent=1))
    print("KARE:", len(kareler), "SÜRE:", round(t, 1), "ORT FPS:", round(len(kareler) / t, 1))


asyncio.run(main())
