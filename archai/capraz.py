"""Çapraz doğrulama: aynı büyüklüğü bağımsız yollardan hesaplayıp karşılaştırır ve kodlanmış kuralları (plan notu / yönetmelik) denetler.

İki sınıf kontrol:
  TUTARLILIK — rapor, metraj, kat irtifakı tablosu, maliyet, statik ön boyutlandırma ve (varsa) avan tablosu birbirini tutuyor mu?
  KURAL      — imar özeti, asansör, sığınak/otopark (avan tablosu hesabı), çatı dairesi (Bahçelievler RUIP 27.07.2025 plan notu).

Her kontrol: {kod, ad, durum: uygun|uyari|ihlal|bilgi, olculen, sinir, aciklama, kaynak}. Kural kaynakları koda yazıldığı tarihteki metinlerdir;
mevzuat ve plan notları değişir, resmî güncel metinle ve imar müdürlüğüyle teyit edilmelidir (AVAN, yetkili teyidi gerekir).
"""
from shapely.geometry import Polygon

from . import kat_irtifaki, quantities as Q, statik
from .notice import AVAN_SHORT

TOL_ALAN = 0.01          # % — bağımsız alan hesapları arası kabul edilen sapma
SRC_RUIP = "Bahçelievler RUIP plan notları — 27.07.2025 çatı katları plan notu"


def _k(kod, ad, durum, olculen, sinir, kaynak, aciklama=""):
    return {"kod": kod, "ad": ad, "durum": durum, "olculen": olculen, "sinir": sinir, "kaynak": kaynak, "aciklama": aciklama}


def _poly(e):
    return Polygon([tuple(p[:2]) for p in e["points"]])


def compute(project, elements):
    rep, cost, brief = project.get("report") or {}, project.get("cost") or {}, project.get("brief") or {}
    out = []
    q = Q.compute(elements)
    gross = rep.get("gross_total")
    # ---- tutarlılık: toplam inşaat alanı
    if gross:
        s_gfa = q["summary"]["gross_floor_area"]
        d = abs(s_gfa - gross) / gross
        out.append(_k("TUT-ALAN-METRAJ", "Toplam inşaat alanı: rapor ↔ metraj", "uygun" if d <= TOL_ALAN else "uyari",
                      f"{gross:.1f} m² ↔ {s_gfa:.1f} m²", f"sapma ≤ %{TOL_ALAN * 100:g} (şimdi %{d * 100:.2f})", "generate/quantities",
                      "rapordaki brüt alan, eleman listesinden bağımsız hesaplanan döşeme toplamıyla karşılaştırıldı"))
        cg = cost.get("gross_floor_area")
        if cg:
            d = abs(cg - gross) / gross
            out.append(_k("TUT-ALAN-MALIYET", "Toplam inşaat alanı: rapor ↔ maliyet", "uygun" if d <= 0.02 else "uyari",
                          f"{gross:.1f} m² ↔ {cg:.1f} m²", f"sapma ≤ %2 (şimdi %{d * 100:.2f})", "costing", "m² birim maliyetin paydası"))
    # ---- kat irtifakı ↔ rapor
    try:
        ki = kat_irtifaki.compute(elements, rep.get("parcel_area"))
        o = ki["ozet"]
        if rep.get("unit_count"):
            ok = o["konut"] == rep["unit_count"]
            out.append(_k("TUT-BOLUM", "Konut sayısı: rapor ↔ kat irtifakı tablosu", "uygun" if ok else "ihlal",
                          f"{rep['unit_count']} ↔ {o['konut']}", "eşit olmalı", "kat_irtifaki", "mahal etiketlerinden sayılan bağımsız bölümler"))
        if gross:
            d = abs(o["brut_toplam"] - gross) / gross
            out.append(_k("TUT-BRUT", "Toplam brüt: rapor ↔ kat irtifakı (bölümler + ortak alan)", "uygun" if d <= TOL_ALAN * 2 else "uyari",
                          f"{gross:.1f} ↔ {o['brut_toplam']:.1f} m²", f"sapma ≤ %{TOL_ALAN * 200:g} (şimdi %{d * 100:.2f})", "kat_irtifaki",
                          "arsa payları bu toplama oranlıdır"))
        out.append(_k("TUT-ARSA-PAYI", "Arsa payları toplamı", "uygun" if sum(b["arsa_payi"] for b in ki["bolumler"]) == ki["payda"] else "ihlal",
                      f"{sum(b['arsa_payi'] for b in ki['bolumler'])}/{ki['payda']}", f"{ki['payda']}/{ki['payda']}", "kat_irtifaki"))
    except Exception:  # noqa: BLE001 — bir kontrol hatası diğerlerini durdurmasın
        out.append(_k("TUT-BOLUM", "Kat irtifakı tablosu hesaplanamadı", "uyari", "—", "—", "kat_irtifaki"))
    # ---- avan tablosu
    at = rep.get("avan_tablo")
    if at:
        for lvl, v in at["karsilastirma"].items():
            a, b = v["tablo"], v["model"]
            d = abs(a - b) / a
            out.append(_k(f"TAB-{lvl.upper()}", f"Kat alanı: tablo ↔ model ({lvl})", "uygun" if d <= 0.005 else "uyari",
                          f"{b:.2f} m²", f"tablo {a:.2f} m² (sapma %{d * 100:.2f})", "avan_tablo"))
        t = at["tablo"]
        out.append(_k("TAB-TAPU", "Tapu alanı ↔ parsel (DXF)", "uygun" if abs(t["tapu_alani"] - rep["parcel_area"]) / t["tapu_alani"] <= 0.03 else "uyari",
                      f"{rep['parcel_area']:.1f} m²", f"tapu {t['tapu_alani']} m²", "avan_tablo", "büyük fark: parsel veya tablo teyit edilmeli"))
    # ---- statik ↔ maliyet
    try:
        s = statik.compute(elements, rep)
        rows = {r["code"]: r for r in cost.get("rows", [])}
        kol = rows.get("KOL-01")
        if kol:
            on = s["miktar"]["beton_m3"]
            d = abs(kol["quantity"] - on) / max(on, 1e-9)
            out.append(_k("TUT-STATIK", "Kolon-kiriş-perde betonu: maliyet ↔ statik ön boyutlandırma",
                          "uygun" if d <= 0.25 else "uyari", f"{kol['quantity']:.0f} m³ ↔ {on:.0f} m³", f"sapma ≤ %25 (şimdi %{d * 100:.0f})",
                          "statik", "sapma büyükse Statik sekmesinden 'maliyete uygula'"))
    except ValueError:
        pass
    # ---- imar özeti
    ck = rep.get("checks") or {}
    for key, lab in (("taks", "TAKS"), ("kaks", "KAKS"), ("floors", "Kat adedi"), ("height", "Yençok/saçak")):
        c = ck.get(key)
        if c:
            lim = "sınır yok (beyan)" if c.get("limit") is None else f"≤ {c['limit']}"
            out.append(_k(f"IMAR-{key.upper()}", f"İmar: {lab}", "uygun" if c.get("ok") else "ihlal", f"{c['value']}", lim, "imar beyanı"))
    for k, d in (ck.get("setbacks_detail") or {}).items():
        out.append(_k(f"IMAR-CEKME-{k.upper()}", f"Çekme: {k}", "uygun" if d["ok"] else "ihlal", f"{d['value']:.2f} m", f"≥ {d['limit']:g} m", "imar beyanı"))
    # ---- asansör / sığınak / otopark
    levels_up = sorted({e["level"] for e in elements if e["type"] == "slab" and e.get("role") == "floor" and e["z"] >= -1e-6})
    n_up = len(levels_up)
    lifts = {e["level"] for e in elements if e["type"] == "room" and Q.room_kind(e) == "lift"}
    konut = rep.get("unit_count") or 0
    if n_up >= 4 or konut > 20:
        need = 2 if konut > 20 else 1
        # bir asansör kuyusu = en alt katta asansör mahali sayısı
        shafts = max((sum(1 for e in elements if e["type"] == "room" and Q.room_kind(e) == "lift" and e["level"] == l) for l in lifts), default=0)
        out.append(_k("KUR-ASANSOR", "Asansör zorunluluğu", "uygun" if shafts >= need else "ihlal", f"{shafts} asansör kuyusu", f"≥ {need}",
                      "Planlı Alanlar İmar Yönetmeliği (4+ kat) ve avan tablosu notu (zemin üstü >20 konut → 2) — teyit gerekir",
                      f"zemin üstü {n_up} kat, {konut} konut"))
    if at and (rep.get("avan") or {}).get("basement"):
        b = rep["avan"]["basement"]
        out.append(_k("KUR-SIGINAK", "Sığınak alanı", "uygun" if b["rooms"].get("Sığınak", 0) >= b["shelter_required"] else "ihlal",
                      f"{b['rooms'].get('Sığınak', 0):.0f} m²", f"≥ {b['shelter_required']:.0f} m²", "avan tablosu sığınak hesabı"))
        out.append(_k("KUR-OTOPARK", "Otopark kapasitesi", "uygun" if b["parking_capacity"] >= b["parking_required"] else "ihlal",
                      f"≈{b['parking_capacity']} araç", f"≥ {b['parking_required']}", "avan tablosu otopark hesabı (24/3)", "rampa çizilmedi, kapasite yaklaşık"))
    elif at:
        t = at["tablo"]
        out.append(_k("KUR-OTOPARK", "Otopark", "ihlal" if t["otopark_projede"] < t["otopark_sayisi_gerekli"] else "uygun",
                      f"{t['otopark_projede']} araç", f"≥ {t['otopark_sayisi_gerekli']}", "avan tablosu otopark hesabı"))
    # ---- çatı dairesi (27.07.2025 plan notu)
    attic = next((e for e in elements if e["type"] == "slab" and e.get("name") == "cati_kati"), None)
    if attic:
        floors = sorted([e for e in elements if e["type"] == "slab" and e.get("role") == "floor" and e["level"] != "Çatı Katı"],
                        key=lambda e: e["z"])
        top = _poly(floors[-1])
        ap = _poly(attic)
        geri = top.boundary.distance(ap) if top.contains(ap.representative_point()) else 0.0
        out.append(_k("CATI-GERI", "Çatı dairesi: son kat konturundan geri çekme", "uygun" if geri >= 1.5 - 1e-6 else "ihlal",
                      f"{geri:.2f} m", "≥ 1,50 m (saçak ≤ 0,50 m)", SRC_RUIP, "madde 1.2"))
        roof_z = next((e["z"] + e.get("thickness", 0) for e in elements if e.get("name") == "cati_kati"), None)
        top_ceiling = next((e["z"] for e in elements if e["type"] == "slab" and e.get("name") == "cati"), None)
        if roof_z is not None and top_ceiling is not None:
            h = roof_z - top_ceiling
            out.append(_k("CATI-MAHYA", "Çatı dairesi: son kat tavanından toplam yükseklik", "uygun" if h <= 4.5 + 1e-6 else "ihlal",
                          f"{h:.2f} m", "mahya ≤ 4,50 m", SRC_RUIP, "madde 1.3 (düz çatılı şematik modelde eğim modellenmedi)"))
        out.append(_k("CATI-ASANSOR", "Çatı dairesine asansör hizmet etmeli", "uygun" if lifts else "ihlal", "var" if lifts else "yok",
                      "zorunlu", SRC_RUIP, "madde 1.12"))
        donusum = bool(brief.get("tablo")) or bool((rep.get("avan_tablo") or {}))
        out.append(_k("CATI-DONUSUM", "Dönüşüm plan notlarıyla yapılan parselde çatı dairesi yapılamaz",
                      "uyari" if donusum else "bilgi",
                      "dönüşüm (ÇAP) hakkı kullanılıyor" if donusum else "dönüşüm notu kullanılmıyor",
                      "24.07.2020 / 22.03.2021 / 17.10.2023 plan değişiklikleriyle uygulanan parsellerde çatı dairesi yapılamaz", SRC_RUIP,
                      "madde 1.14 — bu parselde çatı katı dönüşüm notundaki ÇAP alanı (normal kat alanının %30'u) olarak değerlendirilmeli; "
                      "yeni çatı dairesi notu kapsamında değildir. İmar müdürlüğünden teyit edin." if donusum else
                      "ilgili plan notunun uygulanabilirliği (mahalle: Yenibosna, Kocasinan, Bahçelievler Merkez) imar durumundan teyit edilmeli"))
    return {"kontroller": out, "damga": AVAN_SHORT,
            "ozet": {d: sum(1 for k in out if k["durum"] == d) for d in ("uygun", "uyari", "ihlal", "bilgi")}}
