"""Uçtan uca proje: brif → plan → metraj → maliyet → şartname → çizimler → teklif (→ 3D).

Brif iki şekilde verilebilir:
  arazi modu : {"parcel": {width, depth}, "zoning": {...}, "program": {unit_type, units_per_floor}}
  hızlı mod  : {"quick": {gross_area, floors, unit_type}}  — sanal parsel türetilir
Ortak: {"name", "adjust": {...fiyat ayarları}, "company", "customer"}
"""

import json
import math
from pathlib import Path

from . import costing, drawings, quantities as Q, reports, spec
from .dxf_import import import_dxf
from .generate import generate


def quick_brief(q):
    """m² + kat + daire tipinden, imarı birebir o binayı veren sanal parsel."""
    floors = int(q["floors"])
    fp = q["gross_area"] / floors
    depth = 13.5 if fp >= 120 else max(9.0, math.sqrt(fp))  # konut için tipik bina derinliği
    width = fp / depth
    parcel = {"width": round(width + 6, 2), "depth": round(depth + 8, 2)}
    A = parcel["width"] * parcel["depth"]
    zoning = {"taks": fp / A * 1.001, "kaks": q["gross_area"] / A * 1.001, "front": 5, "side": 3, "rear": 3,
              "max_floors": floors, "floor_height": q.get("floor_height", 3.0)}
    return parcel, zoning, {"unit_type": q.get("unit_type", "auto"), "units_per_floor": q.get("units_per_floor", "auto")}


def run(brief, out_dir, render_3d=False):
    """Arazi veya hızlı mod: plan üret, sonra tüm çıktıları hazırla."""
    if "quick" in brief:
        parcel, zoning, program = quick_brief(brief["quick"])
    else:
        parcel, zoning, program = brief["parcel"], brief["zoning"], brief.get("program", {})
    elements, report = generate(parcel, zoning, program)
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


def finalize(brief, elements, report, meta, out_dir, render_3d=False):
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    name = brief.get("name", "Proje")
    q = Q.compute(elements)
    cost = costing.estimate(q, adjust=brief.get("adjust"))
    files = write_documents(out, name, brief, report, q, cost)
    files.update({f"cizim_{k}": v for k, v in
                  drawings.export_all(out / "cizimler", elements, report, meta.get("zoning", {}), name).items()})
    if render_3d:
        files.update(render(elements, out / "3d"))
    result = {"name": name, "brief": brief, **meta, "report": report, "summary": q["summary"], "rooms": q["rooms"],
              "cost": cost, "files": files}
    (out / "elements.json").write_text(json.dumps(elements, ensure_ascii=False, indent=1))
    (out / "project.json").write_text(json.dumps(result, ensure_ascii=False, indent=1, default=str))
    return result


def write_documents(out, name, brief, report, q, cost):
    sp = spec.build_spec(name, q, cost)
    return {
        "metraj_maliyet_xlsx": str(reports.write_xlsx(out / "metraj_maliyet.xlsx", name, q, cost)),
        "sartname_docx": str(reports.write_docx(out / "teknik_sartname.docx", sp, cost)),
        "teklif_docx": str(reports.write_offer_docx(out / "teklif.docx", name, report, q, cost,
                                                   brief.get("company"), brief.get("customer"))),
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
