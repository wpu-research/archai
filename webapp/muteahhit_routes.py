"""Müteahhit katmanı API'si: resmî poz eşlemesi ve keşif özeti. app.py yalnızca bu router'ı ekler.

    GET    /api/poz/list                   yüklü lisanslı poz listesi (özet) — liste yalnız bu makinede tutulur
    POST   /api/poz/list                   multipart: file (.xlsx/.csv), institution, year → listeyi içe aktar
    DELETE /api/poz/list                   listeyi sil
    GET    /api/projects/{pid}/poz         kalem ↔ poz eşleme tablosu (+ adaylar, durum özeti)
    PUT    /api/projects/{pid}/poz         {"poz": {kod: poz|null}, "apply_prices": bool} → ayar + belgeler yenilenir
    POST   /api/imar/read                  multipart: file (.pdf/.png/.jpg/.webp), consent → arazi formu önerisi
                                           (belge diske yazılmaz; Claude'a yalnız consent=true ile gider)
    GET    /api/projects/{pid}/onay        onay durumu (taslak | onaylandi | gecersiz | degistirilmis | geri_alindi)
    POST   /api/projects/{pid}/onay        {name, title, chamber, reg_no, note, statement:true} → belgeler damgalanır
    POST   /api/projects/{pid}/onay/revoke {reason} → onay geri alınır, belgeler TASLAK
"""

import copy
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

import threading

from archai import approval, costing, imar_doc, poz, project

router = APIRouter()

MB = 1024 * 1024
MAX_LIST_BYTES = 40 * MB
MAX_DOC_BYTES = 20 * MB


def _app():
    import webapp.app as m
    return m


def _list_path():
    return _app().OUT / "poz_listesi.json"


def _read_upload(up, limit, what):
    buf = bytearray()
    while chunk := up.file.read(MB):
        buf += chunk
        if len(buf) > limit:
            raise HTTPException(413, f"{what} çok büyük (en fazla {limit // MB} MB)")
    if not buf:
        raise HTTPException(422, f"{what} boş")
    return bytes(buf)


# ------------------------------------------------------------------ poz listesi

@router.get("/api/poz/list")
def get_list():
    return {"list": poz.list_info(poz.load_list(_list_path()))}


@router.post("/api/poz/list")
def upload_list(file: UploadFile = File(...), institution: Annotated[str, Form(max_length=40)] = "ÇŞB",
                year: Annotated[int | None, Form(ge=2000, le=2100)] = None):
    name = Path(file.filename or "liste").name
    data = _read_upload(file, MAX_LIST_BYTES, "poz listesi")
    try:
        lst = poz.read_price_list(name, data=data, institution=institution.strip() or "ÇŞB", year=year)
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    except Exception:  # noqa: BLE001 — bozuk xlsx/zip: kullanıcıya anlaşılır mesaj
        raise HTTPException(422, "dosya okunamadı (bozuk veya parola korumalı olabilir)")
    poz.save_list(lst, _list_path())
    return {"list": poz.list_info(lst)}


@router.delete("/api/poz/list")
def delete_list():
    _list_path().unlink(missing_ok=True)
    return {"list": None}


# ------------------------------------------------------------------ proje eşlemesi

def _project(pid):
    d = _app()._pdir(pid, "project.json")
    return d, _app()._read_json(d / "project.json", "proje kaydı")


@router.get("/api/projects/{pid}/poz")
def project_poz(pid: str):
    _, r = _project(pid)
    adj = (r.get("brief") or {}).get("adjust") or {}
    lst = poz.load_list(_list_path())
    rows = poz.match(costing.load_prices(), lst, adjust=adj)
    enabled = {x["code"]: x["enabled"] for x in (r.get("cost") or {}).get("rows", [])}
    for x in rows:
        x["enabled"] = enabled.get(x["code"], True)
        x["applied"] = (adj.get("overrides") or {}).get(x["code"]) == x.get("liste_fiyat") and "liste_fiyat" in x
    return {"list": poz.list_info(lst), "rows": rows, "summary": poz.summary(rows),
            "files": {k: v for k, v in _app()._public(pid, r)["files"].items() if k.startswith("kesif_")}}


class PozIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    poz: Annotated[dict[Annotated[str, Field(min_length=1, max_length=30)],
                        Annotated[str, Field(max_length=32)] | None], Field(max_length=500)] = {}
    apply_prices: bool = False


@router.put("/api/projects/{pid}/poz")
def set_project_poz(pid: str, body: PozIn):
    d, r = _project(pid)
    adj = copy.deepcopy((r.get("brief") or {}).get("adjust") or {})
    codes = {it["code"] for it in costing.load_prices()["items"]}
    own = dict(adj.get("poz") or {})
    for code, p in body.poz.items():
        if code not in codes:
            raise HTTPException(422, f"bilinmeyen kalem kodu: {code}")
        if p is None or not p.strip():
            own.pop(code, None)
        elif not poz.norm_poz(p):
            raise HTTPException(422, f"{code}: geçersiz poz numarası {p!r} (ör. 15.150.1006)")
        else:
            own[code] = poz.norm_poz(p)
    adj["poz"] = own
    applied = {}
    if body.apply_prices:
        lst = poz.load_list(_list_path())
        if not lst:
            raise HTTPException(422, "önce lisanslı poz listesini yükleyin")
        applied = poz.overrides(poz.match(costing.load_prices(), lst, adjust=adj, with_suggestions=False))
        adj["overrides"] = {**(adj.get("overrides") or {}), **applied}
    try:
        res = project.readjust(d, costing.validate_adjust(adj))
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    return {"project": _app()._public(pid, res), "applied": len(applied)}


# ------------------------------------------------------------------ imar durum belgesi

@router.post("/api/imar/read")
def read_imar(file: UploadFile = File(...), consent: Annotated[bool, Form()] = False):
    data = _read_upload(file, MAX_DOC_BYTES, "imar belgesi")
    try:
        return imar_doc.read(Path(file.filename or "belge").name, data, consent=consent)
    except ValueError as ex:
        raise HTTPException(422, str(ex))


# ------------------------------------------------------------------ mimar / mühendis onayı

_onay_lock = threading.Lock()


def _onay_public(pid, d):
    st = approval.status(d)
    files = _app()._public(pid, _app()._read_json(d / "project.json", "proje kaydı"))["files"]
    return {**st, "files": {k: files[k] for k in (*approval.DOC_KEYS, "onay_tutanagi_docx") if k in files}}


@router.get("/api/projects/{pid}/onay")
def get_onay(pid: str):
    d, _ = _project(pid)
    return _onay_public(pid, d)


class SignerIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    name: Annotated[str, Field(max_length=120)]
    title: Annotated[str, Field(max_length=60)]
    chamber: Annotated[str, Field(max_length=80)]
    reg_no: Annotated[str, Field(max_length=20)]
    note: Annotated[str, Field(max_length=1000)] = ""
    statement: bool = False


class RevokeIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    reason: Annotated[str, Field(max_length=300)] = ""


@router.post("/api/projects/{pid}/onay")
def post_onay(pid: str, body: SignerIn):
    d, _ = _project(pid)
    with _onay_lock:
        try:
            approval.approve(d, body.model_dump(), project.redocument)
        except ValueError as ex:
            raise HTTPException(422, str(ex))
    return {**_onay_public(pid, d), "project": _app()._public(pid, _app()._read_json(d / "project.json"))}


@router.post("/api/projects/{pid}/onay/revoke")
def revoke_onay(pid: str, body: RevokeIn):
    d, _ = _project(pid)
    with _onay_lock:
        try:
            approval.revoke(d, project.redocument, body.reason)
        except ValueError as ex:
            raise HTTPException(422, str(ex))
    return {**_onay_public(pid, d), "project": _app()._public(pid, _app()._read_json(d / "project.json"))}
