"""Resmî poz eşlemesi: ArchAI kalem kodları ↔ ÇŞB (veya başka idare) poz numaraları.

ÇŞB birim fiyat listeleri ArchAI ile DAĞITILMAZ: Bakanlık listeleri yazılı izin olmadan çoğaltmaya kapalıdır ve
lisanslı dağıtımı AMP Yazılım'dadır. Bu yüzden akış şöyledir:

  1. Kullanıcı kendi lisanslı listesini (AMP / Oska / birimfiyat.net'ten Excel/CSV çıktısı) yükler →
     `read_price_list()` başlıkları tanır, satırları {poz: {tanim, birim, fiyat}} yapar. Liste yalnız bu makinede,
     `out/poz_listesi.json` içinde tutulur.
  2. Her kalemin poz numarası: projede elle verilen (`adjust["poz"]`) > `data/poz_map.json` önerisi.
     Önerilerin hepsi "doğrulanmadı" işaretlidir; poz numarası olmayan kalemler için listeden metin
     benzerliğiyle aday önerilir (`suggest`).
  3. `match()` her kalemin durumunu çıkarır; `overrides()` birimi uyuşan eşleşmelerin liste fiyatını
     `adjust["overrides"]`a çevirir (maliyet motoru değişmez).
  4. `write_kesif()` keşif özeti çıkarır: Sıra No · Poz No · İmalatın Cinsi · Birimi · Miktarı · Birim Fiyatı · Tutarı.
     Bu sütun düzeni AMP/Oska'nın Excel'den aktarım ekranlarına yapıştırılabilir; programların kendi dosya
     biçimleri (.amp, .oska vb.) DOĞRULANMADI ve üretilmez.
"""

import csv
import io
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path

DEFAULT_MAP = Path(__file__).parent / "data" / "poz_map.json"
MAX_ROWS = 200_000

# --------------------------------------------------------------------------- birim ve sayı

_UNIT = {"m2": "m²", "m²": "m²", "mt2": "m²", "metrekare": "m²",
         "m3": "m³", "m³": "m³", "mt3": "m³", "metreküp": "m³",
         "m": "m", "mt": "m", "metre": "m", "mtül": "m", "mtul": "m",
         "ton": "ton", "t": "ton", "tn": "ton",
         "kg": "kg", "adet": "adet", "ad": "adet", "ad.": "adet", "sayı": "adet", "takım": "takım", "tk": "takım",
         "durak": "durak", "götürü": "götürü", "gtr": "götürü", "lt": "lt", "litre": "lt", "sa": "sa", "saat": "sa"}


def norm_unit(u):
    s = str(u or "").strip().lower().replace(" ", "")
    return _UNIT.get(s, _UNIT.get(s.rstrip("."), s))


def parse_num(v):
    """Excel sayısı veya TR/EN biçimli metin ("1.234,56", "1234.56", "₺ 950,00") → float; okunamazsa None."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v) if v == v else None
    s = re.sub(r"[^\d,.\-]", "", str(v))
    if not s or not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".") if s.rfind(",") > s.rfind(".") else s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".") if s.count(",") == 1 else s.replace(",", "")
    elif s.count(".") > 1 or re.fullmatch(r"-?\d{1,3}\.\d{3}", s):   # "3.800": TR binlik ayracı (fiyatlar 2 haneli)
        s = s.replace(".", "")
    try:
        return float(s)
    except ValueError:
        return None


POZ_RE = re.compile(r"^[0-9A-ZÇĞİÖŞÜ][0-9A-ZÇĞİÖŞÜa-zçğıöşü./\-]{1,30}$")


def norm_poz(p):
    s = str(p or "").strip().upper().replace(" ", "")
    return s if POZ_RE.match(s) and re.search(r"\d", s) else None


# --------------------------------------------------------------------------- liste okuma

_HEAD = {
    "poz": re.compile(r"poz|kod|no\.?$"),
    "tanim": re.compile(r"tan[ıi]m|tarif|imalat|a[çc][ıi]klama|cins|i[şs]in ad|kalem"),
    "birim": re.compile(r"^birim[ıi]?$|^birimi$|^br\.?$|ölçü"),
    "fiyat": re.compile(r"fiyat|b\.?\s*f\.?|tutar[ıi]? \(birim"),
    "miktar": re.compile(r"miktar"),
}


def _fold(s):
    s = str(s or "").strip().lower().replace("ı", "i").replace("İ", "i")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode() or str(s).lower()


def _header_map(row):
    """Bir satır başlık mı? Sütun indekslerini döndürür (poz zorunlu)."""
    cols = {}
    for j, cell in enumerate(row):
        t = str(cell or "").strip().lower().replace("\u0307", "")   # "İ".lower() → i + birleşik nokta
        if not t or len(t) > 60:
            continue
        for key, rx in _HEAD.items():
            if key in cols:
                continue
            if key == "birim" and "fiyat" in t:
                continue
            if key == "poz" and ("sıra" in t or "sira" in _fold(t)):
                continue
            if rx.search(t):
                cols[key] = j
                break
    return cols if "poz" in cols and ("tanim" in cols or "fiyat" in cols) else None


def _rows_from_file(path, data=None):
    name = str(path).lower()
    if name.endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook
        wb = load_workbook(io.BytesIO(data) if data is not None else path, read_only=True, data_only=True)
        for ws in wb.worksheets:
            for row in ws.iter_rows(values_only=True):
                yield list(row)
        return
    if name.endswith((".csv", ".txt")):
        raw = data if data is not None else Path(path).read_bytes()
        for enc in ("utf-8-sig", "cp1254", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        sample = text[:4096]
        delim = max(";,\t", key=sample.count)
        yield from csv.reader(io.StringIO(text), delimiter=delim)
        return
    raise ValueError("desteklenen biçimler: .xlsx, .xlsm, .csv (AMP/Oska'dan Excel veya CSV olarak dışa aktarın)")


def read_price_list(path, data=None, institution="ÇŞB", year=None):
    """Lisanslı poz listesini oku. Başlık satırı (Poz No, Tanımı, Birimi, Birim Fiyatı) otomatik bulunur;
    birden çok sayfa/başlık olabilir. Dönen: {"items": {poz: {...}}, "count", "skipped", "source", ...}."""
    items, cols, skipped, n = {}, None, 0, 0
    for row in _rows_from_file(path, data):
        n += 1
        if n > MAX_ROWS:
            raise ValueError(f"liste {MAX_ROWS} satırdan uzun")
        h = _header_map(row)
        if h:
            cols = h
            continue
        if not cols:
            continue
        get = lambda k: row[cols[k]] if k in cols and cols[k] < len(row) else None
        poz = norm_poz(get("poz"))
        price = parse_num(get("fiyat"))
        if not poz:
            continue
        if price is None or price < 0:
            skipped += 1
            continue
        items[poz] = {"poz": poz, "tanim": str(get("tanim") or "").strip()[:600], "birim": norm_unit(get("birim")),
                      "fiyat": round(price, 2)}
    if not items:
        raise ValueError("listede poz satırı bulunamadı: başlık satırında 'Poz No' ve 'Birim Fiyat' sütunları olmalı")
    return {"items": items, "count": len(items), "skipped": skipped, "source": Path(str(path)).name,
            "institution": institution, "year": year, "imported_at": datetime.now().isoformat(timespec="seconds")}


def save_list(lst, path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(lst, ensure_ascii=False))
    return path


def load_list(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return None


def list_info(lst):
    return None if not lst else {k: lst.get(k) for k in ("count", "skipped", "source", "institution", "year", "imported_at")}


# --------------------------------------------------------------------------- eşleme

def load_map(path=None):
    d = json.loads(Path(path or DEFAULT_MAP).read_text(encoding="utf-8"))
    return {k: v for k, v in d["items"].items()}


def poz_of(code, adjust=None, pmap=None):
    """Kalemin poz numarası ve kaynağı: ("15.150.1006", "proje" | "öneri") ya da (None, None)."""
    own = ((adjust or {}).get("poz") or {}).get(code)
    if own:
        return own, "proje"
    m = (pmap if pmap is not None else load_map()).get(code) or {}
    return (m.get("poz"), "öneri") if m.get("poz") else (None, None)


_STOP = {"ve", "ile", "icin", "dahil", "her", "turlu", "yapilmasi", "yapilmasi.", "bir", "veya", "olarak", "avan",
         "yaklasik", "m", "cm", "mm", "m2", "m3", "the", "of", "bu", "da", "de", "alan", "basina", "opsiyonel"}


def _tokens(s):
    words = re.findall(r"[a-z0-9]+", _fold(s))
    return {w[:6] for w in words if len(w) > 2 and w not in _STOP}


def suggest(item, lst, k=3):
    """Poz numarası olmayan kalem için listeden aday: kelime örtüşmesi (Jaccard) + birim uyumu."""
    if not lst:
        return []
    want, unit = _tokens(item["name"]), norm_unit(item["unit"])
    if not want:
        return []
    scored = []
    for p in lst["items"].values():
        got = _tokens(p["tanim"])
        if not got:
            continue
        inter = len(want & got)
        if not inter:
            continue
        s = inter / len(want | got) + (0.15 if p["birim"] == unit else 0)
        scored.append((s, p))
    scored.sort(key=lambda t: -t[0])
    return [{"poz": p["poz"], "tanim": p["tanim"][:160], "birim": p["birim"], "fiyat": p["fiyat"], "skor": round(s, 3)}
            for s, p in scored[:k] if s >= 0.12]


def match(prices, lst=None, adjust=None, pmap=None, with_suggestions=True):
    """Katalogdaki her kalemin poz durumu.
    durum: eslesti (poz listede, birim uyumlu) | birim_uyusmaz | listede_yok | poz_yok | liste_yok"""
    pmap = pmap if pmap is not None else load_map()
    out = []
    for it in prices["items"]:
        code = it["code"]
        poz, src = poz_of(code, adjust, pmap)
        row = {"code": code, "name": it["name"], "unit": it["unit"], "group": it["group"], "poz": poz, "kaynak": src,
               "dogrulandi": src == "proje" or bool((pmap.get(code) or {}).get("dogrulandi")),
               "not": (pmap.get(code) or {}).get("not")}
        if not poz:
            row["durum"] = "poz_yok"
            if with_suggestions:
                row["adaylar"] = suggest(it, lst)
        elif not lst:
            row["durum"] = "liste_yok"
        elif norm_poz(poz) not in lst["items"]:
            row["durum"] = "listede_yok"
        else:
            p = lst["items"][norm_poz(poz)]
            row.update(liste_tanim=p["tanim"][:200], liste_birim=p["birim"], liste_fiyat=p["fiyat"])
            row["durum"] = "eslesti" if p["birim"] == norm_unit(it["unit"]) else "birim_uyusmaz"
        out.append(row)
    return out


def summary(rows):
    s = {}
    for r in rows:
        s[r["durum"]] = s.get(r["durum"], 0) + 1
    return s


def overrides(rows):
    """Birimi uyuşan eşleşmelerin liste fiyatı → adjust["overrides"] biçimi."""
    return {r["code"]: r["liste_fiyat"] for r in rows if r["durum"] == "eslesti"}


def validate_poz_adjust(d):
    if d is None:
        return
    if not isinstance(d, dict):
        raise ValueError("poz {kod: poz no} sözlüğü olmalı")
    for code, p in d.items():
        if not isinstance(code, str) or not code:
            raise ValueError("poz: kalem kodu metin olmalı")
        if p is not None and not norm_poz(p):
            raise ValueError(f"{code}: geçersiz poz numarası {p!r} (ör. 15.150.1006)")


# --------------------------------------------------------------------------- keşif özeti

KESIF_COLS = ["Sıra No", "Poz No", "İmalatın Cinsi", "Birimi", "Miktarı", "Birim Fiyatı (TL)", "Tutarı (TL)",
              "ArchAI Kodu", "Poz Durumu"]


def kesif_rows(cost, adjust=None, pmap=None):
    pmap = pmap if pmap is not None else load_map()
    rows, i = [], 0
    for r in cost["rows"]:
        if not r["enabled"]:
            continue
        i += 1
        poz, src = poz_of(r["code"], adjust, pmap)
        verified = src == "proje" or bool((pmap.get(r["code"]) or {}).get("dogrulandi"))
        durum = "özel kalem (poz yok)" if not poz else ("proje" if src == "proje" else
                                                        "doğrulandı" if verified else "öneri — doğrulanmadı")
        rows.append([i, poz or "", r["name"], r["unit"], r["quantity"], r["unit_price"], r["amount"], r["code"], durum])
    return rows


def write_kesif(xlsx_path, csv_path, project_name, cost, adjust=None, info=None):
    """Keşif özeti: xlsx (formüllü) + CSV (`;` ayraçlı, TR ondalık — AMP/Oska'ya yapıştırmak için)."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font

    from .reports import BOX, FONT, MONEY_XL, _xl_header, _xl_print, _xl_safe, _xl_title
    rows = kesif_rows(cost, adjust)
    wb = Workbook()
    ws = wb.active
    ws.title = "Keşif Özeti"
    _xl_title(ws, "KEŞİF ÖZETİ (YAKLAŞIK MALİYET)", {"project": project_name, **(info or {})}, len(KESIF_COLS))
    _xl_header(ws, 5, KESIF_COLS, [7, 14, 58, 8, 12, 16, 18, 10, 20])
    F = lambda **k: Font(name=FONT, size=9, **k)
    row = 6
    for vals in rows:
        for j, v in enumerate(vals, 1):
            val = f"=E{row}*F{row}" if j == 7 else _xl_safe(v)
            c = ws.cell(row=row, column=j, value=val)
            c.font, c.border = F(italic=j == 9), BOX
            if j in (5, 6, 7):
                c.number_format = MONEY_XL
            if j in (1, 2, 4, 8):
                c.alignment = Alignment(horizontal="center")
        row += 1
    ws.cell(row=row, column=3, value="TOPLAM (genel gider, kâr ve KDV hariç)").font = F(bold=True)
    c = ws.cell(row=row, column=7, value=f"=SUM(G6:G{row - 1})" if rows else 0)
    c.font, c.number_format = F(bold=True), MONEY_XL
    _xl_print(ws)
    wb.save(xlsx_path)

    def tr(v):
        return f"{v:.2f}".replace(".", ",") if isinstance(v, float) else str(v)
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(KESIF_COLS)
    for vals in rows:
        w.writerow([_xl_safe(tr(v)) if isinstance(v, str) else tr(v) for v in vals])
    Path(csv_path).write_text(buf.getvalue(), encoding="utf-8-sig")
    return xlsx_path, csv_path
