import os
import sys, time, json, urllib.request, shutil
from playwright.sync_api import sync_playwright
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
SUBMIT = """async ({maket}) => {
  const out = await window.IN.exportForRender('still', {maket});
  const job = {...out.job, hq: true};
  const fd = new FormData(); fd.append('scene', new Blob([out.glb], {type: 'model/gltf-binary'}), 'scene.glb'); fd.append('job', JSON.stringify(job));
  const r = await fetch(`/api/projects/${location.hash.slice(1)}/real`, {method: 'POST', body: fd}); return await r.json(); }"""
CLOSE = """() => { const seen = new Set(); window.ARCHAI.V.root.traverse(o => { const d = o.userData.door;
  if (d && o.isGroup && !seen.has(d)) { seen.add(d); d.cur = d.tgt = d.th0; o.rotation.y = d.th0; } }); return seen.size; }"""
jobs = {}
with sync_playwright() as p:
    b = p.chromium.launch(args=ARGS)
    pg = b.new_page(viewport={"width": 1600, "height": 900})
    pg.goto(f"{BASE}/?vm=real&nointro=1#{HERO}"); time.sleep(12); fullbleed(pg)
    pg.evaluate("() => { const l = document.querySelector('#lv'); l.value = l.max; l.dispatchEvent(new Event('input')); }"); time.sleep(2)
    pg.evaluate("""() => { const {V, toWorld} = window.ARCHAI; V.O.autoRotate = false;
      V.O.target.copy(toWorld(15, 13, 5.8)); V.C.position.copy(toWorld(-17, -11, 13)); V.C.fov = 36; V.C.updateProjectionMatrix(); V.C.lookAt(V.O.target); V.O.update(); V.C.updateMatrixWorld(); }""")
    time.sleep(2); settle(pg, 3)
    jobs["dis"] = pg.evaluate(SUBMIT, {"maket": False})["id"]; print("dis", jobs["dis"], flush=True)
    pg.evaluate("document.querySelector('#lv').value = 1"); pg.evaluate("document.querySelector('#walk').click()"); time.sleep(3)
    print("kapı kapatıldı:", pg.evaluate(CLOSE))
    for k, (x, y, dx, dy) in {"mutfak": (8.0, 10.2, -1, 0.5), "yatak": (9.4, 14.3, -1, -0.25)}.items():
        pg.evaluate("([x,y,yaw]) => window.WALK_SET(x,y,yaw)", [x, y, yaw_to(dx, dy)]); time.sleep(1); settle(pg, 3)
        jobs[k] = pg.evaluate(SUBMIT, {"maket": False})["id"]; print(k, jobs[k], flush=True)
    b.close()
for k, jid in jobs.items():
    for _ in range(240):
        j = json.load(urllib.request.urlopen(f"{BASE}/api/jobs/{jid}"))
        if j["status"] in ("done", "error"): break
        time.sleep(3)
    print(k, j["status"], j.get("elapsed"), j.get("error"), flush=True)
    if j["status"] == "done": shutil.copy(f"{W}/out/projects/{HERO}/real/{jid}/foto.jpg", f"{W}/cycles/{k}.jpg")
print("BİTTİ", flush=True)
