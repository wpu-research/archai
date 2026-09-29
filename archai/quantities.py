"""Metraj: eleman listesinden miktar satırları.

Her eleman bir veya birkaç "satır" üretir. Satır = {element, type, tag, role, level, kind,
metrics:{...}}. Maliyet kuralları bu satırları filtreleyip bir metriği toplar.

Birimler: metre, m², m³. Duvar uzunluğu aks (merkez çizgisi) uzunluğudur.
"""

import math

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


def _room(e):
    pts = [tuple(p) for p in e["points"]]
    A = polygon_area(pts)
    P = polygon_perimeter(pts)
    h = e.get("height", 2.8)
    return [_line({**e, "role": e.get("role", "room")}, "room",
                  {"area": A, "perimeter": P, "ceiling_area": A, "skirting_length": P,
                   "wall_finish_area": P * h, "count": 1})]


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
    return [_line(e, "stairs", {"count": 1, "steps": n, "tread_area": n * w * run,
                                "volume": w * run * rise * n * (n + 1) / 2})]


def _count(e):
    return [_line(e, e["type"], {"count": 1})]


HANDLERS = {"wall": _wall, "slab": _slab, "room": _room, "box": _box, "cylinder": _cyl,
            "stairs": _stairs, "tree": _count, "sphere": _count, "roof": _roof}


def compute(elements):
    """Eleman listesi → {"lines": [...], "summary": {...}, "rooms": [...], "by_tag": {...}}."""
    lines, skipped = [], []
    for e in elements:
        fn = HANDLERS.get(e.get("type"))
        if fn is None:
            skipped.append(e.get("type"))
            continue
        lines += fn(e)

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


def select(lines, type=None, tag=None, role=None, kind=None, level=None, min_thickness=None,
           max_thickness=None):
    out = []
    for l in lines:
        if not (_match(l["type"], type) and _match(l["tag"], tag) and _match(l["role"], role)
                and _match(l["kind"], kind) and _match(l["level"], level)):
            continue
        t = l["metrics"].get("thickness")
        if min_thickness is not None and (t is None or t < min_thickness - 1e-9):
            continue
        if max_thickness is not None and (t is None or t > max_thickness + 1e-9):
            continue
        out.append(l)
    return out


def quantity(lines, metric, factor=1.0, **flt):
    return sum(l["metrics"].get(metric, 0) for l in select(lines, **flt)) * factor
