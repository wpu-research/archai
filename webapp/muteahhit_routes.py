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
    GET    /api/catalogs                   yüklü tedarikçi katalogları
    POST   /api/catalogs                   multipart: file (.xlsx/.csv), supplier → kataloğu içe aktar
    DELETE /api/catalogs/{sid}
    GET    /api/projects/{pid}/catalog     kataloğu olan kalemler: güncel fiyat + ürünler (ucuzdan pahalıya)
    PUT    /api/projects/{pid}/catalog     {"select": {kod: {"catalog": sid, "product": id} | null}}
"""

import copy
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict, Field

import threading

from archai import approval, catalog, costing, imar_doc, poz, project

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


# ------------------------------------------------------------------ tedarikçi kataloğu

def _cat_root():
    return _app().OUT / "katalog"


def _cat_info(c):
    return {"id": c["id"], "supplier": c["supplier"], "count": len(c["items"]), "skipped": c.get("skipped", 0),
            "warnings": c.get("warnings", [])[:20], "imported_at": c.get("imported_at")}


@router.get("/api/catalogs")
def list_catalogs():
    return {"catalogs": [_cat_info(c) for c in catalog.load_all(_cat_root())]}


@router.post("/api/catalogs")
def upload_catalog(file: UploadFile = File(...), supplier: Annotated[str, Form(max_length=60)] = ""):
    data = _read_upload(file, MAX_LIST_BYTES, "katalog")
    try:
        cat = catalog.read_catalog(Path(file.filename or "katalog").name, data, costing.load_prices(),
                                   supplier.strip() or None)
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    except Exception:  # noqa: BLE001
        raise HTTPException(422, "dosya okunamadı (bozuk veya parola korumalı olabilir)")
    if supplier.strip():
        cat["supplier"] = supplier.strip()
    cat["id"] = catalog.save(_cat_root(), cat)
    return {"catalog": _cat_info(cat)}


@router.delete("/api/catalogs/{sid}")
def delete_catalog(sid: str):
    try:
        catalog.delete(_cat_root(), sid)
    except ValueError as ex:
        raise HTTPException(404, str(ex))
    return {"ok": True}


@router.get("/api/projects/{pid}/catalog")
def project_catalog(pid: str):
    _, r = _project(pid)
    cats = catalog.load_all(_cat_root())
    adj = (r.get("brief") or {}).get("adjust") or {}
    out = []
    for row in (r.get("cost") or {}).get("rows", []):
        prods = catalog.products_for(cats, row["code"], row.get("variant"))
        if not prods and not (adj.get("catalog") or {}).get(row["code"]):
            continue
        out.append({"code": row["code"], "name": row["name"], "unit": row["unit"], "quantity": row["quantity"],
                    "unit_price": row["unit_price"], "variant": row.get("variant"), "selected": row.get("catalog"),
                    "products": prods[:12]})
    return {"catalogs": [_cat_info(c) for c in cats], "rows": out}


class CatPick(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    catalog: Annotated[str, Field(max_length=40)]
    product: Annotated[str, Field(max_length=10)]


class CatSelectIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    select: Annotated[dict[Annotated[str, Field(max_length=30)], CatPick | None], Field(max_length=200)]


@router.put("/api/projects/{pid}/catalog")
def set_project_catalog(pid: str, body: CatSelectIn):
    d, r = _project(pid)
    adj = copy.deepcopy((r.get("brief") or {}).get("adjust") or {})
    cats = {c["id"]: c for c in catalog.load_all(_cat_root())}
    sel = dict(adj.get("catalog") or {})
    for code, pick in body.select.items():
        if pick is None:
            sel.pop(code, None)
            continue
        c = cats.get(pick.catalog)
        p = next((x for x in (c or {}).get("items", []) if x["id"] == pick.product and x["code"] == code), None)
        if p is None:
            raise HTTPException(422, f"{code}: katalog ürünü bulunamadı")
        sel[code] = catalog.selection(p)
        if p.get("variant"):
            adj.setdefault("variants", {})[code] = p["variant"]
        (adj.get("overrides") or {}).pop(code, None)   # elle girilmiş birim fiyat katalog seçimini gölgelemesin
    adj["catalog"] = sel
    try:
        res = project.readjust(d, costing.validate_adjust(adj))
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    return {"project": _app()._public(pid, res)}
