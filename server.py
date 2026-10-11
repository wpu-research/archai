"""ArchAI → Manus uzak MCP sunucusu.

ArchAI (127.0.0.1:8000) dışarı açılmaz; yalnız bu ince katman tünelle açılır.
- /mcp      : Bearer token ister (ARCHAI_MCP_TOKEN)
- /f/...    : imzalı dosya linkleri (fal.ai / Manus token'sız indirebilsin diye), yalnız çıktı dosyaları
"""

import hashlib
import hmac
import os
import io
import re
from pathlib import Path
from typing import Literal

import httpx
import uvicorn
from mcp.server.mcpserver import MCPServer
from PIL import Image
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse, Response


def _load_env():
    p = Path(__file__).with_name(".env")
    if p.exists():
        for line in p.read_text().splitlines():
            line = line.split("#", 1)[0].strip()
            if "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())


_load_env()
TOKEN = os.environ.get("ARCHAI_MCP_TOKEN", "")
ARCHAI = (os.environ.get("ARCHAI_URL") or "http://127.0.0.1:8000").rstrip("/")
PUBLIC = (os.environ.get("ARCHAI_PUBLIC_URL") or "http://127.0.0.1:8765").rstrip("/")
if len(TOKEN) < 24:
    raise SystemExit("ARCHAI_MCP_TOKEN en az 24 karakter olmalı (.env)")

PID_RE = re.compile(r"\d{8}-\d{6}-[a-z0-9-]+")
FILE_RE = re.compile(r"(cizimler/)?[A-Za-z0-9_.-]+\.(png|pdf|docx|xlsx|dxf)")
AVAN = ("Avan / ön fizibilite: fiyatlar örnek birim fiyatlardır, taşıyıcı sistem ve temel kalemleri "
        "dahil değildir; kesin teklif için proje ve güncel birim fiyat gerekir.")

mcp = MCPServer(
    "archai",
    instructions=(
        "ArchAI: arsa ya da brüt alandan avan mimari proje, metraj, maliyet ve teklif üretir. "
        "Rakamları müşteriye her zaman 'ön fizibilite' olarak sun. Görsel üretmek için "
        "dönen 'gorunus_png' linkini görüntüden görüntüye bir modele (ör. fal.ai) ver."
    ),
)


def _sign(path: str) -> str:
    return hmac.new(TOKEN.encode(), path.encode(), hashlib.sha256).hexdigest()[:32]


def _link(url_path: str) -> str:
    """ArchAI '/files/<pid>/<yol>' → imzalı genel link."""
    rel = url_path.removeprefix("/files/")
    return f"{PUBLIC}/f/{rel}?s={_sign(rel)}"


def _summary(p: dict) -> dict:
    c, s, r = p["cost"], p["summary"], p["report"]
    daireler = {x["name"].rsplit("/", 1)[0] for x in p["rooms"] if "/Daire " in x["name"]}
    sheets = {sh["name"]: _link(sh["png"]) for sh in p.get("sheets", [])}
    return {
        "proje_id": p["id"],
        "ad": p["name"],
        "parsel_m2": r.get("parcel_area"),
        "kat_sayisi": r.get("floors"),
        "daire_tipi": r.get("unit_type"),
        "daire_sayisi": len(daireler),
        "brut_insaat_m2": round(s["gross_floor_area"], 1),
        "maliyet_kdv_dahil_tl": round(c["total"]),
        "maliyet_m2_kdv_dahil_tl": round(c["per_m2"]),
        "imar_uyarilari": r.get("warnings", []),
        "sanal_parsel": bool(r.get("virtual_parcel")),
        "dosyalar": {
            "teklif_docx": _link(p["files"]["teklif_docx"]),
            "metraj_maliyet_xlsx": _link(p["files"]["metraj_maliyet_xlsx"]),
            "teknik_sartname_docx": _link(p["files"]["sartname_docx"]),
            "cizimler_pdf": _link(p["files"]["cizim_pdf"]),
        },
        "gorunus_png": f"{PUBLIC}/g/{p['id']}.png?s={_sign('g/' + p['id'])}",
        "pafta_png": sheets,
        "not": AVAN,
    }


async def _create(brief: dict) -> dict:
    async with httpx.AsyncClient(timeout=300) as cl:
        resp = await cl.post(f"{ARCHAI}/api/projects", json=brief)
    if resp.status_code != 200:
        raise ValueError(f"ArchAI {resp.status_code}: {resp.text[:500]}")
    return _summary(resp.json())


DaireTipi = Literal["1+1", "2+1", "3+1", "4+1"]


@mcp.tool()
async def hizli_fizibilite(ad: str, brut_alan_m2: float, kat_sayisi: int, daire_tipi: DaireTipi = "2+1") -> dict:
    """Yalnız toplam brüt inşaat alanı ve kat sayısından avan proje + metraj + maliyet + teklif üretir.

    Arsa ölçüsü bilinmiyorsa bunu kullan (ArchAI sanal bir parsel varsayar).
    brut_alan_m2: 30–100000, kat_sayisi: 1–30.
    """
    return await _create({"name": ad[:120], "quick": {"gross_area": brut_alan_m2, "floors": kat_sayisi,
                                                       "unit_type": daire_tipi}})


@mcp.tool()
async def arsa_fizibilite(ad: str, cephe_m: float, derinlik_m: float, taks: float, kaks: float,
                          maks_kat: int | None = None, on_cekme_m: float = 5, yan_cekme_m: float = 3,
                          arka_cekme_m: float = 3, daire_tipi: DaireTipi = "2+1") -> dict:
    """Arsa ölçüsü ve imar durumundan (TAKS, KAKS/emsal, çekme mesafeleri) en uygun kütleyi kurar;
    avan proje + metraj + maliyet + teklif üretir. İlandaki arsa m² verilip ölçü yoksa kare kabul et
    (cephe = derinlik = √alan) ve bunu kullanıcıya söyle.
    """
    zoning = {"taks": taks, "kaks": kaks, "front": on_cekme_m, "side": yan_cekme_m, "rear": arka_cekme_m}
    if maks_kat:
        zoning["max_floors"] = maks_kat
    return await _create({"name": ad[:120], "parcel": {"width": cephe_m, "depth": derinlik_m},
                          "zoning": zoning, "program": {"unit_type": daire_tipi}})


@mcp.tool()
async def proje_ozet(proje_id: str) -> dict:
    """Daha önce üretilmiş bir projenin özetini ve dosya linklerini döner."""
    if not PID_RE.fullmatch(proje_id):
        raise ValueError("geçersiz proje_id")
    async with httpx.AsyncClient(timeout=30) as cl:
        resp = await cl.get(f"{ARCHAI}/api/projects/{proje_id}")
    if resp.status_code != 200:
        raise ValueError(f"ArchAI {resp.status_code}: {resp.text[:300]}")
    return _summary(resp.json())


app = mcp.streamable_http_app(
    stateless_http=True,
    # Host kontrolü tünel adına izin vermez; güvenlik Bearer token ile sağlanıyor.
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


async def files(request: Request):
    rel = request.path_params["rel"]
    pid, _, path = rel.partition("/")
    if not (PID_RE.fullmatch(pid) and FILE_RE.fullmatch(path)
            and hmac.compare_digest(request.query_params.get("s", ""), _sign(rel))):
        return Response(status_code=404)
    async with httpx.AsyncClient(timeout=60) as cl:
        resp = await cl.get(f"{ARCHAI}/files/{rel}")
    if resp.status_code != 200:
        return Response(status_code=404)
    headers = {k: v for k, v in resp.headers.items() if k.lower() in ("content-type", "content-disposition")}
    return Response(resp.content, headers=headers)


async def facade(request: Request):
    """Ön görünüş paftasından yalnız bina cephesi (antet ve çerçeve kırpılmış): görüntüden görüntüye modeller için."""
    pid = request.path_params["pid"]
    if not (PID_RE.fullmatch(pid) and hmac.compare_digest(request.query_params.get("s", ""), _sign("g/" + pid))):
        return Response(status_code=404)
    async with httpx.AsyncClient(timeout=60) as cl:
        resp = await cl.get(f"{ARCHAI}/files/{pid}/cizimler/05_on_gorunus.png")
    if resp.status_code != 200:
        return Response(status_code=404)
    im = Image.open(io.BytesIO(resp.content)).convert("L")
    w, h = im.size
    inner = im.crop((int(w * 0.06), int(h * 0.05), int(w * 0.94), int(h * 0.71)))  # dış çerçeve ve antet dışarıda
    box = inner.point(lambda v: 255 if v < 128 else 0).getbbox()
    if box:
        pad = 30
        inner = inner.crop((max(box[0] - pad, 0), max(box[1] - pad, 0),
                            min(box[2] + pad, inner.width), min(box[3] + pad, inner.height)))
    buf = io.BytesIO()
    inner.convert("RGB").save(buf, "PNG")
    return Response(buf.getvalue(), media_type="image/png")


app.add_route("/f/{rel:path}", files, methods=["GET"])
app.add_route("/g/{pid}.png", facade, methods=["GET"])


class BearerAuth:
    def __init__(self, inner):
        self.inner = inner

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http" and scope["path"].startswith("/mcp"):
            auth = dict(scope["headers"]).get(b"authorization", b"").decode()
            if not hmac.compare_digest(auth, f"Bearer {TOKEN}"):
                await JSONResponse({"error": "unauthorized"}, status_code=401)(scope, receive, send)
                return
        await self.inner(scope, receive, send)


if __name__ == "__main__":
    uvicorn.run(BearerAuth(app), host="127.0.0.1", port=int(os.environ.get("PORT", 8765)))
