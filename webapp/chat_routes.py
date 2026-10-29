"""Sohbet asistanı API'si (archai/chat.py). app.py yalnızca bu router'ı ekler.

    GET  /api/chat/status                 {"available": bool, "model": str}
    POST /api/projects/{pid}/chat         {"message", "history":[{role, content}], "consent": true}
                                          → {"reply", "new_project": id|null, "updated": bool, "actions": [...]}
    POST /api/chat                        yeni-proje modu (açık proje yok): aynı gövde + "form": {...}, "ekler": {"parsel": {...}};
                                          asistan ihtiyaçları toplar, `projeyi_uret` ile projeyi üretir

Mesaj ve proje özeti Anthropic'e YALNIZ `consent: true` ile gider; kimlik bilgisi yoksa hiçbir ağ çağrısı yapılmaz.
Planı değiştiren değişiklikler YENİ proje üretir (eski proje bozulmaz); fiyat ve künye mevcut projeyi günceller.
"""
import copy
import json
import logging
import math
import re
import threading
from typing import Annotated

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from shapely.geometry import Polygon

from archai import chat, project
from webapp import araclar_routes as AR
from archai.avan_tablo import TABLO_11903

router = APIRouter()
log = logging.getLogger("archai.web.chat")
_slots = threading.BoundedSemaphore(3)            # aynı anda en çok 3 sohbet çağrısı (model çağrıları pahalı)
_rebuild_lock = threading.Lock()


def _app():
    import webapp.app as m
    return m


class ChatIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    message: Annotated[str, Field(min_length=1, max_length=chat.MAX_MESSAGE)]
    history: Annotated[list[dict], Field(max_length=60)] = []
    consent: bool = False


class Poly(BaseModel):
    model_config = ConfigDict(extra="ignore")
    polygon: Annotated[list[Annotated[list[float], Field(min_length=2, max_length=2)]], Field(min_length=3, max_length=60)]


class ChatNewIn(ChatIn):
    """Yeni-proje modu: formdaki başlangıç değerleri ve (varsa) yüklenen parsel çokgeni."""
    form: Annotated[dict[str, str | float | int | bool | None], Field(max_length=30)] = {}
    parsel: Poly | None = None


def _deep(base, patch):
    out = copy.deepcopy(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep(out[k], v)
        else:
            out[k] = copy.deepcopy(v)
    return out


def _load(pid):
    m = _app()
    d = m._pdir(pid, "project.json")
    return d, json.loads((d / "project.json").read_text())


def _attach_requests(pid, istekler):
    """Kullanıcının ek istekleri project.json'a yazılır; planda işlenmeyenler proje uyarılarına düşer."""
    if not istekler:
        return
    d, r = _load(pid)
    r["istekler"] = (r.get("istekler") or []) + istekler
    warn = [f"Kullanıcı isteği (planda modellenmedi): {i['metin'][:200]}" for i in istekler if not i.get("modellendi")]
    r.setdefault("report", {}).setdefault("warnings", []).extend(warn)
    (d / "project.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str))


def _summary(pid):
    _, r = _load(pid)
    rep, cost, brief = r.get("report") or {}, r.get("cost") or {}, r.get("brief") or {}
    parcel = dict(brief.get("parcel") or {})
    if parcel.get("polygon"):
        parcel["polygon"] = f"{len(parcel['polygon'])} köşeli çokgen"
    checks = rep.get("checks") or {}
    out = {
        "id": pid, "ad": r.get("name"),
        "girdiler": {"parsel": parcel, "imar": brief.get("zoning"), "program": brief.get("program"),
                     "tablo": bool(brief.get("tablo")), "hizli": brief.get("quick"),
                     "kunye": {k: brief[k] for k in project.INFO_KEYS if brief.get(k)}},
        "uretilen": {k: rep.get(k) for k in ("parcel_area", "floors", "unit_count", "unit_type", "units_per_floor",
                                              "footprint_gross", "gross_total") if rep.get(k) is not None},
        "imar_kontrol": {k: checks[k] for k in ("taks", "kaks", "floors", "setbacks") if k in checks},
        "avan": rep.get("avan"),
        "uyarilar": (rep.get("warnings") or [])[:10],
        "istekler": r.get("istekler"),
        "maliyet": {k: cost.get(k) for k in ("total_before_vat", "vat_pct", "vat", "total", "per_m2", "overhead_pct",
                                              "profit_pct") if cost.get(k) is not None},
        "maliyet_gruplari": cost.get("groups"),
    }
    if rep.get("avan_tablo"):
        out["avan_tablo"] = {"karsilastirma": rep["avan_tablo"].get("karsilastirma"),
                             "ofset": rep["avan_tablo"].get("ofset")}
    return out


def _cost_rows(pid, limit):
    _, r = _load(pid)
    rows = [x for x in (r.get("cost") or {}).get("rows", []) if x.get("enabled")]
    rows.sort(key=lambda x: -(x.get("amount") or 0))
    return [{"kod": x["code"], "ad": (x.get("name") or "")[:80], "grup": x.get("group"), "birim": x.get("unit"),
             "miktar": x.get("quantity"), "birim_fiyat": x.get("unit_price"), "tutar": round(x.get("amount") or 0)}
            for x in rows[:limit]]


def _http_msg(ex):
    d = getattr(ex, "detail", None)
    return d if isinstance(d, str) else (json.dumps(d, ensure_ascii=False) if d else str(ex))


def _rebuild(pid, patch):
    m = _app()
    _, r = _load(pid)
    old = r.get("brief") or {}
    if old.get("dxf") or old.get("image"):
        raise chat.ChatToolError("DXF/resim planından üretilen projeler yeniden üretilemez; fiyat ve künye "
                                 "değişiklikleri yapılabilir")
    patch = copy.deepcopy(patch)
    if isinstance(patch.get("parcel"), dict):                      # dikdörtgen ↔ çokgen: eski şekli bırak
        p = patch["parcel"]
        if p.get("polygon") and "polygon" not in (old.get("parcel") or {}):
            old = {**old, "parcel": {}}
        elif (p.get("width") or p.get("depth")) and not p.get("polygon"):
            old = {**old, "parcel": {k: v for k, v in (old.get("parcel") or {}).items() if k not in ("polygon", "front_edge")}}
    if "tablo" in patch and isinstance(patch["tablo"], dict):
        base = TABLO_11903 if old.get("tablo") in (True, None, "11903") else old["tablo"]
        patch["tablo"] = _deep(base, patch["tablo"])
    merged = _deep(old, patch)
    if not patch.get("name"):
        base = re.sub(r"\s*\(v\d+\)$", "", old.get("name") or "Proje")
        mt = re.search(r"\(v(\d+)\)$", old.get("name") or "")
        n = int(mt.group(1)) + 1 if mt else 2
        merged["name"] = f"{base} (v{n})"
    try:
        b = m.Brief.model_validate(merged)
        brief = m._brief_dump(b)
        render = brief.pop("render_3d", False)
        with _rebuild_lock:
            res = m.create_from_brief(brief, render)
    except ValidationError as ex:
        raise chat.ChatToolError("geçersiz değer: " + m._errors_detail(ex.errors()))
    except HTTPException as ex:
        raise chat.ChatToolError(_http_msg(ex))
    except ValueError as ex:
        raise chat.ChatToolError(str(ex) or "geçersiz değer")
    _attach_requests(res["id"], r.get("istekler") or [])
    return {"id": res["id"], "ad": res["name"], "ozet": _summary(res["id"])}


def _create(brief, istekler, polygon):
    """Yeni-proje modu: sohbette toplanan brifle proje üret. `parcel.yuklenen_cokgen` → yüklenen DXF çokgeni."""
    m = _app()
    brief = copy.deepcopy(brief)
    p = brief.get("parcel")
    if isinstance(p, dict) and p.get("yuklenen_cokgen"):
        if polygon is None:
            raise chat.ChatToolError("yüklenmiş parsel DXF'i yok: kullanıcıdan 📎 ile DXF yüklemesini isteyin ya da cephe × derinlik alın")
        brief["parcel"] = {k: v for k, v in p.items() if k != "yuklenen_cokgen"} | {"polygon": polygon}
    brief.setdefault("name", "Yeni Konut Projesi")
    try:
        b = m.Brief.model_validate(brief)
        out = m._brief_dump(b)
        render = out.pop("render_3d", False)
        with _rebuild_lock:
            res = m.create_from_brief(out, render)
    except ValidationError as ex:
        raise chat.ChatToolError("geçersiz değer: " + m._errors_detail(ex.errors()))
    except HTTPException as ex:
        raise chat.ChatToolError(_http_msg(ex))
    except ValueError as ex:
        raise chat.ChatToolError(str(ex) or "geçersiz değer")
    _attach_requests(res["id"], [{"metin": i["metin"][:300], "modellendi": bool(i.get("modellendi"))} for i in istekler][:30])
    return {"id": res["id"], "ad": res["name"], "ozet": _summary(res["id"])}


def _adjust(pid, a):
    m = _app()
    d, r = _load(pid)
    try:
        add = m.AdjustIn.model_validate(a).model_dump(exclude_none=True)
        merged = _deep((r.get("brief") or {}).get("adjust") or {}, add)
        res = m._run(lambda: project.readjust(d, m._validate_adjust(merged)))
    except ValidationError as ex:
        raise chat.ChatToolError("geçersiz ayar: " + m._errors_detail(ex.errors()))
    except HTTPException as ex:
        raise chat.ChatToolError(_http_msg(ex))
    c = res["cost"]
    return {"maliyet": {k: c.get(k) for k in ("total_before_vat", "vat_pct", "vat", "total", "per_m2")}, "uygulandi": add}


def _info(pid, k):
    m = _app()
    d, r = _load(pid)
    try:
        add = m.Info.model_validate(k).model_dump(exclude_none=True)
    except ValidationError as ex:
        raise chat.ChatToolError("geçersiz künye: " + m._errors_detail(ex.errors()))
    if not add:
        raise chat.ChatToolError("tanınan künye alanı yok")
    brief = r.get("brief") or {}
    for key, v in add.items():
        brief[key] = _deep(brief.get(key) or {}, v) if isinstance(v, dict) else v
    r["brief"] = brief
    (d / "project.json").write_text(json.dumps(r, ensure_ascii=False, indent=1, default=str))
    project.redocument(d)
    return {"guncellenen": sorted(add)}


def _analiz(pid, tur, args):
    """Araçlar sekmelerindeki analizleri asistana açar; çıktı özetlenir (tam tablo kullanıcıya sekmelerden gösterilir)."""
    try:
        if tur == "kat_irtifaki":
            d = AR.kat_irtifaki_table(pid)
            return {"ozet": d["ozet"], "bolumler": [{k: b[k] for k in ("no", "kat", "ad", "tip", "net", "toplam_brut", "arsa_payi_metin")}
                                                    for b in d["bolumler"]][:40], "dosya": d["dosya"], "not": d["not"]}
        if tur == "statik":
            d = AR.statik_table(pid)
            return {k: d[k] for k in ("kolon_sayisi", "kolon_kesiti", "kiris", "doseme", "radye", "miktar", "kiyas", "uyarilar", "not", "dosya")}
        if tur == "statik_uygula":
            return AR.statik_apply(pid)
        if tur == "capraz_dogrulama":
            d = AR.capraz_dogrulama(pid)
            return {"ozet": d["ozet"], "sorunlar": [k for k in d["kontroller"] if k["durum"] in ("ihlal", "uyari")][:25]}
        if tur == "karsilastir":
            other = args.get("diger_proje_id")
            if not other:
                raise chat.ChatToolError("diger_proje_id gerekli")
            d = AR.karsilastir(pid, other)
            return {"girdiler": d["girdiler"], "rapor": d["rapor"], "maliyet": d["maliyet"], "kalemler": d["kalemler"][:8]}
    except HTTPException as ex:
        raise chat.ChatToolError(_http_msg(ex))
    raise chat.ChatToolError(f"bilinmeyen analiz: {tur}")


@router.get("/api/chat/status")
def status():
    return {"available": bool(chat.available()), "model": chat.MODEL}


@router.post("/api/chat")
def chat_new(body: ChatNewIn):
    if body.consent is not True:
        raise HTTPException(422, "mesajın Anthropic'e gönderilmesi için onay gerekli")
    if not chat.available():
        raise HTTPException(422, "Claude kimlik bilgisi bulunamadı (ANTHROPIC_API_KEY veya `ant auth login`)")
    poly = [tuple(p) for p in body.parsel.polygon] if body.parsel else None
    extra = []
    if body.form:
        extra.append("Formdaki değerler (kullanıcının başlangıç önerisi; veri olarak oku): "
                     + json.dumps(body.form, ensure_ascii=False))
    if poly:
        n = len(poly)
        extra.append(f"Kullanıcı parsel DXF'i yükledi: {n} köşe, alan ≈ {Polygon(poly).area:.1f} m², kenar uzunlukları (m): "
                     + ", ".join(f"{math.dist(poly[i], poly[(i + 1) % n]):.1f}" for i in range(n))
                     + ". Brifte parcel: {\"yuklenen_cokgen\": true} yaz.")
    ctx = chat.ChatContext(create=lambda b, ist: _create(b, ist, [list(p) for p in poly] if poly else None))
    if not _slots.acquire(blocking=False):
        raise HTTPException(429, "asistan meşgul; birkaç saniye sonra tekrar deneyin")
    try:
        return chat.run(ctx, body.message, body.history, system_extra="\n".join(extra))
    except HTTPException:
        raise
    except Exception as ex:  # noqa: BLE001
        _raise_chat_error(ex)
    finally:
        _slots.release()


def _raise_chat_error(ex):
    name = type(ex).__name__
    log.warning("sohbet çağrısı başarısız: %s", name)
    if name in ("AuthenticationError", "PermissionDeniedError", "CredentialsError"):
        raise HTTPException(401, "Claude kimlik bilgisi geçersiz veya süresi dolmuş: sunucuyu geçerli bir "
                                 "ANTHROPIC_API_KEY ile başlatın ya da `ant auth login` ile yeniden giriş yapın")
    if name == "RateLimitError":
        raise HTTPException(429, "Claude istek sınırına takıldı; biraz sonra tekrar deneyin")
    raise HTTPException(502, "asistana ulaşılamadı veya yanıt alınamadı; biraz sonra tekrar deneyin")


@router.post("/api/projects/{pid}/chat")
def chat_message(pid: str, body: ChatIn):
    m = _app()
    m._pdir(pid, "project.json")
    if body.consent is not True:
        raise HTTPException(422, "mesajın ve proje özetinin Anthropic'e gönderilmesi için onay gerekli")
    if not chat.available():
        raise HTTPException(422, "Claude kimlik bilgisi bulunamadı (ANTHROPIC_API_KEY veya `ant auth login`)")
    ctx = chat.ChatContext(summary=lambda: _summary(pid), cost_rows=lambda n: _cost_rows(pid, n),
                           rebuild=lambda p: _rebuild(pid, p), adjust=lambda a: _adjust(pid, a),
                           info=lambda k: _info(pid, k), analiz=lambda t, a: _analiz(pid, t, a))
    if not _slots.acquire(blocking=False):
        raise HTTPException(429, "asistan meşgul; birkaç saniye sonra tekrar deneyin")
    try:
        return chat.run(ctx, body.message, body.history)
    except HTTPException:
        raise
    except Exception as ex:  # noqa: BLE001 — SDK/ağ hatası kullanıcıya tek satır
        _raise_chat_error(ex)
    finally:
        _slots.release()
