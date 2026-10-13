"""Tedarikçi (yapı market, bayi, üretici) fiyat kataloğu: iç mekân ve malzeme seçimlerini gerçek ürün fiyatına bağlar.

Katalog bir CSV/XLSX'tir; başlık satırı otomatik bulunur:
  Tedarikçi · Ürün Kodu · Ürün Adı · Birim · Fiyat · [KDV Dahil] · [İşçilik] · [Fire %] · Kalem · [Varyant] · [URL]
  - Kalem: ArchAI kalem kodu (ZEM-01, SER-01, BOY-01 …); ürün bu kaleme bağlanır.
  - Varyant: varyantlı kalemde hangi seçeneğe karşılık geldiği (ZEM-01: laminat / seramik / masif / traverten).
  - Fiyat birimi kalemin birimiyle aynı olmalı (ör. m²); paket fiyatı (kutu, adet) önce m²'ye çevrilmelidir.
  - Fiyat yalnız MALZEMEDİR. Uygulanmış birim fiyat = malzeme × (1 + fire) + işçilik. İşçilik sütunu boşsa 0 alınır
    ve satır "yalnız malzeme" uyarısı taşır (birim fiyat gerçeğin altında kalır).
  - "KDV Dahil" evet ise fiyat KDV'den arındırılır (ArchAI birim fiyatları KDV hariçtir).

Proje seçimi `adjust["catalog"] = {kod: {supplier, sku, name, unit_price, material, labor, waste_pct, url}}` olarak
saklanır; maliyet motoru bu birim fiyatı kullanır ve kalem adına ürünü ekler. Kataloglar `out/katalog/` altında,
yalnız bu makinede tutulur. ArchAI hiçbir zincirin güncel fiyatını içermez.
"""

import json
import re
from datetime import datetime
from pathlib import Path

from . import poz

MAX_ITEMS = 50_000
VAT_DEFAULT = 20.0

_HEAD = {
    "supplier": re.compile(r"tedarik|firma|ma[gğ]aza|market|bayi|sat[iı]c[iı]"),
    "sku": re.compile(r"[uü]r[uü]n kod|stok kod|sku|barkod|^kod$"),
    "name": re.compile(r"[uü]r[uü]n ad|^[uü]r[uü]n$|a[cç][iı]klama|^ad[iı]?$|tan[iı]m"),
    "unit": re.compile(r"^birim[iı]?$|^br\.?$"),
    "price": re.compile(r"^fiyat|birim fiyat|sat[iı][sş] fiyat|liste fiyat"),
    "vat_incl": re.compile(r"kdv\s*dahil|kdv\s*d\.?$"),
    "labor": re.compile(r"i[sş][cç]ilik|uygulama|montaj"),
    "waste": re.compile(r"fire"),
    "code": re.compile(r"^kalem|archai|kalem kod"),
    "variant": re.compile(r"varyant|se[cç]enek"),
    "url": re.compile(r"url|link|ba[gğ]lant"),
}


def _header(row):
    cols = {}
    for j, cell in enumerate(row):
        t = str(cell or "").strip().lower().replace("\u0307", "")   # "İ".lower() → i + birleşik nokta
        if not t or len(t) > 50:
            continue
        for k, rx in _HEAD.items():
            if k not in cols and rx.search(t):
                if k == "price" and ("işçilik" in t or "iscilik" in t):
                    continue
                cols[k] = j
                break
    return cols if {"name", "price", "code"} <= cols.keys() else None


def _yes(v):
    return str(v or "").strip().lower() in ("evet", "e", "yes", "y", "1", "true", "dahil", "x", "✓")


def read_catalog(filename, data, prices, supplier_default=None):
    """Katalog dosyası → {"supplier", "items": [...], "warnings", "skipped"}; bilinmeyen kalem / birim uyuşmazlığı atlanır."""
    items_by_code = {it["code"]: it for it in prices["items"]}
    cols, out, skipped, warn = None, [], 0, []
    for row in poz._rows_from_file(filename, data):
        h = _header(row)
        if h:
            cols = h
            continue
        if not cols:
            continue
        g = lambda k: row[cols[k]] if k in cols and cols[k] < len(row) else None
        name, code = str(g("name") or "").strip(), str(g("code") or "").strip().upper()
        price = poz.parse_num(g("price"))
        if not name and price is None:
            continue
        it = items_by_code.get(code)
        if not it or price is None or price <= 0 or not name:
            skipped += 1
            if it is None and code and len(warn) < 20:
                warn.append(f"bilinmeyen kalem kodu atlandı: {code}")
            continue
        unit = poz.norm_unit(g("unit") or it["unit"])
        if unit != poz.norm_unit(it["unit"]):
            skipped += 1
            if len(warn) < 20:
                warn.append(f"{name[:40]}: birim {unit} ≠ {code} birimi {it['unit']} — önce {it['unit']} fiyatına çevirin")
            continue
        material = price / (1 + VAT_DEFAULT / 100) if _yes(g("vat_incl")) else price
        labor = poz.parse_num(g("labor"))
        waste = poz.parse_num(g("waste"))
        variant = str(g("variant") or "").strip() or None
        if variant and variant not in {v["id"] for v in it.get("variants", [])}:
            variant = None
        out.append({"id": f"{len(out) + 1}", "supplier": str(g("supplier") or supplier_default or "Tedarikçi").strip()[:60],
                    "sku": str(g("sku") or "").strip()[:40], "name": name[:120], "unit": it["unit"], "code": code,
                    "variant": variant, "material": round(material, 2), "labor": round(labor, 2) if labor is not None else None,
                    "waste_pct": waste if waste is not None and 0 <= waste <= 50 else 0.0,
                    "url": (str(g("url") or "").strip()[:300] if str(g("url") or "").startswith("https://") else "")})
        if len(out) > MAX_ITEMS:
            raise ValueError(f"katalog {MAX_ITEMS} üründen büyük")
    if not out:
        raise ValueError("katalogda geçerli ürün yok: başlıkta 'Ürün Adı', 'Fiyat' ve 'Kalem' (ArchAI kodu) sütunları olmalı")
    return {"supplier": out[0]["supplier"] if len({x["supplier"] for x in out}) == 1 else (supplier_default or "Karma"),
            "items": out, "skipped": skipped, "warnings": warn, "imported_at": datetime.now().isoformat(timespec="seconds")}


def unit_price(p):
    """Uygulanmış birim fiyat (KDV hariç)."""
    return round(p["material"] * (1 + (p.get("waste_pct") or 0) / 100) + (p.get("labor") or 0), 2)


def selection(p):
    return {"supplier": p["supplier"], "sku": p["sku"], "name": p["name"], "variant": p.get("variant"),
            "material": p["material"],
            "labor": p.get("labor") or 0, "waste_pct": p.get("waste_pct") or 0, "url": p.get("url") or "",
            "unit_price": unit_price(p), "material_only": p.get("labor") is None}


# --------------------------------------------------------------------------- depolama

SLUG = re.compile(r"[a-z0-9-]{1,40}")


def slug(name):
    s = re.sub(r"[^a-z0-9]+", "-", str(name).lower().translate(str.maketrans("çğıöşü", "cgiosu"))).strip("-")[:40]
    return s or "katalog"


def save(root, cat):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    sid = slug(cat["supplier"])
    (root / f"{sid}.json").write_text(json.dumps({**cat, "id": sid}, ensure_ascii=False))
    return sid


def load_all(root):
    out = []
    for p in sorted(Path(root).glob("*.json")) if Path(root).is_dir() else []:
        try:
            out.append(json.loads(p.read_text()))
        except (OSError, ValueError):
            continue
    return out


def delete(root, sid):
    if not SLUG.fullmatch(str(sid)):
        raise ValueError("geçersiz katalog kimliği")
    p = Path(root) / f"{sid}.json"
    if not p.is_file():
        raise ValueError("katalog bulunamadı")
    p.unlink()


def products_for(cats, code, variant=None):
    """Kalem (ve varsa varyant) için ürünler, uygulanmış fiyata göre artan."""
    res = []
    for c in cats:
        for p in c["items"]:
            if p["code"] == code and (variant is None or p["variant"] in (None, variant)):
                res.append({**p, "catalog": c["id"], "unit_price": unit_price(p)})
    return sorted(res, key=lambda p: p["unit_price"])


def validate_selection(d, prices=None):
    if d is None:
        return
    if not isinstance(d, dict):
        raise ValueError("catalog {kod: ürün} sözlüğü olmalı")
    codes = {it["code"] for it in (prices or {"items": []})["items"]} if prices else None
    for code, s in d.items():
        if codes is not None and code not in codes:
            raise ValueError(f"katalog seçimi: bilinmeyen kalem {code}")
        if not isinstance(s, dict) or not isinstance(s.get("name"), str) or not s["name"].strip():
            raise ValueError(f"{code}: katalog seçimi ürün adı içermeli")
        up = s.get("unit_price")
        if isinstance(up, bool) or not isinstance(up, (int, float)) or not 0 < up < 1e8:
            raise ValueError(f"{code}: katalog birim fiyatı geçersiz")
