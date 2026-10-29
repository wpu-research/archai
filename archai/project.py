"""Uçtan uca proje: brif → plan → metraj → maliyet → şartname → çizimler → teklif (→ 3D).

Brif iki şekilde verilebilir:
  arazi modu : {"parcel": {width, depth}, "zoning": {...}, "program": {unit_type, units_per_floor}}
  hızlı mod  : {"quick": {gross_area, floors, unit_type}}  — sanal parsel türetilir
Ortak: {"name", "adjust": {...fiyat ayarları}, "company", "customer"}
"""

import json
import math
import os
from pathlib import Path

from . import approval, avan, costing, drawings, poz, quantities as Q, reports, spec
from .dxf_import import import_dxf

SETTINGS = Path(os.environ.get("ARCHAI_OUT") or Path(__file__).resolve().parents[1] / "out") / "settings.json"
INFO_KEYS = ("company", "customer", "site", "owner", "architect", "drawn_by", "checked_by", "approved_by", "rev",
             "offer")


def load_settings():
    try:
        return json.loads(SETTINGS.read_text())
    except (OSError, ValueError):
        return {}


def save_settings(data):
    SETTINGS.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    return data


def build_info(brief):
    """Kalıcı ayarlar (firma, varsayılan imzacılar) + projeye özel künye."""
    base = load_settings()
    info = {k: base.get(k) for k in INFO_KEYS if base.get(k)}
    for k in INFO_KEYS:
        v = brief.get(k)
        if isinstance(v, dict):
            info[k] = {**(info.get(k) or {}), **{a: b for a, b in v.items() if b}}
        elif v:
            info[k] = v
    if not info.get("owner") and (info.get("customer") or {}).get("name"):
        info["owner"] = info["customer"]["name"]
    return info
from .generate import generate


def quick_brief(q):
    """m² + kat + daire tipinden, imarı birebir o binayı veren sanal parsel."""
    from .generate import module_cap, quick_envelope
    floors = int(q["floors"])
    fp = q["gross_area"] / floors
    env = quick_envelope(q)   # kat başına 3–4 daire: çekirdek + ön/arka daireler için gereken kutu (T kütle dahil)
    if env:
        width, depth = env
    elif fp > module_cap(q.get("unit_type", "auto")) and q.get("units_per_floor", "auto") == "auto":
        # birden çok çekirdek modülü gerekecek: üretici 10–15 m derinlik arasında seçebilsin
        depth, width = 15.25, fp / 10.0 + 0.5
    else:
        depth = 13.5 if fp >= 120 else max(9.0, math.sqrt(fp))  # konut için tipik bina derinliği
        width = fp / depth
    # +0,1 m pay: dış yüz çekme çizgisine 5 cm'lik aks yuvarlamasıyla taşmasın (yoksa bina kırpılır)
    parcel = {"width": round(width + 6.1, 2), "depth": round(depth + 8.1, 2)}
    A = parcel["width"] * parcel["depth"]
    zoning = {"taks": fp / A * 1.001, "kaks": q["gross_area"] / A * 1.001, "front": 5, "side": 3, "rear": 3,
              "max_floors": floors, "floor_height": q.get("floor_height", 3.0)}
    return parcel, zoning, {"unit_type": q.get("unit_type", "auto"), "units_per_floor": q.get("units_per_floor", "auto"),
                            "quick_area": float(q["gross_area"])}


def run(brief, out_dir, render_3d=False):
    """Arazi veya hızlı mod: plan üret, sonra tüm çıktıları hazırla."""
    if "quick" in brief:
        parcel, zoning, program = quick_brief(brief["quick"])
    else:
        parcel, zoning, program = brief["parcel"], brief["zoning"], brief.get("program", {})
    if parcel.get("polygon"):
        from .parcel import generate_on_polygon
        elements, report = generate_on_polygon(parcel, zoning, program)
    else:
        elements, report = generate(parcel, zoning, program)
    elements, report = avan.apply(elements, report, parcel, zoning, program)
    meta = {"parcel": parcel, "zoning": zoning, "program": program}
    return finalize(brief, elements, report, meta, out_dir, render_3d), elements


def run_dxf(dxf_path, brief, out_dir, render_3d=False):
    """Mevcut plandan (DXF): içe aktar, sonra tüm çıktıları hazırla."""
    p = brief.get("dxf", {})
    elements, imp = import_dxf(dxf_path, floors=int(p.get("floors", 1)), floor_height=float(p.get("floor_height", 3.0)))
    s = Q.compute(elements)["summary"]
    report = {**imp, "gross_total": s["gross_floor_area"], "unit_count": p.get("unit_count", ""),
              "unit_type": p.get("unit_type", ""), "source": "dxf"}
    return finalize(brief, elements, report, {"dxf": str(dxf_path)}, out_dir, render_3d), elements


VISION_UNVERIFIED = "Mahal adları ve mobilya yapay zekâ okumasıdır — doğrulanmadı"


def _vision(img_path, elements, rep, mode=False, client=None):
    """Hibrit okuma (Claude): mahal adları + çizimdeki mobilya. Plan görseli Anthropic'e YALNIZ kullanıcı onayıyla
    (brief image.vision is True) gönderilir; testte sahte `client` verilirse onay sayılır. Onay yoksa, kimlik yoksa,
    mahal yoksa ya da hata olursa çağrı yapılmaz / geometriyle devam edilir."""
    from PIL import Image

    from . import plan_vision
    if mode is not True and client is None:
        rep["vision"] = "kapalı (onay verilmedi)"
        rep["warnings"].append("Claude görsel okuma kapalı: planı Anthropic'e göndermek için onay kutusunu işaretleyin")
        return None
    if client is None and not plan_vision.available():
        rep["vision"] = "kapalı (kimlik yok)"
        rep["warnings"].append("Claude görsel okuma onaylandı ama Anthropic kimlik bilgisi yok: mahal adı ve mobilya "
                               "okunmadı — ANTHROPIC_API_KEY tanımlayın veya `ant auth login`")
        return None
    rooms = [e for e in elements if e["type"] == "room"]
    if not rooms:
        rep["vision"] = "kapalı (mahal yok)"
        rep["warnings"].append("Claude görsel okuma yapılmadı: tanınan mahal yok")
        return None
    levels = sorted({e["level"] for e in rooms}, key=lambda n: next(e["z"] for e in rooms if e["level"] == n))
    first = [e for e in rooms if e["level"] == levels[0]]
    S, H = rep["px_per_m"], Image.open(img_path).height
    try:
        data = plan_vision.ask(img_path, first, S, client=client)
    except Exception as ex:  # noqa: BLE001 — görsel okuma isteğe bağlı: plan geometrisi yine üretilir
        rep["vision"] = f"hata: {ex}"
        rep["warnings"].append(f"Claude görsel okuma başarısız ({ex}); mahal adları ve mobilya okunmadı")
        return None
    plan_vision.apply(elements, data)
    objs = []
    for lv in levels:  # normal katlar aynı: mobilya her katta tekrarlanır
        for o in plan_vision.furniture_objects(data.get("furniture", []), lv, S, H):
            objs.append({**o, "id": f"{o['id']}_{len(objs)}"})
    rep["vision"] = "claude"
    rep["furniture"] = len(objs) // max(1, len(levels))
    rep["warnings"].append(VISION_UNVERIFIED)
    return {"floors": {}, "paint": "kirik_beyaz", "objects": objs}


def run_image(img_path, brief, out_dir, render_3d=False):
    """Resim plandan (PNG/JPG ekran görüntüsü, tarama): tanı, onay görselini yaz, sonra tüm çıktılar."""
    from . import plan_image
    p = brief.get("image", {})
    elements, rep = plan_image.recognize(img_path, px_per_m=p.get("px_per_m"), grid_m=p.get("grid_m"),
                                         floors=int(p.get("floors", 1)), floor_height=float(p.get("floor_height", 3.0)))
    design = _vision(img_path, elements, rep, p.get("vision") is True)   # yalnız açık onay (bool True)
    s = Q.compute(elements)["summary"]
    report = {**rep, "gross_total": s["gross_floor_area"], "unit_count": p.get("unit_count", ""),
              "unit_type": p.get("unit_type", "")}
    result = finalize(brief, elements, report, {"image": str(img_path)}, out_dir, render_3d)
    if design:
        (Path(out_dir) / "interior.json").write_text(json.dumps(design, ensure_ascii=False))
    ov = plan_image.overlay(img_path, elements, rep, Path(out_dir) / "tanima_onay.png")
    result["files"]["tanima_onay_png"] = str(ov)
    (Path(out_dir) / "project.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    return result, elements


def run_villa(out_dir, brief=None, render_3d=False):
    """Demo senaryosu: döşenmiş iki katlı villa (archai/villa.py)."""
    from . import villa
    elements, report, design = villa.scenario()
    brief = {"name": "Villa Demo", **(brief or {})}
    meta = {"parcel": {"width": villa.PARCEL[0], "depth": villa.PARCEL[1]}, "zoning": villa.ZONING,
            "program": {"unit_type": "Villa 4+2", "scenario": "villa"}}
    result = finalize(brief, elements, report, meta, out_dir, render_3d)
    (Path(out_dir) / "interior.json").write_text(json.dumps(design, ensure_ascii=False))
    return result, elements


def run_cabin(out_dir, brief=None, render_3d=False):
    """Demo senaryosu: tomruk dağ evi, zemin + asma kat, veranda (archai/cabin.py)."""
    from . import cabin
    elements, report, design = cabin.scenario()
    brief = {"name": "Dağ Evi Demo", **(brief or {})}
    meta = {"parcel": {"width": cabin.PARCEL[0], "depth": cabin.PARCEL[1]}, "zoning": cabin.ZONING,
            "program": {"unit_type": "Dağ Evi 1+1", "scenario": "cabin"}}
    result = finalize(brief, elements, report, meta, out_dir, render_3d)
    (Path(out_dir) / "interior.json").write_text(json.dumps(design, ensure_ascii=False))
    return result, elements


def run_apartment(out_dir, brief=None, render_3d=False):
    """Senaryo: 3 daireli apartman normal katı, CAD kat planından birebir (archai/apartment.py)."""
    from . import apartment
    elements, report, design = apartment.scenario()
    brief = {"name": "Apartman Katı", **(brief or {})}
    meta = {"parcel": {"width": apartment.PARCEL[0], "depth": apartment.PARCEL[1]}, "zoning": apartment.ZONING,
            "program": {"unit_type": "3 × 2+1", "scenario": "apartment"}}
    result = finalize(brief, elements, report, meta, out_dir, render_3d)
    (Path(out_dir) / "interior.json").write_text(json.dumps(design, ensure_ascii=False))
    return result, elements


def finalize(brief, elements, report, meta, out_dir, render_3d=False):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = brief.get("name", "Proje")
    Q.mark_exterior(elements)   # dış/iç duvar ayrımı: kaynağın yazmadığı duvarlar için kat konturundan
    q = Q.compute(elements)
    cost = costing.estimate(q, adjust=brief.get("adjust"))
    info = build_info(brief)
    files = write_documents(out, name, brief, report, q, cost, info)
    files.update({f"cizim_{k}": v for k, v in
                  drawings.export_all(out / "cizimler", elements, report, meta.get("zoning", {}), name, info).items()})
    if render_3d:
        files.update(render(elements, out / "3d"))
    result = {"name": name, "brief": brief, **meta, "report": report, "summary": q["summary"], "rooms": q["rooms"],
              "cost": cost, "files": files}
    (out / "elements.json").write_text(json.dumps(elements, ensure_ascii=False, indent=1))
    (out / "project.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    return result


def write_documents(out, name, brief, report, q, cost, info=None):
    info = info if info is not None else build_info(brief)
    # onay damgası: kayıtlı onayın parmak izi bu içerikle tutuyorsa onaylı, yoksa TASLAK (archai/approval.py)
    info = {**info, "onay": approval.stamp_for(out, approval.fingerprint(q, cost, brief))}
    sp = spec.build_spec(name, q, cost)
    return {
        "metraj_maliyet_xlsx": str(reports.write_xlsx(out / "metraj_maliyet.xlsx", name, q, cost, info)),
        "sartname_docx": str(reports.write_docx(out / "teknik_sartname.docx", sp, cost, info)),
        "teklif_docx": str(reports.write_offer_docx(out / "teklif.docx", name, report, q, cost, info=info)),
        **dict(zip(("kesif_xlsx", "kesif_csv"), map(str, poz.write_kesif(
            out / "kesif_ozeti.xlsx", out / "kesif_ozeti.csv", name, cost, brief.get("adjust"), info)))),
    }


def readjust(out_dir, adjust):
    """Fiyat ayarı değişince: maliyeti yeniden hesapla, belgeleri yeniden yaz (çizimler aynı kalır)."""
    out = Path(out_dir)
    result = json.loads((out / "project.json").read_text())
    elements = json.loads((out / "elements.json").read_text())
    q = Q.compute(elements)
    cost = costing.estimate(q, adjust=adjust)
    result["brief"]["adjust"] = adjust
    result["cost"] = cost
    result["files"].update(write_documents(out, result["name"], result["brief"], result["report"], q, cost))
    (out / "project.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    return result


def render(elements, out_dir):
    """Blender'da kur, yörünge kamera, preview + colormap kareleri ve web için GLB."""
    import sys
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "mcp_server"))
    import server as s
    out = Path(out_dir)
    s.reset_scene()
    r = s.build(elements)
    if r["errors"]:
        raise RuntimeError(r["errors"][:5])
    s.camera_path(mode="orbit", frames=2, lens=24, degrees=10, start_angle=-120)
    files = {"preview_png": s.render(kind="preview", still=1, out_dir=str(out), samples=32)["image"],
             "colormap_png": s.render(kind="colormap", still=1, out_dir=str(out))["image"]}
    files["model_glb"] = s.export_glb(str(out / "model.glb"))["glb"]
    return files


def redocument(out_dir):
    """Belgeleri kayıtlı maliyetle yeniden üret (onay damgası değişince); içerik ve çizimler aynı kalır."""
    out = Path(out_dir)
    result = json.loads((out / "project.json").read_text())
    q = Q.compute(json.loads((out / "elements.json").read_text()))
    result["files"].update(write_documents(out, result["name"], result["brief"], result["report"], q, result["cost"]))
    (out / "project.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    return result
