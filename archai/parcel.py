"""Çokgen (yamuk / düzensiz) parsel desteği.

Üretici (`generate`) dikdörtgen parselle çalışır. Çokgen parselde:
  1. parsel, ön cephe kenarı x ekseninde olacak şekilde döndürülür (yerel parsel koordinatı; `rotation_deg` raporda),
  2. kenar başına çekme uygulanıp yapılaşma alanı çıkarılır (ön / yan / arka kenarlar ayrı sınıflanır),
  3. yapılaşma alanına sığan en büyük eksen hizalı dikdörtgen bulunur,
  4. üretici o dikdörtgeni sıfır çekmeli sanal parsel sayarak çalıştırılır (TAKS/KAKS gerçek parsel alanına göre ölçeklenir),
  5. elemanlar yerine taşınır, arazi döşemesi gerçek çokgenle değiştirilir, imar kontrolleri gerçek alan ve gerçek
     kenar mesafeleriyle yeniden hesaplanır.

Bina eksen hizalı dikdörtgen kalır (üreticinin plan şemaları dikdörtgen kütle ister); çokgenin kalan kısmı bahçe olur.
"""
import math

from shapely.geometry import LineString, Polygon, box
from shapely.ops import unary_union

from .generate import emsal_disi_m2, generate
from .imar import imar_summary
from .quantities import polygon_area

STEP = 0.5            # dikdörtgen araması ızgarası (m)
MIN_EDGE = 3.0        # ön cephe adayı en az bu uzunlukta olmalı (m)
EARTH_R = 6371008.8


# ------------------------------------------------------------------ girdi

def to_metric(pts):
    """Boylam/enlem (derece) listesini yerel metreye çevirir; zaten metre ise aynen döner."""
    if not all(abs(x) <= 180 and abs(y) <= 90 for x, y in pts):
        return [tuple(p) for p in pts]
    lat0 = sum(y for _, y in pts) / len(pts)
    kx = math.radians(1) * EARTH_R * math.cos(math.radians(lat0))
    ky = math.radians(1) * EARTH_R
    x0, y0 = pts[0]
    return [((x - x0) * kx, (y - y0) * ky) for x, y in pts]


def polygon_from_dxf(path):
    """TKGM / kadastro DXF'inden parsel çokgeni: kapalı POLYLINE/LWPOLYLINE, yoksa POINT'ler sırayla.
    Dönen: (metrik köşeler, {"geographic": bool, "source": ...}). Koordinat derece ise yerel metreye çevrilir."""
    import ezdxf
    doc = ezdxf.readfile(str(path))
    pts = None
    for e in doc.modelspace():
        t = e.dxftype()
        if t == "LWPOLYLINE" and e.closed:
            pts = [(p[0], p[1]) for p in e.get_points()]
        elif t == "POLYLINE" and e.is_closed:
            pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
        if pts:
            break
    source = "polyline"
    if not pts:
        pts = [(e.dxf.location.x, e.dxf.location.y) for e in doc.modelspace() if e.dxftype() == "POINT"]
        source = "points"
    if len(pts) < 3:
        raise ValueError("DXF'te parsel çokgeni bulunamadı (kapalı polyline veya en az 3 nokta gerekir)")
    geo = all(abs(x) <= 180 and abs(y) <= 90 for x, y in pts)
    return to_metric(pts), {"geographic": geo, "source": source}


def polygon_from_geojson(text):
    """GeoJSON (TKGM parsel sorgu çıktısı dahil): ilk Polygon / MultiPolygon'un dış halkası; koordinat derece ise yerel metreye çevrilir."""
    import json
    d = json.loads(text)
    geoms = []

    def walk(o):
        if isinstance(o, dict):
            t = o.get("type")
            if t == "FeatureCollection":
                for f in o.get("features", []):
                    walk(f)
            elif t == "Feature":
                walk(o.get("geometry"))
            elif t == "GeometryCollection":
                for g in o.get("geometries", []):
                    walk(g)
            elif t in ("Polygon", "MultiPolygon"):
                geoms.append(o)
    walk(d)
    if not geoms:
        raise ValueError("GeoJSON'da Polygon bulunamadı")
    g = geoms[0]
    ring = g["coordinates"][0] if g["type"] == "Polygon" else g["coordinates"][0][0]
    pts = [(float(p[0]), float(p[1])) for p in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        raise ValueError("parsel çokgeni en az 3 köşe içermeli")
    return to_metric(pts), {"geographic": all(abs(x) <= 180 and abs(y) <= 90 for x, y in pts), "source": "geojson"}


def polygon_from_kml(text):
    """KML: ilk <Polygon> dış halkasındaki <coordinates> (boylam,enlem[,yükseklik])."""
    import re
    m = re.search(r"<Polygon.*?<outerBoundaryIs>.*?<coordinates>(.*?)</coordinates>", text, re.S | re.I) or \
        re.search(r"<coordinates>(.*?)</coordinates>", text, re.S | re.I)
    if not m:
        raise ValueError("KML'de koordinat bulunamadı")
    pts = []
    for tok in m.group(1).split():
        parts = tok.split(",")
        if len(parts) >= 2:
            pts.append((float(parts[0]), float(parts[1])))
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    if len(pts) < 3:
        raise ValueError("parsel çokgeni en az 3 köşe içermeli")
    return to_metric(pts), {"geographic": all(abs(x) <= 180 and abs(y) <= 90 for x, y in pts), "source": "kml"}


def polygon_from_file(path):
    """Uzantıya göre parsel çokgeni: .dxf (TKGM/kadastro), .geojson/.json, .kml."""
    from pathlib import Path
    ext = Path(path).suffix.lower()
    if ext == ".dxf":
        return polygon_from_dxf(path)
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    if ext in (".geojson", ".json"):
        return polygon_from_geojson(text)
    if ext == ".kml":
        return polygon_from_kml(text)
    raise ValueError("desteklenen parsel dosyaları: .dxf, .geojson, .json, .kml")


# ------------------------------------------------------------------ geometri

def _ccw(pts):
    a = sum(pts[i][0] * pts[(i + 1) % len(pts)][1] - pts[(i + 1) % len(pts)][0] * pts[i][1] for i in range(len(pts)))
    return pts if a > 0 else pts[::-1]


def _clean(pts):
    """Yinelenen ve art arda aynı köşeleri at."""
    out = []
    for p in pts:
        if not out or math.dist(p, out[-1]) > 1e-6:
            out.append(tuple(p))
    if len(out) > 1 and math.dist(out[0], out[-1]) < 1e-6:
        out.pop()
    return out


def _frame(pts, i):
    """i. kenar (pts[i] → pts[i+1]) x eksenine, parsel içi +y tarafına gelecek şekilde döndür; sol-alt köşeyi sıfırla.
    Dönen: (döndürülmüş köşeler, açı derece). pts saat yönünün tersi (CCW) olmalı."""
    a, b = pts[i], pts[(i + 1) % len(pts)]
    th = -math.atan2(b[1] - a[1], b[0] - a[0])
    c, s = math.cos(th), math.sin(th)
    R = [((x - a[0]) * c - (y - a[1]) * s, (x - a[0]) * s + (y - a[1]) * c) for x, y in pts]
    mx, my = min(x for x, _ in R), min(y for _, y in R)
    return [(x - mx, y - my) for x, y in R], math.degrees(th)


def _classify(pts, front):
    """Kenar sınıfı: ön / arka (ön kenara paralel ve karşıda) / yan. pts döndürülmüş çerçevede, front = ön kenar indeksi."""
    n = len(pts)
    cy = sum(y for _, y in pts) / n
    out = {}
    for i in range(n):
        a, b = pts[i], pts[(i + 1) % n]
        if i == front:
            out[i] = "front"
            continue
        dx, dy = b[0] - a[0], b[1] - a[1]
        ln = math.hypot(dx, dy) or 1.0
        parallel = abs(dy) / ln < 0.5                     # ön kenara ≤ 30° açıyla
        out[i] = "rear" if parallel and (a[1] + b[1]) / 2 > cy else "side"
    return out


def _buildable(poly, pts, classes, zoning):
    lim = {"front": zoning.get("front", 5), "side": zoning.get("side", 3), "rear": zoning.get("rear", 3)}
    strips = []
    for i, cls in classes.items():
        a, b = pts[i], pts[(i + 1) % len(pts)]
        if lim[cls] > 0:
            strips.append(LineString([a, b]).buffer(lim[cls], cap_style=2, join_style=2))
    area = poly.difference(unary_union(strips)) if strips else poly
    if area.is_empty:
        return None
    if area.geom_type != "Polygon":                         # MultiPolygon / GeometryCollection: en büyük poligon
        polys = [g for g in getattr(area, "geoms", []) if g.geom_type == "Polygon" and not g.is_empty]
        if not polys:
            return None
        area = max(polys, key=lambda g: g.area)
    return area


def _best_rect(area, step=STEP):
    """Yapılaşma alanı içindeki en büyük eksen hizalı dikdörtgen: (x0, y0, x1, y1) veya None."""
    x0, y0, x1, y1 = area.bounds
    ys = [y0 + k * step for k in range(int((y1 - y0) / step) + 1)] + [y1]
    best, best_a = None, 0.0
    for i, ya in enumerate(ys):
        for yb in ys[i + 1:]:
            if (yb - ya) * (x1 - x0) <= best_a:
                continue
            xs = []
            for y in (ya, yb):
                seg = area.intersection(LineString([(x0 - 1, y), (x1 + 1, y)]))
                if seg.is_empty:
                    xs = None
                    break
                b = seg.bounds
                xs.append((b[0], b[2]))
            if not xs:
                continue
            a0, a1 = max(xs[0][0], xs[1][0]), min(xs[0][1], xs[1][1])
            if a1 - a0 <= 0:
                continue
            r = box(a0, ya, a1, yb)
            if not area.buffer(1e-6).contains(r):
                continue
            if r.area > best_a:
                best, best_a = (a0, ya, a1, yb), r.area
    return best


def fit(points, zoning, front_edge=None, rank=0):
    """Çokgeni yerleştir. points: metrik köşeler. front_edge: ön cephe kenarı indeksi (pts[i]→pts[i+1]; None → en geniş
    yapılaşma dikdörtgenini veren kenar). Dönen sözlük: pts (yerel), area, front_edge, classes, buildable, box, rotation_deg."""
    pts = _ccw(_clean([tuple(p) for p in points]))
    if len(pts) < 3 or not Polygon(pts).is_valid or Polygon(pts).area < 20:
        raise ValueError("parsel çokgeni geçersiz (en az 3 köşe, kendini kesmeyen, ≥ 20 m²)")
    n = len(pts)
    cands = [front_edge] if front_edge is not None else [
        i for i in range(n) if math.dist(pts[i], pts[(i + 1) % n]) >= MIN_EDGE]
    if front_edge is not None and not 0 <= front_edge < n:
        raise ValueError(f"ön cephe kenarı 0..{n - 1} arasında olmalı")
    found = []
    for i in cands:
        loc, ang = _frame(pts, i)
        poly = Polygon(loc)
        cls = _classify(loc, i)
        area = _buildable(poly, loc, cls, zoning)
        rect = _best_rect(area) if area is not None else None
        if rect is None:
            continue
        w, d = rect[2] - rect[0], rect[3] - rect[1]
        found.append(((w >= 8 and d >= 8, w * d), i, loc, ang, cls, area, rect))
    if not found:
        raise ValueError("çekmelerden sonra parselde bina oturacak dikdörtgen alan kalmıyor")
    found.sort(key=lambda t: t[0], reverse=True)
    _, i, loc, ang, cls, area, rect = found[min(rank, len(found) - 1)]
    return {"pts": loc, "area": Polygon(loc).area, "front_edge": i, "classes": cls, "rotation_deg": round(ang, 2),
            "buildable": [tuple(p) for p in area.exterior.coords][:-1], "box": rect, "edges": n}


# ------------------------------------------------------------------ üretim

def _shift(e, dx, dy):
    for k in ("points",):
        if k in e:
            e[k] = [[round(p[0] + dx, 3), round(p[1] + dy, 3), *p[2:]] for p in e[k]]
    for k in ("start", "end"):
        if k in e:
            e[k] = [round(e[k][0] + dx, 3), round(e[k][1] + dy, 3)]
    if "origin" in e:
        e["origin"] = [round(e["origin"][0] + dx, 3), round(e["origin"][1] + dy, 3), *e["origin"][2:]]
    for k in ("x0", "x1"):
        if k in e:
            e[k] = round(e[k] + dx, 3)
    for k in ("y0", "y1"):
        if k in e:
            e[k] = round(e[k] + dy, 3)


def _edge_distances(outline, pts, classes):
    """Bina dış yüzünden ilgili kenarlara en kısa mesafe: ön, sol yan, sağ yan, arka (parsel çerçevesinde)."""
    b = Polygon(outline)
    cx = b.centroid.x
    d = {"front": [], "side_left": [], "side_right": [], "rear": []}
    n = len(pts)
    for i, cls in classes.items():
        seg = LineString([pts[i], pts[(i + 1) % n]])
        if cls == "side":
            d["side_left" if seg.centroid.x < cx else "side_right"].append(b.distance(seg))
        else:
            d[cls].append(b.distance(seg))
    return {k: (math.floor(min(v) * 1000 + 1e-6) / 1000 if v else float("inf")) for k, v in d.items()}


def generate_on_polygon(parcel, zoning, program):
    # zoning["emsal_yok"]: TAKS/KAKS sınırı yok (ör. dönüşüm hakkı / avan tablosunda yazılı değil) → bağlayıcı olmasın
    if zoning.get("emsal_yok"):
        zoning = {**zoning, "taks": 1.0, "kaks": 10.0}
    """parcel["polygon"] (metrik köşeler) ile üret. Dönen: (elements, report) — `generate` ile aynı biçim,
    ek olarak report["parcel_geom"] (çokgen, yapılaşma alanı, ön kenar, dönüklük, kenar sınıfları)."""
    ranks = [0] if parcel.get("front_edge") is not None else range(3)      # ön kenar verilmediyse en iyi 3 adayı dene
    best = None
    for rk in ranks:
        try:
            f = fit(parcel["polygon"], zoning, parcel.get("front_edge"), rank=rk)
            els, rep = _generate_fitted(f, parcel, zoning, program)
        except ValueError as ex:
            err = ex
            continue
        score = (rep["units_per_floor"] * rep["floors"], rep["gross_total"])
        if best is None or score > best[0]:
            best = (score, els, rep)
    if best is None:
        raise err
    return best[1], best[2]


def _generate_fitted(f, parcel, zoning, program):
    x0, y0, x1, y1 = f["box"]
    bw, bd = x1 - x0, y1 - y0
    A, Ab = f["area"], bw * bd
    zv = {**zoning, "front": 0, "side": 0, "rear": 0, "taks": zoning.get("taks", 0.4) * A / Ab,
          "kaks": zoning.get("kaks", 1.2) * A / Ab}
    els, rep = generate({"width": round(bw, 3), "depth": round(bd, 3)}, zv, program)
    for e in els:
        _shift(e, x0, y0)
    poly = [[round(x, 3), round(y, 3)] for x, y in f["pts"]]
    for e in els:
        if e.get("name") == "parsel":
            e["points"] = poly
        elif e.get("name") == "giris_yolu":     # giriş yolu bina önünden parselin ön sınırına kadar uzar
            for p in e["points"]:
                if p[1] <= y0 + 0.01:
                    seg = Polygon(f["pts"]).intersection(LineString([(p[0], -1000), (p[0], 1000)]))
                    p[1] = round(seg.bounds[1], 3) if not seg.is_empty else p[1]
    floor = next(e for e in els if e["type"] == "slab" and e.get("role") == "floor")
    outline = [tuple(p[:2]) for p in floor["points"]]
    fp_gross = rep["footprint_gross"]
    gross = rep["gross_total"]
    ex = emsal_disi_m2(zoning, gross)
    kaks_val = (gross - ex) / A
    taks_lim, kaks_lim = zoning.get("taks", 0.4), zoning.get("kaks", 1.2)
    sb = _edge_distances(outline, f["pts"], f["classes"])
    lim = {"front": zoning.get("front", 5), "side_left": zoning.get("side", 3), "side_right": zoning.get("side", 3),
           "rear": zoning.get("rear", 3)}
    detail = {k: {"value": (v if v != float("inf") else 0.0), "limit": lim[k], "ok": v >= lim[k] - 1e-6}
              for k, v in sb.items()}
    ch = rep["checks"]
    ch["taks"] = {"value": round(fp_gross / A, 3), "limit": taks_lim, "ok": fp_gross / A <= taks_lim + 1e-3}
    ch["kaks"] = {"value": round(kaks_val, 3), "limit": kaks_lim, "ok": kaks_val <= kaks_lim + 1e-3}
    ch["setbacks"] = {k: d["value"] for k, d in detail.items()}
    ch["setbacks_detail"] = detail
    ch["setback_ok"] = all(d["ok"] for d in detail.values())
    rep["parcel_area"] = round(A, 2)
    rep["buildable"] = (round(bw, 2), round(bd, 2))
    rep["origin"] = (round(rep["origin"][0] + x0, 3), round(rep["origin"][1] + y0, 3))
    kaks_area = kaks_lim * A
    rep["kaks_used_pct"] = round((gross - ex) / kaks_area * 100, 1) if kaks_area else 0.0
    if zoning.get("emsal_yok"):
        ch["taks"].update(limit=None, ok=True)
        ch["kaks"].update(limit=None, ok=True)
        rep["kaks_used_pct"] = None
    rep["imar_ozeti"] = imar_summary(zoning, A, ch)
    rep["warnings"] = [w for w in rep["warnings"] if "KAKS kullanımı" not in w and "çekmesi" not in w]
    rep["warnings"] += [f"{k} bahçe çekmesi {d['value']:.3f} m < {d['limit']:g} m" for k, d in detail.items() if not d["ok"]]
    if rep["kaks_used_pct"] is not None and rep["kaks_used_pct"] < 85:
        rep["warnings"].append(f"KAKS kullanımı %{rep['kaks_used_pct']:.0f} — bina oturumu çokgenin yapılaşma alanıyla sınırlı")
    rep["parcel_geom"] = {"polygon": poly, "buildable": [[round(x, 3), round(y, 3)] for x, y in f["buildable"]],
                          "front_edge": f["front_edge"], "classes": {str(k): v for k, v in f["classes"].items()},
                          "rotation_deg": f["rotation_deg"], "box": [round(v, 3) for v in f["box"]],
                          "plan_area": round(polygon_area([tuple(p) for p in poly]), 2)}
    rep["warnings"].append(
        f"çokgen parsel ({f['edges']} köşe, {A:.0f} m²): ön cephe {f['front_edge']}. kenar; çizimler ön kenar x eksenine "
        f"gelecek şekilde döndürülmüştür ({f['rotation_deg']:+.1f}°), bina eksen hizalı dikdörtgendir")
    return els, rep
