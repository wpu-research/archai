"""Maliyet: metraj satırları × birim fiyat listesi + fiyat ayarlama.

Ayarlar (adjust) sözlüğü:
  overrides   {code: unit_price}      — kalemin birim fiyatını değiştir
  variants    {code: variant_id}      — varyantlı kalemde seçim (ör. ZEM-01: "seramik")
  disabled    [code, ...]             — kalemi hesaptan çıkar
  enabled     [code, ...]             — disabled listesinde olsa da kalemi dahil et; kataloğda
                                        "default_enabled": false olan (opsiyonel / teklif dışı) kalemler yalnız burada
                                        listelenirse hesaba girer
  qty_overrides {code: miktar}        — metrajı elle düzelt
  extra_items [{code, group, name, unit, unit_price, quantity}]  — elle kalem
  overhead_pct / profit_pct / vat_pct — oranlar
  approx_class                         — yaklaşık maliyet yapı sınıfı (ör. "IV-A")
  poz         {code: poz no}           — kalemin resmî poz numarası (archai/poz.py; boşsa data/poz_map.json önerisi)
  catalog     {code: ürün seçimi}      — tedarikçi kataloğundan ürün (archai/catalog.py); birim fiyatı overrides yoksa geçerli
"""

import copy
import json
from pathlib import Path

from . import quantities as Q

DEFAULT_PRICES = Path(__file__).parent / "data" / "prices_default.json"


def load_prices(path=None):
    return json.loads(Path(path or DEFAULT_PRICES).read_text(encoding="utf-8"))


# Kalem bölme öncesi kaydedilmiş fiyat ayarlarındaki eski pencere varyantı iki kaleme (doğrama + cam) ayrılır.
# Not: eski birleşik kalemler (iç sıva+alçı+boya vb.) için kaydedilmiş elle birim fiyatlar artık dar kapsamlı
# kaleme uygulanır; sürüm işareti olmadığından otomatik ayıklanmaz — eski projelerde fiyatlar yeniden gözden geçirilmeli.
LEGACY_VARIANTS = {("PEN-01", "alu_triple"): {"PEN-01": "alu", "PEN-03": "uclu_cam"}}


def migrate_adjust(adjust):
    """Eski (kalem bölmeden önceki) varyant adlarını güncel katalğa çevirir. Değişiklik yoksa aynı nesne döner."""
    var = adjust.get("variants") if isinstance(adjust, dict) else None
    if not isinstance(var, dict) or not any((c, v) in LEGACY_VARIANTS for c, v in var.items()):
        return adjust
    new_var = {}
    for c, v in var.items():
        new_var.update(LEGACY_VARIANTS.get((c, v), {c: v}))
    return {**adjust, "variants": new_var}


def _filters(rule):
    return {k: v for k, v in rule.items() if k not in ("metric", "factor")}


def _num(v, what, lo=0.0, hi=None):
    if isinstance(v, bool) or not isinstance(v, (int, float)) or v != v or v in (float("inf"), float("-inf")):
        raise ValueError(f"{what} sayı olmalı (verilen: {v!r})")
    if v < lo or (hi is not None and v > hi):
        raise ValueError(f"{what} {lo:g}–{hi:g} aralığında olmalı (verilen: {v:g})" if hi is not None
                         else f"{what} {lo:g} veya daha büyük olmalı (verilen: {v:g})")
    return v


ADJUST_KEYS = {"overrides", "variants", "disabled", "enabled", "qty_overrides", "extra_items", "overhead_pct",
               "profit_pct", "vat_pct", "approx_class", "poz", "catalog"}


def validate_adjust(adjust, prices=None):
    """Fiyat ayarı sözlüğünü doğrula; ihlalde Türkçe mesajlı ValueError. Geçerliyse aynı sözlüğü döndürür
    (eski katalogdan kalan varyant adları varsa `migrate_adjust` ile çevrilmiş kopyası)."""
    if adjust is None:
        return {}
    adjust = migrate_adjust(adjust)
    if not isinstance(adjust, dict):
        raise ValueError("fiyat ayarı (adjust) bir sözlük olmalı")
    unknown = set(adjust) - ADJUST_KEYS
    if unknown:
        raise ValueError(f"bilinmeyen fiyat ayarı alanı: {', '.join(sorted(unknown))}")
    for k in ("overhead_pct", "profit_pct", "vat_pct"):
        if k in adjust and adjust[k] is not None:
            _num(adjust[k], {"overhead_pct": "genel gider oranı", "profit_pct": "kâr oranı", "vat_pct": "KDV oranı"}[k], 0, 100)
    for k, label in (("overrides", "birim fiyat"), ("qty_overrides", "miktar")):
        d = adjust.get(k)
        if d is None:
            continue
        if not isinstance(d, dict):
            raise ValueError(f"{k} {{kod: sayı}} sözlüğü olmalı")
        for code, v in d.items():
            if not isinstance(code, str) or not code:
                raise ValueError(f"{k}: kalem kodu metin olmalı")
            _num(v, f"{code} {label}")
    items = {it["code"]: it for it in (prices or load_prices())["items"]}
    var = adjust.get("variants")
    if var is not None:
        if not isinstance(var, dict):
            raise ValueError("variants {kod: varyant} sözlüğü olmalı")
        for code, vid in var.items():
            it = items.get(code)
            if it is None or not it.get("variants"):
                raise ValueError(f"{code} varyantlı bir kalem değil")
            if vid not in {v["id"] for v in it["variants"]}:
                raise ValueError(f"{code} için geçersiz varyant: {vid!r} "
                                 f"(seçenekler: {', '.join(v['id'] for v in it['variants'])})")
    for k in ("disabled", "enabled"):
        lst = adjust.get(k)
        if lst is None:
            continue
        if not isinstance(lst, (list, tuple)) or not all(isinstance(c, str) for c in lst):
            raise ValueError(f"{k} kalem kodu listesi olmalı")
    ex = adjust.get("extra_items")
    if ex is not None:
        if not isinstance(ex, list):
            raise ValueError("extra_items liste olmalı")
        for i, x in enumerate(ex, 1):
            if not isinstance(x, dict):
                raise ValueError(f"ek kalem {i}: sözlük olmalı")
            if not isinstance(x.get("name"), str) or not x["name"].strip():
                raise ValueError(f"ek kalem {i}: ad (name) boş olamaz")
            if "unit" in x and not isinstance(x["unit"], str):
                raise ValueError(f"ek kalem {i}: birim (unit) metin olmalı")
            _num(x.get("quantity", 0), f"ek kalem {i} miktarı")
            _num(x.get("unit_price", 0), f"ek kalem {i} birim fiyatı")
    if "approx_class" in adjust and adjust["approx_class"] is not None and not isinstance(adjust["approx_class"], str):
        raise ValueError("approx_class metin olmalı (ör. \"IV-A\")")
    from .poz import validate_poz_adjust
    validate_poz_adjust(adjust.get("poz"))
    from .catalog import validate_selection
    validate_selection(adjust.get("catalog"), prices or load_prices())
    return adjust


def estimate(qres, prices=None, adjust=None):
    """qres: quantities.compute() çıktısı. Dönen yapı hem UI'da hem raporlarda kullanılır."""
    from .poz import load_map, poz_of
    prices = copy.deepcopy(prices or load_prices())
    adj = validate_adjust(adjust, prices) or {}
    pmap = load_map()
    lines = qres["lines"]
    rows = []
    for it in prices["items"]:
        code = it["code"]
        variant = None
        if it.get("variants"):
            vid = adj.get("variants", {}).get(code, it.get("selected"))
            variant = next((v for v in it["variants"] if v["id"] == vid), it["variants"][0])
        sel = (adj.get("catalog") or {}).get(code)
        if sel and sel.get("variant") and variant and sel["variant"] != variant["id"]:
            sel = None      # varyant sonradan değişti (ör. tasarım ajanı): ürün artık o seçeneğe ait değil
        base_price = sel["unit_price"] if sel else variant["unit_price"] if variant else it["unit_price"]
        unit_price = adj.get("overrides", {}).get(code, base_price)
        rule = it["qty"]
        auto_qty = Q.quantity(lines, rule["metric"], rule.get("factor", 1.0), **_filters(rule))
        qty = adj.get("qty_overrides", {}).get(code, auto_qty)
        default_on = it.get("default_enabled", True)
        enabled = (default_on and code not in adj.get("disabled", [])) or code in adj.get("enabled", [])
        rows.append({
            "approx": bool(it.get("approx")), "default_enabled": default_on,
            "code": code, "group": it["group"],
            "name": it["name"] + (f" — {sel['name']} ({sel.get('supplier') or 'tedarikçi'})" if sel else
                                  f" — {variant['name']}" if variant else ""),
            "unit": it["unit"], "quantity": round(qty, 2), "auto_quantity": round(auto_qty, 2),
            "unit_price": unit_price, "amount": round(qty * unit_price, 2) if enabled else 0.0,
            "enabled": enabled, "variant": variant["id"] if variant else None,
            "variants": [{"id": v["id"], "name": v["name"], "unit_price": v["unit_price"]} for v in it.get("variants", [])],
            "overridden": code in adj.get("overrides", {}) or code in adj.get("qty_overrides", {}),
            "poz": poz_of(code, adj, pmap)[0],
            "catalog": sel,
        })
    for x in adj.get("extra_items", []):
        q, p = float(x.get("quantity", 0)), float(x.get("unit_price", 0))
        rows.append({"approx": False, "code": x.get("code", "EK"), "group": x.get("group", "Ek kalemler"), "name": x["name"],
                     "unit": x.get("unit", "götürü"), "quantity": q, "auto_quantity": None, "unit_price": p,
                     "amount": round(q * p, 2), "enabled": True, "variant": None, "variants": [], "overridden": True,
                     "poz": x.get("poz")})

    subtotal = round(sum(r["amount"] for r in rows), 2)
    oh = adj.get("overhead_pct", prices.get("overhead_pct", 0))
    pr = adj.get("profit_pct", prices.get("profit_pct", 0))
    vat = adj.get("vat_pct", prices.get("vat_pct", 0))
    overhead = subtotal * oh / 100
    profit = (subtotal + overhead) * pr / 100
    before_vat = subtotal + overhead + profit
    vat_amt = before_vat * vat / 100
    total = before_vat + vat_amt
    gfa = qres["summary"]["gross_floor_area"]

    groups = {}
    for r in rows:
        groups[r["group"]] = round(groups.get(r["group"], 0) + r["amount"], 2)

    approx = None
    cls = adj.get("approx_class")
    units = {k: v for k, v in prices.get("approx_unit_costs", {}).items() if not k.startswith("_")}
    if units:
        cls = cls if cls in units else next(iter(units))
        approx = {"class": cls, "unit_cost": units[cls], "area": gfa, "amount": round(gfa * units[cls], 2),
                  "classes": units}

    return {
        "currency": prices.get("currency", "TRY"),
        "note": prices.get("_note"),
        "rows": rows,
        "groups": groups,
        "subtotal": subtotal,
        "overhead_pct": oh, "overhead": round(overhead, 2),
        "profit_pct": pr, "profit": round(profit, 2),
        "vat_pct": vat, "vat": round(vat_amt, 2),
        "total_before_vat": round(before_vat, 2),
        "total": round(total, 2),
        "gross_floor_area": gfa,
        "per_m2_before_vat": round(before_vat / gfa, 2) if gfa else None,
        "per_m2": round(total / gfa, 2) if gfa else None,
        "approx": approx,
    }
