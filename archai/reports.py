"""Resmî belgeler: teklif mektubu + birim fiyat teklif cetveli, teknik şartname (docx),
metraj/maliyet cetveli (xlsx).

`info` sözlüğü (hepsi opsiyonel; boşsa köşeli parantezli yer tutucu basılır):
  company  {name, address, phone, email, web, tax_office, tax_no, signatory, title, city}
  customer {name, address}
  site     {il, ilce, mahalle, pafta, ada, parsel, road}
  owner, architect, drawn_by, checked_by, approved_by, doc_no, rev, date
"""

from datetime import date

from docx import Document
from docx.enum.section import WD_ORIENT
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from .notice import AVAN_NOTE, AVAN_SHORT, IMAR_NOTE

FONT = "Arial"
MONEY_XL = '#,##0.00'


# ================================================================== biçim yardımcıları

def tl(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def num(v, d=2):
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


_ONES = ["", "bir", "iki", "üç", "dört", "beş", "altı", "yedi", "sekiz", "dokuz"]
_TENS = ["", "on", "yirmi", "otuz", "kırk", "elli", "altmış", "yetmiş", "seksen", "doksan"]


def _words999(n):
    h, r = divmod(n, 100)
    t, o = divmod(r, 10)
    out = []
    if h:
        out.append(("" if h == 1 else _ONES[h] + " ") + "yüz")
    if t:
        out.append(_TENS[t])
    if o:
        out.append(_ONES[o])
    return " ".join(out)


def words_tr(n):
    """Tam sayıyı Türkçe yazıyla ('bin' önünde 'bir' söylenmez)."""
    if n == 0:
        return "sıfır"
    parts = []
    for i, name in enumerate(["", "bin", "milyon", "milyar", "trilyon"]):
        n, g = divmod(n, 1000)
        if g:
            parts.append("bin" if (i == 1 and g == 1) else (_words999(g) + (f" {name}" if name else "")))
        if not n:
            break
    return " ".join(reversed(parts))


def amount_in_words(v):
    lira = int(v)
    kurus = int(round((v - lira) * 100))
    if kurus == 100:
        lira, kurus = lira + 1, 0
    s = f"Yalnız {words_tr(lira)} Türk Lirası" + (f" {words_tr(kurus)} Kuruş" if kurus else "")
    return s + "."


def _ph(v, placeholder):
    return v if v else placeholder


# ================================================================== docx yardımcıları

def _doc():
    d = Document()
    st = d.styles["Normal"]
    st.font.name, st.font.size = FONT, Pt(10)
    st.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
    st.paragraph_format.space_after = Pt(3)
    for name, size in (("Heading 1", 11.5), ("Heading 2", 10)):
        s = d.styles[name]
        s.font.name, s.font.size, s.font.bold = FONT, Pt(size), True
        s.font.color.rgb = RGBColor(0, 0, 0)
        s.element.rPr.rFonts.set(qn("w:eastAsia"), FONT)
        s.paragraph_format.space_before, s.paragraph_format.space_after = Pt(10), Pt(4)
    sec = d.sections[0]
    sec.page_height, sec.page_width = Cm(29.7), Cm(21.0)
    sec.left_margin = sec.right_margin = Cm(2.2)
    sec.top_margin, sec.bottom_margin = Cm(2.0), Cm(1.8)
    return d


def _field(run, instr):
    for kind in ("begin", "instr", "end"):
        if kind == "instr":
            el = OxmlElement("w:instrText")
            el.set(qn("xml:space"), "preserve")
            el.text = instr
        else:
            el = OxmlElement("w:fldChar")
            el.set(qn("w:fldCharType"), kind)
        run._r.append(el)


def _bottom_border(p, sz=6):
    pPr = p._p.get_or_add_pPr()
    b = OxmlElement("w:pBdr")
    e = OxmlElement("w:bottom")
    for k, v in (("w:val", "single"), ("w:sz", str(sz)), ("w:space", "1"), ("w:color", "000000")):
        e.set(qn(k), v)
    b.append(e)
    pPr.append(b)


def _header_footer(section, left, right):
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    hp = section.header.paragraphs[0]
    hp.text = ""
    tab = section.page_width - section.left_margin - section.right_margin
    hp.paragraph_format.tab_stops.add_tab_stop(tab, alignment=2)  # sağa hizalı
    r = hp.add_run(left)
    r.font.size, r.bold = Pt(8), True
    hp.add_run("\t" + right).font.size = Pt(8)
    _bottom_border(hp)
    fp = section.footer.paragraphs[0]
    fp.text = ""
    fp.alignment = WD_ALIGN_PARAGRAPH.CENTER
    nr = fp.add_run(AVAN_SHORT + " — statik, tesisat ve ruhsat projesi yetkili mimar/mühendis imzası gerektirir\n")
    nr.font.size, nr.italic = Pt(7), True
    for txt, instr in (("Sayfa ", None), ("", "PAGE"), (" / ", None), ("", "NUMPAGES")):
        run = fp.add_run(txt)
        run.font.size = Pt(8)
        if instr:
            _field(run, instr)


def _shade(cell, hexcolor="E7E7E7"):
    tcPr = cell._tc.get_or_add_tcPr()
    sh = OxmlElement("w:shd")
    sh.set(qn("w:val"), "clear")
    sh.set(qn("w:color"), "auto")
    sh.set(qn("w:fill"), hexcolor)
    tcPr.append(sh)


def _table(d, rows, widths_cm, header=True, align=None, bold_rows=(), size=9):
    t = d.add_table(rows=0, cols=len(widths_cm))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    t.autofit = False
    for j, w in enumerate(widths_cm):  # tblGrid: LibreOffice/Word sütun genişliğini buradan alır
        t.columns[j].width = Cm(w)
    for i, row in enumerate(rows):
        cells = t.add_row().cells
        for j, val in enumerate(row):
            c = cells[j]
            c.width = Cm(widths_cm[j])
            p = c.paragraphs[0]
            p.paragraph_format.space_after = Pt(0)
            run = p.add_run("" if val is None else str(val))
            run.font.size = Pt(size)
            if (header and i == 0) or i in bold_rows:
                run.bold = True
            if header and i == 0:
                _shade(c)
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
            elif align and align[j] == "r":
                p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            elif align and align[j] == "c":
                p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return t


def _kv_table(d, rows, w=(6.0, 10.6)):
    t = _table(d, rows, w, header=False)
    for r in t.rows:
        r.cells[0].paragraphs[0].runs[0].bold = True
        _shade(r.cells[0], "F2F2F2")
    return t


def _para(d, text, bold=False, size=None, align=None, space_after=None, italic=False):
    p = d.add_paragraph()
    r = p.add_run(text)
    r.bold, r.italic = bold, italic
    if size:
        r.font.size = Pt(size)
    p.alignment = {"r": WD_ALIGN_PARAGRAPH.RIGHT, "c": WD_ALIGN_PARAGRAPH.CENTER,
                   "j": WD_ALIGN_PARAGRAPH.JUSTIFY}.get(align, p.alignment)
    if space_after is not None:
        p.paragraph_format.space_after = Pt(space_after)
    return p


def _numbered(d, num_label, text, bold_head=None, indent=0.9):
    p = d.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
    p.paragraph_format.left_indent, p.paragraph_format.first_line_indent = Cm(indent), Cm(-indent)
    p.add_run(f"{num_label}\t").bold = True
    if bold_head:
        p.add_run(f"{bold_head}: ").bold = True
    p.add_run(text)
    return p


def _letterhead(d, co):
    p = d.add_paragraph()
    r = p.add_run(_ph(co.get("name"), "[FİRMA UNVANI]").upper())
    r.bold, r.font.size = True, Pt(14)
    p.paragraph_format.space_after = Pt(0)
    lines = [co.get("address") or "[Adres]",
             " · ".join(filter(None, [f"Tel: {co.get('phone') or '[Telefon]'}", co.get("email") or "[E-posta]", co.get("web")])),
             f"Vergi Dairesi: {co.get('tax_office') or '[—]'} · Vergi No: {co.get('tax_no') or '[—]'}"]
    for i, ln in enumerate(lines):
        q = _para(d, ln, size=8.5, space_after=0)
        if i == len(lines) - 1:
            _bottom_border(q, 12)
    d.add_paragraph()


def _signature(d, co, label="YÜKLENİCİ"):
    t = d.add_table(rows=1, cols=2)
    c = t.rows[0].cells[1]
    lines = [(label, True), (_ph(co.get("name"), "[Firma Unvanı]"), True),
             (_ph(co.get("signatory"), "[Yetkili Adı Soyadı]"), False), (_ph(co.get("title"), "[Unvanı]"), False),
             ("", False), ("", False), ("İmza / Kaşe", False)]
    for i, (txt, b) in enumerate(lines):
        p = c.paragraphs[0] if i == 0 else c.add_paragraph()
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        p.paragraph_format.space_after = Pt(0)
        r = p.add_run(txt)
        r.bold, r.font.size = b, Pt(9.5 if b else 9)


# ================================================================== teklif

DRAFT = " [taslak — firma tarafından düzenlenmeli]"
DEFAULT_PAYMENT = [{"pct": 20, "desc": "sözleşme imzasında avans olarak"}, {"pct": 30, "desc": "kaba inşaat tamamlandığında"},
                   {"pct": 30, "desc": "ince inşaat tamamlandığında"}, {"pct": 20, "desc": "geçici kabulde"}]


def _pct(v):
    return f"{v:g}".replace(".", ",")


_POSS = {"bir": "i", "iki": "si", "üç": "ü", "dört": "ü", "beş": "i", "altı": "sı", "yedi": "si", "sekiz": "i",
         "dokuz": "u", "on": "u", "yirmi": "si", "otuz": "u", "kırk": "ı", "elli": "si", "altmış": "ı", "yetmiş": "i",
         "seksen": "i", "doksan": "ı", "yüz": "ü", "bin": "i", "sıfır": "ı"}


def pct_poss(v):
    """%20'si, %30'u, %25'i … (yüzde değerinin iyelik eki, okunuşun son kelimesine göre)."""
    last = words_tr(int(round(v)) if abs(v - round(v)) < 1e-9 else int(str(v).split(".")[-1])).split()[-1]
    return f"%{_pct(v)}'{_POSS.get(last, 'i')}"


def _has(cost, *codes):
    return any(r["enabled"] and r["quantity"] and r["code"] in codes for r in cost["rows"])


def offer_terms(info, gfa, cost, city):
    """Teklif şartları. Firma değerleri info["offer"] sözlüğünden okunur:
      months, payment [{pct, desc}], court, validity_days, price_diff_pct.
    Verilmeyen maddede varsayılan kullanılır ve metne DRAFT işareti düşer."""
    of = info.get("offer") or {}
    mark = lambda key: "" if of.get(key) not in (None, "", []) else DRAFT

    months = int(of.get("months") or round(6 + gfa / 250))
    pay = of.get("payment") or DEFAULT_PAYMENT
    parts = []
    for p in pay:
        pct, desc = (p.get("pct"), p.get("desc", "")) if isinstance(p, dict) else (p[0], p[1] if len(p) > 1 else "")
        parts.append(f"{pct_poss(float(pct))} {desc}".strip())
    tot = sum(float(p.get("pct") if isinstance(p, dict) else p[0]) for p in pay)
    pay_txt = ("Bedelin " + "; ".join(parts) + " ödenir. Avans, hakedişlerden oransal olarak mahsup edilir."
               + ("" if abs(tot - 100) < 1e-6 else f" [ödeme oranları toplamı %{_pct(tot)} — kontrol edin]") + mark("payment"))
    validity = int(of.get("validity_days") or 30)
    diff = float(of.get("price_diff_pct") or 10)
    court = of.get("court") or f"{city} Mahkemeleri ve İcra Daireleri"

    structural = _has(cost, "KOL-01", "DUV-03") and _has(cost, "TEM-01", "TEM-02")
    if structural:
        scope = ("Teklif, Ek-1 cetvelinde yer alan imalatların malzeme, işçilik, nakliye, iskele ve yardımcı malzemeler "
                 "dahil anahtar teslim yapımını kapsar. Temel, kazı, taşıyıcı sistem, merdiven ve asansör kalemleri "
                 "(cetvelde 'AVAN yaklaşık' işaretli) şematik tasarımdan oran yöntemiyle hesaplanmıştır; miktarları kesin "
                 "statik ve temel projesine göre kesinleşir.")
    else:
        scope = ("Teklif yalnız Ek-1 cetvelinde yer alan imalatların malzeme, işçilik, nakliye, iskele ve yardımcı "
                 "malzemeler dahil yapımını kapsar; cetvelde yer almayan imalatlar (taşıyıcı sistem, temel vb.) teklif "
                 "kapsamı dışındadır ve anahtar teslim değildir.")
    return [
        ("Kapsam", scope),
        ("Ödeme", pay_txt),
        ("Süre", f"İşin süresi, yapı ruhsatının alınması ve yer tesliminden itibaren {months} ({words_tr(months)}) aydır. "
                 "Mücbir sebepler ve yapı sahibinden kaynaklanan gecikmeler süreye eklenir." + mark("months")),
        ("Geçerlilik", f"Teklif, düzenlenme tarihinden itibaren {validity} ({words_tr(validity)}) gün geçerlidir."
                       + mark("validity_days")),
        ("Fiyat farkı", "Birim fiyatlar teklif tarihindeki piyasa fiyatlarına göredir. Sözleşme süresince ana "
                        f"malzeme fiyatlarında {pct_poss(diff)} aşan değişimler, taraflarca belgelenerek fiyat farkı olarak "
                        "değerlendirilir." + mark("price_diff_pct")),
        ("Miktarlar", "Miktarlar şematik ön tasarım üzerinden hesaplanmış ön metrajdır. Kesin bedel, onaylı uygulama "
                      "projeleri üzerinden yapılacak kesin metraj ile teklif birim fiyatları çarpılarak belirlenir."),
        ("Hariç tutulanlar", "Ruhsat, iskân ve belediye harçları; zemin etüdü; proje müellifliği ve yapı denetim hizmet "
                             "bedelleri; altyapı abonelik ve bağlantı bedelleri; mobilya, beyaz eşya ve dekorasyon; imar "
                             "durumu veya zemin koşullarından doğabilecek ek imalatlar; kesin statik/temel projesine göre "
                             "kesinleşen imalatlardaki miktar farkları."),
        ("Uyuşmazlık", f"Doğabilecek uyuşmazlıklarda {court} yetkilidir." + mark("court")),
    ]


def write_offer_docx(path, project, report, qres, cost, company=None, customer=None, offer_no=None, info=None):
    info = info or {}
    co = {**(info.get("company") or {}), **(company or {})}
    cu = {**(info.get("customer") or {}), **(customer or {})}
    site = info.get("site") or {}
    today = info.get("date") or f"{date.today():%d.%m.%Y}"
    no = offer_no or info.get("doc_no") or f"TKL-{date.today():%Y%m%d}-01"
    s = qres["summary"]
    gfa = s["gross_floor_area"]

    d = _doc()
    _header_footer(d.sections[0], _ph(co.get("name"), "[Firma Unvanı]"), f"Teklif No: {no}")
    _letterhead(d, co)
    t = d.add_table(rows=1, cols=2)
    l, r = t.rows[0].cells
    l.paragraphs[0].add_run(f"Sayı : {no}").font.size = Pt(9.5)
    l.add_paragraph().add_run(f"Konu : {project} Yapım İşi Fiyat Teklifi").font.size = Pt(9.5)
    rp = r.paragraphs[0]
    rp.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    rp.add_run(today).font.size = Pt(9.5)
    d.add_paragraph()
    _para(d, f"Sayın {_ph(cu.get('name'), '[Müşteri / Yapı Sahibi]')}", bold=True, space_after=0)
    _para(d, _ph(cu.get("address"), "[Adres]"), space_after=10)
    yer = " / ".join(filter(None, [site.get("il"), site.get("ilce"), site.get("mahalle")]))
    ap = f"{site['ada']} ada {site['parsel']} parsel" if site.get("ada") and site.get("parsel") else "[ada / parsel]"
    _para(d, (f"{yer or '[İl / İlçe]'}, {ap} üzerinde yapılması planlanan {project} yapım işine ait fiyat teklifimiz; "
              "ekte sunulan birim fiyat teklif cetveli, ön tasarım paftaları ve teknik şartname esas alınarak "
              "aşağıda bilgilerinize sunulmuştur."), align="j", space_after=8)

    d.add_heading("1. YAPI BİLGİLERİ", 1)
    rows = [("Yapı yeri", yer or "—"), ("Ada / Parsel", ap)]
    if report.get("parcel_area") and not report.get("virtual_parcel"):   # hızlı modun sanal parseli basılmaz
        rows.append(("Parsel alanı", f"{num(report['parcel_area'])} m²"))
    rows += [("Toplam inşaat alanı (brüt)", f"{num(gfa)} m²"), ("Net kullanım alanı", f"{num(s['net_room_area'])} m²")]
    if report.get("floors"):
        rows.append(("Kat adedi", f"{report['floors']} (Z+{report['floors'] - 1})" if report["floors"] > 1 else "1 (Z)"))
    if report.get("unit_count"):
        rows.append(("Bağımsız bölüm", f"{report['unit_count']} adet {report.get('unit_type', '')} konut"))
    _kv_table(d, rows)

    d.add_heading("2. TEKLİF BEDELİ", 1)
    rows = [("İŞ GRUBU", "TUTAR (TL)")]
    k = (cost["total_before_vat"] / cost["subtotal"]) if cost["subtotal"] else 1
    rows += [(g, tl(a * k)) for g, a in cost["groups"].items() if a]
    rows += [("TOPLAM (KDV HARİÇ)", tl(cost["total_before_vat"])), (f"KDV (%{cost['vat_pct']:g})", tl(cost["vat"])),
             ("GENEL TOPLAM (KDV DAHİL)", tl(cost["total"]))]
    _table(d, rows, (11.0, 5.6), align=("l", "r"), bold_rows=(len(rows) - 3, len(rows) - 1))
    _para(d, "", space_after=0)
    _para(d, amount_in_words(cost["total"]), bold=True, space_after=2)
    if cost.get("per_m2"):
        _para(d, f"Brüt inşaat alanı birim fiyatı (KDV dahil): {tl(cost['per_m2'])} TL/m²", size=9)
    _para(d, "İş gruplarına genel giderler ve yüklenici kârı dahildir. Kalem bazında dağılım Ek-1'dedir.", size=8.5, italic=True)

    d.add_heading("3. TEKLİF ŞARTLARI", 1)
    city = co.get("city") or site.get("il") or "[İl]"
    terms = [("Proje seviyesi", AVAN_NOTE), ("İmar değerleri", IMAR_NOTE), *offer_terms(info, gfa, cost, city)]
    for i, (h, txt) in enumerate(terms, 1):
        _numbered(d, f"3.{i}", txt, h)
    _para(d, "", space_after=0)
    _para(d, "Gereğini bilgilerinize arz ederiz.", space_after=8)
    _signature(d, co)
    _para(d, "", space_after=0)
    _para(d, "EKLER", bold=True, size=9, space_after=0)
    for e in ["Ek-1  Birim Fiyat Teklif Cetveli", "Ek-2  Ön Tasarım Paftaları (A-00 … A-04)", "Ek-3  Teknik Şartname",
              "Ek-4  Metraj Cetveli"]:
        _para(d, e, size=9, space_after=0)

    # ---- Ek-1: yatay sayfada birim fiyat teklif cetveli
    sec = d.add_section()
    sec.orientation = WD_ORIENT.LANDSCAPE
    sec.page_width, sec.page_height = Cm(29.7), Cm(21.0)
    sec.left_margin = sec.right_margin = Cm(1.8)
    _header_footer(sec, _ph(co.get("name"), "[Firma Unvanı]"), f"Teklif No: {no} · Ek-1")
    d.add_heading("EK-1  BİRİM FİYAT TEKLİF CETVELİ", 1)
    _para(d, f"İşin adı: {project}    ·    Teklif No: {no}    ·    Tarih: {today}", size=9, space_after=6)
    rows = [("Sıra No", "Poz No", "İş Kaleminin Adı ve Kısa Açıklaması", "Birimi", "Miktarı", "Birim Fiyat (TL)", "Tutarı (TL)")]
    bold, i, cur = [], 0, None
    for r in [r for r in cost["rows"] if r["enabled"] and r["quantity"]]:
        if r["group"] != cur:
            cur = r["group"]
            rows.append(("", "", cur.upper(), "", "", "", ""))
            bold.append(len(rows) - 1)
        i += 1
        rows.append((str(i), r["code"] + (" *" if r.get("approx") else ""), r["name"], r["unit"], num(r["quantity"]),
                     tl(r["unit_price"]), tl(r["amount"])))
    for lab, v, b in [("TOPLAM", cost["subtotal"], True), (f"Genel giderler (%{cost['overhead_pct']:g})", cost["overhead"], False),
                      (f"Yüklenici kârı (%{cost['profit_pct']:g})", cost["profit"], False),
                      ("TOPLAM (KDV HARİÇ)", cost["total_before_vat"], True), (f"KDV (%{cost['vat_pct']:g})", cost["vat"], False),
                      ("GENEL TOPLAM (KDV DAHİL)", cost["total"], True)]:
        rows.append(("", "", lab, "", "", "", tl(v)))
        if b:
            bold.append(len(rows) - 1)
    _table(d, rows, (1.3, 1.9, 10.8, 1.5, 2.4, 3.0, 3.4), align=("c", "c", "l", "c", "r", "r", "r"), bold_rows=bold, size=8.5)
    _para(d, "", space_after=0)
    _para(d, amount_in_words(cost["total"]), bold=True, size=9)
    if any(r.get("approx") and r["enabled"] and r["quantity"] for r in cost["rows"]):
        _para(d, "* AVAN yaklaşık kalem: miktar şematik tasarımdan oran yöntemiyle hesaplanmıştır (temel, taşıyıcı sistem, "
                 "merdiven, asansör); kesin statik ve temel projesi sonrası kesinleşir.", size=8, italic=True)
    if cost.get("note"):
        _para(d, cost["note"], size=8, italic=True)
    _signature(d, co)
    d.save(path)
    return path


# ================================================================== teknik şartname

def write_docx(path, spec, cost=None, info=None):
    info = info or {}
    co, site = info.get("company") or {}, info.get("site") or {}
    today = info.get("date") or f"{date.today():%d.%m.%Y}"
    project = spec["title"].replace(" — Teknik Şartname", "")
    no = f"TS-{date.today():%Y%m%d}-01"
    d = _doc()
    # ---- kapak (üst/alt bilgi yok)
    _letterhead(d, co)
    for _ in range(5):
        d.add_paragraph()
    _para(d, "TEKNİK ŞARTNAME", bold=True, size=22, align="c", space_after=6)
    _para(d, project.upper(), bold=True, size=13, align="c", space_after=24)
    yer = " / ".join(filter(None, [site.get("il"), site.get("ilce"), site.get("mahalle")])) or "—"
    _kv_table(d, [("Yapı yeri", yer),
                  ("Pafta / Ada / Parsel", " / ".join([site.get("pafta") or "—", site.get("ada") or "—", site.get("parsel") or "—"])),
                  ("Yapı sahibi", info.get("owner") or "—"), ("Belge no", no), ("Revizyon", info.get("rev", "00")),
                  ("Tarih", today)], (5.0, 9.0))
    for _ in range(4):
        d.add_paragraph()
    _table(d, [("HAZIRLAYAN", "KONTROL EDEN", "ONAYLAYAN"),
               (info.get("drawn_by") or "", info.get("checked_by") or "", info.get("approved_by") or co.get("signatory") or ""),
               ("\n\nİmza", "\n\nİmza", "\n\nİmza")], (5.5, 5.5, 5.5), align=("c", "c", "c"))
    # ---- gövde: yeni bölüm, üst/alt bilgili
    body = d.add_section()
    _header_footer(body, _ph(co.get("name"), "[Firma Unvanı]"), f"{project} — Teknik Şartname · {no}")
    d.sections[0].different_first_page_header_footer = True

    d.add_heading("1. GENEL HÜKÜMLER", 1)
    for i, g in enumerate(spec["general"], 1):
        _numbered(d, f"1.{i}", g)
    d.add_heading("2. PROJE BİLGİLERİ", 1)
    _kv_table(d, spec["summary"])
    if spec["rooms"]:
        d.add_heading("3. MAHAL LİSTESİ", 1)
        rows = [("Kat", "Mahal", "Net alan (m²)")]
        rows += [(r["level"], " / ".join(r["name"].split("/")[1:]), num(r["area"])) for r in spec["rooms"]]
        rows.append(("", "TOPLAM", num(sum(r["area"] for r in spec["rooms"]))))
        _table(d, rows, (3.5, 9.5, 3.6), align=("l", "l", "r"), bold_rows=(len(rows) - 1,), size=8.5)
    d.add_heading("4. İMALAT KALEMLERİ", 1)
    for i, it in enumerate(spec["items"], 1):
        d.add_heading(f"4.{i}  {it['code']} — {it['name']}", 2)
        _para(d, f"Ön metraj: {num(it['quantity'])} {it['unit']}", size=9, italic=True)
        for j, (label, key) in enumerate((("Malzeme", "malzeme"), ("Uygulama", "uygulama"), ("Ölçü ve ödeme", "olcum")), 1):
            _numbered(d, f"4.{i}.{j}", it[key], label, indent=1.1)
    d.add_heading("5. KONTROL, KABUL VE TESLİM", 1)
    for i, t in enumerate([
        "İmalatlar yapım süresince yapı sahibi ve yapı denetim kuruluşunun kontrolüne açık tutulacaktır.",
        "Kapanacak imalatlar (donatı, yalıtım, tesisat) kapatılmadan önce tutanakla kontrol ettirilecektir.",
        "Geçici kabulde tespit edilen eksik ve kusurlar, tutanakta belirtilen süre içinde giderilecektir.",
        "Kesin kabul, geçici kabulden itibaren 12 (on iki) aylık garanti süresi sonunda yapılacaktır.",
    ], 1):
        _numbered(d, f"5.{i}", t)
    if cost:
        _para(d, "", space_after=0)
        _para(d, "Bu şartnamedeki miktarlar ön metrajdır; bedeller teklif belgesinde ve Ek-1 cetvelinde verilmiştir.",
              size=8.5, italic=True)
    d.save(path)
    return path


# ================================================================== xlsx

THIN = Side(style="thin", color="000000")
BOX = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
HEAD = PatternFill("solid", fgColor="D9D9D9")
_XL_DANGER = ("=", "+", "-", "@", "\t", "\r")


def _xl_safe(v):
    """Kullanıcı / dosya kaynaklı metin hücreleri formül olarak yorumlanmasın (CSV/Excel enjeksiyonu)."""
    if isinstance(v, str) and v.startswith(_XL_DANGER):
        return "'" + v
    return v


def _xl_title(ws, title, info, ncols):
    co, site = info.get("company") or {}, info.get("site") or {}
    last = get_column_letter(ncols)
    for r, val, font, al in [(1, _xl_safe(_ph(co.get("name"), "[FİRMA UNVANI]").upper()), Font(name=FONT, bold=True, size=12), "left"),
                             (2, title, Font(name=FONT, bold=True, size=12), "center")]:
        ws.merge_cells(f"A{r}:{last}{r}")
        ws[f"A{r}"] = val
        ws[f"A{r}"].font, ws[f"A{r}"].alignment = font, Alignment(horizontal=al)
    yer = " / ".join(filter(None, [site.get("il"), site.get("ilce"), site.get("mahalle")])) or "—"
    ws.merge_cells(f"A3:{last}3")
    ws["A3"] = (f"İşin adı: {info.get('project', '')}   ·   Yeri: {yer}   ·   Ada/Parsel: {site.get('ada') or '—'}/"
                f"{site.get('parsel') or '—'}   ·   Tarih: {info.get('date') or f'{date.today():%d.%m.%Y}'}")
    ws["A3"].font = Font(name=FONT, size=9)
    ws.merge_cells(f"A4:{last}4")
    ws["A4"] = f"{AVAN_NOTE}  {IMAR_NOTE}"
    ws["A4"].font = Font(name=FONT, size=8, italic=True, color="C00000")
    ws["A4"].alignment = Alignment(wrap_text=True, vertical="top")
    ws.row_dimensions[4].height = 36
    ws.oddFooter.center.text = AVAN_SHORT
    ws.oddFooter.center.size = 7


def _xl_header(ws, row, cols, widths):
    for j, (c, w) in enumerate(zip(cols, widths), 1):
        cell = ws.cell(row=row, column=j, value=c)
        cell.font, cell.fill, cell.border = Font(name=FONT, bold=True, size=9), HEAD, BOX
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        ws.column_dimensions[get_column_letter(j)].width = w
    ws.row_dimensions[row].height = 30
    ws.freeze_panes = f"A{row + 1}"
    ws.print_title_rows = f"{row}:{row}"


def _xl_print(ws, landscape=True):
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.orientation = "landscape" if landscape else "portrait"
    ws.page_setup.fitToWidth, ws.page_setup.fitToHeight = 1, 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_options.horizontalCentered = True
    ws.page_margins.left = ws.page_margins.right = 0.5
    ws.oddFooter.center.text = "Sayfa &P / &N"
    ws.oddFooter.center.size = 8


def write_xlsx(path, project_name, qres, cost, info=None):
    info = {"project": project_name, **(info or {})}
    wb = Workbook()
    F = lambda **k: Font(name=FONT, size=9, **k)

    # ---- birim fiyat cetveli (formüllü)
    ws = wb.active
    ws.title = "Birim Fiyat Cetveli"
    _xl_title(ws, "BİRİM FİYAT TEKLİF CETVELİ", info, 7)
    if cost.get("note"):
        ws["A4"] = f"{AVAN_NOTE}  {IMAR_NOTE}  {cost['note']}"
    _xl_header(ws, 5, ["Sıra No", "Poz No", "İş Kaleminin Adı ve Kısa Açıklaması", "Birimi", "Miktarı", "Birim Fiyat (TL)",
                       "Tutarı (TL)"], [7, 10, 58, 8, 12, 16, 18])
    row, i, first = 6, 0, 6
    for r in cost["rows"]:
        if not r["enabled"]:
            continue
        i += 1
        for j, v in enumerate([i, r["code"], r["name"], r["unit"], r["quantity"], r["unit_price"], f"=E{row}*F{row}"], 1):
            c = ws.cell(row=row, column=j, value=_xl_safe(v) if j < 7 else v)  # 7: bilinçli formül
            c.font, c.border = F(), BOX
            if j >= 5:
                c.number_format = MONEY_XL
            if j in (1, 2, 4):
                c.alignment = Alignment(horizontal="center")
        row += 1
    last = row - 1

    def tot(label, formula, bold=False, pct=None):
        nonlocal row
        ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=4)
        ws.cell(row=row, column=1, value=label).font = F(bold=bold)
        ws.cell(row=row, column=1).alignment = Alignment(horizontal="right")
        if pct is not None:
            ws.cell(row=row, column=5, value=pct).font = F()
            ws.cell(row=row, column=6, value="%").font = F()
        c = ws.cell(row=row, column=7, value=formula)
        c.number_format, c.font = MONEY_XL, F(bold=bold)
        for j in range(1, 8):
            ws.cell(row=row, column=j).border = BOX
        row += 1
        return row - 1

    sub = tot("TOPLAM", f"=SUM(G{first}:G{last})", True)
    oh = tot("Genel giderler", f"=G{sub}*E{row}/100", pct=cost["overhead_pct"])
    pr = tot("Yüklenici kârı", f"=(G{sub}+G{oh})*E{row}/100", pct=cost["profit_pct"])
    bv = tot("TOPLAM (KDV HARİÇ)", f"=G{sub}+G{oh}+G{pr}", True)
    vat = tot("KDV", f"=G{bv}*E{row}/100", pct=cost["vat_pct"])
    gt = tot("GENEL TOPLAM (KDV DAHİL)", f"=G{bv}+G{vat}", True)
    area = tot("Brüt inşaat alanı (m²)", cost["gross_floor_area"])
    tot("m² birim fiyatı (KDV dahil)", f"=IF(G{area}>0,G{gt}/G{area},0)", True)
    row += 2
    co = info.get("company") or {}
    for col, lab, name in [(3, "HAZIRLAYAN", info.get("drawn_by")), (5, "KONTROL EDEN", info.get("checked_by")),
                           (7, "ONAYLAYAN", co.get("signatory") or info.get("approved_by"))]:
        for dr, v, b in ((0, lab, True), (1, name or "", False), (3, "İmza", False)):
            c = ws.cell(row=row + dr, column=col, value=_xl_safe(v))
            c.font, c.alignment = F(bold=b), Alignment(horizontal="center")
    _xl_print(ws)

    # ---- metraj cetveli
    ws = wb.create_sheet("Metraj Cetveli")
    _xl_title(ws, "METRAJ CETVELİ", info, 11)
    _xl_header(ws, 5, ["Kat", "Eleman", "Tür", "Tag / rol", "Uzunluk (m)", "Kalınlık (m)", "Brüt alan (m²)", "Boşluk (m²)",
                       "Net alan (m²)", "Hacim (m³)", "Adet"], [11, 26, 10, 12, 12, 12, 14, 12, 14, 12, 8])
    row = 6
    for l in qres["lines"]:
        m = l["metrics"]
        vals = [l["level"], l["element"].split("/")[-1], l["type"] if l["type"] != "opening" else l["kind"], l["role"] or l["tag"],
                m.get("length", m.get("width")), m.get("thickness"), m.get("gross_area", m.get("area")), m.get("opening_area"),
                m.get("net_area"), m.get("volume"), m.get("count")]
        for j, v in enumerate(vals, 1):
            c = ws.cell(row=row, column=j, value=_xl_safe(v))
            c.font, c.border = F(), BOX
            if 5 <= j <= 10 and v is not None:
                c.number_format = MONEY_XL
        row += 1
    _xl_print(ws)

    # ---- mahal listesi
    ws = wb.create_sheet("Mahal Listesi")
    _xl_title(ws, "MAHAL LİSTESİ", info, 4)
    _xl_header(ws, 5, ["Kat", "Mahal", "Net alan (m²)", "Çevre (m)"], [14, 40, 16, 14])
    row = 6
    for r in qres["rooms"]:
        for j, v in enumerate([r["level"], " / ".join(r["name"].split("/")[1:]), r["area"], r["perimeter"]], 1):
            c = ws.cell(row=row, column=j, value=_xl_safe(v))
            c.font, c.border = F(), BOX
            if j > 2:
                c.number_format = MONEY_XL
        row += 1
    ws.cell(row=row, column=2, value="TOPLAM").font = F(bold=True)
    c = ws.cell(row=row, column=3, value=f"=SUM(C6:C{row - 1})")
    c.font, c.number_format = F(bold=True), MONEY_XL
    for j in range(1, 5):
        ws.cell(row=row, column=j).border = BOX
    _xl_print(ws, landscape=False)
    wb.save(path)
    return path
