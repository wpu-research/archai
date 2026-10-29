"""Kat irtifakı / kat mülkiyeti ön tablosu: bağımsız bölümler, net/brüt alan, ortak alan payı ve arsa payı.

Kaynak: projenin eleman listesi. Bağımsız bölüm = "Daire N" etiketli mahaller (konut) ve "İşyeri N" mahali (dükkân).
Brüt alan: katın dış kontur (döşeme) alanı, kattaki bağımsız bölümlere net alanlarıyla orantılı dağıtılır (kat içi ortak alan:
hol, merdiven, asansör ve duvar kalınlıkları dahil). Bağımsız bölümü olmayan katların alanı (sığınak, otopark, teknik) "ortak alan
payı" olarak tüm bölümlere brüt alanları oranında eklenir. Arsa payı = toplam brüt oranı, `payda` üzerinden en büyük kalan yöntemiyle
tamsayıya yuvarlanır. AVAN: kat mülkiyetine esas resmî ölçü ve arsa payları, yetkili mimar / harita mühendisinin hazırlayacağı kat
mülkiyeti (irtifakı) projesiyle belirlenir.
"""
import math
from pathlib import Path

from .notice import AVAN_NOTE
from .quantities import polygon_area

PAYDA = 1000
SPECIAL = ("Sığınak", "Teknik", "Otopark")          # bağımsız bölüm dışı ortak alanlar (aynı katta işyeri olsa bile ayrılır)
NOT = ("Ön tablo (avan): net alanlar mahal iç yüzlerinden, brüt alanlar kat konturundan hesaplandı; arsa payları brüt alana "
       "oranlı ve yaklaşıktır. Kat mülkiyeti / irtifakı için resmî ölçü ve arsa payı yetkili mimar veya harita mühendisi "
       "tarafından hazırlanan projeyle belirlenir; değer katsayısı (cephe, manzara, kat) uygulanmamıştır.")


def _tag(name):
    parts = name.split("/")
    return parts[1] if len(parts) > 1 else name


def compute(elements, parcel_area=None, payda=PAYDA):
    floors = {e["level"]: e for e in elements if e["type"] == "slab" and e.get("role") == "floor"}
    order = sorted(floors, key=lambda l: floors[l]["z"])
    gross = {l: polygon_area([tuple(p[:2]) for p in floors[l]["points"]]) for l in order}
    units = {}
    room_area, special = {}, {}                       # kat → tüm mahal alanı / bağımsız bölüm dışı özel ortak alanlar
    for e in elements:
        if e["type"] == "room":
            a = polygon_area([tuple(p[:2]) for p in e["points"]])
            room_area[e["level"]] = room_area.get(e["level"], 0.0) + a
            if _tag(e["name"]).startswith(SPECIAL):
                special[e["level"]] = special.get(e["level"], 0.0) + a
        if e["type"] != "room" or e.get("role") == "common":
            continue
        tag = _tag(e["name"])
        if not (tag.startswith("Daire ") or tag.startswith("İşyeri ")):
            continue
        u = units.setdefault((e["level"], tag), {"net": 0.0, "yatak": 0})
        u["net"] += polygon_area([tuple(p[:2]) for p in e["points"]])
        short = e["name"].split("/")[-1]
        if short.startswith("Yatak") or short.startswith("Ebeveyn Yatak"):
            u["yatak"] += 1
    rows = []
    net_by_level = {}
    for (lvl, tag), u in units.items():
        net_by_level[lvl] = net_by_level.get(lvl, 0.0) + u["net"]
    spec_gross = {l: gross[l] * special.get(l, 0.0) / room_area[l] for l in order if room_area.get(l)}   # kat brütünden pay
    for lvl in order:
        unit_gross = gross[lvl] - (spec_gross.get(lvl, 0.0) if lvl in net_by_level else 0.0)
        for (l, tag), u in sorted(units.items(), key=lambda kv: kv[0][1]):
            if l != lvl:
                continue
            brut = unit_gross * u["net"] / net_by_level[lvl]
            konut = tag.startswith("Daire ")
            rows.append({"kat": lvl, "ad": tag, "tur": "Konut" if konut else "İşyeri",
                         "tip": f"{max(1, u['yatak'])}+1" if konut else "Dükkân", "net": round(u["net"], 2),
                         "kat_brut": brut})
    unit_levels = set(net_by_level)
    ortak_alanlar, ortak_toplam = [], 0.0
    for l in order:
        a = gross[l] if l not in unit_levels else spec_gross.get(l, 0.0)
        if a > 0.005:
            ortak_alanlar.append({"kat": l, "alan": round(a, 2), "aciklama": "bağımsız bölüm dışı ortak alan (sığınak, otopark, teknik)"})
            ortak_toplam += a
    sum_brut = sum(r["kat_brut"] for r in rows) or 1.0
    for i, r in enumerate(rows, 1):
        r["no"] = i
        r["ortak_pay"] = ortak_toplam * r["kat_brut"] / sum_brut
        r["toplam_brut"] = r["kat_brut"] + r["ortak_pay"]
    tot = sum(r["toplam_brut"] for r in rows) or 1.0
    raw = [payda * r["toplam_brut"] / tot for r in rows]
    ap = [math.floor(v) for v in raw]
    for i in sorted(range(len(rows)), key=lambda i: raw[i] - ap[i], reverse=True)[:payda - sum(ap)]:
        ap[i] += 1                                                       # en büyük kalan yöntemi: toplam tam payda
    for r, a in zip(rows, ap):
        r["arsa_payi"], r["arsa_payi_metin"] = a, f"{a}/{payda}"
        for k in ("net", "kat_brut", "ortak_pay", "toplam_brut"):
            r[k] = round(r[k], 2)
    warn = []
    if not rows:
        warn.append("projede bağımsız bölüm (Daire / İşyeri) bulunamadı")
    return {"payda": payda, "bolumler": rows, "ortak_alanlar": ortak_alanlar,
            "ozet": {"bolum_sayisi": len(rows), "konut": sum(r["tur"] == "Konut" for r in rows),
                     "isyeri": sum(r["tur"] == "İşyeri" for r in rows),
                     "net_toplam": round(sum(r["net"] for r in rows), 2),
                     "brut_toplam": round(sum(r["toplam_brut"] for r in rows), 2),
                     "ortak_alan_toplam": round(ortak_toplam, 2), "parsel_alani": parcel_area},
            "uyarilar": warn, "not": NOT}


def write_xlsx(path, project_name, result):
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    ws = wb.active
    ws.title = "Bağımsız Bölümler"
    ws["A1"] = f"KAT İRTİFAKI / KAT MÜLKİYETİ ÖN TABLOSU — {project_name}"
    ws["A1"].font = Font(bold=True, size=12)
    ws["A2"] = AVAN_NOTE
    ws["A3"] = result["not"]
    for c in ("A2", "A3"):
        ws[c].alignment = Alignment(wrap_text=True, vertical="top")
        ws[c].font = Font(size=8, italic=True)
        ws.merge_cells(f"{c}:I{c[1:]}")
    ws.row_dimensions[2].height = 36
    ws.row_dimensions[3].height = 36
    head = ["No", "Kat", "Tür", "Bölüm", "Tip", "Net m²", "Brüt m² (kat içi)", "Ortak alan payı m²", "Toplam brüt m²",
            f"Arsa payı (/ {result['payda']})"]
    for j, h in enumerate(head, 1):
        c = ws.cell(row=5, column=j, value=h)
        c.font = Font(bold=True)
        c.fill = PatternFill("solid", fgColor="DDE8F0")
        c.alignment = Alignment(wrap_text=True, horizontal="center")
    for i, r in enumerate(result["bolumler"], 6):
        vals = [r["no"], r["kat"], r["tur"], r["ad"], r["tip"], r["net"], r["kat_brut"], r["ortak_pay"], r["toplam_brut"],
                r["arsa_payi"]]
        for j, v in enumerate(vals, 1):
            ws.cell(row=i, column=j, value=v)
    n = len(result["bolumler"])
    t = 6 + n
    ws.cell(row=t, column=4, value="TOPLAM").font = Font(bold=True)
    for j in (6, 7, 8, 9, 10):
        col = ws.cell(row=5, column=j).column_letter
        c = ws.cell(row=t, column=j, value=f"=SUM({col}6:{col}{t - 1})")
        c.font = Font(bold=True)
    for col, w in zip("ABCDEFGHIJ", (5, 16, 9, 12, 9, 10, 14, 16, 14, 16)):
        ws.column_dimensions[col].width = w
    ws2 = wb.create_sheet("Ortak Alanlar")
    ws2.append(["Kat", "Alan m²", "Açıklama"])
    for r in result["ortak_alanlar"]:
        ws2.append([r["kat"], r["alan"], r["aciklama"]])
    ws2.append([])
    ws2.append(["Parsel alanı m²", result["ozet"].get("parsel_alani")])
    for col, w in zip("ABC", (22, 12, 60)):
        ws2.column_dimensions[col].width = w
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    wb.save(path)
    return path
