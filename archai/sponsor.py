"""Sponsor / iş ortağı markalar: mutfak, banyo, kapı, boya vb. firmaların teklifte "önerilen marka" olarak yer alması.

Sponsor kaydı yalnız bu makinede tutulur (`ARCHAI_OUT/sponsorlar.json`); ArchAI hiçbir firmayı, ürünü veya fiyatı kendiliğinden içermez.
Bir sponsor, tedarikçi kataloğundaki tedarikçi adıyla eşleşir; projede o tedarikçinin kataloğundan seçilen ürünler teklifte "Sponsor / Önerilen
Markalar" bölümünde listelenir. Sponsorluk ilişkisi teklifte açıkça belirtilir (reklam / iş ortaklığı olabilir).
"""
import json
import os
import re
from pathlib import Path

CATEGORIES = ("mutfak", "banyo", "kapı", "doğrama", "zemin", "boya", "aydınlatma", "tesisat", "asansör", "diğer")
MAX = 100


def path():
    base = Path(os.environ.get("ARCHAI_OUT") or Path(__file__).resolve().parents[1] / "out")
    return base / "sponsorlar.json"


def _norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip()).casefold()


def load():
    try:
        d = json.loads(path().read_text())
        return [x for x in d.get("sponsorlar", []) if isinstance(x, dict) and x.get("ad")]
    except (OSError, ValueError):
        return []


def clean(items):
    out, seen = [], set()
    for x in items[:MAX]:
        ad = re.sub(r"\s+", " ", str(x.get("ad", "")).strip())[:80]
        if not ad or _norm(ad) in seen:
            continue
        seen.add(_norm(ad))
        kat = [k for k in (x.get("kategoriler") or []) if k in CATEGORIES]
        web = str(x.get("web", "")).strip()[:200]
        if web and not re.match(r"^https?://", web):
            raise ValueError(f"{ad}: web adresi http(s):// ile başlamalı")
        out.append({"ad": ad, "kategoriler": kat, "web": web, "not": str(x.get("not", "")).strip()[:300]})
    return out


def save(items):
    items = clean(items)
    path().parent.mkdir(parents=True, exist_ok=True)
    path().write_text(json.dumps({"sponsorlar": items}, ensure_ascii=False, indent=1))
    return items


def for_project(adjust):
    """Projedeki katalog seçimlerinden sponsor tedarikçilere ait ürünler: [{sponsor, kategoriler, web, urunler: [...]}]."""
    sel = (adjust or {}).get("catalog") or {}
    reg = {_norm(s["ad"]): s for s in load()}
    by = {}
    for code, p in sel.items():
        s = reg.get(_norm(p.get("supplier")))
        if s:
            by.setdefault(s["ad"], {"sponsor": s["ad"], "kategoriler": s["kategoriler"], "web": s["web"], "not": s["not"], "urunler": []})
            by[s["ad"]]["urunler"].append({"kod": code, "ad": p.get("name", ""), "sku": p.get("sku", ""), "birim_fiyat": p.get("unit_price")})
    return list(by.values())
