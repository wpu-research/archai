"""Ödeme planı / hakediş takvimi: maliyetten aylık iş programı ve nakit akışı (avan, varsayımsal).

İş grupları (Kaba inşaat, İnce inşaat, Doğrama, Tesisat, Dış mekân, Genel giderler) şantiye süresinin farklı dilimlerine yayılır; her grup
yumuşak (S) eğriyle dağıtılır. Avans ödenir ve hakedişlerden orantılı mahsup edilir; teminat kesintisi son hakedişte iade edilir.
Süre ve dilimler genel varsayımdır (şantiye programı yerine geçmez); gerçek iş programı müteahhitçe hazırlanmalıdır.
"""
import math

from .notice import AVAN_SHORT

# grup → (başlangıç, bitiş) şantiye süresi oranı
FAZ = {"Genel giderler": (0.0, 1.0), "Kaba inşaat": (0.0, 0.55), "Tesisat": (0.35, 0.85), "Doğrama": (0.45, 0.75),
       "İnce inşaat": (0.45, 0.95), "Dış mekân": (0.85, 1.0)}
VARSAYILAN = {"avans_pct": 10.0, "teminat_pct": 5.0, "stopaj_pct": 0.0}


def sure_ay(gross):
    """Varsayılan şantiye süresi (ay): küçük yapı 6, brüt alanla artan; 6–36 aralığı."""
    return int(min(36, max(6, round(5 + (gross or 0) / 170))))


def _smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def _cdf(t, a, b):
    return _smooth((t - a) / (b - a)) if b > a else float(t >= a)


def compute(cost, gross=None, ay=None, avans_pct=None, teminat_pct=None, kdv_pct=None):
    ay = int(ay or sure_ay(gross or cost.get("gross_floor_area")))
    if not 3 <= ay <= 60:
        raise ValueError("süre 3–60 ay olmalı")
    avans = VARSAYILAN["avans_pct"] if avans_pct is None else float(avans_pct)
    tem = VARSAYILAN["teminat_pct"] if teminat_pct is None else float(teminat_pct)
    kdv = cost.get("vat_pct", 20.0) if kdv_pct is None else float(kdv_pct)
    if not (0 <= avans <= 50 and 0 <= tem <= 20 and 0 <= kdv <= 100):
        raise ValueError("avans 0–50, teminat 0–20, KDV 0–100 aralığında olmalı")
    base = cost["total_before_vat"]
    groups = {g: v for g, v in (cost.get("groups") or {}).items() if v and g in FAZ}
    sub = sum(groups.values()) or 1.0
    k = base / sub                                             # genel gider/kâr dahil ölçekleme
    months = []
    for m in range(1, ay + 1):
        row = {}
        for g, v in groups.items():
            a, b = FAZ[g]
            share = _cdf(m / ay, a, b) - _cdf((m - 1) / ay, a, b)
            row[g] = v * k * share
        months.append(row)
    tot = [sum(r.values()) for r in months]
    corr = base / (sum(tot) or 1.0)                            # yuvarlama/eğri kayıplarını kapat
    tot = [t * corr for t in tot]
    avans_tutar = base * avans / 100
    rows, cum, kes_toplam = [], 0.0, 0.0
    cum_is = 0.0
    for i, t in enumerate(tot, 1):
        cum_is += t
        mahsup = t * avans / 100
        teminat = t * tem / 100
        kes_toplam += teminat
        net_kdvsiz = t - mahsup - teminat
        kdv_t = net_kdvsiz * kdv / 100
        odeme = net_kdvsiz + kdv_t
        rows.append({"ay": i, "is_orani": round(cum_is / base * 100, 1), "hakedis": round(t), "avans_mahsubu": round(mahsup),
                     "teminat_kesintisi": round(teminat), "kdv": round(kdv_t), "net_odeme": round(odeme),
                     "gruplar": {g: round(v * corr) for g, v in months[i - 1].items()}})
    ilk = {"ay": 0, "is_orani": 0.0, "hakedis": 0, "avans_mahsubu": 0, "teminat_kesintisi": 0, "kdv": 0,
           "net_odeme": round(avans_tutar * (1 + kdv / 100)), "not": "avans (KDV dahil)", "gruplar": {}}
    son = {"ay": ay + 1, "is_orani": 100.0, "hakedis": 0, "avans_mahsubu": 0, "teminat_kesintisi": -round(kes_toplam),
           "kdv": round(kes_toplam * kdv / 100), "net_odeme": round(kes_toplam * (1 + kdv / 100)),
           "not": "teminat iadesi", "gruplar": {}}
    tablo = [ilk] + rows + [son]
    kum = 0.0
    for r in tablo:
        kum += r["net_odeme"]
        r["kumulatif_odeme"] = round(kum)
    return {"sure_ay": ay, "varsayimlar": {"avans_pct": avans, "teminat_pct": tem, "kdv_pct": kdv},
            "toplam_kdv_haric": round(base), "toplam_kdv_dahil": round(base * (1 + kdv / 100)),
            "odenen_toplam": round(kum), "tablo": tablo, "damga": AVAN_SHORT,
            "not": "Varsayımsal ödeme planı: iş grupları standart dilimlere yayıldı, süre brüt alandan tahmin edildi. Gerçek iş programı, "
                   "sözleşme (avans, teminat, stopaj) ve hakediş esasları müteahhit ve idare/malik arasında belirlenir."}


def write_xlsx(path, project_name, plan):
    from pathlib import Path

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font
    wb = Workbook()
    ws = wb.active
    ws.title = "Ödeme Planı"
    ws["A1"] = f"ÖDEME PLANI / HAKEDİŞ TAKVİMİ — {project_name}"
    ws["A1"].font = Font(bold=True, size=12)
    ws["A2"] = plan["not"]
    ws["A2"].alignment = Alignment(wrap_text=True)
    ws.merge_cells("A2:H2")
    ws.row_dimensions[2].height = 40
    head = ["Ay", "İş ilerlemesi %", "Hakediş (KDV hariç)", "Avans mahsubu", "Teminat kesintisi", "KDV", "Net ödeme", "Kümülatif ödeme"]
    for j, h in enumerate(head, 1):
        ws.cell(row=4, column=j, value=h).font = Font(bold=True)
    for i, r in enumerate(plan["tablo"], 5):
        ws.append([r["ay"] if not r.get("not") else f"{r['ay']} ({r['not']})", r["is_orani"], r["hakedis"], r["avans_mahsubu"],
                   r["teminat_kesintisi"], r["kdv"], r["net_odeme"], r["kumulatif_odeme"]])
    n = len(plan["tablo"])
    ws.cell(row=5 + n, column=1, value="TOPLAM ÖDENEN").font = Font(bold=True)
    ws.cell(row=5 + n, column=7, value=f"=SUM(G5:G{4 + n})").font = Font(bold=True)
    for col, w in zip("ABCDEFGH", (22, 16, 20, 16, 18, 14, 16, 18)):
        ws.column_dimensions[col].width = w
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
