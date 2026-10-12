"""ArchAI Growth Console: Manus görevini API'den başlatır, ilerlemeyi ve kampanya kartlarını gösterir.

Yalnız bu makineden açılır (tünelden gelen istek reddedilir): Manus API anahtarı kredi harcatır.
"""

import json
import re
import time
from pathlib import Path

import httpx
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response

import server as S

KOK = Path(__file__).parent
MANUS = "https://api.manus.ai/v2"
DURUM = KOK / "logs" / "console_state.json"
TEST_RE = re.compile(r"test|kucuk|cekme|hizli-fizibilite|500-m-parsel")


def _yerel(request: Request) -> bool:
    # cloudflared isteği 127.0.0.1'den iletir ama cf-connecting-ip ekler
    return request.client.host in ("127.0.0.1", "::1") and "cf-connecting-ip" not in request.headers


def _hdr() -> dict:
    import os
    return {"x-manus-api-key": os.environ.get("MANUS_API_KEY", "")}


def _durum() -> dict:
    return json.loads(DURUM.read_text()) if DURUM.exists() else {}


async def sayfa(request: Request):
    if not _yerel(request):
        return Response(status_code=404)
    return FileResponse(KOK / "console.html")


async def baslat(request: Request):
    if not _yerel(request):
        return Response(status_code=404)
    body = await request.json()
    semt = re.sub(r"[^A-Za-zÇĞİÖŞÜçğıöşü ]", "", str(body.get("semt") or "Kartal"))[:30] or "Kartal"
    talimat = (KOK / "prompts" / "manus_kartal.md").read_text().replace("Kartal", semt)
    async with httpx.AsyncClient(timeout=60) as cl:
        con = (await cl.get(f"{MANUS}/connector.list", headers=_hdr())).json().get("connectors", [])
        ids = [c["id"] for c in con if re.match(r"(archai|apify|fal)", c.get("name", ""), re.I)]
        r = (await cl.post(f"{MANUS}/task.create", headers=_hdr(), json={
            "message": {"content": talimat, "connectors": ids},
            "title": f"ArchAI kampanya — {semt}", "share_visibility": "public"})).json()
    if not r.get("ok"):
        return JSONResponse(r, status_code=502)
    DURUM.write_text(json.dumps({"task_id": r["task_id"], "task_url": r.get("task_url"),
                                 "share_url": r.get("share_url"), "semt": semt, "basla": time.time()}))
    return JSONResponse({"task_id": r["task_id"], "task_url": r.get("task_url"), "share_url": r.get("share_url")})


async def _son_gorev(cl: httpx.AsyncClient) -> dict:
    d = _durum()
    if d.get("task_id"):
        return d
    t = (await cl.get(f"{MANUS}/task.list", headers=_hdr(), params={"limit": 1})).json()
    g = (t.get("tasks") or t.get("data") or [{}])[0]
    return {"task_id": g.get("id"), "basla": float(g.get("created_at") or 0)}


def _metin(m: dict) -> str | None:
    am = m.get("assistant_message")
    if isinstance(am, dict) and isinstance(am.get("content"), str):
        return am["content"]
    return None


async def durum(request: Request):
    if not _yerel(request):
        return Response(status_code=404)
    async with httpx.AsyncClient(timeout=30) as cl:
        g = await _son_gorev(cl)
        tid, basla = g.get("task_id"), g.get("basla") or 0
        detay, akis = {}, []
        if tid:
            dj = (await cl.get(f"{MANUS}/task.detail", headers=_hdr(), params={"task_id": tid})).json()
            detay = dj.get("task", dj)
            mj = (await cl.get(f"{MANUS}/task.listMessages", headers=_hdr(),
                               params={"task_id": tid, "limit": 40, "order": "desc"})).json()
            for m in reversed(mj.get("messages", [])):
                if (t := _metin(m)):
                    akis.append({"zaman": int(m.get("timestamp", 0)) // 1000, "metin": t})
        # gösterilecek projeler: görev başladıktan sonra ArchAI'de üretilenler (test adları hariç)
        liste = (await cl.get(f"{S.ARCHAI}/api/projects")).json()
    kayit = json.loads(S.KAYIT.read_text()) if S.KAYIT.exists() else {}
    kartlar = []
    for p in liste:
        pid = p["id"]
        t0 = time.mktime(time.strptime(pid[:15], "%Y%m%d-%H%M%S"))
        if t0 < basla - 60 or TEST_RE.search(pid):
            continue
        k = kayit.get(pid, {})
        if "ozet" not in k:
            try:
                S._kaydet(pid, "ozet", S._summary(await S._get(pid)))
                k = json.loads(S.KAYIT.read_text())[pid]
            except Exception:
                continue
        kartlar.append({"proje_id": pid, **k})
    def skor(k):
        o = ((k.get("kat_karsiligi") or {}).get("onerilen") or {})
        return (o.get("muteahhit_marj_pct", -1e9), (k.get("karlilik") or {}).get("getiri_pct", -1e9))
    kartlar.sort(key=skor, reverse=True)
    return JSONResponse({"gorev": {"id": tid, "durum": detay.get("status"), "url": detay.get("task_url") or g.get("task_url"),
                                   "share_url": detay.get("share_url") or g.get("share_url"),
                                   "kredi": detay.get("credit_usage"), "baslik": detay.get("title"),
                                   "basla": basla},
                         "akis": akis[-25:], "kartlar": kartlar})


async def render(request: Request):
    """Konsoldan tek tıkla render (Manus render üretmediyse)."""
    if not _yerel(request):
        return Response(status_code=404)
    pid = request.path_params["pid"]
    try:
        return JSONResponse(await S.render_cephe(pid))
    except Exception as e:
        return JSONResponse({"hata": str(e)[:300]}, status_code=502)


def kur(app) -> None:
    app.add_route("/console", sayfa, methods=["GET"])
    app.add_route("/console/api/baslat", baslat, methods=["POST"])
    app.add_route("/console/api/durum", durum, methods=["GET"])
    app.add_route("/console/api/render/{pid}", render, methods=["POST"])
