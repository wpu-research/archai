"""Teslim için demo ekran kaydı (Playwright + Google Chrome, 1280×720) → teslim/archai_demo.webm"""
import asyncio, json
from pathlib import Path
from playwright.async_api import async_playwright

KOK = Path(__file__).resolve().parent.parent
OUT = KOK / "teslim"


async def main():
    d = json.loads((KOK / "demo/demo.json").read_text())
    async with async_playwright() as p:
        b = await p.chromium.launch(channel="chrome", args=["--autoplay-policy=no-user-gesture-required"])
        ctx = await b.new_context(viewport={"width": 1280, "height": 720}, record_video_dir=str(OUT / "ham"),
                                  record_video_size={"width": 1280, "height": 720})
        pg = await ctx.new_page()
        await pg.goto("http://127.0.0.1:8765/demo?hiz=1.4")
        await pg.wait_for_timeout(3500)                                   # portföy: villa
        await pg.select_option("#semt", "Kartal"); await pg.wait_for_timeout(800)
        await pg.locator("#go").click()
        await pg.wait_for_selector("#repbtn", state="visible", timeout=60000)   # akış biter
        await pg.wait_for_timeout(2500)
        await pg.locator("#kart1").scroll_into_view_if_needed(); await pg.wait_for_timeout(1500)
        await pg.locator("#kart1 .fb").click(); await pg.wait_for_timeout(13000)  # film: cephe → salon
        await pg.locator("#vmodal .x").click(); await pg.wait_for_timeout(800)
        await pg.locator("#kart1 .kb").click(); await pg.wait_for_timeout(2500)   # kampanya + Instagram
        await pg.mouse.wheel(0, 500); await pg.wait_for_timeout(2500)
        await pg.locator(".post .yay").click(); await pg.wait_for_timeout(2500)
        await pg.locator("#kmodal .x").click(); await pg.wait_for_timeout(600)
        await pg.locator("#repbtn").click(); await pg.wait_for_timeout(3000)     # rapor
        await pg.mouse.move(640, 400); await pg.mouse.wheel(0, 700); await pg.wait_for_timeout(3500)
        await pg.mouse.wheel(0, 900); await pg.wait_for_timeout(3000)
        await pg.locator("#rmodal .x").click(); await pg.wait_for_timeout(500)
        await pg.goto(d["kartlar"][1]["model_3d"]); await pg.wait_for_timeout(9000)  # 3D model
        await pg.locator("#walk").click(); await pg.wait_for_timeout(2500)        # salonda yürü
        await pg.keyboard.down("KeyW"); await pg.wait_for_timeout(1200); await pg.keyboard.up("KeyW")
        for _ in range(30):
            await pg.mouse.move(640 + 6, 400); await pg.wait_for_timeout(80)
        await pg.keyboard.down("KeyW"); await pg.wait_for_timeout(1000); await pg.keyboard.up("KeyW")
        await pg.wait_for_timeout(2500)
        await ctx.close(); await b.close()
    vids = sorted((OUT / "ham").glob("*.webm"), key=lambda f: f.stat().st_mtime)
    vids[-1].replace(OUT / "archai_demo.webm")
    print("KAYIT:", OUT / "archai_demo.webm")

asyncio.run(main())
