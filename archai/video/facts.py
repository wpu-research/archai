"""Proje dosyalarından video için gerçekler (saf okuma / hesap; ağ ve tarayıcı yok).

Yalnız projede olan veri kullanılır: sayılar `project.json` (özet, maliyet, rapor), geometri `elements.json`,
iç mekân `interior.json`. Eksik olan (firma adı, logo, teklif şartları…) hiçbir zaman yer tutucuyla doldurulmaz;
ilgili kare/satır atlanır.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path

SITE = "Arsa"
ROOF = "Çatı"
NON_VISIT = re.compile(r"Merdiven|Şaft|Asansör|Depo|Teknik|Sığınak|Kazan", re.I)
HALLISH = re.compile(r"Hol|Koridor|Ortak|Giriş|Antre", re.I)
IMG_EXT = (".png", ".jpg", ".jpeg", ".webp")
MAX_LOGO_BYTES = 5 * 1024 * 1024


def read_json(p, default=None):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return default


def room_label(name):
    """'Zemin Kat/Salon' → 'Salon'."""
    return str(name).split("/", 1)[-1].strip()


def poly_area(pts):
    return abs(sum(p[0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * p[1] for i, p in enumerate(pts))) / 2


def centroid(pts):
    return (sum(p[0] for p in pts) / len(pts), sum(p[1] for p in pts) / len(pts))


def in_poly(pt, pts):
    x, y = pt
    c = False
    j = len(pts) - 1
    for i in range(len(pts)):
        xi, yi = pts[i]
        xj, yj = pts[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            c = not c
        j = i
    return c


def element_z(e):
    """İstemcideki build() ile aynı kural: katın alt kotu."""
    t = e.get("type")
    if t in ("slab", "roof"):
        return e.get("z") or 0
    if t == "wall":
        return e.get("base_z") or 0
    if e.get("z") is not None:
        return e["z"]
    return e["origin"][2] if e.get("origin") else 1e9


def level_order(elements):
    """Arsa dışındaki katlar, alt kota göre (istemcideki V.nLv sırası)."""
    z = {}
    for e in elements:
        lv = e.get("level") or "0"
        if lv == SITE:
            continue
        z[lv] = min(z.get(lv, 1e9), element_z(e))
    return [k for k, _ in sorted(z.items(), key=lambda kv: kv[1])]


def floor_levels(elements, levels):
    have = {e["level"] for e in elements if e.get("type") == "slab" and e.get("role") == "floor"}
    return [lv for lv in levels if lv in have]


def level_floor_z(elements, level):
    for e in elements:
        if e.get("type") == "slab" and e.get("role") == "floor" and e.get("level") == level:
            return e.get("z") or 0.0
    return 0.0


def building_bounds(elements):
    """Bina (Arsa hariç) yatay sınırı ve tepe kotu: (x0, y0, x1, y1, ztop) ya da None."""
    xs, ys, zt = [], [], 0.0
    for e in elements:
        if e.get("level") == SITE:
            continue
        t = e.get("type")
        if t == "wall":
            for p in (e["start"], e["end"]):
                xs.append(p[0])
                ys.append(p[1])
            zt = max(zt, (e.get("base_z") or 0) + (e.get("height") or 0))
        elif t == "slab":
            for p in e.get("points", []):
                xs.append(p[0])
                ys.append(p[1])
            zt = max(zt, (e.get("z") or 0) + (e.get("thickness") or 0))
        elif t == "roof":
            xs += [e["x0"], e["x1"]]
            ys += [e["y0"], e["y1"]]
            zt = max(zt, (e.get("z") or 0) + (e.get("ridge") or 0))
    if not xs:
        return None
    return (min(xs), min(ys), max(xs), max(ys), zt)


def site_bounds(elements):
    for e in elements:
        if e.get("type") == "slab" and e.get("role") == "site" and e.get("points"):
            xs = [p[0] for p in e["points"]]
            ys = [p[1] for p in e["points"]]
            return (min(xs), min(ys), max(xs), max(ys))
    return None


# ------------------------------------------------------------------ logo / firma
def resolve_logo(out_root, company):
    """Logo dosyası: ayarlarda `company.logo` (OUT altında göreli/mutlak) ya da OUT/logo.png|jpg.
    Yalnız OUT içinden, ≤5 MB ve gerçek resim olanlar kabul edilir; yoksa None (yer tutucu yok)."""
    root = Path(out_root).resolve()
    cands = []
    name = (company or {}).get("logo")
    if isinstance(name, str) and name.strip():
        cands.append(Path(name.strip()))
    cands += [Path("logo.png"), Path("logo.jpg"), Path("logo.jpeg")]
    for c in cands:
        p = (c if c.is_absolute() else root / c)
        try:
            p = p.resolve()
            if not p.is_relative_to(root) or p.suffix.lower() not in IMG_EXT or not p.is_file():
                continue
            if p.stat().st_size > MAX_LOGO_BYTES:
                continue
            from PIL import Image
            with Image.open(p) as im:
                im.verify()
            return p
        except (OSError, ValueError, SyntaxError):
            continue
    return None


SHEET_TOK = {"plani": "planı", "gorunus": "görünüş", "on": "ön", "cati": "çatı", "uzerinden": "üzerinden",
             "yan": "yan", "arka": "arka", "aks": "aks", "temel": "temel", "vaziyet": "vaziyet", "kesit": "kesit",
             "aa": "A-A", "bb": "B-B"}


def sheet_label(stem):
    """'02_zemin_kat_plani' → 'Zemin kat planı'."""
    toks = [t for t in re.split(r"[_\-\s]+", stem) if t and not t.isdigit()]
    out = [SHEET_TOK.get(t.lower(), t) for t in toks]
    s = " ".join(out)
    return s[:1].upper() + s[1:] if s else stem


@dataclass
class Facts:
    pid: str
    name: str
    elements: list
    interior: dict
    summary: dict
    cost: dict
    report: dict
    info: dict
    levels: list                      # Arsa hariç, alttan üste
    floors: list                      # döşemeli katlar (yürüyüş için)
    bounds: tuple | None              # (x0, y0, x1, y1, ztop)
    site: tuple | None
    rooms: list = field(default_factory=list)       # {name, level, points, area}
    sheets: list = field(default_factory=list)      # [(Path, etiket)]
    docs: list = field(default_factory=list)        # ['Teklif', ...] (dosyası gerçekten olanlar)
    logo: Path | None = None

    @property
    def has_building(self):
        return any(e.get("type") == "wall" for e in self.elements) and self.bounds is not None

    @property
    def center(self):
        x0, y0, x1, y1, _ = self.bounds
        return ((x0 + x1) / 2, (y0 + y1) / 2)

    @property
    def size(self):
        x0, y0, x1, y1, zt = self.bounds
        return (x1 - x0, y1 - y0, zt)

    @property
    def company(self):
        return self.info.get("company") or {}

    @property
    def floor_count(self):
        return len(self.floors)


def load_facts(pdir, out_root=None, interior_override=None):
    """Proje klasöründen Facts. Eksik/bozuk zorunlu dosyada ValueError."""
    pdir = Path(pdir)
    elements = read_json(pdir / "elements.json")
    proj = read_json(pdir / "project.json")
    if not isinstance(elements, list) or not isinstance(proj, dict):
        raise ValueError("proje kaydı (elements.json / project.json) okunamadı")
    interior = interior_override if interior_override is not None else read_json(pdir / "interior.json", {})
    if not isinstance(interior, dict):
        interior = {}
    from archai import project as _project
    try:
        info = _project.build_info(proj.get("brief") or {})
    except Exception:  # noqa: BLE001 — ayar dosyası bozuksa videoyu engelleme
        info = {}
    out_root = Path(out_root) if out_root else pdir.parent.parent
    levels = level_order(elements)
    rooms = []
    for e in elements:
        if e.get("type") == "room" and e.get("points"):
            rooms.append({"name": e["name"], "level": e.get("level"), "points": e["points"], "area": poly_area(e["points"])})
    sheets = []
    for p in sorted((pdir / "cizimler").glob("*.png")) if (pdir / "cizimler").is_dir() else []:
        sheets.append((p, sheet_label(p.stem)))
    docs = []
    for fname, lab in (("teklif.docx", "Teklif"), ("teknik_sartname.docx", "Teknik şartname"),
                       ("metraj_maliyet.xlsx", "Metraj · maliyet (Excel)")):
        if (pdir / fname).is_file():
            docs.append(lab)
    return Facts(
        pid=pdir.name, name=str(proj.get("name") or "Proje"), elements=elements, interior=interior,
        summary=proj.get("summary") or {}, cost=proj.get("cost") or {}, report=proj.get("report") or {},
        info=info, levels=levels, floors=floor_levels(elements, levels), bounds=building_bounds(elements),
        site=site_bounds(elements), rooms=rooms, sheets=sheets, docs=docs,
        logo=resolve_logo(out_root, info.get("company")))


def fmt_tl(v):
    """1234567.8 → '1.234.568 ₺' (Türkçe biçim)."""
    return f"{round(float(v)):,}".replace(",", ".") + " ₺"


def fmt_num(v, nd=1):
    s = f"{float(v):,.{nd}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def headline(f):
    """Başlık kartı alt satırı: yalnız veriden — '2 katlı · Villa 4+2 · 447 m² brüt'."""
    parts = []
    n = f.floor_count
    if n:
        parts.append(f"{n} katlı")
    ut = f.report.get("unit_type")
    if ut and ut not in ("auto",):
        parts.append(str(ut))
    g = f.summary.get("gross_floor_area")
    if g:
        parts.append(f"{fmt_num(g, 0)} m² brüt")
    return " · ".join(parts)


def site_line(f):
    """Yer bilgisi (varsa): 'Kadıköy / İstanbul · Ada 12 Parsel 3'."""
    s = f.info.get("site") or {}
    place = " / ".join(x for x in (s.get("ilce"), s.get("il")) if x)
    ap = " ".join(x for x in (f"Ada {s['ada']}" if s.get("ada") else "", f"Parsel {s['parsel']}" if s.get("parsel") else "") if x)
    return " · ".join(x for x in (place, ap) if x)


def contact_lines(f):
    """Firma kartı satırları; boş alan yok. [(etiket, değer)]"""
    c = f.company
    rows = []
    for key, lab in (("address", "Adres"), ("phone", "Telefon"), ("email", "E-posta")):
        if c.get(key):
            rows.append((lab, str(c[key])))
    sig = " · ".join(x for x in (c.get("signatory"), c.get("title")) if x)
    if sig:
        rows.append(("Yetkili", sig))
    return rows


def has_company_card(f):
    c = f.company
    return bool(c.get("name") or f.logo or contact_lines(f))


def offer_terms_given(f):
    """Yalnız kullanıcının girdiği teklif şartları (varsayılan uydurulmaz)."""
    of = f.info.get("offer") or {}
    out = []
    if of.get("months"):
        out.append(("Süre", f"{int(of['months'])} ay"))
    if of.get("validity_days"):
        out.append(("Teklif geçerliliği", f"{int(of['validity_days'])} gün"))
    return out


def wall_opening_counts(f):
    return f.summary.get("window_count"), f.summary.get("door_count")


def dist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])
