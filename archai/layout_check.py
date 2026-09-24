"""İç mekân yerleşim denetimi: nesne oda dışına taşıyor mu, nesneler çakışıyor mu, kapı önü kapanıyor mu.

Nesne sınırları archai/data/item_bounds.json (tarayıcıda Box3 ile ölçülmüş yerel min/max).
Dönüşüm interior.js ile aynı: plan = (px + x·cosθ + z·sinθ, py + x·sinθ − z·cosθ).
"""

import json
import math
from pathlib import Path

from shapely.geometry import Point, Polygon, box
from shapely.affinity import rotate, translate

BOUNDS = json.loads((Path(__file__).parent / "data" / "item_bounds.json").read_text())
LAYERED = {"hali"}                                  # üzerine başka nesne konabilir
STACK = {("tv", "tv_unitesi")}                      # duvar TV'si ünitenin üstünde
DOOR_CLEAR = 0.7


def footprint(o):
    b = BOUNDS[o["kind"]]
    (x0, _, z0), (x1, _, z1) = b["min"], b["max"]
    th = o.get("rot", 0.0)
    c, s = math.cos(th), math.sin(th)
    pts = [(o["x"] + x * c + z * s, o["y"] + x * s - z * c) for x, z in ((x0, z0), (x1, z0), (x1, z1), (x0, z1))]
    return Polygon(pts)


def door_zones(elements, level):
    zones = []
    for w in elements:
        if w["type"] != "wall" or w.get("level") != level:
            continue
        (ax, ay), (bx, by) = w["start"], w["end"]
        L = math.hypot(bx - ax, by - ay) or 1
        ux, uy = (bx - ax) / L, (by - ay) / L
        nx, ny = -uy, ux
        for o in w.get("openings", []):
            if o["kind"] != "door":
                continue
            a, b = o["offset"], o["offset"] + o["width"]
            P = lambda s, d: (ax + ux * s + nx * d, ay + uy * s + ny * d)
            zones.append(Polygon([P(a, -DOOR_CLEAR), P(b, -DOOR_CLEAR), P(b, DOOR_CLEAR), P(a, DOOR_CLEAR)]))
    return zones


def check(elements, design, tol=0.03):
    rooms = [(e["level"], e["name"], Polygon(e["points"])) for e in elements if e["type"] == "room"]
    issues = []
    placed = []
    for o in design["objects"]:
        fp = footprint(o)
        room = next(((lv, n, p) for lv, n, p in rooms if lv == o["level"] and p.contains(Point(o["x"], o["y"]))), None)
        if room is None:
            placed.append((o, fp, None))
            continue
        lv, n, poly = room
        spill = fp.difference(poly.buffer(tol)).area
        if spill > 0.01:
            issues.append(f"{n}: {o['kind']} oda dışına {spill:.2f} m² taşıyor")
        placed.append((o, fp, n))
    for i, (a, fa, ra) in enumerate(placed):
        for b, fb, rb in placed[i + 1:]:
            if ra != rb or a["level"] != b["level"]:
                continue
            ka, kb = a["kind"], b["kind"]
            if ka in LAYERED or kb in LAYERED or (ka, kb) in STACK or (kb, ka) in STACK:
                continue
            ov = fa.intersection(fb).area
            if ov > 0.01:
                issues.append(f"{ra}: {ka} ↔ {kb} çakışıyor ({ov:.2f} m²)")
    for lv in {o["level"] for o in design["objects"]}:
        zones = door_zones(elements, lv)
        for o, fp, r in placed:
            if o["level"] != lv or o["kind"] in LAYERED:
                continue
            for z in zones:
                if fp.intersection(z).area > 0.01:
                    issues.append(f"{r or 'dış mekân'}: {o['kind']} bir kapı önünü kapatıyor")
                    break
    return issues
