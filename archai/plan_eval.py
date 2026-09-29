"""Plan tanıma doğruluğu: tanınan eleman listesini referans modelle (aynı resmin elle kurulmuş hâli) karşılaştırır.

Duvar: aks çizgileri 5 cm örneklenir; tanınan aksın ≤ tol yakınında referans aks varsa isabet (precision),
referans aksın yakınında tanınan aks varsa kapsam (recall). Kapı: merkezler ≤ 0,35 m içinde bire bir eşleşme.
Koordinatlar farklı orijinde olabilir: referans, verilen dönüşümle (metre → resim pikseli → tanıyıcı metresi) taşınır.
"""

import math

import numpy as np


def _samples(walls, step=0.05, skip_openings=False):
    pts = []
    for w in walls:
        (x0, y0), (x1, y1) = w["start"], w["end"]
        L = math.dist(w["start"], w["end"])
        if L < 1e-6:
            continue
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        ops = [(o["offset"], o["offset"] + o["width"]) for o in w.get("openings", []) if o["kind"] == "door"]
        for k in range(int(L / step) + 1):
            s = k * step
            if skip_openings and any(a <= s <= b for a, b in ops):
                continue
            pts.append((x0 + ux * s, y0 + uy * s))
    return np.array(pts) if pts else np.zeros((0, 2))


def _near(a, b, tol):
    """a'nın her noktası için b'de ≤ tol nokta var mı (ızgara kovası)."""
    if not len(a) or not len(b):
        return np.zeros(len(a), bool)
    cell = tol
    buckets = {}
    for p in b:
        buckets.setdefault((int(p[0] // cell), int(p[1] // cell)), []).append(p)
    out = np.zeros(len(a), bool)
    for i, p in enumerate(a):
        cx, cy = int(p[0] // cell), int(p[1] // cell)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for q in buckets.get((cx + dx, cy + dy), ()):
                    if (p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 <= tol * tol:
                        out[i] = True
                        break
                if out[i]:
                    break
            if out[i]:
                break
    return out


def _doors(walls):
    out = []
    for w in walls:
        (x0, y0), (x1, y1) = w["start"], w["end"]
        L = math.dist(w["start"], w["end"]) or 1
        ux, uy = (x1 - x0) / L, (y1 - y0) / L
        for o in w.get("openings", []):
            if o["kind"] == "door":
                s = o["offset"] + o["width"] / 2
                out.append((x0 + ux * s, y0 + uy * s))
    return out


def compare(found, ref, level_found=None, level_ref=None, tol=0.15, door_tol=0.35):
    wf = [e for e in found if e["type"] == "wall" and (level_found is None or e.get("level") == level_found)]
    wr = [e for e in ref if e["type"] == "wall" and (level_ref is None or e.get("level") == level_ref)]
    sf, sr = _samples(wf, skip_openings=True), _samples(wr, skip_openings=True)  # yalnız kapı boşlukları atlanır
    prec = float(_near(sf, sr, tol).mean()) if len(sf) else 0.0
    rec = float(_near(sr, sf, tol).mean()) if len(sr) else 0.0
    df, dr = _doors(wf), _doors(wr)
    used, hit = set(), 0
    for p in dr:
        j = min((j for j in range(len(df)) if j not in used), key=lambda j: math.dist(p, df[j]), default=None)
        if j is not None and math.dist(p, df[j]) <= door_tol:
            used.add(j)
            hit += 1
    rooms_f = sum(1 for e in found if e["type"] == "room" and (level_found is None or e.get("level") == level_found))
    rooms_r = sum(1 for e in ref if e["type"] == "room" and (level_ref is None or e.get("level") == level_ref))
    return {"wall_precision": round(prec, 3), "wall_recall": round(rec, 3),
            "doors_found": len(df), "doors_ref": len(dr), "doors_matched": hit,
            "rooms_found": rooms_f, "rooms_ref": rooms_r}


def apartment_reference(px_per_m, img_h):
    """archai/apartment.py referansını tanıyıcının koordinatına taşı: metre → px → (x/S, (H−y)/S)."""
    from . import apartment as A
    els = A.elements()

    def T(p):
        px = (p[0] - A.OX) * A.S + A.PX0
        py = A.PY0 - (p[1] - A.OY) * A.S
        return [px / px_per_m, (img_h - py) / px_per_m]
    out = []
    for e in els:
        e = dict(e)
        if e["type"] == "wall" and e["thickness"] in (0.06, 0.08):
            continue  # çizimde olmayan varsayım duvarları: merdiven kolları arası perde, asansör kabin önü
        if e["type"] == "wall":
            e["start"], e["end"] = T(e["start"]), T(e["end"])
            k = A.S / px_per_m
            e["openings"] = [{**o, "offset": o["offset"] * k, "width": o["width"] * k} for o in e["openings"]]
        elif "points" in e:
            e["points"] = [T(p) for p in e["points"]]
        out.append(e)
    return out


def align(found, ref, level_found, level_ref):
    """Tanınan planı referansa sınır kutusuyla hizala (öteleme + tek ölçek): pafta resminde orijin/ölçek bilinmez."""
    def box(els, lv):
        pts = [p for e in els if e["type"] == "wall" and e.get("level") == lv and e.get("thickness", 0) >= 0.15
               for p in (e["start"], e["end"])]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)
    fx0, fy0, fx1, fy1 = box(found, level_found)
    rx0, ry0, rx1, ry1 = box(ref, level_ref)
    k = ((rx1 - rx0) / (fx1 - fx0) + (ry1 - ry0) / (fy1 - fy0)) / 2
    T = lambda p: [rx0 + (p[0] - fx0) * k, ry0 + (p[1] - fy0) * k]
    out = []
    for e in found:
        e = dict(e)
        if e["type"] == "wall":
            e["start"], e["end"] = T(e["start"]), T(e["end"])
            e["openings"] = [{**o, "offset": o["offset"] * k, "width": o["width"] * k} for o in e["openings"]]
        elif "points" in e:
            e["points"] = [T(p) for p in e["points"]]
        out.append(e)
    return out, k


def windows(els, level):
    return sum(o["kind"] == "window" for e in els if e["type"] == "wall" and e.get("level") == level for o in e["openings"])
