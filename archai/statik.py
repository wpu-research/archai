"""Statik ÖN BOYUTLANDIRMA (avan): kolon aksı ve kesiti, kiriş yüksekliği, döşeme ve radye kalınlığı kontrolü, betonarme miktarı.

Bu bir statik hesap DEĞİLDİR: deprem (TBDY 2018) ve zemin etüdü olmadan boyutlar kesin sayılamaz; yetkili inşaat mühendisinin
hesabı ve imzası gerekir. Amaç, teklif ve maliyetin "kolon/kiriş/perde" kalemini plana dayalı bir ön boyutlandırmayla desteklemektir.

Yöntem (ön boyutlandırma, ölçüler metre):
  - Kolon konumu: zemin kat planında, kalın (≥ 20 cm) duvar aksları (çekirdek, daire ayırma, dış duvar) arasındaki kesişimler;
    iki kolon arası 6,0 m'yi aşarsa eşit bölünerek ara aks eklenir.
  - Kolon kesiti: Nd = kat adedi × katkı alanı × qd (1,4G + 1,6Q) ve Ac ≥ Nd / (0,40·fck) (C30, TBDY eksenel yük sınırı); en az 30 × 50, 5 cm'ye yuvarlanır.
  - Kiriş: h ≈ L / 12 (≥ 40 cm), b = 25 cm. Döşeme: kalınlık ≥ L_kısa / 35 (≥ 12 cm) kontrolü.
  - Radye: kalınlık önerisi 0,30 + 0,05 × kat adedi (0,40–1,00); ortalama temel gerilmesi, varsayılan zemin emniyet gerilmesiyle kıyaslanır.
  - Miktar: kolon, kiriş, çekirdek perdesi (merdiven/asansör kovası) ve bodrum çevre perdesi betonu; donatı ve kalıp oranlarla.
"""
import math

from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from .notice import AVAN_NOTE

STATIK_NOTE = ("Statik ÖN BOYUTLANDIRMA (avan): statik hesap, deprem (TBDY 2018) ve zemin etüdü değildir; boyutlar yetkili inşaat "
               "mühendisince hesapla doğrulanmadan uygulanamaz. İmzasızdır.")
G, Q = 8.0, 2.0                    # kN/m² (döşeme + kaplama + duvar payı; konut hareketli yükü)
QD = 1.4 * G + 1.6 * Q             # tasarım yükü, kN/m² / kat
QS = G + Q                         # servis yükü
FCK = 30.0                         # MPa (C30/37)
MAX_SPAN = 6.0
SIGMA_EM = 150.0                   # kPa, varsayılan zemin emniyet gerilmesi (zemin etüdü yoksa)
REBAR_COL, REBAR_BEAM, REBAR_WALL = 150.0, 130.0, 90.0      # kg/m³ (avan oranları)


def _r5(v):
    return math.ceil(v / 0.05 - 1e-9) * 0.05


def _cluster(vals, tol=0.35):
    out = []
    for v in sorted(vals):
        if out and v - out[-1][-1] <= tol:
            out[-1].append(v)
        else:
            out.append([v])
    return [sum(c) / len(c) for c in out]


def _fill(axes, limit=MAX_SPAN):
    res = [axes[0]]
    for a in axes[1:]:
        gap = a - res[-1]
        n = max(1, math.ceil(gap / limit - 1e-9))
        res += [res[-1] + gap * k / n for k in range(1, n + 1)]
    return res


def compute(elements, report=None, sigma_em=SIGMA_EM):
    floors = sorted([e for e in elements if e["type"] == "slab" and e.get("role") == "floor"], key=lambda e: e["z"])
    if not floors:
        raise ValueError("projede kat döşemesi yok")
    ground = next((e for e in floors if e["level"] == "Zemin Kat"), None) or next(e for e in floors if e["z"] >= -1e-6)
    below = [e for e in floors if e["z"] < ground["z"] - 1e-6]
    above = [e for e in floors if e["z"] >= ground["z"] - 1e-6]
    fh = (floors[-1]["z"] - floors[0]["z"]) / max(1, len(floors) - 1) if len(floors) > 1 else 3.0
    n_up = len(above)                                           # zemin dahil, zemin üstü kat adedi
    n_all = len(floors)
    t_slab = ground.get("thickness", 0.2)
    gpoly = Polygon([tuple(p[:2]) for p in ground["points"]])
    walls = [e for e in elements if e["type"] == "wall" and e["level"] == ground["level"] and e.get("thickness", 0) >= 0.2 - 1e-6]
    vx = [w["start"][0] for w in walls if abs(w["start"][0] - w["end"][0]) < 1e-6]
    hy = [w["start"][1] for w in walls if abs(w["start"][1] - w["end"][1]) < 1e-6]
    if not vx or not hy:
        raise ValueError("kalın duvar akslarından kolon aksı çıkarılamadı")
    x0, y0, x1, y1 = gpoly.bounds
    xs = _fill(sorted(set([round(x, 3) for x in _cluster(vx)])))
    ys = _fill(sorted(set([round(y, 3) for y in _cluster(hy)])))
    wall_union = unary_union([LineString([w["start"], w["end"]]).buffer(max(0.12, w["thickness"] / 2), cap_style=2) for w in walls])
    cols = []
    for x in xs:
        for y in ys:
            p = Point(x, y)
            if gpoly.buffer(0.2).contains(p) and wall_union.distance(p) <= 0.25:
                cols.append((round(x, 2), round(y, 2)))
    if len(cols) < 4:
        raise ValueError("yeterli kolon konumu bulunamadı")
    gross_level = gpoly.area
    # --- kolon
    a_trib = gross_level / len(cols)
    nd = n_up * a_trib * 1.3 * QD                                # 1,3: iç kolon katkı alanı payı
    ac = nd / (0.40 * FCK * 1000.0)                              # m² (TBDY: Nd ≤ 0,40·fck·Ac)
    short = max(0.30, _r5(math.sqrt(ac / 1.667)))                # 1:1,67 yakın dikdörtgen
    longd = max(0.50, _r5(ac / short))
    col_b, col_h = short, longd
    # --- kiriş / döşeme
    gx = [b - a for a, b in zip(xs, xs[1:])]
    gy = [b - a for a, b in zip(ys, ys[1:])]
    span = max(gx + gy)
    beam_h = max(0.40, _r5(span / 12.0))
    beam_b = 0.25
    panel_short = max(min(gx), min(gy)) if gx and gy else span
    panel = max(min(a, b) for a in gx for b in gy)               # en büyük panelin kısa kenarı
    t_need = max(0.12, panel / 35.0)
    # --- radye / temel
    raft_t = min(1.0, max(0.40, 0.30 + 0.05 * n_all))
    raft_area = gross_level if not below else Polygon([tuple(p[:2]) for p in below[0]["points"]]).area
    total_gross = (report or {}).get("gross_total") or gross_level * n_all
    sigma = QS * total_gross / raft_area
    # --- miktarlar
    H = [floors[i + 1]["z"] - floors[i]["z"] for i in range(len(floors) - 1)] + [fh]
    h_cols = sum(H)                                              # tüm katların kat yükseklikleri toplamı
    n_beam_levels = len(floors)                                  # her kat döşemesi + çatı çevresinde kiriş ağı
    beam_len_level = len(xs) * (y1 - y0) + len(ys) * (x1 - x0)
    v_col = len(cols) * col_b * col_h * h_cols
    v_beam = n_beam_levels * beam_len_level * beam_b * max(0.05, beam_h - t_slab)
    core = [e for e in elements if e["type"] == "wall" and e["level"] == ground["level"] and 0.2 - 1e-6 <= e.get("thickness", 0) < 0.25 - 1e-6
            and not e.get("exterior")]
    core_len = sum(math.dist(w["start"], w["end"]) for w in core)
    v_core = core_len * h_cols * 0.20 * 0.5                      # çekirdek duvarlarının yarısı perde sayılır (kolon payı düşülür)
    v_base = 0.0
    if below:
        per = Polygon([tuple(p[:2]) for p in below[0]["points"]]).length
        v_base = per * sum(H[:len(below)]) * 0.30                # bodrum çevre perdesi 30 cm
    vol = v_col + v_beam + v_core + v_base
    kg = v_col * REBAR_COL + v_beam * REBAR_BEAM + (v_core + v_base) * REBAR_WALL
    form = (len(cols) * 2 * (col_b + col_h) * h_cols + n_beam_levels * beam_len_level * (beam_b + 2 * max(0.05, beam_h - t_slab))
            + (core_len * h_cols * 2 * 0.5) + (per * sum(H[:len(below)]) * 2 if below else 0.0))
    warn = []
    if span > 6.5:
        warn.append(f"kolon aralığı {span:.1f} m: kiriş yüksekliği {beam_h:.2f} m; aralığı azaltmak ekonomik olur")
    if t_need > t_slab + 1e-6:
        warn.append(f"döşeme kalınlığı en az {t_need:.2f} m olmalı (modelde {t_slab:.2f} m): panel {panel:.1f} m")
    if sigma > sigma_em:
        warn.append(f"ortalama temel gerilmesi {sigma:.0f} kPa > {sigma_em:.0f} kPa (varsayılan emniyet): zemin etüdüyle doğrulanmalı, radye/kazık gerekebilir")
    if max(col_b, col_h) > 0.9:
        warn.append(f"kolon {col_b * 100:.0f}×{col_h * 100:.0f} cm: büyük; perde kullanımı veya kolon sayısını artırmak gerekir")
    if n_up >= 6:
        warn.append(f"{n_up} katlı: deprem bölgesinde perde (çekirdek) ve kat ötelenmesi kontrolü zorunludur; kolonlar ön boyuttur")
    warn.append("deprem hesabı (TBDY 2018), perde rijitlik/kat ötelenmesi ve temel zemini kontrolü yapılmadı")
    return {
        "kolonlar": [{"x": x, "y": y} for x, y in cols], "kolon_sayisi": len(cols), "aks_x": [round(v, 2) for v in xs],
        "aks_y": [round(v, 2) for v in ys],
        "kolon_kesiti": {"b": round(col_b, 2), "h": round(col_h, 2)}, "kolon_yuku_kN": round(nd),
        "kiris": {"b": beam_b, "h": round(beam_h, 2), "en_buyuk_aciklik": round(span, 2)},
        "doseme": {"modelde": t_slab, "gereken_min": round(t_need, 3), "uygun": t_need <= t_slab + 1e-6},
        "radye": {"oneri_kalinlik": round(raft_t, 2), "ortalama_gerilme_kPa": round(sigma), "emniyet_kPa": sigma_em,
                  "uygun": sigma <= sigma_em},
        "kat_sayisi": {"zemin_ustu": n_up, "bodrum": len(below), "toplam": n_all},
        "miktar": {"kolon_m3": round(v_col, 1), "kiris_m3": round(v_beam, 1), "cekirdek_perde_m3": round(v_core, 1),
                   "bodrum_perde_m3": round(v_base, 1), "beton_m3": round(vol, 1), "donati_ton": round(kg / 1000.0, 2),
                   "kalip_m2": round(form)},
        "varsayimlar": {"G_kN_m2": G, "Q_kN_m2": Q, "beton": "C30/37", "celik": "B500C"},
        "uyarilar": warn, "not": STATIK_NOTE,
    }


def adjust_for(result):
    """Maliyet ayarı: 'kolon, kiriş ve perde' kalemlerini ön boyutlandırma miktarlarıyla değiştirir (qty_overrides)."""
    m = result["miktar"]
    return {"KOL-01": m["beton_m3"], "DON-02": m["donati_ton"], "KAL-02": float(m["kalip_m2"])}


def write_xlsx(path, project_name, result):
    from pathlib import Path

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Ön Boyutlandırma"
    ws["A1"] = f"STATİK ÖN BOYUTLANDIRMA (AVAN) — {project_name}"
    ws["A1"].font = Font(bold=True, size=12)
    ws["A2"] = result["not"] + " " + AVAN_NOTE
    ws["A2"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.merge_cells("A2:D2")
    ws.row_dimensions[2].height = 48
    kk, ki, m = result["kolon_kesiti"], result["kiris"], result["miktar"]
    rows = [("Kolon sayısı", result["kolon_sayisi"], "adet"), ("Kolon kesiti", f"{kk['b'] * 100:.0f} × {kk['h'] * 100:.0f}", "cm"),
            ("Kolon tasarım yükü (en yüklü, zemin)", result["kolon_yuku_kN"], "kN"),
            ("Kiriş", f"{ki['b'] * 100:.0f} × {ki['h'] * 100:.0f}", "cm"), ("En büyük açıklık", ki["en_buyuk_aciklik"], "m"),
            ("Döşeme kalınlığı (modelde / gereken)", f"{result['doseme']['modelde']} / {result['doseme']['gereken_min']}", "m"),
            ("Radye kalınlığı önerisi", result["radye"]["oneri_kalinlik"], "m"),
            ("Ortalama temel gerilmesi / emniyet (varsayılan)", f"{result['radye']['ortalama_gerilme_kPa']} / {result['radye']['emniyet_kPa']}", "kPa"),
            ("Kolon betonu", m["kolon_m3"], "m³"), ("Kiriş betonu", m["kiris_m3"], "m³"),
            ("Çekirdek perdesi betonu", m["cekirdek_perde_m3"], "m³"), ("Bodrum çevre perdesi betonu", m["bodrum_perde_m3"], "m³"),
            ("TOPLAM BETON", m["beton_m3"], "m³"), ("Donatı (B500C)", m["donati_ton"], "ton"), ("Kalıp", m["kalip_m2"], "m²")]
    for i, (a, b, c) in enumerate(rows, 4):
        ws.cell(row=i, column=1, value=a)
        ws.cell(row=i, column=2, value=b)
        ws.cell(row=i, column=3, value=c)
    ws.cell(row=5 + len(rows), column=1, value="Uyarılar").font = Font(bold=True)
    for j, w in enumerate(result["uyarilar"], 6 + len(rows)):
        ws.cell(row=j, column=1, value="• " + w)
    for col, w in zip("ABC", (52, 18, 8)):
        ws.column_dimensions[col].width = w
    ws2 = wb.create_sheet("Kolon Aksları")
    ws2.append(["No", "X (m)", "Y (m)", "Kesit (cm)"])
    for i, c in enumerate(result["kolonlar"], 1):
        ws2.append([i, c["x"], c["y"], f"{kk['b'] * 100:.0f}×{kk['h'] * 100:.0f}"])
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
