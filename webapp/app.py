"""ArchAI web uygulaması.

    uv run uvicorn webapp.app:app --reload --port 8000
"""

import hmac
import ipaddress
import json
import logging
import os
import queue
import re
import shutil
import subprocess
import threading
import time
import unicodedata
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlencode, urlsplit

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import AliasChoices, BaseModel, ConfigDict, Field, ValidationError, model_validator

from archai import costing, project

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(os.environ.get("ARCHAI_OUT") or ROOT / "out")      # testler ve ortak makineler için çıktı kökü
PROJECTS = OUT / "projects"
PROJECTS.mkdir(parents=True, exist_ok=True)
_blender_lock = threading.Lock()  # tek headless Blender süreci — render'lar sıraya girer

app = FastAPI(title="ArchAI")


log = logging.getLogger("archai.web")


@app.middleware("http")
async def no_stale_frontend(request, call_next):
    """Arayüz dosyaları her istekte doğrulansın: güncelleme sonrası eski JS çalışmasın."""
    resp = await call_next(request)
    if request.url.path == "/" or request.url.path.endswith((".html", ".js")):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


# ------------------------------------------------------------------ erişim koruması
LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}
TOKEN_COOKIE = "archai_token"
MB = 1024 * 1024
MAX_PLAN_BYTES = 25 * MB      # DXF / resim plan
MAX_SCENE_BYTES = 300 * MB    # /real sahne GLB


def _host_name(h):
    """Host başlığından port'u at: 'a.b:8000' → 'a.b', '[::1]:8000' → '::1'."""
    h = (h or "").strip().lower()
    if h.startswith("["):
        return h[1:h.index("]")] if "]" in h else h
    return h.rsplit(":", 1)[0] if h.count(":") == 1 else h


def _is_ip(h):
    try:
        ipaddress.ip_address(h)
        return True
    except ValueError:
        return False


def _host_ok(host):
    """DNS rebinding koruması: yalnız loopback adları, IP adresleri ve ARCHAI_ALLOWED_HOSTS."""
    h = _host_name(host)
    extra = {x.strip().lower() for x in os.environ.get("ARCHAI_ALLOWED_HOSTS", "").split(",") if x.strip()}
    return bool(h) and (h in LOOPBACK_NAMES or h in extra or _is_ip(h))


def _is_loopback(client):
    try:
        ip = ipaddress.ip_address((client.host if client else "") or "")
    except ValueError:
        return False
    if getattr(ip, "ipv4_mapped", None):
        ip = ip.ipv4_mapped
    return ip.is_loopback


def _request_token(request):
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip(), False
    for v in (request.headers.get("x-archai-token"), request.cookies.get(TOKEN_COOKIE)):
        if v:
            return v, False
    q = request.query_params.get("token")
    return (q, True) if q else (None, False)


def _deny(code, msg):
    return JSONResponse({"detail": msg}, status_code=code)


@app.middleware("http")
async def access_guard(request: Request, call_next):
    """Token / loopback kontrolü, Host allow-list, durum değiştiren isteklerde Origin = Host.
    `/` sayfası ve statik dosyalar dahil her istek buradan geçer."""
    host = request.headers.get("host", "")
    if not _host_ok(host):
        return _deny(400, "geçersiz Host başlığı (ARCHAI_ALLOWED_HOSTS ile izin verin)")
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        origin = request.headers.get("origin")
        if origin is not None and (urlsplit(origin).netloc.lower() != host.strip().lower()):
            return _deny(403, "çapraz kaynaklı istek reddedildi (Origin, Host ile uyuşmuyor)")
    expected = os.environ.get("ARCHAI_TOKEN") or ""
    from_query = False
    if expected:
        got, from_query = _request_token(request)
        if not got or not hmac.compare_digest(got.encode(), expected.encode()):
            return _deny(401, "erişim anahtarı eksik veya geçersiz (ARCHAI_TOKEN)")
    elif not _is_loopback(request.client):
        return _deny(403, "uzak erişim için ARCHAI_TOKEN tanımlayın (şu an yalnız bu makineden erişilebilir)")
    # gövde boyutu erken reddi (asıl sayım akış sırasında yapılır)
    try:
        clen = int(request.headers.get("content-length") or 0)
    except ValueError:
        clen = 0
    if clen > MAX_SCENE_BYTES + MB:
        return _deny(413, "istek gövdesi çok büyük")
    if from_query and request.method == "GET" and "text/html" in request.headers.get("accept", ""):
        # anahtar adres çubuğunda/geçmişte kalmasın: çerezi yaz, anahtarsız adrese yönlendir
        rest = [(k, v) for k, v in request.query_params.multi_items() if k != "token"]
        url = request.url.path + (("?" + urlencode(rest)) if rest else "")
        resp = RedirectResponse(url, status_code=303)
        resp.set_cookie(TOKEN_COOKIE, expected, httponly=True, samesite="strict", path="/")
        resp.headers["Referrer-Policy"] = "no-referrer"
        return resp
    resp = await call_next(request)
    if from_query:
        resp.set_cookie(TOKEN_COOKIE, expected, httponly=True, samesite="strict", path="/")
    resp.headers.setdefault("Referrer-Policy", "no-referrer")
    return resp


# ------------------------------------------------------------------ hata biçimi
_ERR_TR = {
    "missing": "zorunlu alan eksik", "extra_forbidden": "tanınmayan alan",
    "float_type": "sayı olmalı", "float_parsing": "sayı olmalı", "int_type": "tam sayı olmalı",
    "int_parsing": "tam sayı olmalı", "int_from_float": "tam sayı olmalı", "string_type": "metin olmalı",
    "bool_type": "true/false olmalı", "dict_type": "nesne ({...}) olmalı", "list_type": "liste olmalı",
    "model_type": "nesne ({...}) olmalı", "json_invalid": "geçersiz JSON", "finite_number": "sonlu sayı olmalı",
}


def _err_msg(e):
    t, ctx = e.get("type", ""), e.get("ctx") or {}
    if t == "greater_than_equal":
        m = f"en az {ctx.get('ge')} olmalı"
    elif t == "greater_than":
        m = f"{ctx.get('gt')} değerinden büyük olmalı"
    elif t == "less_than_equal":
        m = f"en çok {ctx.get('le')} olmalı"
    elif t == "less_than":
        m = f"{ctx.get('lt')} değerinden küçük olmalı"
    elif t == "string_too_long":
        m = f"en çok {ctx.get('max_length')} karakter olmalı"
    elif t == "string_too_short":
        m = "boş olamaz"
    elif t == "too_long":
        m = f"en çok {ctx.get('max_length')} öğe olmalı"
    elif t == "too_short":
        m = f"en az {ctx.get('min_length')} öğe olmalı"
    elif t == "literal_error":
        m = f"şunlardan biri olmalı: {ctx.get('expected')}"
    else:
        m = _ERR_TR.get(t) or e.get("msg", "geçersiz değer")
    loc = ".".join(str(x) for x in e.get("loc", ()) if x not in ("body", "query", "path", "form"))
    return f"{loc}: {m}" if loc else m


def _errors_detail(errors):
    return "geçersiz girdi — " + "; ".join(_err_msg(e) for e in errors[:8])


@app.exception_handler(RequestValidationError)
async def _validation_handler(request, exc):
    return JSONResponse({"detail": _errors_detail(exc.errors()),
                         "errors": [{"loc": list(e.get("loc", ())), "type": e.get("type")} for e in exc.errors()]},
                        status_code=422)


@app.exception_handler(Exception)
async def _internal_handler(request, exc):
    log.exception("işlenmeyen hata: %s %s", request.method, request.url.path)
    return JSONResponse({"detail": "iç hata"}, status_code=500)


# ------------------------------------------------------------------ girdi şemaları
_S = ConfigDict(strict=True, extra="ignore")


def _num(lo=None, hi=None, gt=None):
    return Annotated[float, Field(ge=lo, le=hi, gt=gt, allow_inf_nan=False)]


def _txt(n):
    return Annotated[str, Field(max_length=n)]


class Parcel(BaseModel):
    model_config = _S
    width: _num(3, 500)
    depth: _num(3, 500)


class Zoning(BaseModel):
    model_config = _S
    taks: _num(hi=1, gt=0) | None = None
    kaks: _num(hi=10, gt=0) | None = None
    front: _num(0, 100) | None = None
    side: _num(0, 100) | None = None
    rear: _num(0, 100) | None = None
    max_floors: Annotated[int, Field(ge=1, le=30)] | None = None
    floor_height: _num(2.2, 6) | None = None
    max_height: _num(gt=2.2, hi=200) | None = None       # yençok / saçak kotu sınırı (m)
    emsal_disi_pct: _num(0, 30) | None = None            # emsale girmeyen ortak alan payı (% brüt)


class Program(BaseModel):
    model_config = _S
    unit_type: _txt(20) | None = None
    units_per_floor: Literal["auto"] | Annotated[int, Field(ge=1, le=20)] | None = None


class Quick(Program):
    gross_area: _num(30, 100000)
    floors: Annotated[int, Field(ge=1, le=30)]
    floor_height: _num(2.2, 6) | None = None


_Code = Annotated[str, Field(min_length=1, max_length=30)]


class ExtraItem(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    name: Annotated[str, Field(min_length=1, max_length=80)]
    unit: _txt(20) = "götürü"
    quantity: _num(0)
    unit_price: _num(0)
    code: _txt(30) | None = None
    group: _txt(60) | None = None


class AdjustIn(BaseModel):
    """Maliyet ayarı: varyant, birim fiyat / miktar düzeltmesi, kalem aç/kapa, ek kalem, oranlar."""
    model_config = ConfigDict(strict=True, extra="forbid")
    variants: Annotated[dict[_Code, _txt(60)], Field(max_length=500)] | None = None
    overrides: Annotated[dict[_Code, _num(0)], Field(max_length=500)] | None = None
    qty_overrides: Annotated[dict[_Code, _num(0)], Field(max_length=500)] | None = None
    disabled: Annotated[list[_Code], Field(max_length=500)] | None = None
    enabled: Annotated[list[_Code], Field(max_length=500)] | None = None
    extra_items: Annotated[list[ExtraItem], Field(max_length=200)] | None = None
    overhead_pct: _num(0, 100) | None = None
    profit_pct: _num(0, 100) | None = None
    vat_pct: Annotated[_num(0, 100) | None, Field(validation_alias=AliasChoices("vat_pct", "kdv_pct"))] = None
    approx_class: _txt(80) | None = None

    @model_validator(mode="after")
    def _enabled_wins(self):
        if self.enabled:  # açıkça dahil edilen kalemler kapalı listesinden çıkar
            self.disabled = [c for c in (self.disabled or []) if c not in set(self.enabled)]
            self.enabled = None
        return self


_InfoDict = Annotated[dict[_txt(40), _txt(300)], Field(max_length=30)]


class PayItem(BaseModel):
    model_config = _S
    pct: Annotated[float, Field(ge=0, le=100)]
    desc: _txt(120) = ""


class Offer(BaseModel):
    """Teklif şartları (reports.offer_terms): verilmeyen alan varsayılanla dolar ve belgede taslak işaretlenir."""
    model_config = _S
    months: Annotated[int, Field(ge=1, le=120)] | None = None
    payment: Annotated[list[PayItem], Field(max_length=12)] | None = None
    court: _txt(120) | None = None
    validity_days: Annotated[int, Field(ge=1, le=365)] | None = None
    price_diff_pct: Annotated[float, Field(ge=0, le=100)] | None = None


class Info(BaseModel):
    """Künye alanları (project.INFO_KEYS)."""
    model_config = _S
    offer: Offer | None = None
    company: _InfoDict | None = None
    customer: _InfoDict | None = None
    site: _InfoDict | None = None
    owner: _txt(200) | None = None
    architect: _txt(200) | None = None
    drawn_by: _txt(200) | None = None
    checked_by: _txt(200) | None = None
    approved_by: _txt(200) | None = None
    rev: _txt(40) | None = None


class Brief(Info):
    name: _txt(500) = "Yeni Proje"
    parcel: Parcel | None = None
    zoning: Zoning | None = None
    program: Program | None = None
    quick: Quick | None = None
    adjust: AdjustIn | None = None
    render_3d: bool = False


class UploadMeta(Info):
    """/api/projects/dxf `meta` alanı (JSON metin)."""
    px_per_m: _num(gt=0, hi=100000) | None = None
    grid_m: _num(gt=0, hi=1000) | None = None
    vision: bool = False


_V3 = Annotated[list[_num()], Field(min_length=3, max_length=3)]


class Camera(BaseModel):
    model_config = ConfigDict(extra="ignore")
    matrix: Annotated[list[_num()], Field(min_length=16, max_length=16)]
    fov: _num(5, 120)
    aspect: _num(gt=0, hi=20)


class Light(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pos: _V3
    w: _num(0, 1000)
    d: _num(0, 1000)


class Sun(BaseModel):
    model_config = ConfigDict(extra="ignore")
    pos: _V3
    target: _V3


class RenderJob(BaseModel):
    """/real `job` alanı: render_real.py'nin okuduğu alanlar dışındakiler atılır."""
    model_config = ConfigDict(extra="ignore")
    kind: Literal["still"]
    hq: bool = False
    preset: _txt(40) = ""
    camera: Camera
    lights: Annotated[list[Light], Field(max_length=200)] = []
    sun: Sun | None = None
    sun_energy: _num(0, 1000) | None = None
    sky: _num(0, 100) | None = None
    room_light: _num(0, 1000) | None = None
    exposure: _num(-20, 20) | None = None


_CTRL = re.compile(r"[\x00-\x1f\x7f-\x9f\u200b-\u200f\u2028-\u202e\u2066-\u2069]")


def _clean_name(name, default="Yeni Proje"):
    """Proje adı: kontrol / yön karakterleri atılır, 80 karaktere kırpılır."""
    s = _CTRL.sub("", unicodedata.normalize("NFC", str(name or ""))).strip()[:80].strip()
    return s or default


def _validate_adjust(adj):
    """B üyesinin costing.validate_adjust'u varsa ek iş kuralları için onu da çalıştır (ValueError → 422)."""
    if adj and hasattr(costing, "validate_adjust"):
        costing.validate_adjust(adj)
    return adj


def _new_id(name):
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower().translate(str.maketrans("çğıöşü", "cgiosu"))).strip("-")[:30]
    return f"{datetime.now():%Y%m%d-%H%M%S}-{slug or 'proje'}-{uuid.uuid4().hex[:4]}"


def _public(pid, result):
    """Dosya yollarını /files/... URL'lerine çevir."""
    base = PROJECTS / pid

    def rel(v):  # mutlak yol bu klasörün altındaysa göreli; değilse (klasör taşındı/yeniden adlandırıldı) '.../projects/<ad>/' önekini at
        try:
            return Path(v).resolve().relative_to(base.resolve())
        except ValueError:
            return Path(re.sub(r"^.*?/projects/[^/]+/", "", str(v).replace("\\", "/")))
    files = {k: f"/files/{pid}/{rel(v)}" for k, v in result["files"].items()}
    pngs = sorted((base / "cizimler").glob("*.png"))
    return {**result, "id": pid, "files": files,
            "sheets": [{"name": p.stem, "png": f"/files/{pid}/cizimler/{p.name}",
                        "dxf": f"/files/{pid}/cizimler/{p.stem}.dxf"} for p in pngs]}


def _run(fn):
    try:
        return fn()
    except ValidationError as ex:
        raise HTTPException(422, _errors_detail(ex.errors()))
    except ValueError as ex:
        raise HTTPException(422, str(ex) or "geçersiz değer")


PID_RE = re.compile(r"\d{8}-\d{6}-[a-z0-9-]{1,60}")


def _pdir(pid, need=None):
    """Proje klasörü: kimlik biçimi + PROJECTS altında olma + (varsa) gerekli dosya; değilse 404."""
    if not isinstance(pid, str) or not PID_RE.fullmatch(pid):
        raise HTTPException(404, "proje bulunamadı")
    root = PROJECTS.resolve()
    d = (PROJECTS / pid).resolve()
    if d.parent != root or not d.is_dir() or (need and not (d / need).is_file()):
        raise HTTPException(404, "proje bulunamadı")
    return d


def _read_json(p, what="kayıt"):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        raise HTTPException(422, f"{what} bozuk veya okunamıyor")


def _build(pid, fn):
    """Proje üret; herhangi bir hatada yarım kalan klasörü sil (arşivde bozuk kayıt kalmasın)."""
    try:
        return _run(fn)
    except BaseException:
        shutil.rmtree(PROJECTS / pid, ignore_errors=True)
        raise


def _brief_dump(b):
    brief = b.model_dump(exclude_none=True)
    brief["name"] = _clean_name(brief.get("name"))
    if brief.get("adjust"):
        _run(lambda: _validate_adjust(brief["adjust"]))
    return brief


@app.post("/api/projects")
def create_project(b: Brief):
    brief = _brief_dump(b)
    render_3d = brief.pop("render_3d", False)
    if not brief.get("quick") and not (brief.get("parcel") and b.zoning is not None):
        raise HTTPException(422, "arazi (parcel+zoning) veya hızlı mod (quick) bilgisi gerekli")
    pid = _new_id(brief["name"])
    with _blender_lock if render_3d else _nolock():
        result, _ = _build(pid, lambda: project.run(brief, PROJECTS / pid, render_3d=render_3d))
    return _public(pid, result)


DEMO_KEYS = ("name", "adjust", *project.INFO_KEYS)


def _demo(b, default_name, runner):
    brief = _brief_dump(b) if b else {}
    brief = {k: v for k, v in brief.items() if k in DEMO_KEYS}
    if brief.get("name") in (None, "Yeni Proje", "Yeni Konut Projesi"):
        brief["name"] = default_name
    pid = _new_id(brief["name"])
    result, _ = _build(pid, lambda: runner(PROJECTS / pid, brief))
    return _public(pid, result)


@app.post("/api/projects/villa")
def create_villa(b: Brief | None = None):
    """Demo: döşenmiş iki katlı villa senaryosu (plan + bahçe/havuz + iç mekân)."""
    return _demo(b, "Villa Demo", project.run_villa)


@app.post("/api/projects/cabin")
def create_cabin(b: Brief | None = None):
    """Demo: tomruk dağ evi senaryosu (zemin + asma kat, veranda, döşenmiş iç mekân)."""
    return _demo(b, "Dağ Evi Demo", project.run_cabin)


@app.post("/api/projects/apartment")
def create_apartment(b: Brief | None = None):
    """Senaryo: 3 daireli apartman normal katı (CAD kat planından, döşenmiş)."""
    return _demo(b, "Apartman Katı", project.run_apartment)


IMAGE_EXT = (".png", ".jpg", ".jpeg", ".webp")


def _save_upload(upload, dest, limit, what):
    """Yüklemeyi parça parça diske yaz, sınırı aşarsa 413 (dosya silinir)."""
    n = 0
    with dest.open("wb") as f:
        while chunk := upload.file.read(MB):
            n += len(chunk)
            if n > limit:
                f.close()
                dest.unlink(missing_ok=True)
                raise HTTPException(413, f"{what} çok büyük (en fazla {limit // MB} MB)")
            f.write(chunk)
    if n == 0:
        raise HTTPException(422, f"{what} boş")
    return n


@app.post("/api/projects/dxf")
def create_from_dxf(file: UploadFile = File(...), name: str = Form("DXF Projesi"), floors: int = Form(1),
                    floor_height: float = Form(3.0), render_3d: bool = Form(False), meta: str = Form("{}")):
    ext = Path((file.filename or "").lower()).suffix
    if ext not in (".dxf", *IMAGE_EXT):
        raise HTTPException(422, "yalnız .dxf veya resim plan (.png/.jpg/.webp) kabul ediliyor "
                                 "(DWG'yi AutoCAD/ODA ile DXF'e çevirin; PDF'i resim olarak dışa aktarın)")
    if not 1 <= floors <= 30:
        raise HTTPException(422, "floors: 1 ile 30 arasında olmalı")
    if not 2.2 <= floor_height <= 6:
        raise HTTPException(422, "floor_height: 2.2 ile 6 m arasında olmalı")
    # meta dosya yazılmadan ÖNCE doğrulanır
    try:
        m = UploadMeta.model_validate_json(meta or "{}")
    except ValidationError as ex:
        raise HTTPException(422, "meta: " + _errors_detail(ex.errors()))
    extra = m.model_dump(exclude_none=True, include=set(project.INFO_KEYS))
    name = _clean_name(name, "DXF Projesi")
    pid = _new_id(name)
    d = PROJECTS / pid
    d.mkdir(parents=True)
    src = d / f"plan{ext}"

    def go():
        _save_upload(file, src, MAX_PLAN_BYTES, "plan dosyası")
        if ext in IMAGE_EXT:
            img = {"floors": floors, "floor_height": floor_height, "vision": m.vision}
            img.update({k: getattr(m, k) for k in ("px_per_m", "grid_m") if getattr(m, k)})
            brief = {"name": name, "image": img, **extra}
            with _blender_lock if render_3d else _nolock():
                return project.run_image(src, brief, d, render_3d=render_3d)
        brief = {"name": name, "dxf": {"floors": floors, "floor_height": floor_height}, **extra}
        with _blender_lock if render_3d else _nolock():
            return project.run_dxf(src, brief, d, render_3d=render_3d)

    result, _ = _build(pid, go)
    return _public(pid, result)


@app.get("/api/projects")
def list_projects():
    """Arşiv: bozuk / eksik project.json kayıtları atlanır (liste 500 vermez)."""
    out = []
    for p in sorted(PROJECTS.glob("*/project.json"), reverse=True):
        if len(out) >= 50:
            break
        if not PID_RE.fullmatch(p.parent.name):  # eski/elle açılmış klasörler API'den erişilemez
            continue
        try:
            r = json.loads(p.read_text())
            out.append({"id": p.parent.name, "name": str(r["name"]), "total": float(r["cost"]["total"]),
                        "area": float(r["summary"]["gross_floor_area"])})
        except (OSError, ValueError, KeyError, TypeError):
            log.warning("bozuk proje kaydı atlandı: %s", p)
    return out


@app.get("/api/projects/{pid}")
def get_project(pid: str):
    d = _pdir(pid, "project.json")
    r = _read_json(d / "project.json", "proje kaydı")
    try:
        return _public(pid, r)
    except (KeyError, TypeError, AttributeError, ValueError):
        raise HTTPException(422, "proje kaydı bozuk")


@app.get("/api/projects/{pid}/elements")
def get_elements(pid: str):
    """3D viewport için eleman listesi."""
    d = _pdir(pid, "elements.json")
    return _read_json(d / "elements.json", "eleman listesi")


@app.get("/api/projects/{pid}/interior")
def get_interior(pid: str):
    """İç mekân düzeni: zemin kaplamaları, boya, yerleştirilen nesneler."""
    p = _pdir(pid) / "interior.json"
    return _read_json(p, "iç mekân kaydı") if p.exists() else {"floors": {}, "paint": "kirik_beyaz", "objects": []}


OBJ_KEYS = ("id", "kind", "level", "x", "y", "rot", "h")
# parametrik nesne ölçüleri (interior.js FACTORY): yalnız sayı / bayrak olarak saklanır
OBJ_NUM = ("w", "d", "hy", "v", "p", "side", "ocak", "evye", "suluk")
OBJ_FLAG = ("kitap", "orta", "decor")


def _clean_obj(o):
    c = {k: o[k] for k in OBJ_KEYS if k in o}
    c.update({k: float(o[k]) for k in OBJ_NUM if isinstance(o.get(k), (int, float)) and not isinstance(o[k], bool)})
    c.update({k: o[k] for k in OBJ_FLAG if isinstance(o.get(k), bool)})
    return c


@app.put("/api/projects/{pid}/interior")
def put_interior(pid: str, design: dict):
    d = _pdir(pid)
    objs = design.get("objects", [])
    if not isinstance(objs, list) or len(objs) > 2000:
        raise HTTPException(422, "geçersiz nesne listesi")
    floors = design.get("floors") or {}
    if not isinstance(floors, dict):
        raise HTTPException(422, "floors bir nesne olmalı")
    clean = {"floors": {str(k): str(v) for k, v in floors.items()},
             "paint": str(design.get("paint", "kirik_beyaz")),
             "objects": [_clean_obj(o) for o in objs if isinstance(o, dict)],
             "demolished": [str(n) for n in (design.get("demolished") or []) if isinstance(n, str)][:500]}
    (d / "interior.json").write_text(json.dumps(clean, ensure_ascii=False))
    return {"ok": True, "objects": len(clean["objects"])}


@app.put("/api/projects/{pid}/adjust")
def adjust(pid: str, adj: AdjustIn):
    d = _pdir(pid, "project.json")
    a = adj.model_dump(exclude_none=True)
    return _run(lambda: _public(pid, project.readjust(d, _validate_adjust(a))))


@app.post("/api/projects/{pid}/render")
def render_3d(pid: str):
    d = _pdir(pid, "elements.json")
    els = _read_json(d / "elements.json", "eleman listesi")
    r = _read_json(d / "project.json", "proje kaydı")
    with _blender_lock:
        files = _run(lambda: project.render(els, d / "3d"))
    r["files"].update(files)
    (d / "project.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    return _public(pid, r)


@app.get("/api/settings")
def get_settings():
    return project.load_settings()


@app.put("/api/settings")
def put_settings(data: Info):
    return project.save_settings(data.model_dump(exclude_none=True))


@app.get("/api/prices")
def prices():
    return costing.load_prices()


@app.get("/files/{pid}/{path:path}")
def files(pid: str, path: str):
    d = _pdir(pid)
    f = (d / path).resolve()
    if not f.is_relative_to(d) or not f.is_file():
        raise HTTPException(404)
    return FileResponse(f, filename=f.name if f.suffix in (".docx", ".xlsx", ".dxf", ".pdf") else None)


# ------------------------------------------------------------------ fotogerçekçi render kuyruğu (Blender Cycles)
BLENDER = os.environ.get("ARCHAI_BLENDER", str(Path.home() / "Applications/blender-4.5.14-linux-x64/blender"))
RENDER_SCRIPT = ROOT / "scripts" / "render_real.py"
HDRI = ROOT / "webapp" / "static" / "assets" / "hdri" / "sky_2k.hdr"
JOBS: dict[str, dict] = {}
MAX_JOBS = 200           # bellekteki iş kaydı üst sınırı (eskiler atılır; disk kaydı kalır)
MAX_QUEUE = 8            # bekleyen iş sınırı → 429
RENDER_TIMEOUT = float(os.environ.get("ARCHAI_RENDER_TIMEOUT", 1800))
JID_RE = re.compile(r"still-\d{6}-[0-9a-f]{4}")
_render_q: "queue.Queue[str]" = queue.Queue()
QUALITY = {"still": {"samples": 256, "width": 1920}, "still_hq": {"samples": 512, "width": 2560}}


def _save_job(j):
    try:
        (Path(j["dir"]) / "status.json").write_text(json.dumps(j, ensure_ascii=False, default=str))
    except OSError:
        log.exception("iş durumu yazılamadı: %s", j.get("id"))


def _recover_jobs():
    """Sunucu yeniden başladığında yarım kalan (queued/running) işler hata olarak işaretlenir."""
    for st in PROJECTS.glob("*/real/*/status.json"):
        try:
            j = json.loads(st.read_text())
            if j.get("status") in ("queued", "running"):
                j.update(status="error", error="sunucu yeniden başladı")
                st.write_text(json.dumps(j, ensure_ascii=False, default=str))
        except (OSError, ValueError, AttributeError):
            continue


def _prune_jobs():
    old = [k for k, v in JOBS.items() if v["status"] in ("done", "error")]
    while len(JOBS) > MAX_JOBS and old:
        JOBS.pop(old.pop(0), None)


def _render_worker():
    while True:
        jid = _render_q.get()
        j = JOBS.get(jid)
        if j is None:
            continue
        j["status"] = "running"
        j["started"] = time.time()
        _save_job(j)
        logf = open(Path(j["dir"]) / "blender.log", "w")
        timer = None
        try:
            proc = subprocess.Popen([BLENDER, "-b", "--factory-startup", "--python", str(RENDER_SCRIPT), "--", str(Path(j["dir"]) / "job.json")],
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1)

            def _timeout(p=proc):
                j["timed_out"] = True
                p.kill()

            timer = threading.Timer(RENDER_TIMEOUT, _timeout)
            timer.daemon = True
            timer.start()
            for line in proc.stdout:
                logf.write(line)
                if line.startswith("ARCHAI_PROGRESS"):
                    parts = line.split()
                    j["done"], j["total"] = int(parts[1]), int(parts[2])
                    j["current"] = " ".join(p for p in parts[3:] if not p.replace(".", "").isdigit())
                elif line.startswith("ARCHAI_RESULT"):
                    j["results"].append(Path(line.split(maxsplit=1)[1].strip()).name)
                elif line.startswith("ARCHAI_DEVICE"):
                    j["device"] = line.split(maxsplit=1)[1].strip()
            try:
                proc.wait(timeout=RENDER_TIMEOUT)
            except subprocess.TimeoutExpired:
                j["timed_out"] = True
                proc.kill()
                proc.wait()
            if j.pop("timed_out", False):
                j["status"], j["error"] = "error", f"zaman aşımı: render {int(RENDER_TIMEOUT)} sn içinde bitmedi"
            else:
                j["status"] = "done" if proc.returncode == 0 and j["results"] else "error"
                if j["status"] == "error":
                    j["error"] = f"Blender çıkış kodu {proc.returncode}; log: blender.log"
        except Exception as ex:  # noqa: BLE001 — iş durumu kullanıcıya dönmeli
            j["status"], j["error"] = "error", str(ex)
        finally:
            if timer:
                timer.cancel()
            logf.close()
            j["elapsed"] = round(time.time() - j["started"], 1)
            _save_job(j)


_recover_jobs()
threading.Thread(target=_render_worker, daemon=True).start()


@app.post("/api/projects/{pid}/real")
def submit_real(pid: str, scene: UploadFile = File(...), job: str = Form(...)):
    d = _pdir(pid)
    try:
        spec = RenderJob.model_validate_json(job)
    except ValidationError as ex:
        raise HTTPException(422, "job: " + _errors_detail(ex.errors()))
    if _render_q.qsize() >= MAX_QUEUE:
        raise HTTPException(429, f"render kuyruğu dolu (en fazla {MAX_QUEUE} bekleyen iş); biraz sonra tekrar deneyin")
    kind = spec.kind
    q = QUALITY[kind + ("_hq" if spec.hq else "")]
    jid = f"{kind}-{datetime.now():%H%M%S}-{uuid.uuid4().hex[:4]}"
    jd = d / "real" / jid
    jd.mkdir(parents=True)
    try:
        _save_upload(scene, jd / "scene.glb", MAX_SCENE_BYTES, "sahne")
    except BaseException:
        shutil.rmtree(jd, ignore_errors=True)
        raise
    body = spec.model_dump(exclude_none=True)
    body.update(glb=str(jd / "scene.glb"), hdri=str(HDRI), out_dir=str(jd), samples=q["samples"], width=q["width"])
    (jd / "job.json").write_text(json.dumps(body, ensure_ascii=False))
    JOBS[jid] = {"id": jid, "pid": pid, "kind": kind, "preset": spec.preset, "dir": str(jd), "status": "queued", "done": 0,
                 "total": 1, "results": [], "queued_ahead": _render_q.qsize()}
    _save_job(JOBS[jid])
    _prune_jobs()
    _render_q.put(jid)
    return _job_public(JOBS[jid])


def _job_public(j):
    base = f"/files/{j['pid']}/real/{j['id']}"
    return {k: v for k, v in j.items() if k != "dir"} | {"urls": [f"{base}/{r}" for r in j.get("results", [])]}


@app.get("/api/jobs/{jid}")
def job_status(jid: str):
    j = JOBS.get(jid)
    if j:
        return _job_public(j)
    if JID_RE.fullmatch(jid):  # bellekte yoksa (yeniden başlatma / eski kayıt) diskten
        for st in PROJECTS.glob(f"*/real/{jid}/status.json"):
            try:
                return _job_public(json.loads(st.read_text()))
            except (OSError, ValueError, KeyError, TypeError):
                raise HTTPException(422, "iş kaydı bozuk")
    raise HTTPException(404, "iş bulunamadı")


@app.get("/api/projects/{pid}/real")
def list_real(pid: str):
    """Tamamlanmış gerçek render'lar (sunucu yeniden başlasa da diskten)."""
    d = _pdir(pid) / "real"
    if not d.is_dir():
        return []
    out = []
    for st in sorted(d.glob("*/status.json"), reverse=True):
        try:
            j = json.loads(st.read_text())
            if j.get("status") == "done":
                out.append(_job_public(j))
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            continue
    return out


class _nolock:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


app.mount("/", StaticFiles(directory=Path(__file__).parent / "static", html=True), name="static")
