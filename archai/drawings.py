"""Teknik çizimler — resmî pafta düzeninde, gerçek ölçekli A3 (DXF + PDF).

Türk mimari proje pratiği:
  * Ölçüler cm, kotlar m (±0.00). Kat planı / kesit / görünüş 1/100, vaziyet 1/200–1/500.
  * Aks sistemi (1,2,3… / A,B,C…), üç kademeli ölçü zinciri (boşluk / aks / toplam).
  * Doğrama etiketleri: pencere en/yükseklik/parapet, kapı en/yükseklik (cm).
  * Betonarme perde poşe (dolu), kâgir duvar taralı; kesitte toprak taraması.
  * Pafta çerçevesi + antet (firma, proje, yer, ada/parsel, pafta, ölçek, tarih, rev., imza).

Model uzayı metredir; pafta çerçevesi ve antet, seçilen ölçekte model uzayına çizilir
(DXF'te 1:1 ölçekli pafta). PDF gerçek ölçektir: 1/100'de 1 m = 10 mm.
"""

import logging
import math
from datetime import date
from pathlib import Path

import ezdxf
from ezdxf import bbox as ezbbox
from ezdxf.enums import TextEntityAlignment as TA
from shapely.geometry import Polygon
from shapely.ops import unary_union

from .notice import AVAN_SHORT
from .quantities import polygon_area

logging.getLogger("ezdxf").setLevel(logging.WARNING)

PAPER_W, PAPER_H = 420.0, 297.0        # A3 yatay, mm
FRAME = (20.0, 10.0, 410.0, 287.0)     # sol cilt payı 20 mm
TB_H = 40.0                            # antet yüksekliği
SCALES = (50, 100, 200, 250, 500, 1000)

LAYERS = {  # ad: (renk, çizgi kalınlığı 1/100 mm, çizgi tipi)
    "A-DUVAR": (7, 50, None), "A-DUVAR-TARAMA": (8, 9, None), "A-BETONARME": (7, 50, None),
    "A-PENCERE": (4, 25, None), "A-KAPI": (3, 18, None), "A-MAHAL": (2, 18, None), "A-OLCU": (1, 13, None),
    "A-AKS": (8, 13, "DASHDOT"), "A-AKS-BALON": (7, 18, None), "A-MERDIVEN": (6, 18, None), "A-KOT": (7, 18, None),
    "A-KESIT": (7, 50, None), "A-GORUNUS": (7, 25, None), "A-GORUNUS-INCE": (7, 13, None), "A-ZEMIN": (7, 50, None),
    "A-PARSEL": (5, 50, "DASHDOT"), "A-CEKME": (1, 25, "DASHED"), "A-YAZI": (7, 18, None), "A-KESIT-OKU": (7, 50, None),
    "P-CERCEVE": (7, 50, None), "P-ANTET": (7, 25, None), "P-ANTET-YAZI": (7, 18, None),
}


def tr_num(v, dec=2):
    s = f"{v:,.{dec}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def kot(z):
    return "±0.00" if abs(z) < 1e-6 else f"{'+' if z > 0 else '-'}{abs(z):.2f}"


def level_title(lvl):
    if lvl.startswith("Kat "):
        return f"{lvl.split()[1]}. NORMAL KAT"
    return lvl.upper()


# ================================================================== pafta

class Sheet:
    """Tek pafta: ölçek, çizim yardımcıları, çerçeve + antet."""

    def __init__(self, info, number, title, scale):
        self.info, self.number, self.title, self.S = info, number, title, scale
        self.doc = ezdxf.new("R2018", setup=True)
        self.doc.header["$INSUNITS"] = 6
        self.doc.header["$LTSCALE"] = scale / 100
        self.doc.header["$PSLTSCALE"] = 0
        self.doc.styles.get("Standard").dxf.font = "arial.ttf"
        for name, (color, lw, lt) in LAYERS.items():
            ly = self.doc.layers.add(name, color=color, lineweight=lw)
            if lt:
                ly.dxf.linetype = lt
        ds = self.doc.dimstyles.new("TR-CM")
        ds.dxf.dimscale = scale / 1000       # tüm boyutlar kâğıt mm'si cinsinden
        ds.dxf.dimtxt, ds.dxf.dimasz, ds.dxf.dimtsz = 2.0, 1.6, 1.4   # mimari eğik tik
        ds.dxf.dimexe, ds.dxf.dimexo, ds.dxf.dimgap = 1.2, 1.0, 0.7
        ds.dxf.dimlfac, ds.dxf.dimdec, ds.dxf.dimtad, ds.dxf.dimtih, ds.dxf.dimtoh = 100, 0, 1, 0, 0
        ds.dxf.dimclrd = ds.dxf.dimclre = ds.dxf.dimclrt = 1
        ds.dxf.dimlwd = ds.dxf.dimlwe = 13
        ds.dxf.dimdsep = ord(",")
        ds.dxf.dimtmove = 2                   # dar aralıkta yazı serbest
        self.msp = self.doc.modelspace()

    def mm(self, v):
        return v * self.S / 1000

    # --------------------------------------------------------------- yardımcılar
    def text(self, s, x, y, h_mm=2.5, layer="A-YAZI", align=TA.MIDDLE_CENTER, rot=0.0):
        t = self.msp.add_text(s, height=self.mm(h_mm), rotation=rot, dxfattribs={"layer": layer, "style": "Standard"})
        t.set_placement((x, y), align=align)
        return t

    def line(self, a, b, layer):
        return self.msp.add_line(a, b, dxfattribs={"layer": layer})

    def poly(self, pts, layer, close=True):
        return self.msp.add_lwpolyline(pts, close=close, dxfattribs={"layer": layer})

    def hatch(self, rings, layer, pattern=None, scale_mm=1.0, angle=0.0, solid=False):
        h = self.msp.add_hatch(color=7 if solid else 8, dxfattribs={"layer": layer})
        if solid:
            h.set_solid_fill(color=7)
        else:
            h.set_pattern_fill(pattern, scale=self.mm(scale_mm), angle=angle)
        for i, r in enumerate(rings):
            h.paths.add_polyline_path(list(r), is_closed=True, flags=1 if i == 0 else 16)
        return h

    def dim_chain(self, points, base, angle=0):
        """Ölçü zinciri: points model koordinatı, base ölçü çizgisinin geçtiği nokta."""
        key = (lambda p: p[0]) if angle == 0 else (lambda p: p[1])
        pts = sorted({(round(p[0], 4), round(p[1], 4)) for p in points}, key=key)
        uniq = []
        for p in pts:  # aynı konumdaki noktaları ele (sıfır uzunluklu ölçü olmasın)
            if not uniq or abs(key(p) - key(uniq[-1])) > 1e-3:
                uniq.append(p)
        if len(uniq) < 2:
            return
        self.msp.add_multi_point_linear_dim(base=base, points=uniq, angle=angle, dimstyle="TR-CM",
                                            dxfattribs={"layer": "A-OLCU"})

    def kot_mark(self, x, y, z, plan=True, side=1):
        """Kot işareti: planda üçgen + değer; kesit/görünüşte uç çizgisi + üçgen."""
        s = self.mm(2.2)
        if plan:
            self.poly([(x - s, y + s * 1.2), (x + s, y + s * 1.2), (x, y)], "A-KOT")
            self.line((x - s * 2.2, y + s * 1.2), (x + s * 5.5, y + s * 1.2), "A-KOT")
            self.text(kot(z), x + s * 0.2, y + s * 1.9, 2.0, "A-KOT", TA.BOTTOM_LEFT)
        else:
            self.poly([(x, y), (x - s * 0.9, y + s * 1.4), (x + s * 0.9, y + s * 1.4)], "A-KOT")
            self.line((x - side * s * 1.5, y), (x + side * s * 6.5, y), "A-KOT")
            self.text(kot(z), x + side * s * 1.4, y + s * 0.5, 2.0, "A-KOT", TA.BOTTOM_LEFT if side > 0 else TA.BOTTOM_RIGHT)

    def north(self, x, y):
        r = self.mm(6)
        self.msp.add_circle((x, y), r, dxfattribs={"layer": "A-YAZI"})
        self.poly([(x, y + r), (x + r * 0.35, y - r * 0.6), (x, y - r * 0.3), (x - r * 0.35, y - r * 0.6)], "A-YAZI")
        self.hatch([[(x, y + r), (x, y - r * 0.3), (x - r * 0.35, y - r * 0.6)]], "A-YAZI", solid=True)
        self.text("K", x, y + r + self.mm(3), 3.5, "A-YAZI")

    def drawing_title(self, x, y, title):
        """Çizim başlığı + ölçek + ölçek çubuğu."""
        self.text(title, x, y, 5.0, "A-YAZI", TA.BOTTOM_LEFT)
        w = self.mm(5.0) * 0.66 * len(title)
        self.line((x, y - self.mm(1.5)), (x + w, y - self.mm(1.5)), "P-CERCEVE")
        self.text(f"ÖLÇEK 1/{self.S}", x, y - self.mm(7), 3.0, "A-YAZI", TA.BOTTOM_LEFT)
        span = {50: 2.5, 100: 5, 200: 10, 250: 10, 500: 25, 1000: 50}[self.S]
        bx, by, bh = x + self.mm(32), y - self.mm(7), self.mm(1.6)
        for i in range(5):
            x0, x1 = bx + span / 5 * i, bx + span / 5 * (i + 1)
            r = [(x0, by), (x1, by), (x1, by + bh), (x0, by + bh)]
            self.poly(r, "A-YAZI")
            if i % 2 == 0:
                self.hatch([r], "A-YAZI", solid=True)
        for v in (0, span / 5, span):
            self.text(f"{v:g}", bx + v, by + bh + self.mm(0.8), 1.8, "A-YAZI", TA.BOTTOM_CENTER)
        self.text("m", bx + span + self.mm(3), by, 1.8, "A-YAZI", TA.BOTTOM_LEFT)

    # --------------------------------------------------------------- çerçeve + antet
    def frame(self, origin):
        """origin = kâğıdın (0,0) noktasının model koordinatı."""
        ox, oy = origin
        P = lambda x, y: (ox + self.mm(x), oy + self.mm(y))
        self.poly([P(0, 0), P(PAPER_W, 0), P(PAPER_W, PAPER_H), P(0, PAPER_H)], "P-ANTET")
        x0, y0, x1, y1 = FRAME
        self.poly([P(x0, y0), P(x1, y0), P(x1, y1), P(x0, y1)], "P-CERCEVE")
        ty = y0 + TB_H
        self.line(P(x0, ty), P(x1, ty), "P-CERCEVE")
        info = self.info
        co, site = info.get("company") or {}, info.get("site") or {}
        for cx in (95, 215, 300, 345):
            self.line(P(cx, y0), P(cx, ty), "P-ANTET")

        def lab(x, y, s):
            self.text(s, *P(x, y), 1.6, "P-ANTET-YAZI", TA.TOP_LEFT)

        def val(x, y, s, h=2.6, align=TA.TOP_LEFT):
            if s:
                self.text(str(s), *P(x, y), h, "P-ANTET-YAZI", align)

        lab(x0 + 2, ty - 2, "FİRMA / YÜKLENİCİ")
        val(x0 + 2, ty - 6.5, co.get("name") or "[Firma Adı]", 3.0)
        for i, s in enumerate([co.get("address"), " · ".join(filter(None, [co.get("phone"), co.get("email")])),
                               " · ".join(filter(None, [co.get("tax_office"), co.get("tax_no")]))]):
            val(x0 + 2, ty - 13 - i * 4.2, s, 1.9)
        lab(97, ty - 2, "PROJE")
        val(97, ty - 6.5, info.get("project", ""), 3.0)
        lab(97, ty - 13, "YAPI YERİ")
        val(97, ty - 16.5, " / ".join(filter(None, [site.get("il"), site.get("ilce"), site.get("mahalle")])) or "—", 2.3)
        lab(97, ty - 22.5, "PAFTA · ADA · PARSEL")
        val(97, ty - 26, "  ·  ".join([site.get("pafta") or "—", site.get("ada") or "—", site.get("parsel") or "—"]), 2.3)
        lab(97, ty - 32, "YAPI SAHİBİ")
        val(97, ty - 35.5, info.get("owner") or "—", 2.3)
        lab(217, ty - 2, "PAFTA ADI")
        val(257.5, ty - 18, self.title, 4.0 if len(self.title) < 26 else 3.2, TA.MIDDLE_CENTER)
        val(257.5, ty - 30, AVAN_SHORT, 1.8, TA.MIDDLE_CENTER)
        val(257.5, ty - 34, "Statik, tesisat ve ruhsat projesi yetkili mimar/mühendis imzası gerektirir", 1.3, TA.MIDDLE_CENTER)
        for i, (k, v) in enumerate([("ÖLÇEK", f"1/{self.S}"), ("TARİH", info.get("date") or f"{date.today():%d.%m.%Y}"),
                                    ("PAFTA NO", self.number), ("REVİZYON", info.get("rev", "00"))]):
            yy = ty - i * TB_H / 4
            if i:
                self.line(P(300, yy), P(345, yy), "P-ANTET")
            lab(302, yy - 1.6, k)
            val(343, yy - 5.2, v, 3.2 if k == "PAFTA NO" else 2.6, TA.TOP_RIGHT)
        rows = [("MÜELLİF MİMAR", info.get("architect")), ("ÇİZEN", info.get("drawn_by")),
                ("KONTROL", info.get("checked_by")), ("ONAY", info.get("approved_by"))]
        for i, (k, v) in enumerate(rows):
            yy = ty - i * TB_H / 4
            if i:
                self.line(P(345, yy), P(x1, yy), "P-ANTET")
            lab(347, yy - 1.6, k)
            val(347, yy - 5.4, v or "", 2.1)
            self.text("İMZA", *P(x1 - 2, yy - 1.6), 1.4, "P-ANTET-YAZI", TA.TOP_RIGHT)
            self.line(P(385, yy - 9.5), P(x1 - 2, yy - 9.5), "P-ANTET")

    @staticmethod
    def area():
        x0, y0, x1, y1 = FRAME
        return (x0 + x1) / 2, (y0 + TB_H + y1) / 2, (x1 - x0 - 10), (y1 - y0 - TB_H - 10)


def compose(info, number, title, draw, min_scale=100):
    """Çizimi sığan en büyük standart ölçekte kurar, çerçeve + anteti ortalar."""
    cx, cy, aw, ah = Sheet.area()
    for S in [s for s in SCALES if s >= min_scale]:
        sh = Sheet(info, number, title, S)
        draw(sh)
        ext = ezbbox.extents(sh.msp, fast=True)
        if (ext.size.x * 1000 / S <= aw and ext.size.y * 1000 / S <= ah) or S == SCALES[-1]:
            break
    mc = ext.center
    sh.origin = (mc.x - sh.mm(cx), mc.y - sh.mm(cy))
    sh.frame(sh.origin)
    return sh


# ================================================================== kat planı

def _wall_frame(w):
    (x0, y0), (x1, y1) = w["start"], w["end"]
    L = math.hypot(x1 - x0, y1 - y0)
    u = ((x1 - x0) / L, (y1 - y0) / L)
    n = (-u[1], u[0])
    return L, u, n, (lambda s, off: (x0 + u[0] * s + n[0] * off, y0 + u[1] * s + n[1] * off))


def _rect(at, s0, s1, t):
    return Polygon([at(s0, -t / 2), at(s1, -t / 2), at(s1, t / 2), at(s0, t / 2)])


def _merge(vals, tol=0.05):
    out = []
    for v in sorted(vals):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


def _main_axes(vals, min_gap=1.2):
    """Ana akslar: birbirine min_gap'ten yakın bölme duvarları aks sayılmaz; uç akslar korunur."""
    v = _merge(vals)
    if len(v) < 3:
        return v
    out = [v[0]]
    for x in v[1:-1]:
        if x - out[-1] >= min_gap and v[-1] - x >= min_gap:
            out.append(x)
    return out + [v[-1]]


ABBR = [("SALON + AÇIK MUTFAK", "SALON+A.MUTFAK"), ("YATAK ODASI", "Y. ODASI"), ("EBEVEYN BANYO", "E. BANYO"),
        ("ASANSÖR/ŞAFT", "ASANSÖR")]


def _axis_names(n, letters):
    if letters:
        abc = "ABCDEFGHJKLMNPRSTUVYZ"  # aks harfleri: karışan Türkçe harfler kullanılmaz
        return [abc[i] if i < len(abc) else f"A{i}" for i in range(n)]
    return [str(i + 1) for i in range(n)]


def _geoms(g):
    return [] if g.is_empty else ([g] if g.geom_type == "Polygon" else list(g.geoms))


def draw_plan(sh, elements, level, cut_x=None, title="KAT PLANI"):
    walls = [e for e in elements if e["type"] == "wall" and e.get("level") == level]
    rooms = [e for e in elements if e["type"] == "room" and e.get("level") == level]
    stairs = [e for e in elements if e["type"] == "stairs" and e.get("level") == level]
    z0 = min((w.get("base_z", 0) for w in walls), default=0)
    masonry, concrete = [], []
    for w in walls:
        L, u, n, at = _wall_frame(w)
        t = w.get("thickness", 0.2)
        cuts = sorted((o["offset"], o["offset"] + o["width"]) for o in w.get("openings", []))
        s, pieces = -t / 2, []
        for a, b in cuts:
            pieces.append(_rect(at, s, a, t))
            s = b
        pieces.append(_rect(at, s, L + t / 2, t))
        (concrete if abs(t - 0.20) < 1e-3 else masonry).extend(p for p in pieces if p.area > 1e-6)
        ang = math.degrees(math.atan2(u[1], u[0]))
        ang_t = ang if -90 < ang <= 90 else ang - 180
        for o in w.get("openings", []):
            a, b = o["offset"], o["offset"] + o["width"]
            wcm = round(o["width"] * 100)
            if o["kind"] == "window":
                for off in (-t / 2, -t / 10, t / 10, t / 2):
                    sh.line(at(a, off), at(b, off), "A-PENCERE")
                h, par = round(o.get("height", 1.4) * 100), round(o.get("sill", 0.9) * 100)
                sh.text(f"{wcm}/{h}/{par}", *at((a + b) / 2, t / 2 + sh.mm(3.0)), 1.8, "A-PENCERE", TA.MIDDLE_CENTER, ang_t)
            else:
                wd = b - a
                hinge = at(a, t / 2)
                sh.line(hinge, (hinge[0] + n[0] * wd, hinge[1] + n[1] * wd), "A-KAPI")
                sh.msp.add_arc(hinge, wd, ang, ang + 90, dxfattribs={"layer": "A-KAPI"})
                sh.text(f"{wcm}/{round(o.get('height', 2.1) * 100)}", *at((a + b) / 2, -t / 2 - sh.mm(3.0)), 1.8,
                        "A-KAPI", TA.MIDDLE_CENTER, ang_t)

    for p in _geoms(unary_union(masonry)):
        sh.hatch([p.exterior.coords, *[r.coords for r in p.interiors]], "A-DUVAR-TARAMA", "ANSI31", scale_mm=0.35)
    for p in _geoms(unary_union(concrete)):
        sh.hatch([p.exterior.coords, *[r.coords for r in p.interiors]], "A-BETONARME", solid=True)
    for p in _geoms(unary_union(masonry + concrete)):
        for ring in [p.exterior, *p.interiors]:
            sh.poly(list(ring.coords), "A-DUVAR")

    for r in rooms:
        pts = [tuple(p) for p in r["points"]]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        w_ = max(p[0] for p in pts) - min(p[0] for p in pts)
        w_mm = w_ * 1000 / sh.S - 2
        name = r["name"].split("/")[-1].upper().replace("I", "I")
        h = 2.5
        if len(name) * h * 0.62 > w_mm:
            for a, b in ABBR:
                name = name.replace(a, b)
            h = max(1.6, min(2.5, w_mm / (len(name) * 0.62)))
        sh.text(name, cx, cy + sh.mm(1.8), h, "A-MAHAL")
        area = f"A= {tr_num(polygon_area(pts))} m²"
        sh.text(area, cx, cy - sh.mm(1.8), max(1.4, min(1.8, w_mm / (len(area) * 0.6))), "A-MAHAL")

    for s in stairs:
        ox, oy, _ = s["origin"]
        rot = math.radians(s.get("rotation_z", 0))
        c, sn = math.cos(rot), math.sin(rot)
        run, width, n = s.get("run", 0.28), s.get("width", 1.2), s.get("steps", 10)
        for i in range(n + 1):
            p0 = (ox + c * i * run, oy + sn * i * run)
            sh.line(p0, (p0[0] - sn * width, p0[1] + c * width), "A-MERDIVEN")
        mid = lambda d: (ox + c * d - sn * width / 2, oy + sn * d + c * width / 2)
        tip, a1 = mid(run * (n - 0.3)), math.atan2(sn, c)
        sh.line(mid(run * 0.5), tip, "A-MERDIVEN")
        for da in (2.6, -2.6):
            sh.line(tip, (tip[0] - sh.mm(2) * math.cos(a1 + da), tip[1] - sh.mm(2) * math.sin(a1 + da)), "A-MERDIVEN")

    # ---- aks sistemi ve ölçüler
    vx = _main_axes([w["start"][0] for w in walls if abs(w["start"][0] - w["end"][0]) < 1e-6])
    hy = _main_axes([w["start"][1] for w in walls if abs(w["start"][1] - w["end"][1]) < 1e-6])
    if not (vx and hy):
        return
    tmax = max(w.get("thickness", 0.2) for w in walls)
    X0, X1, Y0, Y1 = vx[0] - tmax / 2, vx[-1] + tmax / 2, hy[0] - tmax / 2, hy[-1] + tmax / 2
    d1, d2, d3, db, br = sh.mm(7), sh.mm(13), sh.mm(19), sh.mm(12), sh.mm(4.0)
    for x, nm in zip(vx, _axis_names(len(vx), False)):
        sh.line((x, Y0 - d3 - sh.mm(2)), (x, Y1 + db - br), "A-AKS")
        sh.msp.add_circle((x, Y1 + db), br, dxfattribs={"layer": "A-AKS-BALON"})
        sh.text(nm, x, Y1 + db, 3.2, "A-AKS-BALON")
    for y, nm in zip(hy, _axis_names(len(hy), True)):
        sh.line((X0 - d3 - sh.mm(2), y), (X1 + db - br, y), "A-AKS")
        sh.msp.add_circle((X1 + db, y), br, dxfattribs={"layer": "A-AKS-BALON"})
        sh.text(nm, X1 + db, y, 3.2, "A-AKS-BALON")

    def facade_points(axis):
        pts = []
        for w in walls:
            (ax, ay), (bx, by) = w["start"], w["end"]
            if axis == "x" and abs(ay - by) < 1e-6 and abs(ay - hy[0]) < 1e-6:
                sgn = 1 if bx >= ax else -1
                for o in w.get("openings", []):
                    pts += [(ax + sgn * o["offset"], Y0), (ax + sgn * (o["offset"] + o["width"]), Y0)]
            if axis == "y" and abs(ax - bx) < 1e-6 and abs(ax - vx[0]) < 1e-6:
                sgn = 1 if by >= ay else -1
                for o in w.get("openings", []):
                    pts += [(X0, ay + sgn * o["offset"]), (X0, ay + sgn * (o["offset"] + o["width"]))]
        return pts

    sh.dim_chain(facade_points("x") + [(X0, Y0), (X1, Y0)], (0, Y0 - d1))
    sh.dim_chain([(x, Y0) for x in vx], (0, Y0 - d2))
    sh.dim_chain([(X0, Y0), (X1, Y0)], (0, Y0 - d3))
    sh.dim_chain(facade_points("y") + [(X0, Y0), (X0, Y1)], (X0 - d1, 0), 90)
    sh.dim_chain([(X0, y) for y in hy], (X0 - d2, 0), 90)
    sh.dim_chain([(X0, Y0), (X0, Y1)], (X0 - d3, 0), 90)

    hall = next((r for r in rooms if "Kat Holü" in r["name"]), None) or next((r for r in rooms if "Hol" in r["name"]), None)
    if hall:
        pts = hall["points"]
        sh.kot_mark(sum(p[0] for p in pts) / len(pts) - sh.mm(4), min(p[1] for p in pts) + sh.mm(4), z0)
    if cut_x is not None:  # A-A kesit oku (bakış yönü: sol)
        for y in (Y0 - d3 - sh.mm(6), Y1 + db + br + sh.mm(5)):
            sh.line((cut_x, y - sh.mm(3)), (cut_x, y + sh.mm(3)), "A-KESIT-OKU")
            sh.line((cut_x, y), (cut_x - sh.mm(6), y), "A-KESIT-OKU")
            sh.hatch([[(cut_x - sh.mm(7), y), (cut_x - sh.mm(4.5), y + sh.mm(1.1)), (cut_x - sh.mm(4.5), y - sh.mm(1.1))]],
                     "A-KESIT-OKU", solid=True)
            sh.text("A", cut_x + sh.mm(2.5), y, 4.0, "A-KESIT-OKU", TA.MIDDLE_LEFT)
    sh.north(X1 + db + sh.mm(16), Y1 + db)
    sh.drawing_title(X0 - d3, Y0 - d3 - sh.mm(17), title)


# ================================================================== vaziyet

def draw_site(sh, elements, report, zoning, info):
    parcel = next(e for e in elements if e.get("name") == "parsel")
    P = [tuple(p) for p in parcel["points"]]
    W, D = P[1][0], P[2][1]
    fr, sd, rr = zoning.get("front", 5), zoning.get("side", 3), zoning.get("rear", 3)
    sh.poly(P, "A-PARSEL")
    sh.poly([(sd, fr), (W - sd, fr), (W - sd, D - rr), (sd, D - rr)], "A-CEKME")
    floor = next(e for e in elements if e["type"] == "slab" and e.get("role") == "floor")
    fp = [tuple(p) for p in floor["points"]]
    sh.poly(fp, "A-DUVAR")
    sh.hatch([fp], "A-DUVAR-TARAMA", "ANSI31", scale_mm=0.6)
    bx0, by0 = fp[0]
    bx1, by1 = fp[2]
    cx, cy = (bx0 + bx1) / 2, (by0 + by1) / 2
    nfl = report.get("floors", 1)
    sh.text(f"Z+{nfl - 1}" if nfl > 1 else "Z", cx, cy + sh.mm(3), 5.0)
    sh.text(f"{report.get('unit_count', '')} BAĞIMSIZ BÖLÜM  ·  ±0.00", cx, cy - sh.mm(3), 2.2)
    site = info.get("site") or {}
    sh.text(f"ADA {site.get('ada') or '—'}  ·  PARSEL {site.get('parsel') or '—'}", W / 2, D - rr / 2, 2.6)
    sh.line((-sh.mm(10), -sh.mm(2)), (W + sh.mm(10), -sh.mm(2)), "A-ZEMIN")
    sh.line((-sh.mm(10), -sh.mm(16)), (W + sh.mm(10), -sh.mm(16)), "A-ZEMIN")
    sh.text((site.get("road") or "YOL").upper(), W / 2, -sh.mm(9), 3.2)
    sh.line((cx, -sh.mm(2)), (cx, by0 - sh.mm(3)), "A-KESIT-OKU")
    sh.hatch([[(cx, by0), (cx - sh.mm(1.5), by0 - sh.mm(3)), (cx + sh.mm(1.5), by0 - sh.mm(3))]], "A-KESIT-OKU", solid=True)
    sh.text("GİRİŞ", cx + sh.mm(2), -sh.mm(5), 1.8, "A-YAZI", TA.MIDDLE_LEFT)
    sh.dim_chain([(0, D), (W, D)], (0, D + sh.mm(10)))
    sh.dim_chain([(W, 0), (W, D)], (W + sh.mm(10), 0), 90)
    yd = (by1 + D - rr) / 2  # yan çekme zinciri: bina ile arka çekme hattı arasında
    sh.dim_chain([(0, yd), (bx0, yd), (bx1, yd), (W, yd)], (0, yd))
    sh.dim_chain([(bx0, 0), (bx0, by0), (bx0, by1), (bx0, D)], (bx0 - sh.mm(6), 0), 90)
    lx, ly = W + sh.mm(26), D
    for i, (lay, txt) in enumerate([("A-PARSEL", "Mülkiyet (parsel) sınırı"), ("A-CEKME", "Yapı yaklaşma sınırı"),
                                    ("A-DUVAR", "Bina oturumu")]):
        yy = ly - i * sh.mm(6)
        sh.line((lx, yy), (lx + sh.mm(10), yy), lay)
        sh.text(txt, lx + sh.mm(13), yy, 2.0, "A-YAZI", TA.MIDDLE_LEFT)
    c = report["checks"]
    rows = [("İMAR DURUMU", "İZİN", "PROJE"),
            ("TAKS", f"{c['taks']['limit']:.2f}", f"{c['taks']['value']:.2f}"),
            ("KAKS (EMSAL)", f"{c['kaks']['limit']:.2f}", f"{c['kaks']['value']:.2f}"),
            ("KAT ADEDİ", str(c["floors"]["limit"]), str(c["floors"]["value"])),
            ("ÇEKME ÖN/YAN/ARKA (m)", f"{fr}/{sd}/{rr}",
             f"{c['setbacks']['front']:.2f}/{min(c['setbacks']['side_left'], c['setbacks']['side_right']):.2f}/{c['setbacks']['rear']:.2f}"),
            ("PARSEL ALANI", "", f"{tr_num(report['parcel_area'])} m²"),
            ("TABAN OTURUMU", "", f"{tr_num(report['footprint_gross'])} m²"),
            ("TOPLAM İNŞAAT ALANI", "", f"{tr_num(report['gross_total'])} m²")]
    tx, ty = lx, ly - sh.mm(26)
    cw, rh = [sh.mm(44), sh.mm(20), sh.mm(32)], sh.mm(5.5)
    for i, row in enumerate(rows):
        y = ty - i * rh
        sh.poly([(tx, y), (tx + sum(cw), y), (tx + sum(cw), y - rh), (tx, y - rh)], "A-YAZI")
        xx = tx
        for j, cell in enumerate(row):
            if j:
                sh.line((xx, y), (xx, y - rh), "A-YAZI")
            sh.text(cell, xx + sh.mm(1.5), y - rh / 2, 2.0, "A-YAZI", TA.MIDDLE_LEFT)
            xx += cw[j]
    sh.north(lx + sh.mm(86), ly - sh.mm(4))
    sh.drawing_title(0, -sh.mm(34), "VAZİYET PLANI")


# ================================================================== kesit / görünüş

def _levels(elements):
    fl = sorted({(e["z"], e["level"]) for e in elements if e["type"] == "slab" and e.get("role") == "floor"})
    roof = next((e for e in elements if e["type"] == "slab" and e.get("role") == "roof"), None)
    return fl, roof


def _pitched(elements):
    """Ana eğimli çatı (en büyük tabanlı 'roof' elemanı) veya None."""
    rs = [e for e in elements if e["type"] == "roof"]
    return max(rs, key=lambda e: (e["x1"] - e["x0"]) * (e["y1"] - e["y0"])) if rs else None


def _roof_top(roof, pitched, fl):
    if pitched:
        return pitched["z"] + pitched.get("ridge", 1.5) + pitched.get("thickness", 0.2)
    return (roof["z"] + 0.9) if roof else fl[-1][0] + 3


def draw_section(sh, elements, cut_x):
    fl, roof = _levels(elements)
    pitched = _pitched(elements)
    floor = next(e for e in elements if e["type"] == "slab" and e.get("role") == "floor")
    ys = [p[1] for p in floor["points"]]
    y0, y1 = min(ys), max(ys)
    X = lambda y: y - y0
    t = floor.get("thickness", 0.2)
    top = _roof_top(roof, pitched, fl)
    if pitched:
        from .quantities import roof_profile
        rt = pitched.get("thickness", 0.2)
        if pitched.get("axis", "x") == "x":
            prof = roof_profile(pitched)
        else:  # mahya kesit düzlemine paralel: kesitte saçak-mahya bandı görünür
            z = pitched["z"]
            prof = [(pitched["y0"], z + pitched.get("ridge", 1.5)), (pitched["y1"], z + pitched.get("ridge", 1.5))]
        lo = [(X(s), z) for s, z in prof]
        hi = [(X(s), z + rt) for s, z in reversed(prof)]
        sh.poly(lo + hi, "A-KESIT")
        sh.hatch([lo + hi], "A-KESIT", solid=True)
    gl, gr = X(y0) - sh.mm(15), X(y1) + sh.mm(15)
    sh.line((gl, -t), (gr, -t), "A-ZEMIN")
    sh.hatch([[(gl, -t), (gr, -t), (gr, -t - sh.mm(5)), (gl, -t - sh.mm(5))]], "A-DUVAR-TARAMA", "EARTH", scale_mm=0.5)
    slabs = [z for z, _ in fl] + ([roof["z"]] if roof else [])
    for z in slabs:
        pts = [(X(y0), z - t), (X(y1), z - t), (X(y1), z), (X(y0), z)]
        sh.poly(pts, "A-KESIT")
        sh.hatch([pts], "A-KESIT", solid=True)
    if roof:
        for yy in (y0, y1 - 0.25):
            pts = [(X(yy), roof["z"]), (X(yy + 0.25), roof["z"]), (X(yy + 0.25), top), (X(yy), top)]
            sh.poly(pts, "A-KESIT")
            sh.hatch([pts], "A-KESIT", solid=True)
    for w in elements:
        if w["type"] != "wall":
            continue
        (ax, ay), (bx, by) = w["start"], w["end"]
        if abs(ay - by) > 1e-6 or not (min(ax, bx) - 1e-6 <= cut_x <= max(ax, bx) + 1e-6):
            continue
        wt, zb, H = w.get("thickness", 0.2), w.get("base_z", 0), w.get("height", 2.8)
        s = abs(cut_x - ax)
        op = next((o for o in w.get("openings", []) if o["offset"] <= s <= o["offset"] + o["width"]), None)
        spans = [(0, H)]
        if op:
            sill = 0 if op["kind"] == "door" else op.get("sill", 0.9)
            head = sill + op.get("height", 2.1 if op["kind"] == "door" else 1.4)
            spans = [(0, sill), (head, H)]
            if op["kind"] == "window":
                for off in (-wt / 2, -wt / 10, wt / 10, wt / 2):
                    sh.line((X(ay + off), zb + sill), (X(ay + off), zb + head), "A-PENCERE")
        for a, b in spans:
            if b - a < 1e-3:
                continue
            pts = [(X(ay - wt / 2), zb + a), (X(ay + wt / 2), zb + a), (X(ay + wt / 2), zb + b), (X(ay - wt / 2), zb + b)]
            sh.poly(pts, "A-KESIT")
            sh.hatch([pts], "A-KESIT", solid=True)
    for z, lvl in fl:
        sh.text(level_title(lvl), X((y0 + y1) / 2), z + 1.3, 2.5)
    kx = X(y1) + sh.mm(10)
    for z in slabs + [top]:
        sh.kot_mark(kx, z, z, plan=False)
    sh.dim_chain([(X(y0), z) for z in [-t] + slabs + [top]], (X(y0) - sh.mm(10), 0), 90)
    sh.dim_chain([(X(y0), -t), (X(y0), top)], (X(y0) - sh.mm(18), 0), 90)
    sh.dim_chain([(X(y0), -t), (X(y1), -t)], (0, -t - sh.mm(10)))
    sh.drawing_title(X(y0) - sh.mm(18), -t - sh.mm(28), "A-A KESİTİ")


def draw_elevation(sh, elements):
    fl, roof = _levels(elements)
    pitched = _pitched(elements)
    floor = next(e for e in elements if e["type"] == "slab" and e.get("role") == "floor")
    xs = [p[0] for p in floor["points"]]
    x0, x1 = min(xs), max(xs)
    X = lambda x: x - x0
    top = _roof_top(roof, pitched, fl)
    t = floor.get("thickness", 0.2)
    if pitched:
        from .quantities import roof_profile
        ez, rt = pitched["z"], pitched.get("thickness", 0.2)
        sh.poly([(X(x0), -t), (X(x1), -t), (X(x1), ez), (X(x0), ez)], "A-GORUNUS")
        if pitched.get("axis", "x") == "x":  # mahya cepheye paralel: saçak ve mahya çizgileri
            rx0, rx1 = X(pitched["x0"]), X(pitched["x1"])
            sh.poly([(rx0, ez), (rx1, ez), (rx1, ez + rt), (rx0, ez + rt)], "A-GORUNUS")
            sh.line((rx0, top), (rx1, top), "A-GORUNUS")
        else:  # alınlık üçgeni cepheden görünür
            prof = roof_profile(pitched)
            sh.poly([(X(s), z) for s, z in prof] + [(X(s), z + rt) for s, z in reversed(prof)], "A-GORUNUS")
    else:
        sh.poly([(X(x0), -t), (X(x1), -t), (X(x1), top), (X(x0), top)], "A-GORUNUS")
    gl, gr = X(x0) - sh.mm(15), X(x1) + sh.mm(15)
    sh.line((gl, -t), (gr, -t), "A-ZEMIN")
    sh.hatch([[(gl, -t), (gr, -t), (gr, -t - sh.mm(4)), (gl, -t - sh.mm(4))]], "A-DUVAR-TARAMA", "EARTH", scale_mm=0.5)
    if roof:
        sh.line((X(x0), roof["z"]), (X(x1), roof["z"]), "A-GORUNUS-INCE")
    walls = [w for w in elements if w["type"] == "wall" and abs(w["start"][1] - w["end"][1]) < 1e-6]
    front_y = min(w["start"][1] for w in walls)
    for w in walls:
        if abs(w["start"][1] - front_y) > 1e-6:
            continue
        ax, bx = w["start"][0], w["end"][0]
        sgn = 1 if bx >= ax else -1
        zb = w.get("base_z", 0)
        for o in w.get("openings", []):
            a, b = sorted((ax + sgn * o["offset"], ax + sgn * (o["offset"] + o["width"])))
            sill = 0 if o["kind"] == "door" else o.get("sill", 0.9)
            h = o.get("height", 2.1 if o["kind"] == "door" else 1.4)
            lay = "A-PENCERE" if o["kind"] == "window" else "A-KAPI"
            sh.poly([(X(a), zb + sill), (X(b), zb + sill), (X(b), zb + sill + h), (X(a), zb + sill + h)], lay)
            f = 0.06
            sh.poly([(X(a) + f, zb + sill + f), (X(b) - f, zb + sill + f), (X(b) - f, zb + sill + h - f),
                     (X(a) + f, zb + sill + h - f)], "A-GORUNUS-INCE")
            if o["kind"] == "window":
                if b - a > 1.0:
                    sh.line((X((a + b) / 2), zb + sill + f), (X((a + b) / 2), zb + sill + h - f), "A-GORUNUS-INCE")
                sh.poly([(X(a) - 0.05, zb + sill - 0.05), (X(b) + 0.05, zb + sill - 0.05), (X(b) + 0.05, zb + sill),
                         (X(a) - 0.05, zb + sill)], "A-GORUNUS")
    kx = X(x1) + sh.mm(10)
    for z in [z for z, _ in fl] + [top]:
        sh.kot_mark(kx, z, z, plan=False)
    sh.dim_chain([(X(x0), -t), (X(x1), -t)], (0, -t - sh.mm(10)))
    sh.dim_chain([(X(x0), -t), (X(x0), top)], (X(x0) - sh.mm(10), 0), 90)
    sh.drawing_title(X(x0) - sh.mm(10), -t - sh.mm(28), "ÖN (SOKAK) GÖRÜNÜŞÜ")


# ================================================================== paket

def export_all(out_dir, elements, report, zoning, project, info=None):
    """Her pafta ayrı DXF + PNG; hepsi tek PDF (A3 yatay, gerçek ölçek). Dönen: {ad: yol}."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration, LineweightPolicy
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    info = {"project": project, **(info or {})}
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    levels = [e["level"] for e in elements if e["type"] == "slab" and e.get("role") == "floor"]
    ground = levels[0]
    typical = levels[1] if len(levels) > 1 else levels[0]
    walls = [e for e in elements if e["type"] == "wall" and e.get("level") == ground]
    salon = next((e for e in elements if e["type"] == "room" and e.get("level") == ground and "Salon" in e["name"]), None)
    cut_x = sum(p[0] for p in salon["points"]) / 4 if salon else sum(w["start"][0] for w in walls) / len(walls)
    n_up = len(levels) - 1

    specs = []
    if any(e.get("name") == "parsel" for e in elements):
        specs.append(("01_vaziyet", "A-00", "VAZİYET PLANI", lambda sh: draw_site(sh, elements, report, zoning, info), 200))
    gt = f"{level_title(ground)} PLANI"
    specs.append(("02_zemin_kat_plani", "A-01", gt, lambda sh: draw_plan(sh, elements, ground, cut_x, gt), 100))
    if typical != ground:
        tt = f"NORMAL KAT PLANI (1.–{n_up}. KATLAR)" if n_up > 1 else "1. KAT PLANI"
        specs.append(("03_normal_kat_plani", "A-02", tt, lambda sh: draw_plan(sh, elements, typical, cut_x, tt), 100))
    specs.append(("04_kesit_AA", "A-03", "A-A KESİTİ", lambda sh: draw_section(sh, elements, cut_x), 100))
    specs.append(("05_on_gorunus", "A-04", "ÖN GÖRÜNÜŞ", lambda sh: draw_elevation(sh, elements), 100))

    cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK,
                        lineweight_policy=LineweightPolicy.ABSOLUTE, lineweight_scaling=1.0)
    paths = {}
    pdf_path = out / "cizimler.pdf"
    with PdfPages(pdf_path) as pdf:
        for name, num, title, fn, min_s in specs:
            sh = compose(info, num, title, fn, min_scale=min_s)
            p = out / f"{name}.dxf"
            sh.doc.saveas(p)
            paths[name] = str(p)
            fig = plt.figure(figsize=(PAPER_W / 25.4, PAPER_H / 25.4))
            ax = fig.add_axes([0, 0, 1, 1])
            Frontend(RenderContext(sh.doc), MatplotlibBackend(ax, adjust_figure=False), config=cfg).draw_layout(sh.msp, finalize=False)
            ox, oy = sh.origin
            ax.set_xlim(ox, ox + sh.mm(PAPER_W))
            ax.set_ylim(oy, oy + sh.mm(PAPER_H))
            ax.set_aspect("equal", adjustable="box")
            ax.axis("off")
            pdf.savefig(fig)
            fig.savefig(out / f"{name}.png", dpi=110)
            plt.close(fig)
    paths["pdf"] = str(pdf_path)
    return paths
