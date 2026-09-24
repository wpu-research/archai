"""Arazi + imar + ihtiyaç programı → şematik (avan) konut projesi.

Üretilen plan ön tasarımdır: kütle imar sınırlarına göre boyutlandırılır, kat planı kural
tabanlı yerleşimle çıkarılır. Ruhsat projesi değildir; mimar kontrolü ve düzeltmesi gerekir.

Koordinatlar: x sokak cephesi boyunca, y parsel derinliği (y=0 ön/sokak), metre.
"""

import math
from dataclasses import dataclass

EXT_T, CORE_T, INT_T = 0.25, 0.20, 0.10

# daire tipi → yaklaşık hedef net alan (m²) ve yatak odası sayısı
UNIT_TYPES = {"1+1": (55, 1), "2+1": (90, 2), "3+1": (125, 3), "4+1": (165, 4)}
CORE_W = 5.0          # çekirdek genişliği (merdiven 2.6 + asansör/şaft)
STAIR_DEPTH = 5.6     # merdiven + asansör bölgesi derinliği (arka)
HALL_BAND = 1.3       # daire içi hol bandı


@dataclass
class Rect:
    x0: float
    y0: float
    x1: float
    y1: float
    name: str
    kind: str = "room"   # room | core | void

    @property
    def w(self):
        return self.x1 - self.x0

    @property
    def d(self):
        return self.y1 - self.y0


def _r(v, step=0.05):
    return round(round(v / step) * step, 3)


# ------------------------------------------------------------------ kütle

def massing(parcel, zoning, program):
    W, D = parcel["width"], parcel["depth"]
    A = W * D
    fr, sd, rr = zoning.get("front", 5), zoning.get("side", 3), zoning.get("rear", 3)
    bw, bd = W - 2 * sd, D - fr - rr
    if bw < 8 or bd < 8:
        raise ValueError(f"çekme mesafelerinden sonra yapılaşma alanı çok küçük ({bw:.1f} × {bd:.1f} m)")
    taks, kaks = zoning.get("taks", 0.4), zoning.get("kaks", 1.2)
    max_floors = zoning.get("max_floors", 5)
    upf = program.get("units_per_floor", "auto")
    target_net = UNIT_TYPES["2+1" if program.get("unit_type", "2+1") == "auto" else program.get("unit_type", "2+1")][0]

    max_fp = min(taks * A, bw * bd)
    total = kaks * A
    floors = max(1, min(max_floors, math.ceil(total / max_fp - 1e-9)))
    fp = min(max_fp, total / floors)
    # daire hedefi binayı büyütmesin: 2 daire + çekirdek ≈ net/0.85 brüt
    fp = min(fp, (2 * target_net / 0.82) + CORE_W * 11)

    # derinlik 10–15 m aralığında, genişlik yapılaşma alanına sığacak şekilde
    depth = min(bd, max(10.0, min(15.0, fp / min(bw, 26))))
    width = min(bw, fp / depth)
    if width < 2 * 5.5 + CORE_W:
        width = min(bw, 2 * 5.5 + CORE_W)
        depth = min(bd, fp / width)
    # brüt ölçü → aks ölçüsü (dış duvar yarı kalınlıkları), sınırı aşmamak için aşağı yuvarla
    width = math.floor((width - EXT_T) / 0.05) * 0.05
    depth = math.floor((depth - EXT_T) / 0.05) * 0.05
    width, depth = round(width, 3), round(depth, 3)
    ox = _r(sd + (bw - width) / 2)
    oy = _r(fr + EXT_T / 2)
    if upf == "auto":
        upf = 2 if (width - CORE_W) / 2 >= 5.0 else 1
    unit_w = (width - CORE_W) / upf
    avail_net = unit_w * depth * 0.88
    warnings = []
    order = list(UNIT_TYPES)
    wanted = program.get("unit_type", "2+1")
    candidates = order[::-1] if wanted == "auto" else order[:order.index(wanted) + 1][::-1]
    chosen, layout = None, None
    for ut in candidates:
        lay = unit_layout(unit_w, depth, UNIT_TYPES[ut][1])
        if lay and UNIT_TYPES[ut][0] <= avail_net * 1.3:
            chosen, layout = ut, lay
            break
    if chosen is None:
        raise ValueError(f"parsel bu imar koşullarında daire yerleşimine yetmiyor (daire genişliği {unit_w:.1f} m)")
    if wanted not in ("auto", chosen):
        warnings.append(f"{wanted} bu parsele sığmıyor (daire {unit_w:.1f} × {depth:.1f} m); {chosen} önerildi")
    return {"parcel_area": A, "buildable": (bw, bd), "footprint": (width, depth), "origin": (ox, oy),
            "floors": floors, "unit_type": chosen, "layout": layout, "units_per_floor": upf, "warnings": warnings}


# ------------------------------------------------------------------ kat planı

def _unit_rects(x0, x1, D, n_bed, mirror, tag):
    """Bir daire: ön (y küçük) gündüz, arka gece bölgesi. mirror → çekirdek solda."""
    w = x1 - x0
    day_d = _r(max(4.8, min(6.0, D * 0.45)))
    night_y0 = day_d + HALL_BAND
    rects = []

    def xs(a, b):  # birim [0,1] aralığını çekirdekten dışa doğru eşle
        if mirror:   # çekirdek solda (x0 tarafı)
            return x0 + a * w, x0 + b * w
        return x1 - b * w, x1 - a * w

    n_back = min(n_bed, int((w - BATH_W) // MIN_BED_W))
    n_front = n_bed - n_back
    # gündüz: mutfak çekirdek tarafında, (arkaya sığmayan oda), salon dış köşede
    kw = min(0.38, 2.8 / w)
    fw = MIN_BED_W / w * n_front
    kx0, kx1 = xs(0, kw)
    rects.append(Rect(_r(kx0), 0, _r(kx1), day_d, f"{tag}/Mutfak"))
    for i in range(n_front):
        fx0, fx1 = xs(kw + i * MIN_BED_W / w, kw + (i + 1) * MIN_BED_W / w)
        rects.append(Rect(_r(fx0), 0, _r(fx1), day_d, f"{tag}/Yatak Odası {n_back + i + 1}"))
    sx0, sx1 = xs(kw + fw, 1)
    rects.append(Rect(_r(sx0), 0, _r(sx1), day_d, f"{tag}/Salon"))
    rects.append(Rect(_r(x0), day_d, _r(x1), night_y0, f"{tag}/Hol"))
    # gece: banyo çekirdek tarafında, sonra yatak odaları
    bath = BATH_W / w
    parts = [("Banyo", bath)] + [(f"Yatak Odası {i + 1}", (1 - bath) / n_back) for i in range(n_back)]
    eb = 1.8 / w
    if n_bed >= 3 and parts[-1][1] - eb >= MIN_BED_W / w:  # ebeveyn banyosu: son odadan ayır
        parts[-1] = (parts[-1][0], parts[-1][1] - eb)
        parts.append(("Ebeveyn Banyo", eb))
    a = 0.0
    for name, frac in parts:
        bx0, bx1 = xs(a, a + frac)
        rects.append(Rect(_r(bx0), night_y0, _r(bx1), D, f"{tag}/{name}"))
        a += frac
    return rects


MIN_BED_W, BATH_W = 2.8, 2.2


def _unit_rects_deep(x0, x1, D, n_bed, mirror, tag):
    """Dar-derin daire: önde salon (+açık mutfak), hol çekirdek boyunca derinliğe uzanır,
    banyo ve yatak odaları dış (yan) cepheye dizilir."""
    w = x1 - x0
    day_d = _r(max(4.8, min(6.0, D * 0.38)))
    hall = 1.2
    if mirror:  # çekirdek solda
        hx0, hx1, ox0, ox1 = x0, x0 + hall, x0 + hall, x1
    else:
        hx0, hx1, ox0, ox1 = x1 - hall, x1, x0, x1 - hall
    rects = []
    if w >= 7.0:
        kw = 2.8
        kx = (x1 - kw, x1) if not mirror else (x0, x0 + kw)  # mutfak çekirdek tarafında
        sx = (x0, x1 - kw) if not mirror else (x0 + kw, x1)
        rects += [Rect(_r(kx[0]), 0, _r(kx[1]), day_d, f"{tag}/Mutfak"),
                  Rect(_r(sx[0]), 0, _r(sx[1]), day_d, f"{tag}/Salon")]
    else:
        rects.append(Rect(_r(x0), 0, _r(x1), day_d, f"{tag}/Salon + Açık Mutfak"))
    rects.append(Rect(_r(hx0), day_d, _r(hx1), D, f"{tag}/Hol"))
    rest = D - day_d
    bed_d = (rest - BATH_W) / n_bed
    y = day_d
    for name, dd in [("Banyo", BATH_W)] + [(f"Yatak Odası {i + 1}", bed_d) for i in range(n_bed)]:
        y1 = D if name.endswith(str(n_bed)) and name.startswith("Yatak") else _r(y + dd)
        rects.append(Rect(_r(ox0), _r(y), _r(ox1), y1, f"{tag}/{name}"))
        y = y1
    return rects


def unit_layout(unit_w, depth, n_bed):
    """Uygun yerleşim tipi: 'wide' (ön/arka bölge) veya 'deep' (yan cepheye dizilim); sığmazsa None."""
    n_back = min(n_bed, int((unit_w - BATH_W) // MIN_BED_W))
    n_front = n_bed - n_back
    if n_back >= 1 and n_front <= 1 and unit_w - 2.8 - n_front * MIN_BED_W >= 3.6 and depth <= 16:
        return "wide"
    day_d = max(4.8, min(6.0, depth * 0.38))
    if unit_w - 1.2 >= 3.0 and (depth - day_d - BATH_W) / n_bed >= MIN_BED_W:
        return "deep"
    return None


def floor_plan(width, depth, n_bed, layout, upf=2):
    fn = _unit_rects if layout == "wide" else _unit_rects_deep
    if upf == 1:  # çekirdek sağ yanda, tek daire
        cx0, cx1 = _r(width - CORE_W), width
        rects = fn(0, cx0, depth, n_bed, mirror=False, tag="Daire A")
    else:
        cx0 = _r((width - CORE_W) / 2)
        cx1 = _r(cx0 + CORE_W)
        rects = fn(0, cx0, depth, n_bed, mirror=False, tag="Daire A")
        rects += fn(cx1, width, depth, n_bed, mirror=True, tag="Daire B")
    sy = _r(depth - STAIR_DEPTH)
    rects += [Rect(cx0, 0, cx1, sy, "Kat Holü", "core"),
              Rect(cx0, sy, _r(cx0 + 2.8), depth, "Merdiven", "core"),
              Rect(_r(cx0 + 2.8), sy, cx1, depth, "Asansör/Şaft", "core")]
    return rects, (cx0, cx1, sy)


def _wall_segments(rects, width, depth):
    """Hücre kenarlarından tekil duvar aksları: {(orient, coord): [(s0, s1, t), ...]}."""
    edges = {}
    for r in rects:
        core = r.kind == "core"
        for orient, c, s0, s1 in (("h", r.y0, r.x0, r.x1), ("h", r.y1, r.x0, r.x1),
                                   ("v", r.x0, r.y0, r.y1), ("v", r.x1, r.y0, r.y1)):
            ext = (orient == "h" and c in (0, depth)) or (orient == "v" and c in (0, width))
            t = EXT_T if ext else CORE_T if core else INT_T
            edges.setdefault((orient, round(c, 3)), []).append((round(s0, 3), round(s1, 3), t))
    lines = {}
    for key, es in edges.items():
        pts = sorted({p for s0, s1, _ in es for p in (s0, s1)})
        pieces = []
        for a, b in zip(pts, pts[1:]):
            m = (a + b) / 2
            cover = [t for s0, s1, t in es if s0 <= m <= s1]
            if cover:
                t = max(cover)
                if pieces and abs(pieces[-1][1] - a) < 1e-6 and pieces[-1][2] == t:
                    pieces[-1] = (pieces[-1][0], b, t)
                else:
                    pieces.append((a, b, t))
        lines[key] = pieces
    return lines


WIN_W = {"Salon": 3.0, "Mutfak": 1.4, "Yatak": 1.6, "Banyo": 0.6, "Ebeveyn": 0.6}


def _shared(r, q):
    """İki dikdörtgenin ortak kenarı: (orient, coord, s0, s1) veya None."""
    for orient, a, b in (("v", r.x1, q.x0), ("v", r.x0, q.x1)):
        if abs(a - b) < 1e-6:
            s0, s1 = max(r.y0, q.y0), min(r.y1, q.y1)
            if s1 - s0 > 0.05:
                return orient, a, s0, s1
    for orient, a, b in (("h", r.y1, q.y0), ("h", r.y0, q.y1)):
        if abs(a - b) < 1e-6:
            s0, s1 = max(r.x0, q.x0), min(r.x1, q.x1)
            if s1 - s0 > 0.05:
                return orient, a, s0, s1
    return None


def _door(edge, width=0.9, at="mid"):
    orient, c, s0, s1 = edge
    avail = s1 - s0 - 0.2
    if avail < 0.7:
        return None
    w = min(width, avail)
    m = (s0 + s1) / 2 if at == "mid" else (s0 + 0.1 + w / 2 if at == "start" else s1 - 0.1 - w / 2)
    return (orient, c, _r(m - w / 2), _r(m + w / 2), "door")


def _openings(rects, width, depth, core, ground):
    """Kural tabanlı açıklıklar: (orient, coord, s0, s1, kind) listesi."""
    cx0, cx1, sy = core
    ops = []

    def win(orient, c, a, b, w):
        w = min(w, b - a - 0.8)
        if w >= 0.5:
            m = (a + b) / 2
            ops.append((orient, c, _r(m - w / 2), _r(m + w / 2), "window"))

    hall_core = next(r for r in rects if r.name == "Kat Holü")
    for tag in sorted({r.name.split("/")[0] for r in rects if r.kind == "room"}):
        unit = [r for r in rects if r.name.startswith(tag + "/")]
        hol = next(r for r in unit if r.name.endswith("/Hol"))
        rooms = [r for r in unit if r is not hol]
        for r in rooms:
            short = r.name.split("/")[1]
            ww = next((v for k, v in WIN_W.items() if short.startswith(k)), 1.4)
            ext = []
            if r.y0 == 0: ext.append(("h", 0, r.x0, r.x1))
            if r.y1 == depth: ext.append(("h", depth, r.x0, r.x1))
            if r.x0 == 0: ext.append(("v", 0, r.y0, r.y1))
            if r.x1 == width: ext.append(("v", width, r.y0, r.y1))
            ext.sort(key=lambda e: -(e[3] - e[2]))
            for e in ext[:2 if short.startswith("Salon") else 1]:
                win(*e, ww if e is ext[0] else 2.0)
            # kapı: holle ortak kenar, yoksa holle bağlantılı komşu odaya
            edge = _shared(r, hol)
            if edge is None:
                for q in rooms:
                    if q is not r and _shared(q, hol) and _shared(r, q):
                        edge = _shared(r, q)
                        break
            if edge:
                d = _door(edge, 0.8 if "Banyo" in short else 0.9)
                if d:
                    ops.append(d)
        # daire girişi: kat holü ↔ daire holü, yoksa kat holüne bakan odaya
        entry = _shared(hol, hall_core)
        if entry is None:
            entry = next((_shared(r, hall_core) for r in rooms if _shared(r, hall_core)), None)
        d = _door(entry, 1.0) if entry else None
        if d:
            ops.append(d)
    if ground:
        ops.append(("h", 0, _r((cx0 + cx1) / 2 - 0.6), _r((cx0 + cx1) / 2 + 0.6), "door"))
    else:
        win("h", 0, cx0, cx1, 1.4)
    ops.append(("h", sy, _r(cx0 + 0.5), _r(cx0 + 1.6), "door"))
    return ops


def _room_poly(r, lines):
    def half(orient, c, s_mid):
        for s0, s1, t in lines.get((orient, round(c, 3)), []):
            if s0 - 1e-6 <= s_mid <= s1 + 1e-6:
                return t / 2
        return INT_T / 2
    xm, ym = (r.x0 + r.x1) / 2, (r.y0 + r.y1) / 2
    a = r.x0 + half("v", r.x0, ym)
    b = r.x1 - half("v", r.x1, ym)
    c = r.y0 + half("h", r.y0, xm)
    d = r.y1 - half("h", r.y1, xm)
    return [[round(a, 3), round(c, 3)], [round(b, 3), round(c, 3)], [round(b, 3), round(d, 3)], [round(a, 3), round(d, 3)]]


def generate(parcel, zoning, program):
    m = massing(parcel, zoning, program)
    width, depth = m["footprint"]
    ox, oy = m["origin"]
    fh = zoning.get("floor_height", 3.0)
    slab_t = 0.2
    n_bed = UNIT_TYPES[m["unit_type"]][1]
    rects, core = floor_plan(width, depth, n_bed, m["layout"], m["units_per_floor"])
    lines = _wall_segments(rects, width, depth)
    P = lambda x, y: [round(ox + x, 3), round(oy + y, 3)]

    elements = [{"type": "slab", "name": "parsel", "tag": "terrain", "role": "site", "level": "Arsa",
                 "points": [[0, 0], [parcel["width"], 0], [parcel["width"], parcel["depth"]], [0, parcel["depth"]]],
                 "z": -0.02, "thickness": 0.3},
                {"type": "slab", "name": "giris_yolu", "tag": "stone", "role": "paving", "level": "Arsa",
                 "points": [P((core[0] + core[1]) / 2 - 1.0, -oy), P((core[0] + core[1]) / 2 + 1.0, -oy),
                            P((core[0] + core[1]) / 2 + 1.0, 0), P((core[0] + core[1]) / 2 - 1.0, 0)],
                 "z": 0.02, "thickness": 0.05}]
    outline = [P(-EXT_T / 2, -EXT_T / 2), P(width + EXT_T / 2, -EXT_T / 2),
               P(width + EXT_T / 2, depth + EXT_T / 2), P(-EXT_T / 2, depth + EXT_T / 2)]
    units = []
    for f in range(m["floors"]):
        lvl = f"Kat {f}" if f else "Zemin Kat"
        z = f * fh
        elements.append({"type": "slab", "name": f"{lvl}/doseme", "tag": "concrete", "role": "floor", "level": lvl,
                         "points": outline, "z": z, "thickness": slab_t})
        ops = _openings(rects, width, depth, core, ground=(f == 0))
        wi = 0
        for (orient, c), pieces in sorted(lines.items()):
            for s0, s1, t in pieces:
                wi += 1
                mine = sorted([(a, b, k) for o, cc, a, b, k in ops if o == orient and abs(cc - c) < 1e-6
                               and a >= s0 - 1e-6 and b <= s1 + 1e-6])
                start, end = ((s0, c), (s1, c)) if orient == "h" else ((c, s0), (c, s1))
                elements.append({
                    "type": "wall", "name": f"{lvl}/D{wi:02d}", "tag": "wall", "level": lvl,
                    "start": P(*start), "end": P(*end), "thickness": t, "height": fh - slab_t, "base_z": z,
                    "openings": [{"offset": round(a - s0, 3), "width": round(b - a, 3), "kind": k,
                                  **({"sill": 0.9, "height": 1.4 if (b - a) < 2 else 1.6} if k == "window"
                                     else {"height": 2.1, "leaf": True})} for a, b, k in mine]})
        for r in rects:
            poly = [P(x, y) for x, y in _room_poly(r, lines)]
            elements.append({"type": "room", "name": f"{lvl}/{r.name}", "level": lvl, "points": poly, "z": z,
                             "height": fh - slab_t, "role": "common" if r.kind == "core" else "room"})
        cx0, cx1, sy = core
        steps = int(round(fh / 0.17))
        elements.append({"type": "stairs", "name": f"{lvl}/merdiven", "tag": "stone", "level": lvl,
                         "origin": [ox + cx0 + 0.15, oy + depth - 0.2, z], "width": 1.2, "steps": steps // 2,
                         "rise": 0.17, "run": 0.28, "rotation_z": -90})
        for tag in sorted({r.name.split("/")[0] for r in rects if r.kind == "room"}):
            units.append({"level": lvl, "unit": tag, "type": m["unit_type"]})
    elements.append({"type": "slab", "name": "cati", "tag": "roof", "role": "roof", "level": "Çatı",
                     "points": outline, "z": m["floors"] * fh, "thickness": slab_t})
    elements.append({"type": "box", "name": "cati_parapet", "tag": "wall", "level": "Çatı",
                     "origin": [outline[0][0], outline[0][1], m["floors"] * fh], "size": [width + EXT_T, EXT_T, 0.9]})

    # uygunluk kontrolü
    A = m["parcel_area"]
    fp_gross = (width + EXT_T) * (depth + EXT_T)
    gross_total = fp_gross * m["floors"]
    unit_net = {}
    for r in rects:
        if r.kind == "room":
            u = r.name.split("/")[0]
            from .quantities import polygon_area
            unit_net[u] = unit_net.get(u, 0) + polygon_area([tuple(p) for p in _room_poly(r, lines)])
    checks = {
        "taks": {"value": round(fp_gross / A, 3), "limit": zoning.get("taks", 0.4), "ok": fp_gross / A <= zoning.get("taks", 0.4) + 1e-3},
        "kaks": {"value": round(gross_total / A, 3), "limit": zoning.get("kaks", 1.2), "ok": gross_total / A <= zoning.get("kaks", 1.2) + 1e-3},
        "floors": {"value": m["floors"], "limit": zoning.get("max_floors", 5), "ok": m["floors"] <= zoning.get("max_floors", 5)},
        "setbacks": {"front": oy, "side_left": ox, "side_right": round(parcel["width"] - ox - width, 2),
                     "rear": round(parcel["depth"] - oy - depth, 2)},
    }
    report = {
        **m, "footprint_gross": round(fp_gross, 2), "gross_total": round(gross_total, 2),
        "unit_count": len(units), "unit_net_area": {k: round(v, 2) for k, v in unit_net.items()},
        "unit_target_net": UNIT_TYPES[m["unit_type"]][0], "checks": checks,
        "note": "Şematik ön tasarım — emsal hesabı yaklaşık (emsal dışı alanlar ayrıştırılmadı); mimar kontrolü gerekir.",
    }
    return elements, report
