"""Maliyet: metraj satırları × birim fiyat listesi + fiyat ayarlama.

Ayarlar (adjust) sözlüğü:
  overrides   {code: unit_price}      — kalemin birim fiyatını değiştir
  variants    {code: variant_id}      — varyantlı kalemde seçim (ör. ZEM-01: "seramik")
  disabled    [code, ...]             — kalemi hesaptan çıkar
  qty_overrides {code: miktar}        — metrajı elle düzelt
  extra_items [{code, group, name, unit, unit_price, quantity}]  — elle kalem
  overhead_pct / profit_pct / vat_pct — oranlar
  approx_class                         — yaklaşık maliyet yapı sınıfı (ör. "IV-A")
"""

import copy
import json
from pathlib import Path

from . import quantities as Q

DEFAULT_PRICES = Path(__file__).parent / "data" / "prices_default.json"


def load_prices(path=None):
    return json.loads(Path(path or DEFAULT_PRICES).read_text(encoding="utf-8"))


def _filters(rule):
    return {k: v for k, v in rule.items() if k not in ("metric", "factor")}


def estimate(qres, prices=None, adjust=None):
    """qres: quantities.compute() çıktısı. Dönen yapı hem UI'da hem raporlarda kullanılır."""
    prices = copy.deepcopy(prices or load_prices())
    adj = adjust or {}
    lines = qres["lines"]
    rows = []
    for it in prices["items"]:
        code = it["code"]
        variant = None
        if it.get("variants"):
            vid = adj.get("variants", {}).get(code, it.get("selected"))
            variant = next((v for v in it["variants"] if v["id"] == vid), it["variants"][0])
        unit_price = adj.get("overrides", {}).get(code, variant["unit_price"] if variant else it["unit_price"])
        rule = it["qty"]
        auto_qty = Q.quantity(lines, rule["metric"], rule.get("factor", 1.0), **_filters(rule))
        qty = adj.get("qty_overrides", {}).get(code, auto_qty)
        enabled = code not in adj.get("disabled", [])
        rows.append({
            "code": code, "group": it["group"], "name": it["name"] + (f" — {variant['name']}" if variant else ""),
            "unit": it["unit"], "quantity": round(qty, 2), "auto_quantity": round(auto_qty, 2),
            "unit_price": unit_price, "amount": round(qty * unit_price, 2) if enabled else 0.0,
            "enabled": enabled, "variant": variant["id"] if variant else None,
            "variants": [{"id": v["id"], "name": v["name"], "unit_price": v["unit_price"]} for v in it.get("variants", [])],
            "overridden": code in adj.get("overrides", {}) or code in adj.get("qty_overrides", {}),
        })
    for x in adj.get("extra_items", []):
        q, p = float(x.get("quantity", 0)), float(x.get("unit_price", 0))
        rows.append({"code": x.get("code", "EK"), "group": x.get("group", "Ek kalemler"), "name": x["name"],
                     "unit": x.get("unit", "götürü"), "quantity": q, "auto_quantity": None, "unit_price": p,
                     "amount": round(q * p, 2), "enabled": True, "variant": None, "variants": [], "overridden": True})

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
