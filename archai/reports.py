"""Rapor çıktıları: metraj + maliyet Excel'i, teknik şartname Word'ü."""

from datetime import date

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.shared import Pt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

HEAD = PatternFill("solid", fgColor="1F3A5F")
HFONT = Font(color="FFFFFF", bold=True)
MONEY = '#,##0.00 "₺"'


def _header(ws, cols, widths):
    ws.append(cols)
    for i, w in enumerate(widths, 1):
        c = ws.cell(row=ws.max_row, column=i)
        c.fill, c.font = HEAD, HFONT
        c.alignment = Alignment(vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(i)].width = w
    ws.freeze_panes = f"A{ws.max_row + 1}"


def write_xlsx(path, project_name, qres, cost):
    wb = Workbook()

    # Maliyet — formüllü: birim fiyat veya miktar Excel'de değişince toplamlar güncellenir
    ws = wb.active
    ws.title = "Maliyet"
    ws.append([f"{project_name} — Yaklaşık Maliyet", "", "", "", "", f"{date.today():%d.%m.%Y}"])
    ws["A1"].font = Font(bold=True, size=14)
    if cost.get("note"):
        ws.append([cost["note"]])
        ws["A2"].font = Font(italic=True, color="C00000")
    ws.append([])
    _header(ws, ["Poz", "Grup", "İmalat", "Birim", "Miktar", "Birim fiyat", "Tutar"], [10, 14, 52, 8, 12, 14, 16])
    first = ws.max_row + 1
    for r in cost["rows"]:
        if not r["enabled"]:
            continue
        ws.append([r["code"], r["group"], r["name"], r["unit"], r["quantity"], r["unit_price"], None])
        row = ws.max_row
        ws.cell(row=row, column=7, value=f"=E{row}*F{row}")
        for col in (6, 7):
            ws.cell(row=row, column=col).number_format = MONEY
    last = ws.max_row
    ws.append([])

    def total(label, formula, bold=False):
        ws.append(["", "", label, "", "", "", formula])
        c = ws.cell(row=ws.max_row, column=7)
        c.number_format = MONEY
        ws.cell(row=ws.max_row, column=3).font = Font(bold=bold)
        c.font = Font(bold=bold)
        return ws.max_row

    sub = total("Ara toplam", f"=SUM(G{first}:G{last})", True)
    ws.append(["", "", "Genel gider %", "", cost["overhead_pct"]])
    oh_pct = ws.max_row
    oh = total("Genel gider", f"=G{sub}*E{oh_pct}/100")
    ws.append(["", "", "Kâr %", "", cost["profit_pct"]])
    pr_pct = ws.max_row
    pr = total("Kâr", f"=(G{sub}+G{oh})*E{pr_pct}/100")
    bv = total("KDV hariç toplam", f"=G{sub}+G{oh}+G{pr}", True)
    ws.append(["", "", "KDV %", "", cost["vat_pct"]])
    vat_pct = ws.max_row
    vat = total("KDV", f"=G{bv}*E{vat_pct}/100")
    tot = total("GENEL TOPLAM", f"=G{bv}+G{vat}", True)
    ws.append(["", "", "Brüt inşaat alanı (m²)", "", cost["gross_floor_area"]])
    area = ws.max_row
    total("m² birim maliyet (KDV dahil)", f"=IF(E{area}>0,G{tot}/E{area},0)", True)
    if cost.get("approx"):
        a = cost["approx"]
        ws.append([])
        ws.append(["", "", f"Kontrol: yaklaşık birim maliyet yöntemi ({a['class']})", "", a["area"], a["unit_cost"],
                   f"=E{ws.max_row + 1}*F{ws.max_row + 1}"])
        ws.cell(row=ws.max_row, column=7).value = f"=E{ws.max_row}*F{ws.max_row}"
        for col in (6, 7):
            ws.cell(row=ws.max_row, column=col).number_format = MONEY

    # Metraj
    ws = wb.create_sheet("Metraj")
    _header(ws, ["Kat", "Eleman", "Tür", "Tag/rol", "Uzunluk (m)", "Kalınlık (m)", "Brüt alan (m²)",
                 "Boşluk (m²)", "Net alan (m²)", "Hacim (m³)", "Adet"], [10, 26, 10, 12, 12, 12, 14, 12, 14, 12, 8])
    for l in qres["lines"]:
        m = l["metrics"]
        ws.append([l["level"], l["element"], l["type"] if l["type"] != "opening" else l["kind"],
                   l["role"] or l["tag"], m.get("length", m.get("width")), m.get("thickness"),
                   m.get("gross_area", m.get("area")), m.get("opening_area"), m.get("net_area"), m.get("volume"),
                   m.get("count")])

    # Mahal listesi
    ws = wb.create_sheet("Mahaller")
    _header(ws, ["Kat", "Mahal", "Net alan (m²)", "Çevre (m)"], [12, 28, 14, 12])
    for r in qres["rooms"]:
        ws.append([r["level"], r["name"].split("/")[-1], r["area"], r["perimeter"]])
    ws.append(["", "TOPLAM", f"=SUM(C2:C{ws.max_row})", ""])
    ws.cell(row=ws.max_row, column=2).font = Font(bold=True)
    wb.save(path)
    return path


def write_docx(path, spec, cost=None):
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(10.5)
    h = doc.add_heading(spec["title"], 0)
    h.alignment = WD_ALIGN_PARAGRAPH.CENTER
    doc.add_paragraph(f"Tarih: {date.today():%d.%m.%Y}")

    doc.add_heading("1. Genel hükümler", 1)
    for g in spec["general"]:
        doc.add_paragraph(g, style="List Number")

    doc.add_heading("2. Proje bilgileri", 1)
    t = doc.add_table(rows=0, cols=2)
    t.style = "Light Grid Accent 1"
    for k, v in spec["summary"]:
        row = t.add_row().cells
        row[0].text, row[1].text = k, v
    if spec["rooms"]:
        doc.add_heading("Mahal listesi", 2)
        t = doc.add_table(rows=1, cols=3)
        t.style = "Light Grid Accent 1"
        t.rows[0].cells[0].text, t.rows[0].cells[1].text, t.rows[0].cells[2].text = "Kat", "Mahal", "Net alan (m²)"
        for r in spec["rooms"]:
            c = t.add_row().cells
            c[0].text, c[1].text, c[2].text = r["level"], r["name"].split("/")[-1], f'{r["area"]:.2f}'

    doc.add_heading("3. İmalat kalemleri", 1)
    for i, it in enumerate(spec["items"], 1):
        doc.add_heading(f"3.{i}  {it['code']} — {it['name']}", 2)
        doc.add_paragraph(f"Ön metraj: {it['quantity']:,.2f} {it['unit']}".replace(",", "X").replace(".", ",").replace("X", "."))
        for label, key in (("Malzeme", "malzeme"), ("Uygulama", "uygulama"), ("Ölçü ve ödeme", "olcum")):
            p = doc.add_paragraph()
            p.add_run(f"{label}: ").bold = True
            p.add_run(it[key])

    if cost:
        doc.add_heading("Ek: Yaklaşık maliyet özeti", 1)
        t = doc.add_table(rows=0, cols=2)
        t.style = "Light Grid Accent 1"
        fmt = lambda v: f"{v:,.2f} ₺".replace(",", "X").replace(".", ",").replace("X", ".")
        for k, v in [("Ara toplam", cost["subtotal"]), (f"Genel gider (%{cost['overhead_pct']})", cost["overhead"]),
                     (f"Kâr (%{cost['profit_pct']})", cost["profit"]), (f"KDV (%{cost['vat_pct']})", cost["vat"]),
                     ("Genel toplam", cost["total"])] + ([("m² birim maliyet", cost["per_m2"])] if cost["per_m2"] else []):
            c = t.add_row().cells
            c[0].text, c[1].text = k, fmt(v)
        if cost.get("note"):
            doc.add_paragraph(cost["note"]).runs[0].italic = True
    doc.save(path)
    return path


def _tl(v):
    return f"{v:,.2f} ₺".replace(",", "X").replace(".", ",").replace("X", ".")


def write_offer_docx(path, project, report, qres, cost, company=None, customer=None, offer_no=None):
    """Müşteriye gidecek teklif mektubu."""
    company = company or {"name": "[Firma Adı]", "address": "[Adres]", "phone": "[Telefon]", "email": "[E-posta]"}
    customer = customer or {"name": "[Müşteri Adı]"}
    s = qres["summary"]
    gfa = s["gross_floor_area"]
    months = round(6 + gfa / 250)  # kaba süre tahmini
    doc = Document()
    st = doc.styles["Normal"]
    st.font.name, st.font.size = "Calibri", Pt(10.5)
    p = doc.add_paragraph()
    p.add_run(company["name"]).bold = True
    doc.add_paragraph(f'{company.get("address", "")}  ·  {company.get("phone", "")}  ·  {company.get("email", "")}')
    doc.add_paragraph(f"Tarih: {date.today():%d.%m.%Y}      Teklif No: {offer_no or date.today():%Y%m%d}".replace(
        f"{date.today():%Y%m%d}", offer_no or f"{date.today():%Y%m%d}-01"))
    doc.add_heading(f"{project} — Yapım Teklifi", 0)
    doc.add_paragraph(f"Sayın {customer['name']},")
    doc.add_paragraph("Aşağıda bilgileri verilen yapının anahtar teslim yapımı için fiyat teklifimizi bilgilerinize sunarız. "
                      "Teklif, ekteki şematik ön tasarım ve ön metraja dayanmaktadır.")

    doc.add_heading("1. Proje özeti", 1)
    t = doc.add_table(rows=0, cols=2)
    t.style = "Light Grid Accent 1"
    rows = [("Toplam inşaat alanı (brüt)", f"{gfa:.2f} m²"), ("Net kullanım alanı", f"{s['net_room_area']:.2f} m²"),
            ("Kat sayısı", str(report.get("floors", ""))),
            ("Daire", f"{report.get('unit_count', '')} adet {report.get('unit_type', '')}")]
    if report.get("parcel_area"):
        rows.insert(0, ("Parsel alanı", f"{report['parcel_area']:.2f} m²"))
    for k, v in rows:
        c = t.add_row().cells
        c[0].text, c[1].text = k, v

    doc.add_heading("2. Kapsam ve bedel", 1)
    t = doc.add_table(rows=1, cols=2)
    t.style = "Light Grid Accent 1"
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "İş grubu", "Tutar (KDV hariç, kâr/genel gider dahil)"
    k = (cost["total_before_vat"] / cost["subtotal"]) if cost["subtotal"] else 1
    for g, amt in cost["groups"].items():
        if amt:
            c = t.add_row().cells
            c[0].text, c[1].text = g, _tl(amt * k)
    for label, val in [("KDV hariç toplam", cost["total_before_vat"]), (f"KDV (%{cost['vat_pct']})", cost["vat"]),
                       ("GENEL TOPLAM", cost["total"])]:
        c = t.add_row().cells
        c[0].text, c[1].text = label, _tl(val)
        if label == "GENEL TOPLAM":
            for cell in c:
                cell.paragraphs[0].runs[0].bold = True
    if cost.get("per_m2"):
        doc.add_paragraph(f"Brüt m² birim fiyatı (KDV dahil): {_tl(cost['per_m2'])}")

    doc.add_heading("3. Ödeme planı", 1)
    for x in ["%20 sözleşme imzasında avans", "%30 kaba inşaat tamamlandığında", "%30 ince inşaat tamamlandığında",
              "%20 geçici kabulde"]:
        doc.add_paragraph(x, style="List Bullet")
    doc.add_heading("4. Süre", 1)
    doc.add_paragraph(f"Tahmini yapım süresi, ruhsat alımından itibaren yaklaşık {months} aydır.")
    doc.add_heading("5. Teklife dahil olmayanlar", 1)
    for x in ["Ruhsat, iskân ve belediye harçları; zemin etüdü", "Proje müellifliği ve kontrollük hizmetleri",
              "Altyapı bağlantı bedelleri (elektrik, su, doğalgaz abonelikleri)", "Mobilya, beyaz eşya ve dekorasyon",
              "İmar durumu veya zemin koşullarından doğacak ek imalatlar"]:
        doc.add_paragraph(x, style="List Bullet")
    doc.add_heading("6. Geçerlilik ve notlar", 1)
    doc.add_paragraph("Bu teklif düzenlenme tarihinden itibaren 30 gün geçerlidir.")
    doc.add_paragraph("Miktarlar şematik ön tasarımdan hesaplanmıştır; kesin fiyat, onaylı uygulama projeleri üzerinden "
                      "yapılacak kesin metraj ile belirlenecektir.")
    if cost.get("note"):
        doc.add_paragraph(cost["note"]).runs[0].italic = True
    doc.add_paragraph("\nSaygılarımızla,")
    doc.add_paragraph(company["name"]).runs[0].bold = True
    doc.save(path)
    return path
