"""Proje araçları API'si: kat irtifakı ön tablosu, statik ön boyutlandırma, versiyon karşılaştırma. app.py yalnızca bu router'ı ekler.

    GET  /api/projects/{pid}/kat-irtifaki           bağımsız bölümler, net/brüt, arsa payı (+ .xlsx)
    GET  /api/projects/{pid}/statik?sigma=150       statik ön boyutlandırma (avan, imzasız) (+ .xlsx)
    POST /api/projects/{pid}/statik/uygula          kolon/kiriş/perde kalemlerini ön boyutlandırma miktarıyla günceller (maliyet + belgeler)
    GET  /api/projects/{pid}/karsilastir/{other}    iki projenin girdi, alan ve maliyet farkı
"""
import copy
import json
import math
import re
import shutil
from typing import Annotated, Literal

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from archai import approval, capraz, compare, finance_scenarios, fizibilite, kat_irtifaki, odeme_plani, offer_packages, project, sponsor, statik
from archai.notice import AVAN_SHORT

router = APIRouter()


def _app():
    import webapp.app as m
    return m


def _load(pid):
    d = _app()._pdir(pid, "elements.json")
    return d, json.loads((d / "project.json").read_text()), json.loads((d / "elements.json").read_text())


@router.get("/api/projects/{pid}/kat-irtifaki")
def kat_irtifaki_table(pid: str):
    d, r, els = _load(pid)
    res = kat_irtifaki.compute(els, (r.get("report") or {}).get("parcel_area"))
    kat_irtifaki.write_xlsx(d / "kat_irtifaki.xlsx", r.get("name", pid), res)
    return {**res, "dosya": f"/files/{pid}/kat_irtifaki.xlsx", "damga": AVAN_SHORT}


@router.get("/api/projects/{pid}/statik")
def statik_table(pid: str, sigma: float = statik.SIGMA_EM):
    if not 30 <= sigma <= 2000:
        raise HTTPException(422, "sigma (zemin emniyet gerilmesi, kPa) 30–2000 olmalı")
    d, r, els = _load(pid)
    try:
        res = statik.compute(els, r.get("report"), sigma)
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    statik.write_xlsx(d / "statik_on_boyutlandirma.xlsx", r.get("name", pid), res)
    cost = {x["code"]: x for x in (r.get("cost") or {}).get("rows", [])}
    onerilen = statik.adjust_for(res)
    kiyas = [{"kod": k, "ad": (cost.get(k) or {}).get("name", "")[:60], "birim": (cost.get(k) or {}).get("unit"),
              "avan_orani": (cost.get(k) or {}).get("quantity"), "on_boyutlandirma": v} for k, v in onerilen.items()]
    return {**res, "kiyas": kiyas, "dosya": f"/files/{pid}/statik_on_boyutlandirma.xlsx", "damga": AVAN_SHORT}


@router.post("/api/projects/{pid}/statik/uygula")
def statik_apply(pid: str):
    m = _app()
    d, r, els = _load(pid)
    try:
        res = statik.compute(els, r.get("report"))
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    adj = copy.deepcopy((r.get("brief") or {}).get("adjust") or {})
    adj.setdefault("qty_overrides", {}).update(statik.adjust_for(res))
    out = m._run(lambda: m._public(pid, project.readjust(d, m._validate_adjust(adj))))
    return {"uygulanan": statik.adjust_for(res), "maliyet": {k: out["cost"].get(k) for k in ("total_before_vat", "vat", "total", "per_m2")}}


@router.get("/api/projects/{pid}/karsilastir/{other}")
def karsilastir(pid: str, other: str):
    m = _app()
    a = json.loads((m._pdir(pid, "project.json") / "project.json").read_text())
    b = json.loads((m._pdir(other, "project.json") / "project.json").read_text())
    return {**compare.diff(a, b), "a": {"id": pid, "ad": a.get("name")}, "b": {"id": other, "ad": b.get("name")}}


# ------------------------------------------------------------------ kontrollü proje alternatifi
_ALT_FIELDS = ("name", "floors", "unit_type", "units_per_floor")


class AlternatifIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    name: Annotated[str, Field(min_length=1, max_length=100)]
    floors: Annotated[int, Field(ge=1, le=30)] | None = None
    unit_type: Annotated[str, Field(max_length=20)] | None = None
    units_per_floor: Literal["auto"] | Annotated[int, Field(ge=1, le=20)] | None = None
    acknowledgement: Annotated[bool, Field(default=False)] = False


def _is_compatible_source(brief):
    """Kaynak proje uygun mu? Sadece arazi ve hızlı mod desteklenir."""
    if brief.get("tablo"):
        return False, "avan tablosu projelerinden alternatif oluşturulamaz"
    if brief.get("dxf"):
        return False, "DXF/resim planından üretilen projelerden alternatif oluşturulamaz"
    if brief.get("image"):
        return False, "resim planından üretilen projelerden alternatif oluşturulamaz"
    if (brief.get("program") or {}).get("scenario") in ("villa", "cabin", "apartment"):
        return False, "demo senaryo projelerinden alternatif oluşturulamaz"
    return True, ""


@router.post("/api/projects/{pid}/alternatif")
def create_alternative(pid: str, body: AlternatifIn):
    """Kaynak projeden, kayıtlı brifi baz alarak bağımsız bir alternatif proje oluşturur.

    - Kaynak proje değişmez (onay/senaryo kopyalanmaz)
    - Manuel geometri düzenlemeleri (cephe düzeltmesi vb.) KOPYALANMAZ; kaydedilen girdilerden yeniden üretilir
    - Sadece 'arazi' ve 'hızlı mod' kaynak projeleri desteklenir
    - Alternatif brief'a `lineage` (parent_id, source_fingerprint) eklenir
    - Onay, fizibilite senaryoları, tasarım setleri kopyalanmaz
    - Karşılaştırma için mevcut /karsilastir endpoint'i kullanılabilir
    """
    if not body.acknowledgement:
        raise HTTPException(422, "manuel geometri düzenlemelerinin (cephe düzeltmesi vb.) KOPYALANMADIĞINI ve "
                                 "alternatif projenin KAYITLI GİRDİLERDEN YENİDEN ÜRETİLECEĞİNİ onaylamalısınız")

    m = _app()
    src_dir = m._pdir(pid, "project.json")
    src_result = json.loads((src_dir / "project.json").read_text())
    src_brief = src_result.get("brief") or {}

    # Demo bilgisi brifte değil, üretim metadata'sında saklanır.
    if (src_result.get("program") or {}).get("scenario") in ("villa", "cabin", "apartment"):
        raise HTTPException(422, "demo senaryo projelerinden alternatif oluşturulamaz")
    # Kaynak uygunluk kontrolü
    ok, msg = _is_compatible_source(src_brief)
    if not ok:
        raise HTTPException(422, msg)

    # Kaydedilmiş girdilerden yeni brief oluştur (manuel düzenlemeler atlanır)
    if src_brief.get("quick"):
        # Hızlı mod: quick alanlarını kopyala, opsiyonel override ile
        quick = dict(src_brief["quick"])
        if body.floors is not None:
            quick["floors"] = body.floors
        if body.unit_type is not None:
            quick["unit_type"] = body.unit_type
        if body.units_per_floor is not None:
            quick["units_per_floor"] = body.units_per_floor
        new_brief = {
            "name": body.name,
            "quick": quick,
        }
    else:
        # Arazi modu: parcel + zoning + program
        parcel = src_brief.get("parcel")
        zoning = src_brief.get("zoning")
        program = dict(src_brief.get("program") or {})
        if body.floors is not None:
            if zoning:
                zoning = dict(zoning)
                zoning["max_floors"] = body.floors
        if body.unit_type is not None:
            program["unit_type"] = body.unit_type
        if body.units_per_floor is not None:
            program["units_per_floor"] = body.units_per_floor
        new_brief = {
            "name": body.name,
            "parcel": parcel,
            "zoning": zoning,
            "program": program,
        }

    # Lineage: parent_id + source_fingerprint (metraj parmak izi)
    from archai import approval as A
    elements = json.loads((src_dir / "elements.json").read_text())
    from archai import quantities as Q
    q = Q.compute(elements)
    source_fp = A.quantities_fp(q)

    lineage = {
        "parent_id": pid,
        "source_fingerprint": source_fp,
    }

    # Ayarları kopyala (adjust, company, customer, vb.) — onay/senaryo hariç
    for k in ("adjust", *project.INFO_KEYS):
        if src_brief.get(k):
            new_brief[k] = src_brief[k]

    # Yeni proje üret
    render_3d = src_brief.get("render_3d", False)
    try:
        b = m.Brief.model_validate(new_brief)
        brief_dump = m._brief_dump(b)
        brief_dump["lineage"] = lineage
        result = m.create_from_brief(brief_dump, render_3d)
    except ValidationError as ex:
        raise HTTPException(422, "geçersiz değer: " + m._errors_detail(ex.errors()))
    except HTTPException:
        raise
    except ValueError as ex:
        raise HTTPException(422, str(ex) or "geçersiz değer")

    return {"ok": True, "alternative": result, "source": {"id": pid, "name": src_result.get("name")}}


@router.get("/api/projects/{pid}/capraz-dogrulama")
def capraz_dogrulama(pid: str):
    d, r, els = _load(pid)
    return capraz.compute(r, els)


@router.get("/api/projects/{pid}/odeme-plani")
def odeme(pid: str, ay: int | None = None, avans: float | None = None, teminat: float | None = None):
    d, r, _ = _load(pid)
    try:
        plan = odeme_plani.compute(r["cost"], (r.get("report") or {}).get("gross_total"), ay, avans, teminat)
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    odeme_plani.write_xlsx(d / "odeme_plani.xlsx", r.get("name", pid), plan)
    return {**plan, "dosya": f"/files/{pid}/odeme_plani.xlsx"}


class FizibiliteIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", allow_inf_nan=False)
    arsa_bedeli_tl: Annotated[float, Field(ge=0, le=1e15)]
    satis_m2_fiyati_tl: Annotated[float, Field(ge=0.01, le=1e9)]
    satilabilir_alan_m2: Annotated[float, Field(ge=0.01, le=1e8)]
    ek_gider_pct: Annotated[float, Field(ge=0, le=100)] = 0


@router.post("/api/projects/{pid}/fizibilite")
def fizibilite_hesapla(pid: str, body: FizibiliteIn):
    _, r, els = _load(pid)
    try:
        result = fizibilite.compute(r, els, **body.model_dump())
    except approval.QuantitiesMismatchError as ex:
        raise HTTPException(409, str(ex)) from ex
    except ValueError as ex:
        raise HTTPException(422, str(ex)) from ex
    return {"proje_id": pid, **result}


class ScenarioIn(FizibiliteIn):
    ad: Annotated[str, Field(min_length=1, max_length=80)]
    proje_parmak_izi: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


@router.get("/api/projects/{pid}/fizibilite/senaryolar")
def fizibilite_senaryolari(pid: str):
    d, r, els = _load(pid)
    return finance_scenarios.list_saved(d, r, els)


@router.post("/api/projects/{pid}/fizibilite/senaryolar")
def fizibilite_kaydet(pid: str, body: ScenarioIn):
    d, r, els = _load(pid)
    try:
        result = fizibilite.compute(r, els, **body.model_dump(exclude={"ad", "proje_parmak_izi"}))
        if result["kaynak"]["proje_parmak_izi"] != body.proje_parmak_izi:
            raise HTTPException(409, "Proje hesaplamadan sonra değişti. Kaydetmeden önce fizibiliteyi yeniden hesaplayın.")
        saved = finance_scenarios.save(d, body.ad, result)
    except approval.QuantitiesMismatchError as ex:
        raise HTTPException(409, str(ex)) from ex
    except ValueError as ex:
        raise HTTPException(422, str(ex)) from ex
    return {"senaryo": saved}


@router.get("/api/projects/{pid}/fizibilite/senaryolar/{scenario_id}/export")
def fizibilite_senaryo_export(pid: str, scenario_id: str):
    """Kaydedilen hesabı, güncellik bilgisini koruyarak JSON dosyası olarak indirir."""
    if not re.fullmatch(r"[0-9a-f]{32}", scenario_id):
        raise HTTPException(404, "senaryo bulunamadı")
    d, r, els = _load(pid)
    rows = finance_scenarios.list_saved(d, r, els)["senaryolar"]
    row = next((item for item in rows if item["id"] == scenario_id), None)
    if row is None:
        raise HTTPException(404, "senaryo bulunamadı")
    return JSONResponse(row, headers={"Content-Disposition": f'attachment; filename="fizibilite-{scenario_id}.json"'})


@router.delete("/api/projects/{pid}/fizibilite/senaryolar/{scenario_id}")
def fizibilite_senaryo_sil(pid: str, scenario_id: str):
    if not re.fullmatch(r"[0-9a-f]{32}", scenario_id):
        raise HTTPException(404, "senaryo bulunamadı")
    d, _, _ = _load(pid)
    if not finance_scenarios.delete(d, scenario_id):
        raise HTTPException(404, "senaryo bulunamadı")
    return {"ok": True, "id": scenario_id}


# ------------------------------------------------------------------ sürümlü teklif paketi
def _offer_urls(pid, package):
    return {**package, "documents": {
        key: {**doc, "url": f"/files/{pid}/teklif_paketleri/v{package['version']:04d}/{doc['file']}"}
        for key, doc in package["documents"].items()}}


@router.get("/api/projects/{pid}/teklif-paketleri")
def teklif_paketleri(pid: str):
    d = _app()._pdir(pid, "project.json")
    return {"paketler": [_offer_urls(pid, p) for p in offer_packages.list_saved(d)]}


@router.post("/api/projects/{pid}/teklif-paketleri")
def teklif_paketi_olustur(pid: str):
    d, record, elements = _load(pid)
    try:
        package = offer_packages.create(d, record, elements)
    except approval.QuantitiesMismatchError as ex:
        raise HTTPException(409, str(ex)) from ex
    except ValueError as ex:
        raise HTTPException(422, str(ex)) from ex
    return {"paket": _offer_urls(pid, package)}


# ------------------------------------------------------------------ cephe düzeltme (elle)
SIDE_TR = {"on": "ÖN", "arka": "ARKA", "sol": "SOL", "sag": "SAĞ"}
DOOR_W, WIN_W = (0.7, 3.0), (0.4, 6.0)
GAP = 0.10


def _ext_walls(els):
    bx = [p[0] for e in els if e["type"] == "slab" and e.get("role") == "floor" for p in e["points"]]
    by = [p[1] for e in els if e["type"] == "slab" and e.get("role") == "floor" for p in e["points"]]
    cx, cy = (min(bx) + max(bx)) / 2, (min(by) + max(by)) / 2
    out = []
    for e in els:
        if e["type"] != "wall" or not e.get("exterior"):
            continue
        (ax, ay), (bx_, by_) = e["start"], e["end"]
        horiz = abs(ay - by_) < 1e-6
        side = ("on" if ay < cy else "arka") if horiz else ("sol" if ax < cx else "sag")
        out.append((e, side, math.dist((ax, ay), (bx_, by_))))
    return out


def _level_key(name):
    return name.split("/", 1)[0]


class CepheOp(BaseModel):
    model_config = ConfigDict(extra="forbid")
    duvar: Annotated[str, Field(max_length=80)]
    islem: Literal["degistir", "sil", "ekle"]
    index: Annotated[int, Field(ge=0, le=200)] | None = None
    kind: Literal["window", "door"] | None = None
    offset: Annotated[float, Field(ge=0, le=200)] | None = None
    width: Annotated[float, Field(gt=0, le=20)] | None = None
    sill: Annotated[float, Field(ge=0, le=3)] | None = None
    height: Annotated[float, Field(gt=0, le=5)] | None = None
    ayni_katlar: bool = False


class CepheIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    islemler: Annotated[list[CepheOp], Field(min_length=1, max_length=60)]


@router.get("/api/projects/{pid}/cephe")
def cephe(pid: str):
    _, _, els = _load(pid)
    out = []
    for e, side, ln in sorted(_ext_walls(els), key=lambda t: (t[0]["base_z"], t[1], t[0]["name"])):
        out.append({"duvar": e["name"], "kat": e["level"], "yon": side, "yon_ad": SIDE_TR[side], "uzunluk": round(ln, 2),
                    "yukseklik": round(e.get("height", 0), 2), "acikliklar": [
                        {"index": i, "kind": o["kind"], "offset": o["offset"], "width": o["width"], "sill": o.get("sill", 0.0),
                         "height": o.get("height")} for i, o in enumerate(e.get("openings", []))]})
    return {"duvarlar": out, "damga": AVAN_SHORT,
            "not": "Cephe düzeltmesi eleman listesini değiştirir; metraj, maliyet, belgeler ve çizimler yeniden üretilir. Önceki hal "
                   "elements.onceki.json olarak yedeklenir."}


def _apply_op(wall, op, length):
    ops = wall.setdefault("openings", [])
    if op.islem == "sil":
        if op.index is None or op.index >= len(ops):
            raise ValueError("silinecek açıklık yok")
        ops.pop(op.index)
        return
    if op.islem == "ekle":
        if op.kind is None or op.offset is None or op.width is None:
            raise ValueError("ekleme için kind, offset ve width gerekli")
        o = {"offset": op.offset, "width": op.width, "kind": op.kind}
        o.update({"height": op.height or (2.1 if op.kind == "door" else 1.4)})
        o.update({"leaf": True} if op.kind == "door" else {"sill": 0.9 if op.sill is None else op.sill})
        ops.append(o)
        target = o
    else:
        if op.index is None or op.index >= len(ops):
            raise ValueError("değiştirilecek açıklık yok")
        target = ops[op.index]
        for k, v in (("kind", op.kind), ("offset", op.offset), ("width", op.width), ("sill", op.sill), ("height", op.height)):
            if v is not None:
                target[k] = v
        if target["kind"] == "door":
            target.pop("sill", None)
            target["leaf"] = True
        elif "sill" not in target:
            target["sill"] = 0.9
            target.pop("leaf", None)
    lo, hi = DOOR_W if target["kind"] == "door" else WIN_W
    if not lo <= target["width"] <= hi:
        raise ValueError(f"{'kapı' if target['kind'] == 'door' else 'pencere'} genişliği {lo:g}–{hi:g} m olmalı")
    if target["offset"] < GAP - 1e-9 or target["offset"] + target["width"] > length - GAP + 1e-9:
        raise ValueError(f"açıklık duvarın içinde kalmalı (duvar {length:.2f} m, kenarlardan ≥ {GAP:g} m)")
    sill = target.get("sill", 0.0)
    if sill + target["height"] > wall.get("height", 2.8) + 1e-9:
        raise ValueError(f"alt kot + yükseklik duvar yüksekliğini ({wall.get('height', 2.8):.2f} m) aşıyor")
    for o in ops:
        if o is not target and not (target["offset"] + target["width"] <= o["offset"] - GAP + 1e-9 or o["offset"] + o["width"] <= target["offset"] - GAP + 1e-9):
            raise ValueError("açıklıklar birbirine çok yakın veya çakışıyor (≥ 10 cm boşluk)")


@router.put("/api/projects/{pid}/cephe")
def cephe_duzelt(pid: str, body: CepheIn):
    m = _app()
    d, r, els = _load(pid)
    walls = {e["name"]: (e, ln) for e, _, ln in _ext_walls(els)}
    applied = 0
    try:
        for op in body.islemler:
            if op.duvar not in walls:
                raise ValueError(f"dış duvar bulunamadı: {op.duvar}")
            targets = [op.duvar]
            if op.ayni_katlar:                                   # aynı plandaki normal katlar (Kat 1, Kat 2 …): aynı duvar adı
                suffix = op.duvar.split("/", 1)[1]
                if _level_key(op.duvar).startswith("Kat "):
                    targets = [n for n in walls if n.startswith("Kat ") and n.split("/", 1)[1] == suffix]
            for n in targets:
                w, ln = walls[n]
                if n != op.duvar and (abs(ln - walls[op.duvar][1]) > 1e-6 or (op.index is not None and op.index >= len(w.get("openings", [])))):
                    continue                                     # aynı geometride olmayan kat atlanır
                _apply_op(w, op, ln)
                applied += 1
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    shutil.copy2(d / "elements.json", d / "elements.onceki.json")      # doğrulama geçti: önceki hali yedekle
    (d / "elements.json").write_text(json.dumps(els, ensure_ascii=False, indent=1))
    out = m._run(lambda: m._public(pid, project.refinalize(d)))
    return {"uygulanan": applied, "maliyet": {k: out["cost"].get(k) for k in ("total", "per_m2")}}


# ------------------------------------------------------------------ sponsor / iş ortağı markalar
class SponsorIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ad: Annotated[str, Field(min_length=1, max_length=80)]
    kategoriler: Annotated[list[str], Field(max_length=10)] = []
    web: Annotated[str, Field(max_length=200)] = ""
    not_: Annotated[str, Field(max_length=300, alias="not")] = ""


class SponsorListIn(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sponsorlar: Annotated[list[SponsorIn], Field(max_length=sponsor.MAX)]


@router.get("/api/sponsorlar")
def sponsorlar():
    return {"sponsorlar": sponsor.load(), "kategoriler": list(sponsor.CATEGORIES),
            "not": "Sponsor, tedarikçi kataloğundaki tedarikçi adıyla eşleşir; projede o kataloğtan seçilen ürünler teklifte "
                   "'Sponsor / Önerilen Markalar' bölümünde görünür. ArchAI firma, ürün veya fiyat içermez."}


@router.put("/api/sponsorlar")
def sponsorlar_kaydet(body: SponsorListIn):
    try:
        items = sponsor.save([{"ad": s.ad, "kategoriler": s.kategoriler, "web": s.web, "not": s.not_} for s in body.sponsorlar])
    except ValueError as ex:
        raise HTTPException(422, str(ex))
    return {"sponsorlar": items}


@router.get("/api/projects/{pid}/sponsorlar")
def proje_sponsorlari(pid: str):
    _, r, _ = _load(pid)
    return {"sponsorlar": sponsor.for_project((r.get("brief") or {}).get("adjust"))}
