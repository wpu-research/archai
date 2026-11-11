"""ArchAI → Manus uzak MCP sunucusu.

ArchAI (127.0.0.1:8000) dışarı açılmaz; yalnız bu ince katman tünelle açılır.
- /mcp      : Bearer token ister (ARCHAI_MCP_TOKEN)
- /f/...    : imzalı dosya linkleri (fal.ai / Manus token'sız indirebilsin diye), yalnız çıktı dosyaları
"""

import asyncio
import hashlib
import hmac
import os
import io
import json
import time
import re
import statistics
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
ARCHAI_TOKEN = os.environ.get("ARCHAI_TOKEN", "")
if len(TOKEN) < 24:
    raise SystemExit("ARCHAI_MCP_TOKEN en az 24 karakter olmalı (.env)")
if not ARCHAI_TOKEN:
    raise SystemExit("ARCHAI_TOKEN (core API erişim anahtarı) tanımlı değil (.env)")

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


KAYIT = Path(__file__).with_name("logs") / "kampanya.json"


def _kaydet(pid: str, alan: str, veri) -> None:
    """Konsol için: proje başına son araç sonuçlarını yerel bir JSON'a yazar."""
    KAYIT.parent.mkdir(exist_ok=True)
    d = json.loads(KAYIT.read_text()) if KAYIT.exists() else {}
    d.setdefault(pid, {})[alan] = veri
    d[pid]["guncel"] = time.time()
    tmp = KAYIT.with_suffix(".tmp")
    tmp.write_text(json.dumps(d, ensure_ascii=False))
    tmp.replace(KAYIT)


def _sign(path: str) -> str:
    return hmac.new(TOKEN.encode(), path.encode(), hashlib.sha256).hexdigest()[:32]


def _link(url_path: str) -> str:
    """ArchAI '/files/<pid>/<yol>' → imzalı genel link."""
    rel = url_path.removeprefix("/files/")
    return f"{PUBLIC}/f/{rel}?s={_sign(rel)}"


def _daireler(p: dict) -> set[str]:
    return {x["name"].rsplit("/", 1)[0] for x in p["rooms"] if "/Daire " in x["name"]}


def _satilabilir_m2(p: dict) -> float:
    """Brüt alanın daire payı: ortak alanlar (hol, merdiven, asansör) net alan oranında düşülür."""
    net = sum(x["area"] for x in p["rooms"])
    daire = sum(x["area"] for x in p["rooms"] if "/Daire " in x["name"])
    return p["summary"]["gross_floor_area"] * (daire / net if net else 0)


def _summary(p: dict) -> dict:
    c, s, r = p["cost"], p["summary"], p["report"]
    daireler = _daireler(p)
    sheets = {sh["name"]: _link(sh["png"]) for sh in p.get("sheets", [])}
    return {
        "proje_id": p["id"],
        "ad": p["name"],
        "parsel_m2": r.get("parcel_area"),
        "kat_sayisi": r.get("floors"),
        "daire_tipi": r.get("unit_type"),
        "daire_sayisi": len(daireler),
        "brut_insaat_m2": round(s["gross_floor_area"], 1),
        "satilabilir_brut_m2": round(_satilabilir_m2(p), 1),
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
        "model_3d_link": _view_link(p["id"]),  # tarayıcıda döndürülebilir 3D bina
        "gezinti_3d_link": _view_link(p["id"]) + "&walk=salon&tour=1",  # döşenmiş salonda birinci şahıs gezinti
        "not": AVAN,
    }


async def _create(brief: dict) -> dict:
    async with httpx.AsyncClient(timeout=300) as cl:
        resp = await cl.post(f"{ARCHAI}/api/projects", json=brief, headers=_core_auth())
    if resp.status_code == 422:
        # arsa imar/çekme nedeniyle yapılaşmaya uygun değil: hata değil, Manus'un atlayacağı bir sonuç
        try:
            neden = resp.json().get("detail")
        except ValueError:
            neden = resp.text[:300]
        return {"uygun": False, "neden": neden if isinstance(neden, str) else str(neden)[:300],
                "oneri": "Bu arsayı ele ve sıradakine geç. Küçük parsellerde imar planı daha küçük çekme "
                         "(ör. ön 3, yan 2, arka 2) tanıyorsa onunla bir kez yeniden dene ve bunu raporda belirt."}
    if resp.status_code != 200:
        raise ValueError(f"ArchAI {resp.status_code}: {resp.text[:500]}")
    ozet = _summary(resp.json())
    _kaydet(ozet["proje_id"], "ozet", ozet)
    return ozet


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
    # Çekme verilmediyse (varsayılan 5/3/3) küçük parseller için kademeli dene: ilanlarda çekme yazmıyor,
    # Kartal gibi semtlerde küçük parsellerde daha küçük çekme veya bitişik nizam yaygın.
    kademeler = [(on_cekme_m, yan_cekme_m, arka_cekme_m)]
    if kademeler[0] == (5, 3, 3):
        kademeler += [(3, 2, 2), (3, 0, 2)]
    for on, yan, arka in kademeler:
        zoning = {"taks": taks, "kaks": kaks, "front": on, "side": yan, "rear": arka}
        if maks_kat:
            zoning["max_floors"] = maks_kat
        sonuc = await _create({"name": ad[:120], "parcel": {"width": cephe_m, "depth": derinlik_m},
                               "zoning": zoning, "program": {"unit_type": daire_tipi}})
        if sonuc.get("uygun") is not False:
            sonuc["cekme_varsayimi"] = (f"ön {on} m, yan {yan} m, arka {arka} m"
                                        + ("" if (on, yan, arka) == kademeler[0] else
                                           " (5/3/3 sığmadığı için küçültüldü; imar durumu belgesiyle teyit edilmeli)"))
            _kaydet(sonuc["proje_id"], "ozet", sonuc)
            return sonuc
    sonuc["denenen_cekmeler"] = [f"{a}/{b}/{c}" for a, b, c in kademeler]
    return sonuc


def _core_auth() -> dict:
    """Core API her istekte anahtar ister (baslat.sh core'u ARCHAI_TOKEN ile başlatır)."""
    return {"Authorization": f"Bearer {ARCHAI_TOKEN}"}


async def _get(proje_id: str) -> dict:
    if not PID_RE.fullmatch(proje_id):
        raise ValueError("geçersiz proje_id")
    async with httpx.AsyncClient(timeout=30) as cl:
        resp = await cl.get(
            f"{ARCHAI}/api/projects/{proje_id}",
            headers=_core_auth(),
        )
    if resp.status_code != 200:
        raise ValueError(f"ArchAI {resp.status_code}: {resp.text[:300]}")
    return resp.json()


async def _fizibilite_hesapla(
    proje_id: str,
    arsa_bedeli_tl: float,
    satis_m2_fiyati_tl: float,
    ek_gider_pct: float,
    satilabilir_alan_m2: float | None = None,
) -> dict:
    """Core fizibilite API'sini çağırır. Stale quantities reddedilir, hata net şekilde iletilir."""
    if not PID_RE.fullmatch(proje_id):
        raise ValueError("geçersiz proje_id")
    body = {
        "arsa_bedeli_tl": arsa_bedeli_tl,
        "satis_m2_fiyati_tl": satis_m2_fiyati_tl,
        "ek_gider_pct": ek_gider_pct,
    }
    body["satilabilir_alan_m2"] = (
        satilabilir_alan_m2 if satilabilir_alan_m2 is not None
        else _satilabilir_m2(await _get(proje_id))
    )
    headers = _core_auth()
    async with httpx.AsyncClient(timeout=30) as cl:
        resp = await cl.post(
            f"{ARCHAI}/api/projects/{proje_id}/fizibilite",
            json=body,
            headers=headers,
        )
    if resp.status_code == 401:
        raise ValueError("Core API yetkisiz: ARCHAI_TOKEN geçersiz veya eksik")
    if resp.status_code == 409:
        raise ValueError(f"Metraj referansı değişmiş: {resp.json().get('detail', 'ONAY sekmesinden yenileyin')}")
    if resp.status_code == 422:
        raise ValueError(f"Geçersiz girdi: {resp.json().get('detail', resp.text[:300])}")
    if resp.status_code != 200:
        raise ValueError(f"Core API {resp.status_code}: {resp.text[:500]}")
    result = resp.json()
    # source metadata ekle
    result["_kaynak"] = {
        "endpoint": "/api/projects/{pid}/fizibilite",
        "satilabilir_alan_kaynak": "explicit" if satilabilir_alan_m2 is not None else "inferred_from_project",
        "core_fingerprint": result.get("kaynak", {}).get("proje_parmak_izi"),
        "metraj_fingerprint": result.get("kaynak", {}).get("metraj_parmak_izi"),
    }
    return result


@mcp.tool()
async def proje_ozet(proje_id: str) -> dict:
    """Daha önce üretilmiş bir projenin özetini ve dosya linklerini döner."""
    return _summary(await _get(proje_id))


# --- fal.ai: Manus'un fal connector'ı kapalı olsa da render/video bu araçlarla üretilir --------------
FAL_KEY = os.environ.get("FAL_KEY", "")
FAL_IMAGE = os.environ.get("FAL_IMAGE_MODEL") or "fal-ai/flux-pro/kontext"
FAL_VIDEO = os.environ.get("FAL_VIDEO_MODEL") or "fal-ai/kling-video/v2.1/standard/image-to-video"
RENDER_PROMPT = ("Turn this architectural elevation line drawing into a photorealistic photo of the same modern "
                 "residential apartment building in Istanbul. Keep the exact window layout, floor count and proportions. "
                 "Light warm plaster facade, anthracite window frames, small balconies, street level with sidewalk and "
                 "trees, late afternoon sun, eye-level architectural photography, no text, no dimension lines.")
VIDEO_PROMPT = ("Slow cinematic camera push-in towards the building facade, gentle parallax, trees moving slightly "
                "in the breeze, warm late afternoon light, realistic, no text.")


async def _fal(model: str, payload: dict, wait_s: int) -> dict:
    if not FAL_KEY:
        raise ValueError("FAL_KEY tanımlı değil")
    h = {"Authorization": f"Key {FAL_KEY}"}
    async with httpx.AsyncClient(timeout=60) as cl:
        job = (await cl.post(f"https://queue.fal.run/{model}", headers=h, json=payload)).raise_for_status().json()
        for _ in range(wait_s // 3):
            st = (await cl.get(job["status_url"], headers=h)).json()
            if st.get("status") == "COMPLETED":
                return (await cl.get(job["response_url"], headers=h)).json()
            await asyncio.sleep(3)
    raise ValueError(f"fal {wait_s} sn içinde bitmedi (request_id {job.get('request_id')})")


@mcp.tool()
async def render_cephe(proje_id: str) -> dict:
    """Projenin ön görünüş çiziminden fal.ai ile fotogerçekçi bina fotoğrafı üretir (~15-30 sn).
    Dönen `render_url` kampanya sayfasında ve `tanitim_videosu` aracında kullanılır."""
    if not PID_RE.fullmatch(proje_id):
        raise ValueError("geçersiz proje_id")
    src = f"{PUBLIC}/g/{proje_id}.png?s={_sign('g/' + proje_id)}"
    res = await _fal(FAL_IMAGE, {"prompt": RENDER_PROMPT, "image_url": src}, 120)
    _kaydet(proje_id, "render_url", res["images"][0]["url"])
    return {"proje_id": proje_id, "render_url": res["images"][0]["url"], "kaynak_cizim": src, "model": FAL_IMAGE}


@mcp.tool()
async def tanitim_videosu(render_url: str, proje_id: str = "") -> dict:
    """`render_cephe` görselinden fal.ai ile 5 sn'lik yavaş kamera hareketli tanıtım videosu üretir (1-4 dk sürer)."""
    if not render_url.startswith("https://"):
        raise ValueError("render_url https olmalı")
    res = await _fal(FAL_VIDEO, {"prompt": VIDEO_PROMPT, "image_url": render_url, "duration": "5"}, 330)
    if PID_RE.fullmatch(proje_id):
        _kaydet(proje_id, "video_url", res["video"]["url"])
    return {"video_url": res["video"]["url"], "model": FAL_VIDEO}


@mcp.tool()
def bolge_m2_fiyati(ilanlar: list[dict]) -> dict:
    """Aynı semtteki satılık daire ilanlarından (her biri {"fiyat_tl": ..., "m2": ...}, m2 = brüt)
    m² satış fiyatını çıkarır. Uç değerler (en ucuz ve en pahalı %10) atılır, medyan döner.
    Sonucu `karlilik` ve `kat_karsiligi` araçlarına `satis_m2_fiyati_tl` olarak ver.
    """
    birim = sorted(float(i["fiyat_tl"]) / float(i["m2"]) for i in ilanlar
                   if float(i.get("m2") or 0) >= 30 and float(i.get("fiyat_tl") or 0) > 0)
    if len(birim) < 3:
        raise ValueError("en az 3 geçerli ilan gerekli (fiyat_tl > 0, m2 >= 30)")
    k = len(birim) // 10
    kirpik = birim[k:len(birim) - k]
    return {"satis_m2_fiyati_tl": round(statistics.median(kirpik)), "ilan_sayisi": len(birim),
            "min_tl_m2": round(kirpik[0]), "max_tl_m2": round(kirpik[-1])}


def _ekonomi(p: dict, satis_m2: float, ek_gider_pct: float) -> tuple[float, float, float]:
    gelir = _satilabilir_m2(p) * satis_m2
    insaat = p["cost"]["total"]
    return gelir, insaat, insaat * ek_gider_pct / 100


def _pct(a: float, b: float) -> float:
    return round(100 * a / b, 1) if b else 0.0


@mcp.tool()
async def karlilik(
    proje_id: str,
    arsa_fiyati_tl: float,
    satis_m2_fiyati_tl: float,
    ek_gider_pct: float = 10,
    satilabilir_alan_m2: float | None = None,
) -> dict:
    """Arsa satın alınarak yapılırsa tahmini kâr: satış geliri − (arsa + inşaat + ek giderler).

    ek_gider_pct: inşaat maliyetinin yüzdesi olarak ruhsat, proje, pazarlama, finansman (varsayılan %10).
    satilabilir_alan_m2: opsiyonel, açıkça verirse proje varsayımı (odalar net alanı oranı) yerine geçer.
    Birden çok arsayı `kar_tl` ya da `getiri_pct` ile sırala.
    """
    fiz = await _fizibilite_hesapla(
        proje_id=proje_id,
        arsa_bedeli_tl=arsa_fiyati_tl,
        satis_m2_fiyati_tl=satis_m2_fiyati_tl,
        ek_gider_pct=ek_gider_pct,
        satilabilir_alan_m2=satilabilir_alan_m2,
    )
    sonuc = {
        "proje_id": proje_id,
        "satilabilir_brut_m2": fiz["varsayimlar"]["satilabilir_alan_m2"],
        "satis_geliri_tl": fiz["sonuc"]["satis_geliri_tl"],
        "arsa_tl": fiz["varsayimlar"]["arsa_bedeli_tl"],
        "insaat_tl": fiz["sonuc"]["insaat_bedeli_tl"],
        "ek_gider_tl": fiz["sonuc"]["ek_gider_tl"],
        "toplam_yatirim_tl": fiz["sonuc"]["toplam_gider_tl"],
        "kar_tl": fiz["sonuc"]["tahmini_kar_tl"],
        "kar_marji_pct": fiz["sonuc"]["kar_marji_pct"],
        "getiri_pct": fiz["sonuc"]["maliyet_getirisi_pct"],
        "basabas_satis_m2_tl": fiz["sonuc"]["basabas_m2_fiyati_tl"],
        "not": AVAN + " Satış fiyatı ilan ortalamasıdır; vergi ve satış süresi dahil değildir.",
        "uyarilar": fiz.get("uyarilar", []),
        "_kaynak": fiz["_kaynak"],
    }
    _kaydet(proje_id, "karlilik", sonuc)
    return sonuc


@mcp.tool()
async def kat_karsiligi(
    proje_id: str,
    satis_m2_fiyati_tl: float,
    arsa_sahibi_payi_pct: float = 45,
    hedef_marj_pct: float = 20,
    ek_gider_pct: float = 10,
    satilabilir_alan_m2: float | None = None,
) -> dict:
    """Kat karşılığı anlaşma: arsa sahibine daire verilir, müteahhit kalan daireleri satar (arsa parası yok).

    Verilen payla daire paylaşımını ve müteahhidin kârını hesaplar; ayrıca müteahhidin hedef marjını
    koruyarak arsa sahibine verilebilecek en yüksek payı (`onerilen_*`) döner. Daireler eşit büyüklükte kabul edilir.
    satilabilir_alan_m2: opsiyonel, açıkça verirse proje varsayımı (odalar net alanı oranı) yerine geçer.
    """
    if isinstance(arsa_sahibi_payi_pct, bool) or not 0 <= arsa_sahibi_payi_pct <= 100:
        raise ValueError("arsa_sahibi_payi_pct 0–100 arasında sonlu bir sayı olmalı")
    if isinstance(hedef_marj_pct, bool) or not 0 <= hedef_marj_pct < 100:
        raise ValueError("hedef_marj_pct 0 dahil, 100 hariç aralığında sonlu bir sayı olmalı")
    # Core fizibilite API'sini çağır (arsa bedeli 0 çünkü kat karşılığında arsa parası yok)
    fiz = await _fizibilite_hesapla(
        proje_id=proje_id,
        arsa_bedeli_tl=0,
        satis_m2_fiyati_tl=satis_m2_fiyati_tl,
        ek_gider_pct=ek_gider_pct,
        satilabilir_alan_m2=satilabilir_alan_m2,
    )

    p = await _get(proje_id)
    n = len(_daireler(p))
    if not n:
        raise ValueError("projede daire yok")

    gelir = fiz["sonuc"]["satis_geliri_tl"]
    maliyet = fiz["sonuc"]["insaat_bedeli_tl"] + fiz["sonuc"]["ek_gider_tl"]

    # Sınır kontrolü: gelir 0 veya negatifse bölme hatası önle
    if gelir <= 0:
        raise ValueError("Satış geliri sıfır veya negatif; kat karşılığı hesaplanamaz (satis_m2_fiyati_tl > 0 ve satilabilir_alan_m2 > 0 olmalı)")

    def durum(sahip: int) -> dict:
        mgelir = gelir * (n - sahip) / n
        return {
            "arsa_sahibi_daire": sahip,
            "muteahhit_daire": n - sahip,
            "arsa_sahibi_payi_pct": _pct(sahip, n),
            "muteahhit_satis_geliri_tl": round(mgelir),
            "muteahhit_kar_tl": round(mgelir - maliyet),
            "muteahhit_marj_pct": _pct(mgelir - maliyet, mgelir),
        }

    istenen = durum(min(n, int(n * arsa_sahibi_payi_pct / 100 + 0.5)))

    # (1-p)·gelir·(1-h) >= maliyet  →  p <= 1 - maliyet / ((1-h)·gelir)
    payda = (1 - hedef_marj_pct / 100) * gelir
    if payda <= 0:
        raise ValueError("Hedef marj için geçersiz parametreler: (1 - hedef_marj_pct/100) * gelir <= 0")
    ust = 1 - maliyet / payda
    onerilen = durum(max(0, min(n, int(n * ust)))) if ust >= 0 else None

    sonuc = {
        "proje_id": proje_id,
        "daire_sayisi": n,
        "daire_basi_deger_tl": round(gelir / n),
        "insaat_ve_ek_gider_tl": round(maliyet),
        "istenen_pay": istenen,
        "onerilen": onerilen,
        "hedef_marj_pct": hedef_marj_pct,
        "uyari": None if onerilen else "bu satış fiyatında hedef marjla kat karşılığı yapılamaz",
        "not": AVAN,
        "uyarilar": fiz.get("uyarilar", []),
        "_kaynak": fiz["_kaynak"],
    }
    _kaydet(proje_id, "kat_karsiligi", sonuc)
    return sonuc


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
        resp = await cl.get(f"{ARCHAI}/files/{rel}", headers=_core_auth())
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
        resp = await cl.get(f"{ARCHAI}/files/{pid}/cizimler/05_on_gorunus.png", headers=_core_auth())
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


# --- salt-okunur 3D görüntüleyici: /v/<pid>/?s=<imza> ---------------------------------------------
# ArchAI arayüzü /v/<pid>/ altında sunulur (göreli statik yollar oraya düşer). Sayfa mutlak /api ve /files
# isteklerini kendisi yapar; bunlara yalnız imzalı linkten alınan çerezdeki proje için, yalnız GET ile izin verilir.
VCOOKIE = "archai_v"
STATIC_RE = re.compile(r"(?:(?:assets|vendor)/[A-Za-z0-9_./-]+|[a-z]+\.(?:js|css))")
VIEWER_HEAD = """<script>if(location.hash!=='#{pid}')history.replaceState(null,'',location.pathname+location.search+'#{pid}');</script>
<style>main.grid>aside,#vidbtn,.chip.opt,.truebtn,#edit,#wedit,#tabs [data-t="3d"],#tabs [data-t="tasarim"]{{display:none!important}}
main.grid{{grid-template-columns:1fr!important}}
.avan-not{{position:fixed;left:0;right:0;bottom:0;z-index:50;padding:6px 12px;font:12px/1.4 system-ui;text-align:center;
color:#cfe;background:rgba(4,16,28,.85)}}</style>"""
VIEWER_BODY = """<div class="avan-not">ArchAI · avan / ön fizibilite görselidir, ruhsat projesi değildir.</div>
<div id="yukle" style="position:fixed;inset:0;z-index:99;display:grid;place-items:center;background:#050b14;color:#3ee8ff;
font:600 14px/1.6 system-ui;letter-spacing:.2em;text-align:center;transition:opacity .6s">ARCHAI<br>
<span style="color:#7d97ab;font-weight:400;letter-spacing:.1em">3D proje hazırlanıyor…</span></div>
<script>(()=>{const q=new URLSearchParams(location.search),y=document.getElementById('yukle'),t0=Date.now();
const ok=()=>{const h=document.getElementById('hname');return h&&h.textContent&&!['—','ArchAI'].includes(h.textContent.trim());};
const iv=setInterval(()=>{if((ok()&&Date.now()-t0>(q.get('walk')?4500:2500))||Date.now()-t0>20000){clearInterval(iv);
y.style.opacity=0;setTimeout(()=>y.remove(),700);}},250);
if(q.get('cinema')){const w=document.getElementById('whelp');if(w)w.style.display='none';}
if(q.get('cinema')){const st=document.createElement('style');st.textContent='header.bar,main.grid>section>.glass:not(#vp),'+
'.hud,.whud .hud,.cross,.avan-not,.idrawer,.ihint{display:none!important}#vp{position:fixed!important;inset:0;width:100vw!important;height:100vh!important;max-height:none!important;border-radius:0!important;'+
'z-index:40;margin:0}body{overflow:hidden}';document.head.appendChild(st);setTimeout(()=>dispatchEvent(new Event('resize')),300);}
if(q.get('tour')&&!q.get('cinema')){const b=document.createElement('a');b.id='serbest';b.textContent='◉ Yürümek için W/A/S/D ya da ekrana dokun';q.delete('tour');
b.href=location.pathname+'?'+q+location.hash;b.style.cssText='position:fixed;right:16px;bottom:44px;z-index:60;padding:10px 14px;'+
'border-radius:10px;background:#0e2033;color:#3ee8ff;border:1px solid #1d6b80;font:13px system-ui;text-decoration:none';
document.body.appendChild(b);}})();</script>"""


def _vpid(request: Request) -> str | None:
    """Çerezdeki görüntüleme izni geçerliyse proje kimliği."""
    pid, _, sig = request.cookies.get(VCOOKIE, "").partition(".")
    if PID_RE.fullmatch(pid) and hmac.compare_digest(sig, _sign("v/" + pid)):
        return pid
    return None


async def _proxy(path: str) -> Response:
    async with httpx.AsyncClient(timeout=60) as cl:
        resp = await cl.get(f"{ARCHAI}/{path}", headers=_core_auth())
    if resp.status_code != 200:
        return Response(status_code=404)
    headers = {k: v for k, v in resp.headers.items() if k.lower() in ("content-type", "cache-control")}
    return Response(resp.content, headers=headers)


async def viewer(request: Request):
    pid = request.path_params["pid"]
    sig = request.query_params.get("s", "")
    if not (PID_RE.fullmatch(pid) and hmac.compare_digest(sig, _sign("v/" + pid))):
        return Response(status_code=404)
    if not request.url.path.endswith("/"):  # göreli statik yollar /v/<pid>/ altına düşsün
        return Response(status_code=307, headers={"location": f"/v/{pid}/?{request.url.query}"})
    async with httpx.AsyncClient(timeout=30) as cl:
        ok = (await cl.get(f"{ARCHAI}/api/projects/{pid}", headers=_core_auth())).status_code == 200
        html = (await cl.get(f"{ARCHAI}/index.html", headers=_core_auth())).text
    if not ok:
        return Response(status_code=404)
    head = VIEWER_HEAD.format(pid=pid)
    yerel = _yerel_istek(request)
    if yerel:  # bu makineden açıldıysa iç mekân düzenleyici açık
        head = head.replace("#edit,#wedit,", "", 1)
    galeri = _galeri(pid, yerel)
    if galeri["gorseller"]:  # 06 RENDER sekmesi: fal görselleri + tanıtım filmi
        head = head.replace('#tabs [data-t="3d"],', "", 1) + FAL_SEKME.replace("__GALERI__", json.dumps(galeri))
    html = html.replace("</head>", head + "</head>", 1)
    html = html.replace("</body>", VIEWER_BODY + "</body>", 1)
    r = Response(html, media_type="text/html")
    r.set_cookie(VCOOKIE, f"{pid}.{sig}", max_age=7 * 86400, httponly=True, secure=True, samesite="lax", path="/")
    return r


async def viewer_static(request: Request):
    path = request.path_params["path"]
    if ".." in path or not STATIC_RE.fullmatch(path):
        return Response(status_code=404)
    return await _proxy(path)


FAL_SEKME = """<style>.falgal{display:grid;grid-template-columns:repeat(2,1fr);gap:14px}.falgal img{width:100%;border-radius:12px;
cursor:zoom-in;aspect-ratio:16/10;object-fit:cover}.falgal figure{margin:0}.falgal figcaption{font-size:11px;letter-spacing:.14em;color:#7d97ab;
margin-top:6px}.falvid{width:100%;border-radius:12px;margin-bottom:16px;background:#000}</style>
<script>window.FAL=__GALERI__;addEventListener('click',e=>{const b=e.target.closest('#tabs [data-t="3d"]');if(!b)return;
setTimeout(()=>{const v=document.getElementById('view'),F=window.FAL,ad={cephe:'CEPHE',salon:'SALON',yatak:'YATAK ODASI',kus:'KUŞBAKIŞI'};
v.innerHTML='<p class="sec-t">FAL · FOTOGERÇEKÇİ RENDER VE TANITIM FİLMİ</p>'+(F.film?'<video class="falvid" controls src="'+F.film+'"></video>':'')+
'<div class="falgal">'+F.gorseller.map(g=>'<figure><img src="'+g.url+'" onclick="window.open(this.src)"><figcaption>'+(ad[g.ad]||g.ad)+
' · FAL RENDER</figcaption></figure>').join('')+'</div>';},0);},true);</script>"""


def _galeri(pid: str, yerel: bool) -> dict:
    """RENDER sekmesi için: demo paketinden (yerel dosyalar) ya da kampanya kaydından fal görselleri."""
    g = {"gorseller": [], "film": None}
    dj = Path(__file__).with_name("demo") / "demo.json"
    if yerel and dj.exists():
        for k in json.loads(dj.read_text())["kartlar"]:
            if k["proje_id"] == pid:
                g["gorseller"] = [{"ad": a, "url": u} for a, u in k["gorseller"].items()]
                g["film"] = k.get("film")
                return g
    k = json.loads(KAYIT.read_text()).get(pid, {}) if KAYIT.exists() else {}
    if k.get("render_url"):
        g["gorseller"] = [{"ad": "cephe", "url": k["render_url"]}]
    if k.get("video_url"):
        g["film"] = k["video_url"]
    return g


def _yerel_istek(request: Request) -> bool:
    """Tünelden değil, doğrudan bu makineden gelen istek (cloudflared cf-connecting-ip ekler)."""
    return request.client.host in ("127.0.0.1", "::1") and "cf-connecting-ip" not in request.headers


async def viewer_api(request: Request):
    pid, path = _vpid(request), request.url.path
    if request.method == "PUT" and pid and path == f"/api/projects/{pid}/interior" and _yerel_istek(request):
        async with httpx.AsyncClient(timeout=30) as cl:
            r = await cl.put(f"{ARCHAI}{path}", content=await request.body(), headers={"content-type": "application/json", **_core_auth()})
        return Response(r.content, status_code=r.status_code, media_type="application/json")
    if request.method != "GET":
        return JSONResponse({"detail": "salt-okunur görünüm"}, status_code=403)
    if path == "/api/settings":
        return JSONResponse({"company": {"name": "ArchAI"}})
    if path == "/api/projects":
        return JSONResponse([])  # arşiv listesi dışarı verilmez
    if pid and path in (f"/api/projects/{pid}", f"/api/projects/{pid}/interior",
                        f"/api/projects/{pid}/elements", f"/api/projects/{pid}/real"):
        return await _proxy(path.lstrip("/"))
    return JSONResponse({"detail": "salt-okunur görünüm"}, status_code=403)


async def viewer_files(request: Request):
    pid = _vpid(request)
    rel = request.path_params["rel"]
    if not pid or ".." in rel or not rel.startswith(pid + "/"):
        return Response(status_code=404)
    return await _proxy("files/" + rel)


def _view_link(pid: str) -> str:
    return f"{PUBLIC}/v/{pid}/?s={_sign('v/' + pid)}&vm=real"


app.add_route("/f/{rel:path}", files, methods=["GET"])
app.add_route("/g/{pid}.png", facade, methods=["GET"])
app.add_route("/v/{pid}", viewer, methods=["GET"])
app.add_route("/v/{pid}/", viewer, methods=["GET"])
app.add_route("/v/{pid}/{path:path}", viewer_static, methods=["GET"])
app.add_route("/api/{rest:path}", viewer_api, methods=["GET", "POST", "PUT", "DELETE", "PATCH"])
app.add_route("/files/{rel:path}", viewer_files, methods=["GET"])


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
    import console
    console.kur(app)
    uvicorn.run(BearerAuth(app), host="127.0.0.1", port=int(os.environ.get("PORT", 8765)))
