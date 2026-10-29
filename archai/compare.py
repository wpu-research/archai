"""İki projenin (versiyon) farkı: girdiler, üretilen değerler, maliyet toplamları ve kalem farkları."""
import json
from pathlib import Path

REPORT_KEYS = [("parcel_area", "Parsel alanı", "m²"), ("floors", "Kat adedi", ""), ("unit_count", "Bağımsız bölüm", "adet"),
               ("unit_type", "Daire tipi", ""), ("footprint_gross", "Taban oturumu (zemin)", "m²"),
               ("gross_total", "Toplam inşaat alanı", "m²")]
COST_KEYS = [("total_before_vat", "Toplam (KDV hariç)", "TL"), ("vat", "KDV", "TL"), ("total", "Genel toplam", "TL"),
             ("per_m2", "m² birim maliyet", "TL/m²")]


def _flat(d, prefix=""):
    out = {}
    for k, v in (d or {}).items():
        key = f"{prefix}{k}"
        if isinstance(v, dict):
            out.update(_flat(v, key + "."))
        elif isinstance(v, list) and v and isinstance(v[0], (list, dict)):
            out[key] = f"{len(v)} öğe"
        else:
            out[key] = v
    return out


def _delta(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        d = b - a
        return {"fark": round(d, 2), "yuzde": round(d / a * 100, 1) if a else None}
    return {"fark": None, "yuzde": None}


def load(pdir):
    return json.loads((Path(pdir) / "project.json").read_text())


def diff(a, b, limit=15):
    """a: eski, b: yeni proje kaydı (project.json içeriği)."""
    ra, rb = a.get("report") or {}, b.get("report") or {}
    rapor = [{"anahtar": k, "ad": lab, "birim": u, "a": ra.get(k), "b": rb.get(k), **_delta(ra.get(k), rb.get(k))}
             for k, lab, u in REPORT_KEYS if ra.get(k) is not None or rb.get(k) is not None]
    for k, lab in (("taks", "TAKS"), ("kaks", "KAKS")):
        va, vb = ((r.get("checks") or {}).get(k, {}).get("value") for r in (ra, rb))
        if va is not None or vb is not None:
            rapor.append({"anahtar": k, "ad": lab, "birim": "", "a": va, "b": vb, **_delta(va, vb)})
    ca, cb = a.get("cost") or {}, b.get("cost") or {}
    maliyet = [{"anahtar": k, "ad": lab, "birim": u, "a": ca.get(k), "b": cb.get(k), **_delta(ca.get(k), cb.get(k))}
               for k, lab, u in COST_KEYS]
    gruplar = []
    for g in sorted(set(ca.get("groups") or {}) | set(cb.get("groups") or {})):
        va, vb = (ca.get("groups") or {}).get(g, 0), (cb.get("groups") or {}).get(g, 0)
        gruplar.append({"ad": g, "a": round(va), "b": round(vb), **_delta(va, vb)})
    rows_a = {r["code"]: r for r in ca.get("rows") or [] if r.get("enabled")}
    rows_b = {r["code"]: r for r in cb.get("rows") or [] if r.get("enabled")}
    kal = []
    for code in set(rows_a) | set(rows_b):
        ra_, rb_ = rows_a.get(code), rows_b.get(code)
        aa, ab = (ra_ or {}).get("amount", 0), (rb_ or {}).get("amount", 0)
        if abs(ab - aa) < 1:
            continue
        r_ = rb_ or ra_
        kal.append({"kod": code, "ad": (r_.get("name") or "")[:70], "birim": r_.get("unit"),
                    "miktar_a": (ra_ or {}).get("quantity"), "miktar_b": (rb_ or {}).get("quantity"),
                    "tutar_a": round(aa), "tutar_b": round(ab), "fark": round(ab - aa)})
    kal.sort(key=lambda x: -abs(x["fark"]))
    fa, fb = _flat((a.get("brief") or {})), _flat((b.get("brief") or {}))
    girdi = [{"anahtar": k, "a": fa.get(k), "b": fb.get(k)} for k in sorted(set(fa) | set(fb))
             if fa.get(k) != fb.get(k) and k not in ("name",) and not k.startswith("adjust")]
    wa, wb = set(ra.get("warnings") or []), set(rb.get("warnings") or [])
    return {"a": {"ad": a.get("name")}, "b": {"ad": b.get("name")}, "girdiler": girdi, "rapor": rapor, "maliyet": maliyet,
            "maliyet_gruplari": gruplar, "kalemler": kal[:limit],
            "yeni_uyarilar": sorted(wb - wa)[:10], "kalkan_uyarilar": sorted(wa - wb)[:10]}
