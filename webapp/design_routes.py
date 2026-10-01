"""Tasarım ajanı API'si (archai/design_agent.py). app.py yalnızca bu router'ı ekler.

    POST /api/projects/{pid}/designs                      multipart: photos[0..4], brief, n 3–5, provider, claude_consent
    GET  /api/projects/{pid}/designs                      önceki tasarım setleri + kullanılabilir sağlayıcılar
    GET  /api/projects/{pid}/designs/{did}/preview/{vid}  alternatif önizlemesi (JPEG)
    POST /api/projects/{pid}/designs/{did}/select         {"variant": "v2"} → interior.json + maliyet güncellenir

Veri: out/projects/<pid>/designs/<did>/{set.json, v1.jpg, …}. Kimlikler (pid/did/vid) regex'le doğrulanır; dosya yolu
hiçbir zaman kullanıcı girdisinden kurulmaz. Yüklenen fotoğraflar diske YAZILMAZ (yalnız sağlayıcıya gider).
"""

import json
import logging
import os
import re
import shutil
import threading
import uuid
from datetime import datetime
from pathlib import Path
from typing import Annotated, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from archai import costing, design_agent as DA, project
from archai import quantities as Q
from archai.notice import AVAN_NOTE, AVAN_SHORT

router = APIRouter()
log = logging.getLogger("archai.web.design")

MB = 1024 * 1024
MAX_PHOTO_BYTES = 12 * MB
MAX_SETS = 20                                    # proje başına saklanan tasarım seti (eskiler silinir)
DID_RE = re.compile(r"\d{12}-[0-9a-f]{4}")
VID_RE = re.compile(r"v[1-9]\d?")
_gen_slots = threading.BoundedSemaphore(2)        # aynı anda en çok 2 üretim (dış ajan/Claude çağrıları pahalı)
_apply_lock = threading.Lock()


def _app():
    """webapp.app'in yardımcıları (döngüsel içe aktarma olmasın diye çağrı anında)."""
    import webapp.app as m
    return m


def _designs_dir(pid, need=None):
    return _app()._pdir(pid, need) / "designs"


def _set_dir(pid, did):
    if not isinstance(did, str) or not DID_RE.fullmatch(did):
        raise HTTPException(404, "tasarım seti bulunamadı")
    d = (_designs_dir(pid) / did)
    if not d.is_dir() or d.parent.resolve() != _designs_dir(pid).resolve():
        raise HTTPException(404, "tasarım seti bulunamadı")
    return d


def _load_set(d):
    try:
        s = json.loads((d / "set.json").read_text())
        if not isinstance(s, dict) or not isinstance(s.get("variants"), list):
            raise ValueError
        return s
    except (OSError, ValueError):
        raise HTTPException(422, "tasarım kaydı bozuk veya okunamıyor")


def _write_json(p, data):
    tmp = p.with_name(p.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False))
    os.replace(tmp, p)


def _public_set(pid, s):
    did = s["id"]
    vs = []
    for v in s["variants"]:
        if not isinstance(v, dict) or not VID_RE.fullmatch(str(v.get("id", ""))):
            continue
        vs.append({**{k: v[k] for k in v if k != "preview"},
                   "floor_name": DA.FLOORS.get(v.get("floor"), ("", 0, 0))[0],
                   "wet_name": DA.FLOORS.get(((v.get("patch") or {}).get("floors") or {}).get("wet"), ("", 0, 0))[0],
                   "paint_name": DA.PAINTS.get(v.get("wall_paint"), ("", 0))[0],
                   "style_name": DA.STYLES.get(v.get("furniture_style"), {}).get("ad", ""),
                   "preview": f"/api/projects/{pid}/designs/{did}/preview/{v['id']}"})
    return {**{k: s[k] for k in ("id", "created", "provider", "brief", "n", "photos", "warnings", "selected") if k in s},
            "variants": vs, "notice": AVAN_NOTE, "notice_short": AVAN_SHORT}


def _read_photo(up):
    """Yüklemeyi sınırlı belleğe oku → temiz JPEG baytları (EXIF atılır, küçültülür). 413/422."""
    buf = bytearray()
    while chunk := up.file.read(MB):
        buf += chunk
        if len(buf) > MAX_PHOTO_BYTES:
            raise HTTPException(413, f"fotoğraf çok büyük (en fazla {MAX_PHOTO_BYTES // MB} MB)")
    if not buf:
        raise HTTPException(422, "fotoğraf boş")
    try:
        return DA.clean_photo(bytes(buf))
    except DA.PhotoError as ex:
        raise HTTPException(422, str(ex))


def _scenario_cost(elements, adjust, floor_id):
    """Seçilen zemin için toplam maliyet (diğer ayarlar korunur)."""
    adj = json.loads(json.dumps(adjust or {}))
    adj.setdefault("variants", {})["ZEM-01"] = DA.cost_variant(floor_id)
    (adj.get("overrides") or {}).pop("ZEM-01", None)
    try:
        return costing.estimate(Q.compute(elements), adjust=adj)["total"]
    except (ValueError, KeyError):
        return None


def _prune(root):
    sets = sorted(p for p in root.iterdir() if p.is_dir() and DID_RE.fullmatch(p.name))
    for old in sets[:-MAX_SETS]:
        shutil.rmtree(old, ignore_errors=True)


@router.post("/api/projects/{pid}/designs")
def create_designs(pid: str, photos: Annotated[list[UploadFile], File()] = [],
                   brief: Annotated[str, Form(max_length=DA.MAX_BRIEF)] = "",
                   n: Annotated[int, Form(ge=DA.N_MIN, le=DA.N_MAX)] = 4,
                   provider: Annotated[Literal["kural", "claude", "http"], Form()] = "kural",
                   claude_consent: Annotated[bool, Form()] = False):
    A = _app()
    pdir = A._pdir(pid, "elements.json")
    if len(photos) > DA.MAX_PHOTOS:
        raise HTTPException(422, f"photos: en çok {DA.MAX_PHOTOS} fotoğraf yüklenebilir")
    text = DA.clean_text(brief, DA.MAX_BRIEF)
    imgs = [_read_photo(p) for p in photos]        # sağlayıcıdan ÖNCE doğrula: kötü dosyada dış çağrı yapılmaz
    if not text and not imgs:
        raise HTTPException(422, "en az bir fotoğraf veya metin gerekli")
    try:
        prov = DA.get_provider(provider, consent=claude_consent)
    except DA.ProviderError as ex:
        raise HTTPException(ex.status, str(ex))
    elements = A._read_json(pdir / "elements.json", "eleman listesi")
    pr = A._read_json(pdir / "project.json", "proje kaydı") if (pdir / "project.json").is_file() else {}
    ctx = DA.project_context(elements)
    if not _gen_slots.acquire(blocking=False):
        raise HTTPException(429, "çok sayıda tasarım isteği çalışıyor; biraz sonra tekrar deneyin")
    try:
        try:
            variants, warnings = DA.generate(prov, text, imgs, n, ctx)
        except DA.ProviderError as ex:
            raise HTTPException(ex.status, str(ex))
    finally:
        _gen_slots.release()
    adjust = (pr.get("brief") or {}).get("adjust") or {}
    base = (pr.get("cost") or {}).get("total")
    root = pdir / "designs"
    did = f"{datetime.now():%y%m%d%H%M%S}-{uuid.uuid4().hex[:4]}"
    d = root / did
    d.mkdir(parents=True)
    try:
        pub = []
        for v in variants:
            (d / f"{v['id']}.jpg").write_bytes(v["preview"])
            row = DA.public_variant(v)
            total = _scenario_cost(elements, adjust, v["floor"])
            row["cost"] = {"total": total, "delta": (round(total - base, 2) if total is not None and base is not None else None),
                           "zem_variant": DA.cost_variant(v["floor"])}
            pub.append(row)
        s = {"id": did, "created": datetime.now().isoformat(timespec="seconds"), "provider": prov.name, "brief": text,
             "n": n, "photos": len(imgs), "warnings": warnings, "selected": None, "variants": pub}
        _write_json(d / "set.json", s)
        _prune(root)
    except BaseException:
        shutil.rmtree(d, ignore_errors=True)         # yarım set bırakma
        raise
    return _public_set(pid, s)


@router.get("/api/projects/{pid}/designs")
def list_designs(pid: str):
    root = _designs_dir(pid)
    sets = []
    if root.is_dir():
        for p in sorted((x for x in root.iterdir() if x.is_dir() and DID_RE.fullmatch(x.name)), reverse=True):
            try:
                sets.append(_public_set(pid, _load_set(p)))
            except HTTPException:
                log.warning("bozuk tasarım kaydı atlandı: %s", p)
    return {"sets": sets, "providers": DA.provider_status(), "notice": AVAN_NOTE, "notice_short": AVAN_SHORT}


@router.get("/api/projects/{pid}/designs/{did}/preview/{vid}")
def design_preview(pid: str, did: str, vid: str):
    d = _set_dir(pid, did)
    if not VID_RE.fullmatch(vid):
        raise HTTPException(404, "önizleme bulunamadı")
    f = d / f"{vid}.jpg"
    if not f.is_file():
        raise HTTPException(404, "önizleme bulunamadı")
    return FileResponse(f, media_type="image/jpeg", headers={"Cache-Control": "private, max-age=3600"})


class SelectIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    variant: Annotated[str, Field(pattern=r"^v[1-9]\d?$")]


@router.post("/api/projects/{pid}/designs/{did}/select")
def select_design(pid: str, did: str, body: SelectIn):
    A = _app()
    pdir = A._pdir(pid, "project.json")
    d = _set_dir(pid, did)
    s = _load_set(d)
    raw = next((v for v in s["variants"] if isinstance(v, dict) and v.get("id") == body.variant), None)
    if raw is None:
        raise HTTPException(404, "alternatif bulunamadı")
    variant = DA.sanitize_variant({k: raw.get(k) for k in ("title", "summary", "palette", "floor", "wall_paint",
                                                           "furniture_style", "decor", "patch")}, int(body.variant[1:]) - 1)
    variant["id"] = body.variant
    elements = A._read_json(pdir / "elements.json", "eleman listesi")
    with _apply_lock:
        ip = pdir / "interior.json"
        try:
            cur = json.loads(ip.read_text()) if ip.exists() else DA._default_interior()
        except (OSError, ValueError):
            cur = DA._default_interior()
        new = DA.apply_variant(variant, cur if isinstance(cur, dict) else DA._default_interior(), elements)
        clean = {"floors": {str(k): str(v) for k, v in (new.get("floors") or {}).items()},
                 "paint": str(new.get("paint", DA.DEFAULT_PAINT)),
                 "objects": [A._clean_obj(o) for o in new.get("objects", []) if isinstance(o, dict)][:2000],
                 "demolished": [str(x) for x in (cur.get("demolished") or []) if isinstance(x, str)][:500]
                 if isinstance(cur, dict) else []}
        _write_json(ip, clean)
        # maliyet: mevcut ZEM-01 akışı (varyant seçimi) → readjust belgeleri yeniden yazar
        pr = A._read_json(pdir / "project.json", "proje kaydı")
        adj = json.loads(json.dumps((pr.get("brief") or {}).get("adjust") or {}))
        adj.setdefault("variants", {})["ZEM-01"] = DA.cost_variant(variant["floor"])
        (adj.get("overrides") or {}).pop("ZEM-01", None)       # eski elle birim fiyat yeni kaplamayı gölgelemesin
        result = A._run(lambda: project.readjust(pdir, A._validate_adjust(adj)))
        s["selected"] = body.variant
        _write_json(d / "set.json", s)
    return {"ok": True, "design": {"id": did, "variant": {k: variant[k] for k in variant if k != "preview"}},
            "interior": clean, "decor": variant["decor"], "project": A._public(pid, result),
            "notice": AVAN_NOTE, "notice_short": AVAN_SHORT}
