"""İhale / teklif analizi (yüklenici tarafı): idarenin cetvelini oku, kontrol et, teklif stratejisini sına.

Girdi: birim fiyat teklif cetveli / keşif özeti / metraj cetveli (xlsx, csv) — Poz No, Tanım, Birim, Miktar,
[Birim Fiyat]. İsteğe bağlı: kullanıcının lisanslı poz listesi (archai/poz.py) ve aynı işin ArchAI projesi
(çizimden üretilmiş metraj).

Kontroller
  1. Poz fiyat sapması — cetvel (ya da yüklenicinin) birim fiyatı ↔ referans poz listesi; birim uyuşmazlığı;
     listede olmayan (özel) pozlar → "analiz gerekli". Ağırlıklı kalemler (tutarın %80'ini yapan kalemler).
  2. Metraj tutarlılığı — ArchAI projesinin poz bazında metrajı ↔ cetvel miktarı; cetvelde olmayan imalatlar.
     Götürü bedel işte metraj riski yüklenicidedir: bu kontrol orada en kritik olandır.
  3. Sınır değer — Kamu İhale Genel Tebliği 45.1.1 (RG 29.12.2010/27800 mük. değişikliği, tebliğ örneği testte):
     YM'nin %40–%120 aralığındaki geçerli teklifler → Tort1, σ (n−1) → Tort2 → C = Tort2/YM → K → SD = K·Tort2/(C·N).
     K: C < 0,60 → K = C; 0,60 ≤ C ≤ 1,00 → K = (3,2C − C² − 0,6)/(C + 1); C > 1,00 → K = 1.
     (Uç aralıklardaki K eşitlikleri tebliğ metninde görsel olarak yer alır; KİK hesaplama aracıyla doğrulayın.)
  4. Teklif simülasyonu — rakip teklif dağılımı VARSAYIMIYLA (kullanıcı girer) Monte Carlo: teklif oranına göre
     aşırı düşük kalma ve en düşük geçerli teklif olma olasılığı. Geçmiş EKAP sonuçları bağlanmadı.

Hiçbir sonuç ihale kararı yerine geçmez; idari şartname, sınır değer katsayısı (N) ve ilan koşulları esastır.
"""

import math
import random
import re

from . import poz

# --------------------------------------------------------------------------- cetvel okuma


def read_cetvel(filename, data):
    """Cetvel satırları: [{sira, poz, tanim, birim, miktar, birim_fiyat}] (birim_fiyat boş olabilir)."""
    rows, cols, n = [], None, 0
    for raw in poz._rows_from_file(filename, data):
        n += 1
        if n > poz.MAX_ROWS:
            raise ValueError("cetvel çok uzun")
        h = poz._header_map(raw)
        if h and "miktar" in h:
            cols = h
            continue
        if not cols:
            continue
        g = lambda k: raw[cols[k]] if k in cols and cols[k] < len(raw) else None
        p = poz.norm_poz(g("poz"))
        qty = poz.parse_num(g("miktar"))
        tanim = str(g("tanim") or "").strip()
        if not p and not tanim:
            continue
        if qty is None or qty <= 0:
            continue
        price = poz.parse_num(g("fiyat")) if "fiyat" in cols else None
        rows.append({"sira": len(rows) + 1, "poz": p, "tanim": tanim[:400], "birim": poz.norm_unit(g("birim")),
                     "miktar": round(qty, 3), "birim_fiyat": round(price, 2) if price and price > 0 else None})
    if not rows:
        raise ValueError("cetvelde kalem bulunamadı: başlık satırında 'Poz No', 'Tanım', 'Birim' ve 'Miktar' olmalı")
    return rows


# --------------------------------------------------------------------------- analiz

LOW, HIGH = -20.0, 30.0          # % sapma eşikleri (referansa göre)
QTY_TOL = 10.0                    # % metraj farkı eşiği


def _pareto(lines, key):
    tot = sum(l[key] or 0 for l in lines)
    if not tot:
        return set()
    acc, out = 0.0, set()
    for l in sorted(lines, key=lambda l: -(l[key] or 0)):
        if acc >= 0.8 * tot:
            break
        acc += l[key] or 0
        out.add(l["sira"])
    return out


def analyze(rows, ref=None, project_cost=None, project_adjust=None, kind="birim_fiyat"):
    """rows: read_cetvel çıktısı; ref: poz.load_list sözlüğü; project_cost: ArchAI projesinin cost'u."""
    lines = []
    for r in rows:
        l = {**r, "ref_fiyat": None, "ref_birim": None, "sapma_pct": None, "flags": []}
        p = ref["items"].get(r["poz"]) if ref and r["poz"] else None
        if not r["poz"]:
            l["flags"].append("poz numarası yok (özel kalem) — fiyat analizi gerekli")
        elif ref and not p:
            l["flags"].append("referans listede yok (özel / farklı idare pozu) — analiz gerekli")
        if p:
            l["ref_fiyat"], l["ref_birim"] = p["fiyat"], p["birim"]
            if r["birim"] and p["birim"] and r["birim"] != p["birim"]:
                l["flags"].append(f"birim uyuşmuyor: cetvel {r['birim']}, poz {p['birim']}")
            elif r["birim_fiyat"]:
                l["sapma_pct"] = round((r["birim_fiyat"] / p["fiyat"] - 1) * 100, 1) if p["fiyat"] else None
                if l["sapma_pct"] is not None and l["sapma_pct"] < LOW:
                    l["flags"].append(f"birim fiyat referansın %{-l['sapma_pct']:g} altında — maliyetin altında kalma "
                                      "ve aşırı düşük teklif açıklaması riski")
                elif l["sapma_pct"] is not None and l["sapma_pct"] > HIGH:
                    l["flags"].append(f"birim fiyat referansın %{l['sapma_pct']:g} üstünde")
        l["tutar"] = round(r["miktar"] * r["birim_fiyat"], 2) if r["birim_fiyat"] else None
        l["ref_tutar"] = round(r["miktar"] * l["ref_fiyat"], 2) if l["ref_fiyat"] and "birim uyuşmuyor" not in " ".join(l["flags"]) else None
        lines.append(l)
    key = "tutar" if any(l["tutar"] for l in lines) else "ref_tutar"
    heavy = _pareto(lines, key)
    for l in lines:
        l["agirlikli"] = l["sira"] in heavy

    priced = [l for l in lines if l["tutar"]]
    refd = [l for l in lines if l["ref_tutar"]]
    summary = {
        "kalem": len(lines), "fiyatli_kalem": len(priced), "referansli_kalem": len(refd),
        "teklif_toplam": round(sum(l["tutar"] for l in priced), 2) if priced else None,
        "referans_toplam": round(sum(l["ref_tutar"] for l in refd), 2) if refd else None,
        "referans_kapsam_pct": round(len(refd) / len(lines) * 100, 1) if lines else 0,
        "uyari": sum(1 for l in lines if l["flags"]), "agirlikli_kalem": len(heavy), "tur": kind,
    }
    both = [l for l in lines if l["tutar"] and l["ref_tutar"]]
    if both:
        a, b = sum(l["tutar"] for l in both), sum(l["ref_tutar"] for l in both)
        summary["karsilastirilabilir_oran_pct"] = round((a / b - 1) * 100, 1) if b else None

    metraj = compare_quantities(lines, project_cost, project_adjust) if project_cost else None
    notes = []
    if kind == "goturu":
        notes.append("Anahtar teslim götürü bedel: metraj riski yüklenicidedir. Cetvel miktarları bağlayıcı değildir; "
                     "metrajı çizimlerden bağımsız çıkarın (ArchAI projesiyle karşılaştırma aşağıda).")
    else:
        notes.append("Birim fiyat işi: ödeme gerçekleşen miktar üzerinden yapılır; metraj farkları iş artışı / eksilişi "
                     "olarak döner. Fazla metrajlı kalemlerde düşük, eksik metrajlı kalemlerde gerçekçi fiyat verin.")
    if ref is None:
        notes.append("Referans poz listesi yüklenmedi: fiyat sapması kontrol edilmedi (08 POZ · KATALOG sekmesinden yükleyin).")
    return {"lines": lines, "summary": summary, "metraj": metraj, "notes": notes}


def compare_quantities(lines, cost, adjust=None):
    """ArchAI projesinin poz bazında metrajı ↔ cetvel. Poz yoksa tanım benzerliğiyle (öneri) eşler."""
    pmap = poz.load_map()
    proj = {}
    for r in cost["rows"]:
        if not r["enabled"] or not r["quantity"]:
            continue
        p = r.get("poz") or poz.poz_of(r["code"], adjust, pmap)[0]
        proj.setdefault(p or ("#" + r["code"]), []).append(r)
    by_poz = {}
    for l in lines:
        if l["poz"]:
            by_poz.setdefault(l["poz"], []).append(l)
    out, matched_codes = [], set()
    for p, rs in proj.items():
        if p.startswith("#"):
            continue
        if p not in by_poz:
            continue
        units = {poz.norm_unit(r["unit"]) for r in rs}
        q_proj = sum(r["quantity"] for r in rs)
        q_cet = sum(l["miktar"] for l in by_poz[p])
        u_cet = {l["birim"] for l in by_poz[p]}
        row = {"poz": p, "tanim": by_poz[p][0]["tanim"][:160], "birim": "/".join(sorted(u_cet)),
               "cetvel": round(q_cet, 2), "archai": round(q_proj, 2), "kodlar": [r["code"] for r in rs], "flags": []}
        if units != u_cet:
            row["flags"].append("birimler farklı — karşılaştırılamaz")
        else:
            row["fark_pct"] = round((q_cet / q_proj - 1) * 100, 1) if q_proj else None
            if row["fark_pct"] is not None and abs(row["fark_pct"]) > QTY_TOL:
                row["flags"].append(("cetvel FAZLA" if row["fark_pct"] > 0 else "cetvel EKSİK") +
                                    f" (%{abs(row['fark_pct']):g}) — çizimden yeniden kontrol edin")
        matched_codes.update(row["kodlar"])
        out.append(row)
    missing = []
    for p, rs in proj.items():
        for r in rs:
            if r["code"] in matched_codes or r["amount"] <= 0:
                continue
            missing.append({"code": r["code"], "name": r["name"][:120], "unit": r["unit"], "quantity": r["quantity"],
                            "poz": None if p.startswith("#") else p, "amount": r["amount"]})
    missing.sort(key=lambda m: -m["amount"])
    total = sum(r["amount"] for r in cost["rows"] if r["enabled"]) or 1
    return {"satirlar": out, "cetvelde_yok": missing[:40],
            "cetvelde_yok_pay_pct": round(sum(m["amount"] for m in missing) / total * 100, 1),
            "not": "ArchAI metrajı avan seviyededir (oran yöntemli kalemler dahil); farklar kesin hata değil, "
                   "kontrol edilmesi gereken yerlerdir. Poz numarası olmayan ArchAI kalemleri 'cetvelde yok' "
                   "listesinde görünebilir: cetvelde farklı pozla yer alıyor olabilirler."}


# --------------------------------------------------------------------------- sınır değer (KİK 45.1.1)

def _r2(v):
    return math.floor(v * 100 + 0.5) / 100


def _r3(v):
    return math.floor(v * 1000 + 0.5) / 1000


def k_value(C):
    if C < 0.60:
        return C
    if C <= 1.00:
        return (3.2 * C - C * C - 0.6) / (C + 1)
    return 1.0


def sinir_deger(offers, ym, n=1.0):
    """Geçerli teklifler (TL) + yaklaşık maliyet → adım adım sınır değer. Tebliğ yuvarlamaları uygulanır."""
    if not ym or ym <= 0:
        raise ValueError("yaklaşık maliyet pozitif olmalı")
    if not 1.0 <= n <= 1.2:
        raise ValueError("sınır değer katsayısı N 1,00–1,20 arasında olmalı")
    offers = [float(o) for o in offers if o is not None and float(o) > 0]
    band = [o for o in offers if 0.40 * ym <= o <= 1.20 * ym]
    steps = {"ym": ym, "n": n, "teklif_sayisi": len(offers), "aralik_ici": len(band)}
    if not band:
        sd = _r2(0.40 * ym)
        return {**steps, "sd": sd, "aciklama": "YM'nin %40–120 aralığında geçerli teklif yok: SD = YM × 0,40",
                "asiri_dusuk": [o for o in offers if o < sd]}
    if len(band) == 1:
        tort1 = sigma = None
        tort2 = band[0]
    else:
        tort1 = _r2(sum(band) / len(band))
        sigma = _r2(math.sqrt(sum((o - tort1) ** 2 for o in band) / (len(band) - 1)))
        inner = [o for o in band if tort1 - sigma <= o <= tort1 + sigma]
        tort2 = _r2(sum(inner) / len(inner))
    C = _r3(tort2 / ym)
    K = _r3(k_value(C))
    sd = _r2(K * tort2 / (C * n))
    note = None
    if sd < 0.40 * ym:
        sd, note = _r2(0.40 * ym), "hesaplanan SD YM'nin %40'ının altında: SD = YM × 0,40"
    return {**steps, "tort1": tort1, "sigma": sigma, "tort2": tort2, "c": C, "k": K, "sd": sd, "aciklama": note,
            "asiri_dusuk": sorted(o for o in offers if o < sd)}


# --------------------------------------------------------------------------- teklif simülasyonu

def simulate(ym, rivals=8, mean=0.85, sd=0.10, n=1.0, valid_pct=80, runs=4000, seed=7, ratios=None):
    """Rakip teklifleri YM oranı olarak N(mean, sd) varsayar; geçersiz teklif payı valid_pct ile düşülür.
    Dönen: her teklif oranı için P(aşırı düşük değil), P(kazanır = SD üstü en düşük geçerli teklif)."""
    if not 0 < mean < 2 or not 0 < sd < 1 or not 1 <= rivals <= 60 or not 10 <= valid_pct <= 100:
        raise ValueError("simülasyon parametreleri aralık dışında")
    if not 100 <= runs <= 20000:
        raise ValueError("deneme sayısı 100–20.000 olmalı")
    rnd = random.Random(seed)
    ratios = ratios or [round(0.55 + i * 0.025, 3) for i in range(23)]          # 0,55 … 1,10
    acc = {r: [0, 0] for r in ratios}
    sds = []
    for _ in range(runs):
        others = [max(0.2, rnd.gauss(mean, sd)) * ym for _ in range(rivals) if rnd.random() * 100 < valid_pct]
        for r in ratios:
            mine = r * ym
            res = sinir_deger(others + [mine], ym, n)
            ok = mine >= res["sd"]
            win = ok and all(o >= mine or o < res["sd"] for o in others)
            acc[r][0] += ok
            acc[r][1] += win
        sds.append(sinir_deger(others, ym, n)["sd"] / ym if others else 0.4)
    sds.sort()
    table = [{"oran": r, "teklif": round(r * ym, 2), "p_gecerli": round(acc[r][0] / runs, 3),
              "p_kazanir": round(acc[r][1] / runs, 3)} for r in ratios]
    best = max(table, key=lambda t: t["p_kazanir"] * (t["oran"]))   # basit beklenen ciro ölçütü
    q = lambda p: round(sds[min(len(sds) - 1, int(p * len(sds)))], 3)
    return {"tablo": table, "sd_oran_p10": q(0.10), "sd_oran_p50": q(0.50), "sd_oran_p90": q(0.90), "oneri": best,
            "varsayim": f"{rivals} rakip, teklif/YM ~ N({mean:g}, {sd:g}), geçerli teklif oranı %{valid_pct:g}, N={n:g}, "
                        f"{runs} deneme. Rakip dağılımı varsayımdır; geçmiş EKAP sonuçlarıyla kalibre edilmedi."}


# --------------------------------------------------------------------------- rapor

def write_report(path, title, res, sd=None, sim=None):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    from .reports import BOX, FONT, MONEY_XL, _xl_header, _xl_print, _xl_safe
    wb = Workbook()
    F = lambda **k: Font(name=FONT, size=9, **k)

    def put(ws, r, vals, money=(), bold=False):
        for j, v in enumerate(vals, 1):
            c = ws.cell(row=r, column=j, value=_xl_safe(v))
            c.font, c.border = F(bold=bold), BOX
            c.alignment = Alignment(wrap_text=True, vertical="top")
            if j in money and isinstance(v, (int, float)):
                c.number_format = MONEY_XL

    ws = wb.active
    ws.title = "Özet"
    ws["A1"], ws["A1"].font = f"İHALE / TEKLİF ANALİZİ — {title}", Font(name=FONT, bold=True, size=12)
    s = res["summary"]
    rows = [("Kalem sayısı", s["kalem"]), ("Fiyatlı kalem", s["fiyatli_kalem"]), ("Referanslı kalem", s["referansli_kalem"]),
            ("Referans kapsamı (%)", s["referans_kapsam_pct"]), ("Teklif toplamı (KDV hariç)", s["teklif_toplam"]),
            ("Referans toplam (yaklaşık maliyet tahmini, yalnız referanslı kalemler)", s["referans_toplam"]),
            ("Karşılaştırılabilir kalemlerde fark (%)", s.get("karsilastirilabilir_oran_pct")),
            ("Uyarılı kalem", s["uyari"]), ("Ağırlıklı kalem (tutarın %80'i)", s["agirlikli_kalem"])]
    for i, (k, v) in enumerate(rows, 3):
        put(ws, i, [k, v], money=(2,))
    r = len(rows) + 4
    for n_ in res["notes"]:
        ws.cell(row=r, column=1, value=_xl_safe(n_)).font = F(italic=True)
        r += 1
    ws.cell(row=r + 1, column=1, value="Bu rapor karar desteğidir; idari şartname, ilan ve KİK mevzuatı esastır.").font = F(italic=True)
    ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 70, 22
    _xl_print(ws, landscape=False)

    ws = wb.create_sheet("Kalemler")
    cols = ["Sıra", "Poz No", "Tanım", "Birim", "Miktar", "Birim Fiyat", "Tutar", "Ref. Fiyat", "Sapma %", "Ref. Tutar",
            "Ağırlıklı", "Uyarılar"]
    _xl_header(ws, 1, cols, [6, 14, 50, 7, 11, 13, 15, 13, 9, 15, 9, 60])
    for i, l in enumerate(res["lines"], 2):
        put(ws, i, [l["sira"], l["poz"] or "", l["tanim"], l["birim"], l["miktar"], l["birim_fiyat"], l["tutar"],
                    l["ref_fiyat"], l["sapma_pct"], l["ref_tutar"], "●" if l["agirlikli"] else "", "; ".join(l["flags"])],
            money=(5, 6, 7, 8, 10))
    _xl_print(ws)

    if res.get("metraj"):
        m = res["metraj"]
        ws = wb.create_sheet("Metraj Karşılaştırma")
        _xl_header(ws, 1, ["Poz No", "Tanım", "Birim", "Cetvel", "ArchAI", "Fark %", "ArchAI kalemleri", "Uyarı"],
                   [14, 50, 8, 12, 12, 9, 22, 50])
        r = 2
        for x in m["satirlar"]:
            put(ws, r, [x["poz"], x["tanim"], x["birim"], x["cetvel"], x["archai"], x.get("fark_pct"), ", ".join(x["kodlar"]),
                        "; ".join(x["flags"])], money=(4, 5))
            r += 1
        r += 1
        ws.cell(row=r, column=1, value="CETVELDE KARŞILIĞI BULUNMAYAN ARCHAI KALEMLERİ").font = F(bold=True)
        r += 1
        for x in m["cetvelde_yok"]:
            put(ws, r, [x["poz"] or x["code"], x["name"], x["unit"], None, x["quantity"], None, x["code"], f"ArchAI tutarı {x['amount']:,.0f} TL"],
                money=(5,))
            r += 1
        ws.cell(row=r + 1, column=1, value=_xl_safe(m["not"])).font = F(italic=True)
        _xl_print(ws)

    if sd:
        ws = wb.create_sheet("Sınır Değer")
        rows = [("Yaklaşık maliyet (YM)", sd["ym"]), ("N", sd["n"]), ("Teklif sayısı", sd["teklif_sayisi"]),
                ("%40–120 aralığında", sd["aralik_ici"]), ("Tort1", sd.get("tort1")), ("σ (n−1)", sd.get("sigma")),
                ("Tort2", sd.get("tort2")), ("C", sd.get("c")), ("K", sd.get("k")), ("SINIR DEĞER", sd["sd"]),
                ("Açıklama", sd.get("aciklama") or "")]
        for i, (k, v) in enumerate(rows, 1):
            put(ws, i, [k, v], money=(2,), bold=k == "SINIR DEĞER")
        ws.column_dimensions["A"].width, ws.column_dimensions["B"].width = 30, 20
    if sim:
        ws = wb.create_sheet("Teklif Simülasyonu")
        _xl_header(ws, 1, ["Teklif / YM", "Teklif (TL)", "P(aşırı düşük değil)", "P(kazanır)"], [12, 16, 18, 14])
        for i, t in enumerate(sim["tablo"], 2):
            put(ws, i, [t["oran"], t["teklif"], t["p_gecerli"], t["p_kazanir"]], money=(2,))
        ws.cell(row=len(sim["tablo"]) + 3, column=1, value=_xl_safe("Varsayım: " + sim["varsayim"])).font = F(italic=True)
    wb.save(path)
    return path


SAFE_ID = re.compile(r"\d{8}-\d{6}-[0-9a-f]{6}")
