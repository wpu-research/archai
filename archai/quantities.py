"""Metraj: eleman listesinden miktar satırları.

Her eleman bir veya birkaç "satır" üretir. Satır = {element, type, tag, role, level, kind,
metrics:{...}}. Maliyet kuralları bu satırları filtreleyip bir metriği toplar.

Birimler: metre, m², m³. Duvar uzunluğu aks (merkez çizgisi) uzunluğudur.

Not (T/L birleşimleri): duvar parçaları aks uzunluğuyla ölçülür; T ve L birleşimlerinde kesişen
duvarın yarı kalınlığı iki kez sayılır (tipik plan için duvar alanında ~%1–2 fazla). Ön metraj için
kabul edilmiştir, kesin metrajda birleşim payları düşülmelidir.

Dış/iç duvar ayrımı: duvar elemanındaki `exterior` (bool) alanıyla yapılır — üreticiler kendi
bildiklerini yazar, yoksa `mark_exterior()` kat konturundan hesaplar. Alanı olmayan eski eleman
listelerinde fiyat kuralları kalınlık eşiğine (`legacy` filtreleri) düşer.
"""

import math
import re

# slab'ın rolü verilmemişse tag'den tahmin
SLAB_ROLE_BY_TAG = {"floor": "floor", "roof": "roof", "water": "pool", "stone": "paving",
                    "terrain": "site", "ground": "site", "concrete": "floor", "wood": "deck"}

DOOR_H, WINDOW_H, WINDOW_SILL = 2.1, 1.4, 0.9


def polygon_area(pts):
    s = 0.0
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        s += x0 * y1 - x1 * y0
    return abs(s) / 2


def polygon_perimeter(pts):
    return sum(math.dist(a, b) for a, b in zip(pts, pts[1:] + pts[:1]))


def _line(e, type_, metrics, **extra):
    return {"element": e.get("name", type_), "type": type_, "tag": e.get("tag"),
            "role": e.get("role"), "level": e.get("level", "0"), "kind": extra.get("kind"),
            "exterior": e.get("exterior"),
            "metrics": {k: round(v, 4) for k, v in metrics.items()}}


def _wall(e):
    (x0, y0), (x1, y1) = e["start"], e["end"]
    L = math.hypot(x1 - x0, y1 - y0)
    H = e.get("height", 3.0)
    T = e.get("thickness", 0.2)
    e = {**e, "tag": e.get("tag", "wall")}
    lines, open_area = [], 0.0
    for i, o in enumerate(e.get("openings", [])):
        kind = o.get("kind", "window")
        h = o.get("height", DOOR_H if kind == "door" else WINDOW_H)
        a = o["width"] * h
        open_area += a
        lines.append(_line({**e, "name": f"{e.get('name', 'wall')}/{kind}{i}"}, "opening",
                           {"count": 1, "width": o["width"], "height": h, "area": a,
                            "perimeter": 2 * (o["width"] + h), "reveal_area": 2 * (o["width"] + h) * T},
                           kind=kind))
    gross = L * H / (2 if e.get("profile") == "gable" else 1)
    net = max(gross - open_area, 0.0)
    lines.insert(0, _line(e, "wall", {"length": L, "height": H, "thickness": T, "gross_area": gross,
                                      "opening_area": open_area, "net_area": net,
                                      "volume": net * T, "plaster_area": 2 * net}))
    return lines


def _slab(e):
    pts = [tuple(p) for p in e["points"]]
    A = polygon_area(pts)
    t = e.get("thickness", 0.2)
    role = e.get("role") or SLAB_ROLE_BY_TAG.get(e.get("tag", "floor"), "other")
    return [_line({**e, "role": role}, "slab", {"area": A, "perimeter": polygon_perimeter(pts),
                                                 "thickness": t, "volume": A * t, "count": 1})]


LIFT_RE = re.compile(r"asansör|asansor|lift", re.I)
SHAFT_RE = re.compile(r"şaft|saft|shaft|ışıklık|kuyu", re.I)
STAIR_RE = re.compile(r"merdiven|stair", re.I)


def room_kind(e):
    """Mahal sınıfı: room (daire içi) | common (ortak hol) | stair | lift (asansör kuyusu) | shaft.
    Asansör kuyusu ve şaftlar hiçbir iç finiş kalemine girmez; merdiven evi yalnız sıva/tavan alır."""
    name = e.get("name", "").split("/", 1)[-1]   # kat öneki hariç tüm ad ("Asansör/Şaft" asansördür)
    if LIFT_RE.search(name):
        return "lift"
    if SHAFT_RE.search(name):
        return "shaft"
    if e.get("role") == "common":
        return "stair" if STAIR_RE.search(name) else "common"
    return "room"


def _room(e, deduct=None):
    """deduct: {"wall": m² (kapı/pencere boşlukları, bu mahalin yüzü), "door_w": m (kapı genişlikleri)}."""
    pts = [tuple(p) for p in e["points"]]
    A = polygon_area(pts)
    P = polygon_perimeter(pts)
    h = e.get("height", 2.8)
    d = deduct or {}
    gross = P * h
    return [_line({**e, "role": e.get("role", "room")}, "room",
                  {"area": A, "perimeter": P, "ceiling_area": A,
                   "skirting_length": max(P - d.get("door_w", 0.0), 0.0),
                   "wall_finish_gross": gross, "wall_finish_area": max(gross - d.get("wall", 0.0), 0.0), "count": 1},
                  kind=room_kind(e))]


def _room_deductions(elements):
    """Her mahal için kendi yüzündeki açıklıklar: iç kapı iki mahale (iki yüz), pencere ve dış kapı tek mahale düşer.
    Açıklık, mahal poligonunun bir kenarına paralel ve duvar yarı kalınlığı (+5 cm) mesafedeyse o mahale aittir."""
    ops = []
    for w in elements:
        if w.get("type") != "wall":
            continue
        (x0, y0), (x1, y1) = w["start"][:2], w["end"][:2]
        L = math.hypot(x1 - x0, y1 - y0)
        if L < 1e-9:
            continue
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        for o in w.get("openings", []):
            kind = o.get("kind", "window")
            m = o.get("offset", 0) + o["width"] / 2
            h = o.get("height", DOOR_H if kind == "door" else WINDOW_H)
            ops.append((w.get("level"), x0 + ux * m, y0 + uy * m, ux, uy, w.get("thickness", 0.2) / 2 + 0.05,
                        o["width"], o["width"] * h, kind))
    out = {}
    for r in elements:
        if r.get("type") != "room":
            continue
        pts = [tuple(p[:2]) for p in r["points"]]
        dw = dd = 0.0
        for lvl, mx, my, ux, uy, tol, width, area, kind in ops:
            if lvl != r.get("level"):
                continue
            for (ax, ay), (bx, by) in zip(pts, pts[1:] + pts[:1]):
                ex, ey = bx - ax, by - ay
                el = math.hypot(ex, ey)
                if el < 1e-9 or abs(ex / el * uy - ey / el * ux) > 0.05:   # paralel değil
                    continue
                t = ((mx - ax) * ex + (my - ay) * ey) / el
                dist = abs((mx - ax) * ey - (my - ay) * ex) / el
                if dist <= tol and -1e-6 <= t <= el + 1e-6:
                    dw += area
                    dd += width if kind == "door" else 0.0
                    break
        out[id(r)] = {"wall": dw, "door_w": dd}
    return out


def roof_profile(e):
    """Eğimli çatı kesiti (mahya eksenine dik düzlemde): [(s, z), ...] saçaktan saçağa, üst yüz."""
    s0, s1 = (e["y0"], e["y1"]) if e.get("axis", "x") == "x" else (e["x0"], e["x1"])
    z, r, f = e.get("z", 0.0), e.get("ridge", 1.5), e.get("ridge_at", 0.5)
    pts = [(s0, z), (s0 + (s1 - s0) * f, z + r), (s1, z)]
    return [p for i, p in enumerate(pts) if i == 0 or abs(p[0] - pts[i - 1][0]) > 1e-6]


def _roof(e):
    L = (e["x1"] - e["x0"]) if e.get("axis", "x") == "x" else (e["y1"] - e["y0"])
    prof = roof_profile(e)
    slope_len = sum(math.dist(a, b) for a, b in zip(prof, prof[1:]))
    area = slope_len * L
    fp = (e["x1"] - e["x0"]) * (e["y1"] - e["y0"])
    t = e.get("thickness", 0.2)
    return [_line({**e, "role": "roof"}, "roof", {"area": area, "footprint": fp, "thickness": t, "volume": area * t,
                                                  "ridge": e.get("ridge", 1.5), "count": 1})]


def _box(e):
    sx, sy, sz = e["size"]
    return [_line(e, "box", {"count": 1, "footprint": sx * sy, "volume": sx * sy * sz, "height": sz})]


def _cyl(e):
    r1, h = e["radius"], e["height"]
    r2 = e.get("radius_top", r1)
    vol = math.pi * h * (r1 * r1 + r1 * r2 + r2 * r2) / 3
    return [_line(e, "cylinder", {"count": 1, "volume": vol, "height": h})]


def _stairs(e):
    n, w, rise, run = e.get("steps", 10), e.get("width", 1.2), e.get("rise", 0.17), e.get("run", 0.28)
    return [_line(e, "stairs", {"count": 1, "steps": n, "tread_area": n * w * run, "stair_length": n * w,
                                "rise_total": n * rise, "volume": w * run * rise * n * (n + 1) / 2})]


def _count(e):
    return [_line(e, e["type"], {"count": 1})]


def _building(elements):
    """Temel/kazı metrajı için tek bina satırı: en alt kat döşemesinin oturum alanı.
    kind = temel tipi (döşemedeki `foundation`, varsayılan "raft"; ayaklı temel için "piers")."""
    floors = [e for e in elements if e.get("type") == "slab"
              and (e.get("role") or SLAB_ROLE_BY_TAG.get(e.get("tag", "floor"))) == "floor"]
    if not floors:
        return []
    z0 = min(e.get("z", 0.0) for e in floors)
    base = [e for e in floors if abs(e.get("z", 0.0) - z0) < 1e-6]
    fp = sum(polygon_area([tuple(p) for p in e["points"]]) for e in base)
    per = sum(polygon_perimeter([tuple(p) for p in e["points"]]) for e in base)
    n = len({e.get("level") for e in floors})
    raft_t = min(1.0, 0.30 + 0.04 * n)   # AVAN: radye kalınlığı kat adedine göre (1 kat 0,34 m … 10 kat 0,70 m)
    e0 = {"name": "bina_oturum", "tag": base[0].get("tag"), "role": "foundation", "level": base[0].get("level", "0")}
    return [_line(e0, "building", {"footprint": fp, "perimeter": per, "count": 1, "floors": n, "raft_thickness": raft_t,
                                   "raft_volume": fp * raft_t, "excavation_volume": fp * (raft_t + 1.0)},
                  kind=base[0].get("foundation", "raft"))]


def _seg_dist(px, py, ax, ay, bx, by):
    ex, ey = bx - ax, by - ay
    L2 = ex * ex + ey * ey
    t = 0.0 if L2 < 1e-12 else max(0.0, min(1.0, ((px - ax) * ex + (py - ay) * ey) / L2))
    return math.hypot(px - ax - t * ex, py - ay - t * ey)


def _inside(pt, poly):
    x, y = pt
    c = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > y) != (y1 > y) and x < x0 + (y - y0) * (x1 - x0) / (y1 - y0):
            c = not c
    return c


def mark_exterior(elements, force=False):
    """Duvarlara `exterior` (bool) yaz: duvar aksı kat konturunun (o katın döşeme çokgeni; yoksa tüm kat
    döşemeleri) bir kenarına paralel ve ≤ kalınlık/2 + 0.05 m uzaktaysa, ve duvarın dış tarafı aynı kattaki
    bir mahalin içine düşmüyorsa (döşeme boşluğu/merdiven kenarı değilse) dış duvardır.
    Var olan `exterior` değerine dokunmaz (force=True hariç). Eleman listesini yerinde değiştirir, döner."""
    slabs = [e for e in elements if e.get("type") == "slab"
             and (e.get("role") or SLAB_ROLE_BY_TAG.get(e.get("tag", "floor"))) in ("floor", "roof")]
    by_level = {}
    for e in slabs:
        if (e.get("role") or SLAB_ROLE_BY_TAG.get(e.get("tag", "floor"))) == "floor":
            by_level.setdefault(e.get("level"), []).append([tuple(p[:2]) for p in e["points"]])
    every = [[tuple(p[:2]) for p in e["points"]] for e in slabs]
    rooms = {}
    for r in elements:
        if r.get("type") == "room":
            rooms.setdefault(r.get("level"), []).append([tuple(p[:2]) for p in r["points"]])
    for w in elements:
        if w.get("type") != "wall" or ("exterior" in w and not force):
            continue
        (x0, y0), (x1, y1) = w["start"][:2], w["end"][:2]
        L = math.hypot(x1 - x0, y1 - y0)
        polys = by_level.get(w.get("level")) or every
        ext = False
        if L > 1e-9:
            ux, uy = (x1 - x0) / L, (y1 - y0) / L
            tol = w.get("thickness", 0.2) / 2 + 0.05
            mx, my = (x0 + x1) / 2, (y0 + y1) / 2
            for poly in polys:
                for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
                    el = math.hypot(bx - ax, by - ay)
                    if el < 1e-9 or abs((bx - ax) / el * uy - (by - ay) / el * ux) > 0.02:
                        continue
                    if _seg_dist(mx, my, ax, ay, bx, by) > tol or \
                            min(_seg_dist(x, y, ax, ay, bx, by) for x, y in ((x0, y0), (x1, y1))) > tol + 0.01:
                        continue
                    # dış taraf: aks normali boyunca kenara doğru; orada mahal varsa iç duvardır
                    nx, ny = -uy, ux
                    if ((ax - mx) * nx + (ay - my) * ny) < 0:
                        nx, ny = -nx, -ny
                    probe = (mx + nx * (tol + 0.25), my + ny * (tol + 0.25))
                    if not any(_inside(probe, rp) for rp in rooms.get(w.get("level"), [])):
                        ext = True
                        break
                if ext:
                    break
        w["exterior"] = ext
    return elements


HANDLERS = {"wall": _wall, "slab": _slab, "room": _room, "box": _box, "cylinder": _cyl,
            "stairs": _stairs, "tree": _count, "sphere": _count, "roof": _roof}


def compute(elements):
    """Eleman listesi → {"lines": [...], "summary": {...}, "rooms": [...], "by_tag": {...}}."""
    lines, skipped = [], []
    deduct = _room_deductions(elements)
    for e in elements:
        fn = HANDLERS.get(e.get("type"))
        if fn is None:
            skipped.append(e.get("type"))
            continue
        lines += fn(e, deduct.get(id(e))) if fn is _room else fn(e)
    lines += _building(elements)

    def total(metric, **flt):
        return round(sum(l["metrics"].get(metric, 0) for l in select(lines, **flt)), 3)

    rooms = [{"name": l["element"], "level": l["level"], "area": round(l["metrics"]["area"], 2),
              "perimeter": round(l["metrics"]["perimeter"], 2)} for l in lines if l["type"] == "room"]
    by_tag = {}
    for l in lines:
        d = by_tag.setdefault(f'{l["type"]}:{l["tag"]}', {})
        for k, v in l["metrics"].items():
            if k in ("area", "net_area", "gross_area", "volume", "length", "count", "footprint"):
                d[k] = round(d.get(k, 0) + v, 3)
    levels = sorted({l["level"] for l in lines})
    summary = {
        "gross_floor_area": total("area", type="slab", role="floor"),
        "net_room_area": total("area", type="room"),
        "wall_length": total("length", type="wall"),
        "wall_net_area": total("net_area", type="wall"),
        "wall_volume": total("volume", type="wall"),
        "window_count": total("count", type="opening", kind="window"),
        "window_area": total("area", type="opening", kind="window"),
        "door_count": total("count", type="opening", kind="door"),
        "door_area": total("area", type="opening", kind="door"),
        "roof_area": total("area", type=["slab", "roof"], role="roof"),
        "pool_area": total("area", type="slab", role="pool"),
        "paving_area": total("area", type="slab", role="paving"),
        "levels": levels,
    }
    return {"lines": lines, "summary": summary, "rooms": rooms, "by_tag": by_tag,
            "skipped_types": sorted(set(skipped))}


def _match(val, want):
    if want is None:
        return True
    if isinstance(want, (list, tuple, set)):
        return val in want
    return val == want


def _thick_ok(l, min_thickness, max_thickness):
    t = l["metrics"].get("thickness")
    if min_thickness is not None and (t is None or t < min_thickness - 1e-9):
        return False
    if max_thickness is not None and (t is None or t > max_thickness + 1e-9):
        return False
    return True


def select(lines, type=None, tag=None, role=None, kind=None, level=None, min_thickness=None,
           max_thickness=None, exterior=None, legacy=None):
    """exterior: True/False → satırın `exterior` alanıyla eşleşir. Alan yoksa (eski eleman listesi) `legacy`
    sözlüğündeki kalınlık filtreleri kullanılır ({"min_thickness": 0.2} gibi); legacy verilmemişse satır dışlanır."""
    out = []
    for l in lines:
        if not (_match(l["type"], type) and _match(l["tag"], tag) and _match(l["role"], role)
                and _match(l["kind"], kind) and _match(l["level"], level)):
            continue
        if not _thick_ok(l, min_thickness, max_thickness):
            continue
        if exterior is not None:
            ext = l.get("exterior")
            if ext is None:
                if legacy is None or not _thick_ok(l, legacy.get("min_thickness"), legacy.get("max_thickness")):
                    continue
            elif bool(ext) != bool(exterior):
                continue
        out.append(l)
    return out


def quantity(lines, metric, factor=1.0, **flt):
    return sum(l["metrics"].get(metric, 0) for l in select(lines, **flt)) * factor
