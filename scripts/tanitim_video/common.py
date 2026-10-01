import os
import json, math, time
W = os.environ.get("ARCHAI_PROMO_DIR") or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "out", "promo"))
HERO = open(f"{W}/hero_id").read().strip() if os.path.exists(f"{W}/hero_id") else ""
BASE = os.environ.get("ARCHAI_URL", "http://localhost:8070")
ARGS = ["--use-gl=angle", "--use-angle=gl", "--ignore-gpu-blocklist", "--disable-gpu-sandbox", "--enable-gpu-rasterization"]   # RTX 4070 (swiftshader ~40 sn/kare)
# sanal saat: animasyonlar performance.now() ile ilerler; kare kare çekimde elle ilerletilir
VCLOCK = "(() => { let t = 0; performance.now = () => t; window.__adv = ms => { t += ms; return t; }; })();"
CURSOR_OFF = ""
def yaw_to(dx, dy):  # YÜRÜ: ileri = (−sin yaw, cos yaw)
    return math.atan2(-dx, dy)
def settle(pg, n=2):
    pg.evaluate("n => new Promise(r => { let k = n; const f = () => --k <= 0 ? r() : requestAnimationFrame(f); requestAnimationFrame(f); })", n)
# görüntüleyiciyi pencerenin tamamına yay (16:9 çekim): HUD kalır, alttaki sekmeler örtülür
FULLBLEED = ".vp{position:fixed!important;left:0!important;top:0!important;width:100vw!important;height:100vh!important;z-index:60!important;border-radius:0!important;margin:0!important}"
def fullbleed(pg):
    pg.add_style_tag(content=FULLBLEED); pg.wait_for_timeout(600)
