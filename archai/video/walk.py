"""Yürüyüş yolu planlayıcı: giriş kapısından odalara, kapılar üzerinden, duvardan geçmeden.

Geometri istemcideki YÜRÜ ile aynı kuralı izler (webapp/static/index.html prepLevel): kapı boşlukları
geçilebilir, pencereler duvar gibi engeldir; yıkılan duvarlar (interior.json `demolished`) yoktur. Duvar yüzünden
en az MARGIN kadar uzak durulur; ızgara üzerinde Dijkstra ile yol bulunur, doğrultulur, yumuşatılır ve
her aşamada duvar bölgesiyle kesişimi yeniden doğrulanır.

Saf fonksiyonlar: tarayıcı gerekmez. Yaw kuralı istemciyle aynı: ileri = (−sin yaw, cos yaw).
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

import numpy as np
import shapely
from shapely.geometry import LineString, Point, Polygon
from shapely.ops import unary_union

from .facts import HALLISH, NON_VISIT, in_poly, poly_area, room_label

FPS = 24
MARGIN = 0.22          # kamera ile duvar yüzü arası asgari mesafe (m)
SPEED = 1.9            # yürüme hızı (m/sn); kamera ivmelenip yavaşladığı için ortalama ~1,5
EYE = 1.6              # göz yüksekliği (istemcideki EYE)
OUT_APPROACH = (3.4, 2.6, 1.8, 1.2)       # dış kapının önünden başlama mesafesi adayları


def yaw_to(dx, dy):
    return math.atan2(-dx, dy)


def wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


def smooth(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


@dataclass
class Door:
    x: float
    y: float
    nx: float
    ny: float
    width: float
    thick: float
    exterior: bool
    a: dict | None            # +n yanındaki oda
    b: dict | None            # −n yanındaki oda
    wall: str = ""

    @property
    def pt(self):
        return (self.x, self.y)


def wall_solids(elements, level, demolished=()):
    """[(x0, y0, x1, y1, yarı_kalınlık)] — kapı boşlukları açık, pencereler dolu."""
    dem = set(demolished or ())
    segs = []
    for w in elements:
        if w.get("type") != "wall" or w.get("level") != level or w.get("name") in dem:
            continue
        (x0, y0), (x1, y1) = w["start"], w["end"]
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-4:
            continue
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        t = (w.get("thickness") or 0.2) / 2
        cur = 0.0
        doors = sorted((o for o in (w.get("openings") or []) if o.get("kind") == "door"), key=lambda o: o["offset"])
        for o in doors:
            if o["offset"] - cur > 1e-3:
                segs.append((x0 + ux * cur, y0 + uy * cur, x0 + ux * o["offset"], y0 + uy * o["offset"], t))
            cur = max(cur, o["offset"] + o["width"])
        if L - cur > 1e-3:
            segs.append((x0 + ux * cur, y0 + uy * cur, x1, y1, t))
    return segs


def _rect(s):
    x0, y0, x1, y1, t = s
    return LineString([(x0, y0), (x1, y1)]).buffer(t, cap_style="flat")


def level_doors(elements, level, rooms, demolished=()):
    dem = set(demolished or ())
    polys = [r for r in rooms if r["level"] == level]
    out = []
    for w in elements:
        if w.get("type") != "wall" or w.get("level") != level or w.get("name") in dem:
            continue
        (x0, y0), (x1, y1) = w["start"], w["end"]
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-4:
            continue
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        nx, ny = -uy, ux
        T = w.get("thickness") or 0.2
        for o in w.get("openings") or []:
            if o.get("kind") != "door":
                continue
            m = o["offset"] + o["width"] / 2
            cx, cy = x0 + ux * m, y0 + uy * m
            d = T / 2 + 0.45

            def side(sg):
                p = (cx + nx * sg * d, cy + ny * sg * d)
                return next((r for r in polys if in_poly(p, r["points"])), None)
            a, b = side(1), side(-1)
            out.append(Door(cx, cy, nx, ny, o["width"], T, bool(w.get("exterior")) or (a is None) != (b is None), a, b, w.get("name", "")))
    return out


# kapıdan geçişe engel olmayan düşük/yassı eşyalar (halı vb.) hiç engel sayılmaz
SOFT_FLAT = ("hali", "carpet", "rug")
# yüksek eşyalar (göz hizasını keser) sert engel; kalan eşyalar yumuşak maliyet
TALL = ("gardirop", "buzdolabi", "kitaplik", "mutfak", "dolap", "dus", "ada")


class Geometry:
    """Bir katın yürüyüş geometrisi."""

    def __init__(self, elements, level, rooms, objects=(), demolished=()):
        self.level = level
        self.rooms = [r for r in rooms if r["level"] == level]
        self.solids = wall_solids(elements, level, demolished)
        self.doors = level_doors(elements, level, rooms, demolished)
        rects = [_rect(s) for s in self.solids]
        self.obstacle = unary_union(rects) if rects else Polygon()
        hard, soft = [], []
        for o in objects or []:
            if o.get("level") != level or not isinstance(o.get("x"), (int, float)):
                continue
            kind = str(o.get("kind", "")).lower()
            if any(k in kind for k in SOFT_FLAT):
                continue
            hw = max(float(o.get("w") or 0), float(o.get("d") or 0)) / 2
            if any(k in kind for k in TALL):
                hard.append(Point(o["x"], o["y"]).buffer(max(0.35, min(hw, 0.9))))
            else:
                soft.append(Point(o["x"], o["y"]).buffer(max(0.45, min(hw, 1.0))))
        self.hard = unary_union(hard) if hard else Polygon()
        self.soft = unary_union(soft) if soft else Polygon()
        self.blocked = unary_union([self.obstacle.buffer(MARGIN), self.hard]) if not self.obstacle.is_empty else self.hard
        self.near = self.obstacle.buffer(MARGIN + 0.30) if not self.obstacle.is_empty else Polygon()
        for g in (self.blocked, self.near, self.soft):
            if not g.is_empty:
                shapely.prepare(g)

    # ---- doğrulama
    def crosses(self, pts):
        """Yol (nokta listesi) duvar gövdesiyle kesişiyor mu?"""
        if len(pts) < 2 or self.obstacle.is_empty:
            return False
        return bool(self.obstacle.intersects(LineString(pts)))

    def clearance(self, pts):
        """Yolun duvar yüzüne en yakın mesafesi (m)."""
        if self.obstacle.is_empty or not pts:
            return math.inf
        return float(shapely.distance(shapely.points(np.asarray(pts, float)), self.obstacle).min())

    def free(self, p):
        return self.blocked.is_empty or not self.blocked.contains(Point(p))


class Grid:
    def __init__(self, geo, step=None):
        b = geo.obstacle.bounds if not geo.obstacle.is_empty else (0, 0, 10, 10)
        pad = 5.0
        self.x0, self.y0 = b[0] - pad, b[1] - pad
        w, h = b[2] - b[0] + 2 * pad, b[3] - b[1] + 2 * pad
        step = step or max(0.12, math.sqrt(w * h / 120000.0))
        self.s = step
        self.nx, self.ny = int(math.ceil(w / step)) + 1, int(math.ceil(h / step)) + 1
        xs = self.x0 + np.arange(self.nx) * step
        ys = self.y0 + np.arange(self.ny) * step
        X, Y = np.meshgrid(xs, ys)
        fx, fy = X.ravel(), Y.ravel()
        blocked = shapely.contains_xy(geo.blocked, fx, fy) if not geo.blocked.is_empty else np.zeros(fx.shape, bool)
        extra = np.zeros(fx.shape, np.float32)
        if not geo.near.is_empty:
            extra += 1.2 * shapely.contains_xy(geo.near, fx, fy)
        if not geo.soft.is_empty:
            extra += 2.5 * shapely.contains_xy(geo.soft, fx, fy)
        self.free = (~blocked).tolist()
        self.extra = extra.tolist()

    def idx(self, p):
        return int(round((p[1] - self.y0) / self.s)) * self.nx + int(round((p[0] - self.x0) / self.s))

    def xy(self, k):
        j, i = divmod(k, self.nx)
        return (self.x0 + i * self.s, self.y0 + j * self.s)

    def nearest_free(self, p, maxr=2.0):
        k = self.idx(p)
        if 0 <= k < len(self.free) and self.free[k]:
            return k
        j0, i0 = divmod(k, self.nx)
        r = 1
        R = int(maxr / self.s)
        while r <= R:
            best = None
            for j in range(j0 - r, j0 + r + 1):
                for i in range(i0 - r, i0 + r + 1):
                    if abs(j - j0) != r and abs(i - i0) != r:
                        continue
                    if 0 <= j < self.ny and 0 <= i < self.nx and self.free[j * self.nx + i]:
                        d = (j - j0) ** 2 + (i - i0) ** 2
                        if best is None or d < best[0]:
                            best = (d, j * self.nx + i)
            if best:
                return best[1]
            r += 1
        return None

    def dijkstra(self, src, targets):
        """src: hücre indeksi; targets: küme. Tüm hedefler çözülünce durur. (dist, prev) sözlükleri."""
        nx, ny = self.nx, self.ny
        free, extra, s = self.free, self.extra, self.s
        dist = {src: 0.0}
        prev = {}
        heap = [(0.0, src)]
        left = set(targets)
        done = set()
        D = s * math.sqrt(2)
        while heap and left:
            d, k = heapq.heappop(heap)
            if k in done:
                continue
            done.add(k)
            left.discard(k)
            j, i = divmod(k, nx)
            for dj in (-1, 0, 1):
                jj = j + dj
                if jj < 0 or jj >= ny:
                    continue
                for di in (-1, 0, 1):
                    if not dj and not di:
                        continue
                    ii = i + di
                    if ii < 0 or ii >= nx:
                        continue
                    kk = jj * nx + ii
                    if not free[kk] or kk in done:
                        continue
                    if dj and di and not (free[j * nx + ii] and free[jj * nx + i]):
                        continue            # köşe kesme
                    nd = d + (D if dj and di else s) * (1.0 + extra[kk])
                    if nd < dist.get(kk, 1e18):
                        dist[kk] = nd
                        prev[kk] = k
                        heapq.heappush(heap, (nd, kk))
        return dist, prev

    def trace(self, prev, src, dst):
        out = [dst]
        while out[-1] != src:
            out.append(prev[out[-1]])
        return [self.xy(k) for k in reversed(out)]


def pull(geo, pts):
    """Doğrultma: görüş hattı engel bölgesiyle kesişmeyen en uzak noktaya atla."""
    if len(pts) < 3:
        return list(pts)
    out = [pts[0]]
    i = 0
    while i < len(pts) - 1:
        j = len(pts) - 1
        while j > i + 1 and (geo.blocked.intersects(LineString([pts[i], pts[j]])) if not geo.blocked.is_empty else False):
            j -= 1
        out.append(pts[j])
        i = j
    return out


def chaikin(pts, n):
    for _ in range(n):
        if len(pts) < 3:
            break
        new = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            new += [(0.75 * a[0] + 0.25 * b[0], 0.75 * a[1] + 0.25 * b[1]), (0.25 * a[0] + 0.75 * b[0], 0.25 * a[1] + 0.75 * b[1])]
        new.append(pts[-1])
        pts = new
    return pts


def smooth_safe(geo, pts):
    """Köşeleri yumuşat; duvar bölgesine girerse daha az yumuşat."""
    for n in (3, 2, 1):
        cand = chaikin(pts, n)
        if geo.blocked.is_empty or not geo.blocked.intersects(LineString(cand)):
            return cand
    return list(pts)


def plen(pts):
    return sum(math.dist(a, b) for a, b in zip(pts[:-1], pts[1:]))


def resample(pts, step):
    """Kümülatif yay uzunluğuna göre [(s, x, y)] arama için; (s_toplam, fn(s)->(x,y,tx,ty))."""
    cum = [0.0]
    for a, b in zip(pts[:-1], pts[1:]):
        cum.append(cum[-1] + math.dist(a, b))
    total = cum[-1]

    def at(s):
        s = min(max(s, 0.0), total)
        lo, hi = 0, len(cum) - 1
        while hi - lo > 1:
            m = (lo + hi) // 2
            if cum[m] <= s:
                lo = m
            else:
                hi = m
        seg = cum[hi] - cum[lo] or 1e-9
        u = (s - cum[lo]) / seg
        a, b = pts[lo], pts[hi]
        return (a[0] + (b[0] - a[0]) * u, a[1] + (b[1] - a[1]) * u)
    return total, at


@dataclass
class WalkPlan:
    level: str
    frames: list                       # [(t, x, y, yaw)]
    duration: float
    z: float
    door_open: dict | None             # {"x","y","t": kapının açılma başlangıç zamanı}
    tags: list = field(default_factory=list)       # [(t0, t1, etiket, alan_m2)]
    visited: list = field(default_factory=list)    # gezilen oda adları
    notes: list = field(default_factory=list)


def _pole(room, geo, grid):
    """Odanın içinde duvardan en uzak, serbest nokta."""
    poly = Polygon(room["points"])
    if not poly.is_valid:
        poly = poly.buffer(0)
    try:
        c = shapely.polylabel(poly, tolerance=0.1)
        p = (c.x, c.y)
    except Exception:  # noqa: BLE001
        c = poly.representative_point()
        p = (c.x, c.y)
    k = grid.nearest_free(p, 1.5)
    return grid.xy(k) if k is not None else None


def pick_entrance(geo):
    ex = [d for d in geo.doors if d.exterior and (d.a or d.b) and not (d.a and d.b)]
    if not ex:
        return None

    def score(d):
        r = d.a or d.b
        return (1 if HALLISH.search(room_label(r["name"])) else 0, min(r["area"], 60), -d.y)
    return max(ex, key=score)


def plan_walk(facts, level=None, budget_s=20.0, dwell=1.15, min_area=5.5, max_rooms=9, objects=None):
    """Yürüyüş planı ya da None (yürünecek geometri yok). `facts`: facts.Facts."""
    level = level or (facts.floors[0] if facts.floors else None)
    if not level:
        return None
    objs = facts.interior.get("objects", []) if objects is None else objects
    geo = Geometry(facts.elements, level, facts.rooms, objs, facts.interior.get("demolished") or [])
    if not geo.solids or not geo.rooms:
        return None
    grid = Grid(geo)
    z = next((e.get("z") or 0.0 for e in facts.elements if e.get("type") == "slab" and e.get("role") == "floor" and e.get("level") == level), 0.0)

    cand = []
    for r in geo.rooms:
        if r["area"] < min_area or NON_VISIT.search(room_label(r["name"])):
            continue
        p = _pole(r, geo, grid)
        if p is not None:
            cand.append({"room": r, "pt": p})
    if not cand:
        return None

    notes = []
    ent = pick_entrance(geo)
    start = None
    approach = []                       # S → kapı → içeri
    door_pt = None
    if ent:
        outn = (ent.nx, ent.ny) if ent.a is None else (-ent.nx, -ent.ny)       # dışa bakan normal
        inroom = ent.b if ent.a is None else ent.a
        p_in = None
        for dd in (0.9, 0.7, 0.5):
            q = (ent.x - outn[0] * dd, ent.y - outn[1] * dd)
            if geo.free(q):
                p_in = q
                break
        for D in OUT_APPROACH:
            q = (ent.x + outn[0] * D, ent.y + outn[1] * D)
            if p_in and geo.free(q) and not geo.blocked.intersects(LineString([q, p_in])):
                start = q
                break
        if start and p_in:
            approach = [start, (ent.x, ent.y), p_in]
            door_pt = (ent.x, ent.y)
        else:
            notes.append("giriş kapısı geçilemez: iç mekândan başlanıyor")
            ent = None
    if not approach:
        # girişsiz: en büyük hol/salon ortasından
        r0 = max(cand, key=lambda c: (1 if HALLISH.search(room_label(c["room"]["name"])) else 0, c["room"]["area"]))
        start = r0["pt"]
        approach = [start]

    cur_pt = approach[-1]
    cur_cell = grid.nearest_free(cur_pt, 1.0)
    if cur_cell is None:
        return None
    legs = []                           # her bacak: noktalar listesi (durak → durak)
    order = []
    t_est = (plen(approach) / SPEED) if len(approach) > 1 else 0.0
    remaining = list(cand)
    first = True
    cur_leg_prefix = approach if len(approach) > 1 else []
    while remaining and len(order) < max_rooms:
        dist, prev = grid.dijkstra(cur_cell, {grid.idx(c["pt"]) for c in remaining})
        reach = [(c, dist[grid.idx(c["pt"])]) for c in remaining if grid.idx(c["pt"]) in dist]
        if not reach:
            break
        if first and ent:
            inr = ent.b if ent.a is None else ent.a
            pref = [rc for rc in reach if rc[0]["room"] is inr]
            reach = pref or reach
        c, dv = min(reach, key=lambda rc: rc[1] * (1.0 - min(rc[0]["room"]["area"], 40) / 100.0))
        path = grid.trace(prev, cur_cell, grid.idx(c["pt"]))
        path = pull(geo, [cur_pt] + path[1:] if path else [cur_pt, c["pt"]])
        path[-1] = c["pt"] if not geo.blocked.intersects(LineString([path[-2] if len(path) > 1 else cur_pt, c["pt"]])) else path[-1]
        leg = (cur_leg_prefix + path[1:]) if cur_leg_prefix else path
        cur_leg_prefix = []
        dt = plen(leg) / SPEED * 1.2 + dwell
        if order and t_est + dt > budget_s:
            break
        t_est += dt
        legs.append((leg, c))
        order.append(c["room"]["name"])
        remaining.remove(c)
        cur_pt, cur_cell = path[-1], grid.nearest_free(path[-1], 0.5)
        first = False
        if cur_cell is None:
            break
    if not legs:
        return None

    # ---- kareler
    frames = []
    t = 0.0
    yaw = None
    dt_f = 1.0 / FPS
    tags_raw = []
    door_t = None

    def push(x, y, yw):
        frames.append((round(t, 4), x, y, yw))

    def step_yaw(cur, want, dt):
        d = wrap(want - cur)
        return cur + max(-math.radians(110) * dt, min(math.radians(110) * dt, d * 5.0 * dt))

    for li, (leg, c) in enumerate(legs):
        pts = smooth_safe(geo, leg) if len(leg) > 2 else list(leg)
        total, at = resample(pts, 0.05)
        T = max(total / SPEED * 1.2, 0.6)
        if yaw is None:
            dx, dy = at(min(total, 1.5))[0] - pts[0][0], at(min(total, 1.5))[1] - pts[0][1]
            yaw = yaw_to(dx, dy)
        n = int(T * FPS)
        for k in range(n + 1):
            s = total * smooth(k / n) if n else total
            x, y = at(s)
            la = at(min(total, s + 1.1))
            if math.hypot(la[0] - x, la[1] - y) < 0.15:
                la = pts[-1] if math.hypot(pts[-1][0] - x, pts[-1][1] - y) > 0.15 else at(total)
                if math.hypot(la[0] - x, la[1] - y) < 0.15:
                    la = None
            want = yaw_to(la[0] - x, la[1] - y) if la else yaw
            yaw = step_yaw(yaw, want, dt_f) if frames else yaw
            if door_pt and door_t is None and li == 0 and math.hypot(x - door_pt[0], y - door_pt[1]) < 0.25:
                door_t = t
            push(x, y, yaw)
            t += dt_f
        # durak: odaya bakarak hafifçe süpür
        room = c["room"]
        px, py = pts[-1]
        far = max(room["points"], key=lambda p: math.hypot(p[0] - px, p[1] - py))
        base = yaw_to(far[0] - px, far[1] - py)
        hold = dwell + (0.4 if li == len(legs) - 1 else 0)
        m = int(hold * FPS)
        for k in range(m):
            sweep = (smooth(k / max(1, m - 1)) * 2 - 1) * math.radians(38)
            yaw = step_yaw(yaw, base + sweep, dt_f)
            push(px, py, yaw)
            t += dt_f
    duration = t

    # ---- oda etiketleri (bir odada ≥0.8 sn kalındıysa)
    last = None
    start_t = 0.0
    spans = []
    for (ft, x, y, _) in frames:
        r = next((r for r in geo.rooms if in_poly((x, y), r["points"])), None)
        if r is not last:
            if last is not None:
                spans.append((start_t, ft, last))
            last, start_t = r, ft
    if last is not None:
        spans.append((start_t, duration, last))
    tags = []
    for a, b, r in spans:
        if b - a >= 0.8 and not NON_VISIT.search(room_label(r["name"])):
            tags.append((round(a + 0.15, 3), round(b - 0.1, 3), room_label(r["name"]), round(r["area"], 1)))
    # çakışmayı önle: her etiket bir sonrakinin başlangıcında biter
    for i in range(len(tags) - 1):
        if tags[i][1] > tags[i + 1][0] - 0.05:
            tags[i] = (tags[i][0], round(tags[i + 1][0] - 0.05, 3), tags[i][2], tags[i][3])
    tags = [t_ for t_ in tags if t_[1] - t_[0] >= 0.6]

    dopen = None
    if door_pt and door_t is not None:
        dopen = {"x": door_pt[0], "y": door_pt[1], "t": max(0.0, round(door_t - 1.7, 3))}
    return WalkPlan(level=level, frames=frames, duration=duration, z=z, door_open=dopen, tags=tags,
                    visited=order, notes=notes)


def validate(plan, facts, margin=0.12):
    """Testler ve planlayıcı için: (duvarla kesişme var mı, en yakın mesafe)."""
    geo = Geometry(facts.elements, plan.level, facts.rooms, [], facts.interior.get("demolished") or [])
    pts = [(f[1], f[2]) for f in plan.frames]
    return geo.crosses(pts), geo.clearance(pts)
