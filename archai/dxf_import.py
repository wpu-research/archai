"""DXF mimari plan → eleman listesi.

Katman kuralları (büyük/küçük harf ve TR/EN takma adlar):
  DUVAR / WALL          duvar çizgileri. Çift çizgi (iki yüz) veya tek çizgi (aks) olabilir.
  PENCERE / WINDOW      pencere boşluğundaki çizgiler (türü belirlemek için)
  KAPI / DOOR           kapı kanadı/yayı (türü belirlemek için)
  MAHAL / ROOM / SPACE  kapalı polyline = mahal; içine düşen TEXT/MTEXT = mahal adı
  KONTUR / OUTLINE      (opsiyonel) kapalı polyline = brüt kat konturu

2D plandan gelmeyen bilgiler (kat yüksekliği, parapet, pencere yüksekliği) parametredir.
"""

import math
from dataclasses import dataclass, field

import ezdxf

from .quantities import polygon_area

LAYER_ALIASES = {
    "wall": ("DUVAR", "WALL", "WALLS", "A-WALL", "DUVARLAR"),
    "window": ("PENCERE", "WINDOW", "WINDOWS", "A-GLAZ", "A-WIND"),
    "door": ("KAPI", "DOOR", "DOORS", "A-DOOR"),
    "room": ("MAHAL", "ROOM", "ROOMS", "SPACE", "A-AREA", "MAHALLER"),
    "outline": ("KONTUR", "OUTLINE", "DIS", "DIŞ", "A-AREA-GROS"),
}
INSUNITS_TO_M = {1: 0.0254, 2: 0.3048, 4: 0.001, 5: 0.01, 6: 1.0}


def _role(layer):
    up = layer.upper()
    for role, names in LAYER_ALIASES.items():
        if up in names or any(up.startswith(n + "-") or up.startswith(n + "_") for n in names):
            return role
    return None


@dataclass
class Seg:
    a: tuple
    b: tuple

    @property
    def length(self):
        return math.dist(self.a, self.b)

    @property
    def dir(self):
        L = self.length
        return ((self.b[0] - self.a[0]) / L, (self.b[1] - self.a[1]) / L)


@dataclass
class Piece:
    """Aks parçası: u ekseni boyunca [s0, s1], normal ofset n, kalınlık t."""
    ux: float
    uy: float
    n: float
    s0: float
    s1: float
    t: float
    openings: list = field(default_factory=list)  # [(s_start, s_end, kind, classified)]


def _canon(d):
    """Yönü [0, π) aralığına katla: paralel ama ters çizgiler aynı eksende olsun."""
    ang = math.atan2(d[1], d[0]) % math.pi
    return math.cos(ang), math.sin(ang), ang


def _proj(p, ux, uy):
    return p[0] * ux + p[1] * uy, -p[0] * uy + p[1] * ux  # (s, n)


def _segments(msp, role_of, scale):
    segs = {"wall": [], "window": [], "door": []}
    polys = {"room": [], "outline": []}
    texts = []
    for e in msp:
        role = role_of(e.dxf.layer)
        t = e.dxftype()
        if t in ("TEXT", "MTEXT"):
            txt = e.plain_text() if t == "MTEXT" else e.dxf.text
            p = e.dxf.insert
            texts.append(((float(p.x) * scale, float(p.y) * scale), txt.strip()))
            continue
        if role is None:
            continue
        pts, closed = None, False
        if t == "LINE":
            pts = [(e.dxf.start.x, e.dxf.start.y), (e.dxf.end.x, e.dxf.end.y)]
        elif t == "LWPOLYLINE":
            pts = [(x, y) for x, y, *_ in e.get_points()]
            closed = e.closed or (len(pts) > 2 and math.dist(pts[0], pts[-1]) < 1e-6)
        elif t == "POLYLINE":
            pts = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            closed = e.is_closed
        elif t == "ARC" and role == "door":
            c = e.dxf.center
            pts = [(c.x, c.y), (c.x, c.y)]
        if not pts:
            continue
        pts = [(float(x) * scale, float(y) * scale) for x, y in pts]
        if role in polys:
            if closed or math.dist(pts[0], pts[-1]) < 1e-3:
                if math.dist(pts[0], pts[-1]) < 1e-6 and len(pts) > 3:
                    pts = pts[:-1]
                polys[role].append(pts)
            continue
        ring = pts + ([pts[0]] if closed else [])
        for a, b in zip(ring, ring[1:]):
            if math.dist(a, b) > 1e-4 or role == "door":
                segs[role].append(Seg(a, b))
    return segs, polys, texts


def _pair_walls(wall_segs, t_min, t_max, default_t):
    """Paralel çizgi çiftlerinden aks parçaları; eşleşmeyenler tek çizgi aks sayılır."""
    info = []
    for s in wall_segs:
        if s.length < 0.05:
            continue
        ux, uy, ang = _canon(s.dir)
        sa, na = _proj(s.a, ux, uy)
        sb, nb = _proj(s.b, ux, uy)
        info.append({"ang": ang, "ux": ux, "uy": uy, "n": (na + nb) / 2, "s0": min(sa, sb), "s1": max(sa, sb),
                     "used": False})
    pieces = []
    order = sorted(range(len(info)), key=lambda i: -(info[i]["s1"] - info[i]["s0"]))
    for i in order:
        A = info[i]
        if A["used"]:
            continue
        best, best_d = None, None
        for j in order:
            B = info[j]
            if j == i or B["used"]:
                continue
            da = abs(A["ang"] - B["ang"])
            if min(da, math.pi - da) > math.radians(1.0):
                continue
            d = abs(A["n"] - B["n"])
            if not (t_min <= d <= t_max):
                continue
            ov = min(A["s1"], B["s1"]) - max(A["s0"], B["s0"])
            shorter = min(A["s1"] - A["s0"], B["s1"] - B["s0"])
            if ov < 0.5 * shorter:
                continue
            if best is None or d < best_d:
                best, best_d = j, d
        if best is not None:
            B = info[best]
            A["used"] = B["used"] = True
            pieces.append(Piece(A["ux"], A["uy"], (A["n"] + B["n"]) / 2, max(A["s0"], B["s0"]),
                                min(A["s1"], B["s1"]), round(best_d, 3)))
    singles = [x for x in info if not x["used"]]
    return pieces, singles


def _merge_collinear(pieces, win_segs, door_segs, max_gap, bare_gap):
    """Aynı hat üzerindeki kesik parçaları tek duvar + açıklıklara birleştir."""
    def mids(segs, ends=False):
        pts = [((s.a[0] + s.b[0]) / 2, (s.a[1] + s.b[1]) / 2) for s in segs]
        return pts + ([s.a for s in segs] + [s.b for s in segs] if ends else [])
    wmid, dmid = mids(win_segs), mids(door_segs, ends=True)  # kapı kanadı duvar dışına taşar: uçlara da bak

    def crossed(cur, s_mid):
        """Boşluktan dik bir duvar geçiyorsa bu bir T/artı birleşimidir, açıklık değil."""
        pt = (s_mid * cur.ux - cur.n * cur.uy, s_mid * cur.uy + cur.n * cur.ux)
        for q in pieces:
            if abs(q.ux * cur.uy - q.uy * cur.ux) < 0.2:
                continue
            sq, nq = _proj(pt, q.ux, q.uy)
            if abs(nq - q.n) <= q.t / 2 + 0.03 and q.s0 - cur.t <= sq <= q.s1 + cur.t:
                return True
        return False
    groups = []
    for p in sorted(pieces, key=lambda p: (round(math.atan2(p.uy, p.ux), 2), round(p.n, 2), p.s0)):
        for g in groups:
            q = g[-1]
            if abs(q.ux * p.uy - q.uy * p.ux) < 0.02 and abs(q.n - p.n) < 0.03 and abs(q.t - p.t) < 0.02:
                g.append(p)
                break
        else:
            groups.append([p])
    out = []
    for g in groups:
        g.sort(key=lambda p: p.s0)
        cur = g[0]
        for p in g[1:]:
            gap = p.s0 - cur.s1
            if gap < 0.01:  # bitişik/çakışık
                cur.s1 = max(cur.s1, p.s1)
                continue
            if gap > max_gap:
                out.append(cur)
                cur = p
                continue
            if crossed(cur, (cur.s1 + p.s0) / 2):
                cur.s1 = p.s1
                continue

            def inside(m):
                s, n = _proj(m, cur.ux, cur.uy)
                return cur.s1 - 0.01 <= s <= p.s0 + 0.01 and abs(n - cur.n) <= cur.t
            kind = "window" if any(inside(m) for m in wmid) else "door" if any(inside(m) for m in dmid) else None
            if kind is None and gap > bare_gap:
                out.append(cur)
                cur = p
                continue
            cur.openings.append((cur.s1, p.s0, kind or "door", kind is not None))
            cur.s1 = p.s1
        out.append(cur)
    return out


def _snap_ends(pieces):
    """Aks uçlarını dik komşu duvarın aksına uzat/kısalt (aks-aks metraj)."""
    for p in pieces:
        for end in ("s0", "s1"):
            s = getattr(p, end)
            pt = (s * p.ux - p.n * p.uy, s * p.uy + p.n * p.ux)
            best = None
            for q in pieces:
                if q is p or abs(p.ux * q.uy - p.uy * q.ux) < 0.2:
                    continue
                sq, nq = _proj(pt, q.ux, q.uy)
                # q aksı üzerindeki izdüşüm: p'nin ekseniyle kesişim
                # p ekseni: pt + t*u_p ; q aksı: n = q.n  →  t = (q.n - nq) / (u_p · n_q)
                dot = -p.ux * q.uy + p.uy * q.ux
                tpar = (q.n - nq) / dot
                if abs(tpar) > max(p.t, q.t) + 0.05:
                    continue
                cross_s = s + tpar
                cp = (cross_s * p.ux - p.n * p.uy, cross_s * p.uy + p.n * p.ux)
                cs, _ = _proj(cp, q.ux, q.uy)
                if not (q.s0 - q.t - 0.05 <= cs <= q.s1 + q.t + 0.05):
                    continue
                if best is None or abs(tpar) < abs(best):
                    best = tpar
            if best is not None:
                setattr(p, end, s + best)
    return pieces


def _point_in_poly(pt, poly):
    x, y = pt
    inside = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > y) != (y1 > y) and x < (x1 - x0) * (y - y0) / (y1 - y0) + x0:
            inside = not inside
    return inside


def build_elements(walls, rooms, outline, floors=1, floor_height=3.0, slab_thickness=0.2, window_sill=0.9,
                   window_height=1.4, door_height=2.1, add_roof=True):
    """Aks parçaları (Piece) + mahaller + kontur → kat kat eleman listesi (DXF ve resim planı ortak)."""
    wall_h = floor_height - slab_thickness
    elements = []
    for f in range(floors):
        z = f * floor_height
        lvl = f"Kat {f}" if floors > 1 else "Zemin"
        elements.append({"type": "slab", "name": f"{lvl}/doseme", "tag": "concrete", "role": "floor", "level": lvl,
                         "points": outline, "z": z, "thickness": slab_thickness})
        for i, w in enumerate(walls):
            ax, ay = w.s0 * w.ux - w.n * w.uy, w.s0 * w.uy + w.n * w.ux
            bx, by = w.s1 * w.ux - w.n * w.uy, w.s1 * w.uy + w.n * w.ux
            ops = []
            for s0, s1, kind, _ in w.openings:
                o = {"offset": round(s0 - w.s0, 3), "width": round(s1 - s0, 3), "kind": kind}
                if kind == "window":
                    o.update(sill=window_sill, height=window_height)
                else:
                    o.update(height=door_height, leaf=True)
                ops.append(o)
            elements.append({"type": "wall", "name": f"{lvl}/D{i + 1:02d}", "tag": "wall", "level": lvl, "structural": w.t >= 0.18,
                             "start": [round(ax, 4), round(ay, 4)], "end": [round(bx, 4), round(by, 4)],
                             "height": wall_h, "thickness": w.t, "base_z": z, "openings": ops})
        for r in rooms:
            elements.append({"type": "room", "name": f"{lvl}/{r['name']}", "level": lvl, "points": r["points"],
                             "z": z, "height": wall_h})
    if add_roof:
        elements.append({"type": "slab", "name": "cati", "tag": "roof", "role": "roof", "level": "Çatı",
                         "points": outline, "z": floors * floor_height, "thickness": slab_thickness})
    return elements


def import_dxf(path, floors=1, floor_height=3.0, slab_thickness=0.2, window_sill=0.9,
               window_height=1.4, door_height=2.1, default_thickness=0.2, wall_t_range=(0.08, 0.5),
               max_opening=3.5, bare_gap=1.2, units=None, add_roof=True):
    doc = ezdxf.readfile(str(path))
    msp = doc.modelspace()
    warnings = []
    ins = doc.header.get("$INSUNITS", 0)
    if units is not None:
        scale = units
    elif ins in INSUNITS_TO_M:
        scale = INSUNITS_TO_M[ins]
    else:
        ext = [abs(v) for e in msp.query("LINE") for v in (e.dxf.start.x, e.dxf.end.x)]
        scale = 0.001 if ext and max(ext) > 500 else 1.0
        warnings.append(f"$INSUNITS yok; birim {'mm' if scale == 0.001 else 'm'} varsayıldı")

    segs, polys, texts = _segments(msp, _role, scale)
    if not segs["wall"]:
        raise ValueError("DUVAR/WALL katmanında çizgi bulunamadı")

    pieces, singles = _pair_walls(segs["wall"], *wall_t_range, default_thickness)
    if singles:
        warnings.append(f"{len(singles)} duvar çizgisi eşleşmedi; tek çizgi aks sayıldı (kalınlık {default_thickness} m)")
        pieces += [Piece(x["ux"], x["uy"], x["n"], x["s0"], x["s1"], default_thickness) for x in singles]
    walls = _snap_ends(_merge_collinear(pieces, segs["window"], segs["door"], max_opening, bare_gap))

    # mahaller
    rooms = []
    for i, poly in enumerate(polys["room"]):
        names = [t for p, t in texts if _point_in_poly(p, poly) and t]
        rooms.append({"points": [[round(x, 4), round(y, 4)] for x, y in poly],
                      "name": names[0].split("\n")[0] if names else f"Mahal {i + 1}"})
    if not rooms:
        warnings.append("MAHAL/ROOM katmanında kapalı polyline yok; net alan hesaplanamaz")

    # brüt kontur
    if polys["outline"]:
        outline = max(polys["outline"], key=polygon_area)
    else:
        xs, ys = [], []
        for w in walls:
            for s in (w.s0, w.s1):
                for off in (-w.t / 2, w.t / 2):
                    n = w.n + off
                    xs.append(s * w.ux - n * w.uy)
                    ys.append(s * w.uy + n * w.ux)
        outline = [(min(xs), min(ys)), (max(xs), min(ys)), (max(xs), max(ys)), (min(xs), max(ys))]
        warnings.append("KONTUR katmanı yok; brüt alan duvarların dış sınır kutusundan hesaplandı")
    outline = [[round(x, 4), round(y, 4)] for x, y in outline]

    unclassified = sum(1 for w in walls for o in w.openings if not o[3])
    if unclassified:
        warnings.append(f"{unclassified} açıklıkta pencere/kapı çizgisi yok; kapı boşluğu sayıldı")

    elements = build_elements(walls, rooms, outline, floors, floor_height, slab_thickness, window_sill, window_height,
                              door_height, add_roof)

    report = {"units_scale": scale, "walls": len(walls), "openings": sum(len(w.openings) for w in walls),
              "rooms": len(rooms), "floors": floors, "outline_area": round(polygon_area([tuple(p) for p in outline]), 2),
              "warnings": warnings}
    return elements, report
