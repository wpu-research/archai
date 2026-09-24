"""Teknik çizimler: kat planı, vaziyet planı, kesit, görünüş → DXF + çok sayfalı PDF.

Tüm çizimler metre biriminde (1 birim = 1 m), 1/100 ölçekte okunacak metin boyutlarıyla.
"""

import math
from datetime import date
from pathlib import Path

import logging

import ezdxf
from ezdxf.enums import TextEntityAlignment
from shapely.geometry import Polygon, box
from shapely.ops import unary_union

from .quantities import polygon_area

LAYERS = {  # ad: (ACI renk, çizgi kalınlığı 1/100 mm)
    "DUVAR": (7, 50), "DUVAR-TARAMA": (8, 13), "PENCERE": (4, 25), "KAPI": (3, 18), "MAHAL": (2, 18),
    "OLCU": (1, 13), "AKS": (8, 13), "MERDIVEN": (6, 18), "PARSEL": (5, 35), "CEKME": (1, 18),
    "KESIT": (7, 50), "GORUNUS": (7, 25), "YAZI": (7, 18), "ANTET": (7, 25),
}
TXT = 0.25
logging.getLogger("ezdxf").setLevel(logging.WARNING)


def _new_doc():
    doc = ezdxf.new("R2018", setup=True)
    doc.header["$INSUNITS"] = 6
    doc.header["$DIMSCALE"] = 1
    for name, (color, lw) in LAYERS.items():
        doc.layers.add(name, color=color, lineweight=lw)
    doc.layers.get("CEKME").dxf.linetype = "DASHED"
    doc.layers.get("AKS").dxf.linetype = "DASHDOT"
    ds = doc.dimstyles.new("ARCH100")
    ds.dxf.dimtxt, ds.dxf.dimasz, ds.dxf.dimexe, ds.dxf.dimexo = 0.18, 0.12, 0.1, 0.1
    ds.dxf.dimtsz, ds.dxf.dimdec, ds.dxf.dimlfac = 0.1, 2, 1
    ds.dxf.dimtad = 1
    ds2 = doc.dimstyles.duplicate_entry("ARCH100", "ARCH200")
    ds2.dxf.dimtxt, ds2.dxf.dimasz = 0.4, 0.25
    return doc


def _text(msp, s, x, y, h=TXT, layer="YAZI", align=TextEntityAlignment.MIDDLE_CENTER):
    msp.add_text(s, height=h, dxfattribs={"layer": layer}).set_placement((x, y), align=align)


def _title(msp, x0, y0, w, title, project, scale="1/100"):
    msp.add_lwpolyline([(x0, y0), (x0 + w, y0), (x0 + w, y0 - 1.6), (x0, y0 - 1.6)], close=True, dxfattribs={"layer": "ANTET"})
    _text(msp, title, x0 + 0.3, y0 - 0.5, 0.4, "ANTET", TextEntityAlignment.MIDDLE_LEFT)
    _text(msp, f"{project}   Ölçek {scale}   {date.today():%d.%m.%Y}   ŞEMATİK ÖN TASARIM", x0 + 0.3, y0 - 1.15, 0.2,
          "ANTET", TextEntityAlignment.MIDDLE_LEFT)


def _wall_frame(w):
    (x0, y0), (x1, y1) = w["start"], w["end"]
    L = math.hypot(x1 - x0, y1 - y0)
    u = ((x1 - x0) / L, (y1 - y0) / L)
    n = (-u[1], u[0])
    at = lambda s, off: (x0 + u[0] * s + n[0] * off, y0 + u[1] * s + n[1] * off)
    return L, u, n, at


def _rect(at, s0, s1, t):
    return Polygon([at(s0, -t / 2), at(s1, -t / 2), at(s1, t / 2), at(s0, t / 2)])


# ------------------------------------------------------------------ kat planı

def draw_plan(msp, elements, level, project, title=None):
    walls = [e for e in elements if e["type"] == "wall" and e.get("level") == level]
    rooms = [e for e in elements if e["type"] == "room" and e.get("level") == level]
    stairs = [e for e in elements if e["type"] == "stairs" and e.get("level") == level]
    solids = []
    for w in walls:
        L, u, n, at = _wall_frame(w)
        t = w.get("thickness", 0.2)
        # uçları yarım kalınlık uzat: birleşimlerde köşeler kapansın
        cuts = sorted((o["offset"], o["offset"] + o["width"]) for o in w.get("openings", []))
        s = -t / 2
        for a, b in cuts:
            solids.append(_rect(at, s, a, t))
            s = b
        solids.append(_rect(at, s, L + t / 2, t))
        for o in w.get("openings", []):
            a, b = o["offset"], o["offset"] + o["width"]
            if o["kind"] == "window":
                for off in (-t / 6, t / 6):
                    msp.add_line(at(a, off), at(b, off), dxfattribs={"layer": "PENCERE"})
                for off in (-t / 2, t / 2):
                    msp.add_line(at(a, off), at(b, off), dxfattribs={"layer": "PENCERE"})
            else:
                wd = b - a
                hinge = at(a, t / 2)
                tip = (hinge[0] + n[0] * wd, hinge[1] + n[1] * wd)
                msp.add_line(hinge, tip, dxfattribs={"layer": "KAPI"})
                a0 = math.degrees(math.atan2(u[1], u[0]))
                msp.add_arc(hinge, wd, a0, a0 + 90, dxfattribs={"layer": "KAPI"})
    # adım adım birleşim: pencere boşluklarını dolduran komşu parçaları kesmemek için buffer yok
    geom = unary_union([g for g in solids if g.area > 1e-6])
    polys = [geom] if geom.geom_type == "Polygon" else list(geom.geoms)
    for p in polys:
        for ring in [p.exterior, *p.interiors]:
            msp.add_lwpolyline(list(ring.coords), close=True, dxfattribs={"layer": "DUVAR"})
        h = msp.add_hatch(color=8, dxfattribs={"layer": "DUVAR-TARAMA"})
        h.set_pattern_fill("ANSI31", scale=0.02)
        h.paths.add_polyline_path(list(p.exterior.coords), is_closed=True, flags=1)
        for ring in p.interiors:
            h.paths.add_polyline_path(list(ring.coords), is_closed=True, flags=16)

    for r in rooms:
        pts = [tuple(p) for p in r["points"]]
        cx = sum(p[0] for p in pts) / len(pts)
        cy = sum(p[1] for p in pts) / len(pts)
        name = r["name"].split("/")[-1]
        _text(msp, name, cx, cy + 0.18, 0.2, "MAHAL")
        _text(msp, f"{polygon_area(pts):.2f} m²", cx, cy - 0.18, 0.16, "MAHAL")
    for s in stairs:
        ox, oy, _ = s["origin"]
        rot = math.radians(s.get("rotation_z", 0))
        c, sn = math.cos(rot), math.sin(rot)
        run, width = s.get("run", 0.28), s.get("width", 1.2)
        for i in range(s.get("steps", 10) + 1):
            d = i * run
            p0 = (ox + c * d, oy + sn * d)
            p1 = (p0[0] - sn * width, p0[1] + c * width)
            msp.add_line(p0, p1, dxfattribs={"layer": "MERDIVEN"})

    # ölçüler: dış ölçü + aks zinciri (alt ve sol)
    xs = sorted({round(v, 3) for w in walls for v in (w["start"][0], w["end"][0]) if w["start"][0] == w["end"][0]})
    ys = sorted({round(v, 3) for w in walls for v in (w["start"][1], w["end"][1]) if w["start"][1] == w["end"][1]})
    if xs and ys:
        tmax = max(w.get("thickness", 0.2) for w in walls)
        x0, x1, y0, y1 = xs[0] - tmax / 2, xs[-1] + tmax / 2, ys[0] - tmax / 2, ys[-1] + tmax / 2
        for a, b in zip(xs, xs[1:]):
            msp.add_linear_dim(base=(0, y0 - 1.0), p1=(a, y0), p2=(b, y0), dimstyle="ARCH100",
                               dxfattribs={"layer": "OLCU"}).render()
        msp.add_linear_dim(base=(0, y0 - 1.8), p1=(x0, y0), p2=(x1, y0), dimstyle="ARCH100",
                           dxfattribs={"layer": "OLCU"}).render()
        for a, b in zip(ys, ys[1:]):
            msp.add_linear_dim(base=(x0 - 1.0, 0), p1=(x0, a), p2=(x0, b), angle=90, dimstyle="ARCH100",
                               dxfattribs={"layer": "OLCU"}).render()
        msp.add_linear_dim(base=(x0 - 1.8, 0), p1=(x0, y0), p2=(x0, y1), angle=90, dimstyle="ARCH100",
                           dxfattribs={"layer": "OLCU"}).render()
        _title(msp, x0 - 2.0, y0 - 2.6, (x1 - x0) + 4.0, title or f"{level} Planı", project)
        return (x0 - 2.5, y0 - 4.5, x1 + 1.0, y1 + 1.0)


# ------------------------------------------------------------------ vaziyet

def draw_site(msp, elements, report, zoning, project):
    parcel = next(e for e in elements if e.get("name") == "parsel")
    P = [tuple(p) for p in parcel["points"]]
    msp.add_lwpolyline(P, close=True, dxfattribs={"layer": "PARSEL"})
    W, D = P[1][0], P[2][1]
    fr, sd, rr = zoning.get("front", 5), zoning.get("side", 3), zoning.get("rear", 3)
    msp.add_lwpolyline([(sd, fr), (W - sd, fr), (W - sd, D - rr), (sd, D - rr)], close=True, dxfattribs={"layer": "CEKME"})
    floor = next(e for e in elements if e["type"] == "slab" and e.get("role") == "floor")
    fp = [tuple(p) for p in floor["points"]]
    msp.add_lwpolyline(fp, close=True, dxfattribs={"layer": "DUVAR"})
    h = msp.add_hatch(color=8, dxfattribs={"layer": "DUVAR-TARAMA"})
    h.set_pattern_fill("ANSI37", scale=0.08)
    h.paths.add_polyline_path(fp, is_closed=True)
    cx = sum(p[0] for p in fp) / 4
    cy = sum(p[1] for p in fp) / 4
    _text(msp, f"{report['floors']} KAT  {report['unit_count']} DAİRE ({report['unit_type']})", cx, cy + 0.4, 0.4)
    _text(msp, f"Taban brüt {report['footprint_gross']:.2f} m²", cx, cy - 0.4, 0.3)
    _text(msp, "SOKAK", W / 2, -1.5, 0.5)
    msp.add_line((-2, -0.6), (W + 2, -0.6), dxfattribs={"layer": "PARSEL"})
    # çekme ölçüleri
    bx0, by0 = fp[0]
    bx1, by1 = fp[2]
    for p1, p2, base, ang in [((bx0, by0), (bx0, 0), (bx0 - 0.8, 0), 90), ((0, cy), (bx0, cy), (0, cy + 0.8), 0),
                              ((bx1, cy), (W, cy), (0, cy + 0.8), 0), ((bx0, by1), (bx0, D), (bx0 - 0.8, 0), 90)]:
        msp.add_linear_dim(base=base, p1=p1, p2=p2, angle=ang, dimstyle="ARCH200", dxfattribs={"layer": "OLCU"}).render()
    msp.add_linear_dim(base=(0, D + 1.5), p1=(0, D), p2=(W, D), dimstyle="ARCH200", dxfattribs={"layer": "OLCU"}).render()
    msp.add_linear_dim(base=(W + 1.5, 0), p1=(W, 0), p2=(W, D), angle=90, dimstyle="ARCH200", dxfattribs={"layer": "OLCU"}).render()
    # kuzey oku + imar tablosu
    msp.add_lwpolyline([(W + 3, D - 1), (W + 3.4, D - 2.2), (W + 3, D - 1.9), (W + 2.6, D - 2.2)], close=True,
                       dxfattribs={"layer": "YAZI"})
    _text(msp, "K", W + 3, D - 0.6, 0.4)
    c = report["checks"]
    rows = [("Parsel alanı", f"{report['parcel_area']:.2f} m²"),
            ("TAKS (izin / proje)", f"{c['taks']['limit']:.2f} / {c['taks']['value']:.3f}"),
            ("KAKS (izin / proje)", f"{c['kaks']['limit']:.2f} / {c['kaks']['value']:.3f}"),
            ("Kat (izin / proje)", f"{c['floors']['limit']} / {c['floors']['value']}"),
            ("Çekme ön / yan / arka", f"{fr} / {sd} / {rr} m"),
            ("Toplam inşaat alanı", f"{report['gross_total']:.2f} m²")]
    tx, ty = W + 2.0, D - 4.0
    for i, (k, v) in enumerate(rows):
        _text(msp, k, tx, ty - i * 0.6, 0.22, "YAZI", TextEntityAlignment.MIDDLE_LEFT)
        _text(msp, v, tx + 5.2, ty - i * 0.6, 0.22, "YAZI", TextEntityAlignment.MIDDLE_LEFT)
    _title(msp, -2, -3.0, W + 12, "Vaziyet Planı", project, "1/200")
    return (-3, -5, W + 10, D + 3)


# ------------------------------------------------------------------ kesit ve görünüş

def _levels(elements):
    fl = sorted({(e["z"], e["level"]) for e in elements if e["type"] == "slab" and e.get("role") == "floor"})
    roof = next((e for e in elements if e["type"] == "slab" and e.get("role") == "roof"), None)
    return fl, roof


def draw_section(msp, elements, cut_x, project, ox=0.0):
    """A-A kesiti: x = cut_x düzleminde, y ekseni boyunca bakış. Çizimde yatay = y, düşey = z."""
    fl, roof = _levels(elements)
    floor = next(e for e in elements if e["type"] == "slab" and e.get("role") == "floor")
    ys = [p[1] for p in floor["points"]]
    y0, y1 = min(ys), max(ys)
    X = lambda y: ox + (y - y0)
    msp.add_line((X(y0) - 3, 0), (X(y1) + 3, 0), dxfattribs={"layer": "KESIT"})
    for z, lvl in fl + ([(roof["z"], "Çatı")] if roof else []):
        t = 0.2
        msp.add_lwpolyline([(X(y0), z - t), (X(y1), z - t), (X(y1), z), (X(y0), z)], close=True, dxfattribs={"layer": "KESIT"})
        h = msp.add_hatch(color=8, dxfattribs={"layer": "DUVAR-TARAMA"})
        h.set_solid_fill(color=8)
        h.paths.add_polyline_path([(X(y0), z - t), (X(y1), z - t), (X(y1), z), (X(y0), z)], is_closed=True)
        _text(msp, f"{'±' if z == 0 else '+'}{z:.2f}", X(y1) + 1.4, z, 0.2, "YAZI")
        _text(msp, lvl, X(y0) - 1.8, z + 1.3, 0.22, "YAZI")
    if roof:
        top = roof["z"] + 0.9
        for yy in (y0, y1 - 0.25):
            msp.add_lwpolyline([(X(yy), roof["z"]), (X(yy + 0.25), roof["z"]), (X(yy + 0.25), top), (X(yy), top)],
                               close=True, dxfattribs={"layer": "KESIT"})
    # kesilen duvarlar: x = cut_x'i kesen yatay (h) duvarlar
    for w in elements:
        if w["type"] != "wall":
            continue
        (ax, ay), (bx, by) = w["start"], w["end"]
        if abs(ay - by) > 1e-6 or not (min(ax, bx) - 1e-6 <= cut_x <= max(ax, bx) + 1e-6):
            continue
        t, zb, H = w.get("thickness", 0.2), w.get("base_z", 0), w.get("height", 2.8)
        s = abs(cut_x - ax)
        op = next((o for o in w.get("openings", []) if o["offset"] <= s <= o["offset"] + o["width"]), None)
        spans = [(0, H)]
        if op:
            sill = 0 if op["kind"] == "door" else op.get("sill", 0.9)
            top = sill + op.get("height", 2.1 if op["kind"] == "door" else 1.4)
            spans = [(0, sill), (top, H)]
            if op["kind"] == "window":
                msp.add_line((X(ay), zb + sill), (X(ay), zb + top), dxfattribs={"layer": "PENCERE"})
        for a, b in spans:
            if b - a < 1e-3:
                continue
            pts = [(X(ay - t / 2), zb + a), (X(ay + t / 2), zb + a), (X(ay + t / 2), zb + b), (X(ay - t / 2), zb + b)]
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "KESIT"})
            h = msp.add_hatch(color=8, dxfattribs={"layer": "DUVAR-TARAMA"})
            h.set_solid_fill(color=8)
            h.paths.add_polyline_path(pts, is_closed=True)
    H = (roof["z"] + 0.9) if roof else fl[-1][0] + 3
    msp.add_linear_dim(base=(X(y0) - 3.2, 0), p1=(X(y0), 0), p2=(X(y0), H), angle=90, dimstyle="ARCH100",
                       dxfattribs={"layer": "OLCU"}).render()
    _title(msp, X(y0) - 4, -1.5, (y1 - y0) + 8, "A-A Kesiti", project)
    return (X(y0) - 5, -3.5, X(y1) + 3, H + 1.5)


def draw_elevation(msp, elements, project, ox=0.0):
    """Ön (sokak) görünüşü: y = en küçük aks çizgisindeki duvarlar. Yatay = x, düşey = z."""
    fl, roof = _levels(elements)
    floor = next(e for e in elements if e["type"] == "slab" and e.get("role") == "floor")
    xs = [p[0] for p in floor["points"]]
    x0, x1 = min(xs), max(xs)
    X = lambda x: ox + (x - x0)
    top = (roof["z"] + 0.9) if roof else fl[-1][0] + 3
    msp.add_lwpolyline([(X(x0), 0), (X(x1), 0), (X(x1), top), (X(x0), top)], close=True, dxfattribs={"layer": "GORUNUS"})
    msp.add_line((X(x0) - 3, 0), (X(x1) + 3, 0), dxfattribs={"layer": "KESIT"})
    for z, _ in fl[1:] + ([(roof["z"], "")] if roof else []):
        msp.add_line((X(x0), z), (X(x1), z), dxfattribs={"layer": "AKS"})
    walls = [w for w in elements if w["type"] == "wall" and abs(w["start"][1] - w["end"][1]) < 1e-6]
    front_y = min(w["start"][1] for w in walls)
    for w in walls:
        if abs(w["start"][1] - front_y) > 1e-6:
            continue
        ax, bx = w["start"][0], w["end"][0]
        sgn = 1 if bx >= ax else -1
        for o in w.get("openings", []):
            a, b = ax + sgn * o["offset"], ax + sgn * (o["offset"] + o["width"])
            a, b = min(a, b), max(a, b)
            zb = w.get("base_z", 0)
            sill = 0 if o["kind"] == "door" else o.get("sill", 0.9)
            h = o.get("height", 2.1 if o["kind"] == "door" else 1.4)
            pts = [(X(a), zb + sill), (X(b), zb + sill), (X(b), zb + sill + h), (X(a), zb + sill + h)]
            msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": "PENCERE" if o["kind"] == "window" else "KAPI"})
            if o["kind"] == "window":
                msp.add_line((X((a + b) / 2), zb + sill), (X((a + b) / 2), zb + sill + h), dxfattribs={"layer": "PENCERE"})
                msp.add_lwpolyline([(X(a) - 0.05, zb + sill - 0.05), (X(b) + 0.05, zb + sill - 0.05),
                                    (X(b) + 0.05, zb + sill), (X(a) - 0.05, zb + sill)], close=True,
                                   dxfattribs={"layer": "GORUNUS"})
    msp.add_linear_dim(base=(0, -1.0), p1=(X(x0), 0), p2=(X(x1), 0), dimstyle="ARCH100", dxfattribs={"layer": "OLCU"}).render()
    msp.add_linear_dim(base=(X(x1) + 1.2, 0), p1=(X(x1), 0), p2=(X(x1), top), angle=90, dimstyle="ARCH100",
                       dxfattribs={"layer": "OLCU"}).render()
    _title(msp, X(x0) - 2, -2.2, (x1 - x0) + 6, "Ön Görünüş", project)
    return (X(x0) - 3, -4.2, X(x1) + 3, top + 1.5)


# ------------------------------------------------------------------ paket

def export_all(out_dir, elements, report, zoning, project):
    """Her çizim ayrı DXF + hepsi tek PDF. Dönen: {ad: yol}."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    levels = [e["level"] for e in elements if e["type"] == "slab" and e.get("role") == "floor"]
    ground = levels[0]
    typical = levels[1] if len(levels) > 1 else levels[0]
    walls = [e for e in elements if e["type"] == "wall" and e.get("level") == ground]
    # kesit düzlemi: A dairesi salonunun ortası (yoksa bina ortası)
    salon = next((e for e in elements if e["type"] == "room" and e.get("level") == ground and "Salon" in e["name"]), None)
    cut_x = sum(p[0] for p in salon["points"]) / 4 if salon else sum(w["start"][0] for w in walls) / len(walls)

    sheets = [("01_vaziyet", lambda m: draw_site(m, elements, report, zoning, project)),
              ("02_zemin_kat_plani", lambda m: draw_plan(m, elements, ground, project, "Zemin Kat Planı")),
              ("03_normal_kat_plani", lambda m: draw_plan(m, elements, typical, project, f"Normal Kat Planı ({typical})")),
              ("04_kesit_AA", lambda m: draw_section(m, elements, cut_x, project)),
              ("05_on_gorunus", lambda m: draw_elevation(m, elements, project))]
    if typical == ground:
        sheets.pop(2)
    paths = {}
    cfg = Configuration(background_policy=BackgroundPolicy.WHITE, color_policy=ColorPolicy.BLACK,
                        lineweight_scaling=1.2, min_lineweight=0.1)
    pdf_path = out / "cizimler.pdf"
    with PdfPages(pdf_path) as pdf:
        for name, fn in sheets:
            doc = _new_doc()
            msp = doc.modelspace()
            ext = fn(msp)
            # kesit çizgisini planlarda göster
            if "plani" in name and ext:
                msp.add_line((cut_x, ext[1] + 0.8), (cut_x, ext[3] - 0.3), dxfattribs={"layer": "AKS"})
                _text(msp, "A", cut_x, ext[3] - 0.1, 0.35)
                _text(msp, "A", cut_x, ext[1] + 0.6, 0.35)
            p = out / f"{name}.dxf"
            doc.saveas(p)
            paths[name] = str(p)
            fig = plt.figure(figsize=(16.54, 11.69))  # A3 yatay
            ax = fig.add_axes([0.02, 0.02, 0.96, 0.96])
            Frontend(RenderContext(doc), MatplotlibBackend(ax), config=cfg).draw_layout(msp)
            ax.set_aspect("equal")
            if ext:
                x0, y0, x1, y1 = ext
                cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
                half = max((x1 - x0) / 2 / 0.96 * 1.0, (y1 - y0) / 2 * 16.54 / 11.69)
                ax.set_xlim(cx - half, cx + half)
                ax.set_ylim(cy - half * 11.69 / 16.54, cy + half * 11.69 / 16.54)
            ax.axis("off")
            pdf.savefig(fig)
            fig.savefig(out / f"{name}.png", dpi=110)
            plt.close(fig)
    paths["pdf"] = str(pdf_path)
    return paths
