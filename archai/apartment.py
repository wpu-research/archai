"""Senaryo: kat başına 3 daireli apartman normal katı — verilen CAD kat planından birebir.

Kaynak: çekirdekli (U merdiven + asansör) kat planı; batı (camgöbeği) ve doğu (eflatun) 2+1'ler
birbirinin aynası, güney (yeşil) daire 2+1 + çekirdeğin altındaki banyo. Her duvar, kapı ve
mobilya çizimden ölçüldü: ölçek arka plan ızgarasından (23,1 px = 0,5 m → 46,2 px/m).
Koordinatlar aşağıda doğrudan görsel pikseliyle (px, y aşağı) yazılır, `P()` metreye çevirir;
böylece her değer çizimle karşılaştırılabilir.

Çizimde olmayan, 3D için varsayılanlar: dış duvar 25 cm (iç yüzü çizgideki gibi), pencereler
(planda yok; dış duvarlarda oda ortasına), kat yüksekliği 3,0 m, asansör kabin kapısı.
Doğu dairesi batıdakinin x = 884 px eksenine göre aynası.
"""

import math

from .generate import setback_checks, setback_warnings
from .layout_check import local_box
from .quantities import polygon_area

S = 46.2                               # px / m
PX0, PY0 = 2.0, 724.0                  # bina dış yüzü (sol, alt) px
MX = 884.0                             # batı ↔ doğu daire ayna ekseni (px)
PARCEL = (29.2, 26.0)
OX, OY = 5.05, 5.05                    # binanın parseldeki yeri (m): dış yüz 5 m çekmenin içinde (dış yüzden ölçülür)
FH, SLAB = 3.0, 0.2
WH = FH - SLAB
EXT, INT = 0.25, 0.10
HE = EXT / 2 * S                       # dış duvar yarı kalınlığı (px)
LV = "Normal Kat"
ZONING = {"taks": 0.40, "kaks": 0.40, "front": 5.0, "side": 5.0, "rear": 5.0, "max_floors": 1, "floor_height": FH}


def P(px, py):
    return [round(OX + (px - PX0) / S, 3), round(OY + (PY0 - py) / S, 3)]


def mx(px):
    return MX - px


# ---------------------------------------------------------------- dış duvar aksları (iç yüz + yarım kalınlık)
XW = 13.5 - HE                         # batı dairesi batı cephesi
YN = 12.5 - HE                         # kuzey cephe
XK = 338.5 + HE                        # batı mutfağının doğu cephesi (ışıklık)
XG = 105.5 - HE                        # güney dairesi batı cephesi
YG = 712.5 + HE                        # güney cephe
XE = 778.5 + HE                        # güney dairesi doğu cephesi
YP = 490.5                             # daireler arası ayırma duvarı / batı ve doğu dairenin güney cephesi
YC = 171.5                             # çekirdeğin kuzey duvarı (mutfakların güney duvarı)

# Duvar: (x0, y0, x1, y1, kalınlık, açıklıklar); açıklık = (a, b, tür[, parapet, yükseklik]) px, duvar ekseni boyunca
WEST_WALLS = [
    # dış cephe
    (XW, YN, XW, YP, EXT, [(85, 150, "window"), (262, 330, "window"), (395, 450, "window")]),
    (XW, YN, XK, YN, EXT, [(70, 140, "window"), (215, 290, "window")]),
    (XK, YN, XK, YC, EXT, []),
    # salon | mutfak-yemek; hol ve yatak odası kapıları aynı aks üzerinde
    (201.5, YN, 201.5, YP, INT, [(175, 219, "door"), (233, 274, "door"), (365, 408, "door")]),
    (XW, 229.5, 201.5, 229.5, INT, []),                              # salon | ebeveyn
    (XW, 359.5, 201.5, 359.5, 0.11, []),                             # ebeveyn | çocuk
    (201.5, 415, 347.5, 415, INT, [(203, 249, "door")]),              # hol | banyo
]
CORE_WALLS = [
    (201.5, YC, mx(201.5), YC, 0.15, [(213, 254, "door"), (mx(254), mx(213), "door")]),   # mutfak girişleri + çekirdek
    (260, YC, 260, 305, INT, []),                                     # merdiven evi batı
    (260, 305, 462, 305, INT, []),                                    # merdiven evi güney
    (337.7, 237, 462.7, 237, 0.06, []),                               # kollar arası perde
    (347.5, 305, 347.5, YP, 0.15, [(326, 371, "door")]),              # batı daire girişi
    (mx(347.5), 277.5, mx(347.5), YP, 0.15, [(325, 371, "door")]),    # doğu daire girişi
    (531, 277.5, 626, 277.5, 0.24, []),                               # asansör kuyusu güney
    (620.5, YC, 620.5, 277.5, 0.24, []),                              # asansör kuyusu doğu
    (533, YC, 533, 277.5, 0.08, [(203, 247, "door")]),                # asansör kabin kapısı (varsayım)
    (347.5, 379.5, mx(347.5), 379.5, 0.15, [(357, 403, "door")]),     # güney daire girişi
]
SOUTH_WALLS = [
    (XW, YP, 347.5, YP, 0.2, []),                                     # batı daire | güney daire
    (mx(347.5), YP, mx(XW), YP, 0.2, []),                             # doğu daire | güney daire
    (XG, YP, XG, YG, EXT, [(570, 640, "window")]),
    (XG, YG, XE, YG, EXT, [(255, 335, "window"), (380, 440, "window", 1.05, 1.1), (510, 590, "window"), (670, 750, "window")]),
    (XE, YP, XE, YG, EXT, []),
    (422.5, 379.5, 422.5, 491.5, INT, []),                            # hol | banyo
    (422.5, 491.5, mx(347.5), 491.5, INT, [(430, 471, "door")]),       # banyo kapısı
    (348.5, YP, 348.5, YG, 0.11, [(494, 540, "door")]),               # hol | salon
    (348.5, 546.5, 629, 546.5, 0.11, [(352, 397, "door"), (485, 526, "door")]),  # mutfak + yatak odası kapıları
    (478, 546.5, 478, YG, INT, []),                                   # mutfak | yatak odası
    (629, YP, 629, YG, INT, [(494, 544, "door")]),                    # yatak odası | ebeveyn
]
COLUMNS = [(599, 494), (596, 542)]     # çizimdeki iki küçük kare (tesisat/kolon işareti)


def _mirror_wall(w):
    x0, y0, x1, y1, t, ops = w
    vertical = abs(x0 - x1) < 1e-6
    ops2 = [(a, b, *r) if vertical else (mx(b), mx(a), *r) for a, b, *r in ops]
    return (mx(x0), y0, mx(x1), y1, t, ops2)


def _wall(i, w):
    x0, y0, x1, y1, t, ops = w
    a, b = P(x0, y0), P(x1, y1)
    L = math.dist(a, b)
    ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
    vertical = abs(x0 - x1) < 1e-6
    out = []
    for o in ops:
        s0, s1, kind = o[:3]
        pts = [P(x0, s) if vertical else P(s, y0) for s in (s0, s1)]
        d = sorted((p[0] - a[0]) * ux + (p[1] - a[1]) * uy for p in pts)
        op = {"offset": round(d[0], 3), "width": round(d[1] - d[0], 3), "kind": kind}
        if kind == "window":
            op.update(sill=o[3] if len(o) > 3 else 0.9, height=o[4] if len(o) > 4 else 1.4)
        else:
            op.update(height=2.1, leaf=True)
        out.append(op)
    return {"type": "wall", "name": f"{LV}/D{i:02d}", "tag": "wall", "level": LV, "start": a, "end": b,
            "thickness": t, "height": WH, "base_z": 0.0, "openings": out, "structural": t >= 0.2,
            "exterior": t == EXT}   # ışıklığa bakan 15 cm çekirdek duvarı iç sayılır (mantolanmaz)


def walls():
    ws = WEST_WALLS + [_mirror_wall(w) for w in WEST_WALLS] + CORE_WALLS + SOUTH_WALLS
    return [_wall(i + 1, w) for i, w in enumerate(ws)]


# ---------------------------------------------------------------- mahaller (px poligon)
def _rect(x0, y0, x1, y1):
    return [(x0, y0), (x1, y0), (x1, y1), (x0, y1)]


WEST_ROOMS = [
    ("Salon", _rect(XW, YN, 201.5, 229.5)),
    ("Mutfak ve Yemek", _rect(201.5, YN, XK, YC)),
    ("Ebeveyn Yatak Odası", _rect(XW, 229.5, 201.5, 359.5)),
    ("Çocuk Odası", _rect(XW, 359.5, 201.5, YP)),
    ("Banyo", _rect(201.5, 415, 347.5, YP)),
]
WEST_HALL = [(201.5, YC), (260, YC), (260, 305), (347.5, 305), (347.5, 415), (201.5, 415)]
EAST_HALL = [(620.5, YC), (mx(201.5), YC), (mx(201.5), 415), (mx(347.5), 415), (mx(347.5), 277.5), (620.5, 277.5)]
CORE_ROOMS = [
    ("Ortak/Merdiven", _rect(260, YC, 462, 305)),
    ("Ortak/Asansör", _rect(533, YC, 620.5, 277.5)),
    ("Ortak/Kat Holü", [(462, YC), (533, YC), (533, 277.5), (mx(347.5), 277.5), (mx(347.5), 379.5), (347.5, 379.5),
                        (347.5, 305), (462, 305)]),
]
SOUTH_ROOMS = [
    ("Salon", _rect(XG, YP, 348.5, YG)),
    ("Hol", [(347.5, 379.5), (422.5, 379.5), (422.5, YP), (629, YP), (629, 546.5), (348.5, 546.5)]),
    ("Banyo", _rect(422.5, 379.5, mx(347.5), 491.5)),
    ("Mutfak", _rect(348.5, 546.5, 478, YG)),
    ("Yatak Odası", _rect(478, 546.5, 629, YG)),
    ("Ebeveyn Yatak Odası", _rect(629, YP, XE, YG)),
]
UNITS = ("Daire 1", "Daire 2", "Daire 3")   # batı, doğu, güney


def rooms():
    out = []

    def add(name, poly, role="room"):
        pts = [P(x, y) for x, y in poly]
        out.append({"type": "room", "name": f"{LV}/{name}", "level": LV, "points": pts, "z": 0.0, "height": WH, "role": role})
    for n, poly in WEST_ROOMS:
        add(f"{UNITS[0]} {n}", poly)
        add(f"{UNITS[1]} {n}", [(mx(x), y) for x, y in poly])
    add(f"{UNITS[0]} Hol", WEST_HALL)
    add(f"{UNITS[1]} Hol", EAST_HALL)
    for n, poly in CORE_ROOMS:
        add(n, poly, "common")
    for n, poly in SOUTH_ROOMS:
        add(f"{UNITS[2]} {n}", poly)
    return out


def outline():
    """Brüt kat konturu (dış yüzler): kuzeyde iki mutfak arasında ışıklık girintisi."""
    o = HE
    xw, yn, xk, xg, yg, xe = XW - o, YN - o, XK + o, XG - o, YG + o, XE + o
    yc = YC - 0.075 * S
    ys = YP + 0.1 * S
    return [P(*p) for p in [(xw, yn), (xk, yn), (xk, yc), (mx(xk), yc), (mx(xk), yn), (mx(xw), yn), (mx(xw), ys),
                            (xe, ys), (xe, yg), (xg, yg), (xg, ys), (xw, ys)]]


def elements():
    PW, PD = PARCEL
    rect = lambda x0, y0, x1, y1: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    fp = outline()
    els = [
        {"type": "slab", "name": "parsel", "tag": "terrain", "role": "site", "level": "Arsa", "points": rect(0, 0, PW, PD),
         "z": -0.02, "thickness": 0.3},
        {"type": "slab", "name": f"{LV}/doseme", "tag": "concrete", "role": "floor", "level": LV, "points": fp, "z": 0.0,
         "thickness": SLAB},
    ]
    els += walls()
    els += rooms()
    # U merdiven: doğudan (kat holü) batıya çıkan kol → sahanlık → doğuya dönen kol; 20 × 15 cm rıht, 31,6 cm basamak
    run = round(13.9 / S, 3)
    x_top = P(462.7, 0)[0]
    for name, py0, py1, z, rot in (("kol1", 180, 237, 0.0, 180), ("kol2", 296, 237, 1.5, 0)):
        width = round(abs(py1 - py0) / S, 3)
        if rot == 180:
            origin = [x_top, P(0, py0)[1], z]
        else:
            origin = [P(337.7, 0)[0], P(0, py0)[1], z]
        els.append({"type": "stairs", "name": f"{LV}/merdiven_{name}", "tag": "stone", "level": LV, "origin": origin,
                    "width": width, "steps": 9, "rise": 0.15, "run": run, "rotation_z": rot})
    (lx0, ly0), (lx1, ly1) = P(270, 296), P(337.7, 180)
    els.append({"type": "box", "name": f"{LV}/merdiven_sahanlik", "tag": "stone", "level": LV,
                "origin": [lx0, ly0, 0.0], "size": [round(lx1 - lx0, 3), round(ly1 - ly0, 3), 1.5]})
    for i, (cx, cy) in enumerate(COLUMNS):
        (x0, y0) = P(cx - 3.5, cy + 3.5)
        els.append({"type": "box", "name": f"{LV}/kolon{i + 1}", "tag": "concrete", "level": LV,
                    "origin": [x0, y0, 0.0], "size": [0.15, 0.15, WH]})
    els.append({"type": "slab", "name": "cati", "tag": "roof", "role": "roof", "level": "Çatı", "points": fp,
                "z": FH, "thickness": SLAB})
    return els


# ---------------------------------------------------------------- mobilya (çizimdeki kutular, px)
N, SO, W, E = 0.0, math.pi, math.pi / 2, -math.pi / 2          # sırtı hangi duvara dönük (interior.js yönü)
# (tür, kutu x0, y0, x1, y1, sırt yönü, parametreler); kutu = çizimdeki dış hat
WEST_ITEMS = [
    # salon
    ("kanepe", 15, 58, 60, 178, W, {"w": 2.6, "p": 1}),
    ("kanepe_2li", 63, 13, 146, 58, N, {"w": 1.8, "p": -1}),
    ("kanepe_2li", 63, 178, 146, 222, SO, {"w": 1.8, "p": -1}),
    ("sehpa_yuvarlak", 74, 114, 120, 160, N, {"d": 1.0, "kitap": True}),
    ("sehpa_yuvarlak", 107, 101, 131, 125, N, {"d": 0.5}),
    # mutfak + yemek
    ("mutfak", 310, 14, 338, 167, E, {"w": 3.3, "ocak": -0.43, "evye": 1.27, "suluk": -1}),
    ("yemek_masasi", 222, 32, 268, 106, W, {"w": 1.6, "d": 1.0, "orta": True}),
    ("sandalye", 234, 15, 256, 37, N, {}), ("sandalye", 234, 100, 256, 122, SO, {}),
    ("sandalye", 205, 43, 227, 65, W, {}), ("sandalye", 205, 71, 227, 93, W, {}),
    ("sandalye", 263, 43, 285, 65, E, {}), ("sandalye", 263, 71, 285, 93, E, {}),
    # ebeveyn yatak odası
    ("yatak_cift", 37, 232, 111, 323, N, {"w": 1.45, "d": 1.97}),
    ("komodin", 14, 232, 35, 256, N, {}), ("komodin", 112, 232, 133, 256, N, {}),
    ("gardirop", 171, 274, 198, 357, E, {"w": 1.8}),
    # çocuk odası
    ("yatak_tek", 40, 397, 84, 485, SO, {"w": 0.8, "d": 1.9}),
    ("komodin", 18, 462, 40, 485, SO, {}), ("komodin", 85, 462, 107, 485, SO, {}),
    ("gardirop", 112, 456, 195, 484, SO, {"w": 1.8}),
    # banyo
    ("lavabo", 222, 463, 258, 487, SO, {}),
    ("klozet", 270, 457, 287, 487, SO, {}),
    ("dus", 303, 423, 340, 485, E, {"w": 1.35, "d": 0.8, "side": -1}),
]
SOUTH_ITEMS = [
    ("kanepe", 108, 543, 153, 662, W, {"w": 2.57, "p": 1}),
    ("kanepe_2li", 164, 498, 248, 543, N, {"w": 1.8, "p": -1}),
    ("kanepe_2li", 158, 667, 242, 712, SO, {"w": 1.8, "p": -1}),
    ("sehpa_yuvarlak", 172, 584, 218, 630, N, {"d": 1.0, "kitap": True}),
    ("sehpa_yuvarlak", 200, 574, 224, 598, N, {"d": 0.5}),
    ("yemek_masasi", 274, 615, 322, 689, W, {"w": 1.6, "d": 1.0, "orta": True}),
    ("sandalye", 288, 599, 308, 620, N, {}), ("sandalye", 288, 684, 308, 705, SO, {}),
    ("sandalye", 258, 628, 280, 649, W, {}), ("sandalye", 258, 655, 280, 677, W, {}),
    ("sandalye", 317, 628, 338, 649, E, {}), ("sandalye", 317, 655, 338, 677, E, {}),
    ("mutfak", 448, 549, 478, 712, E, {"w": 3.5, "d": 0.65, "ocak": -0.34, "evye": 1.37, "suluk": -1}),
    ("gardirop", 533, 550, 618, 578, N, {"w": 1.84}),
    ("yatak_cift", 529, 612, 626, 689, E, {"w": 1.5, "d": 2.1}),
    ("komodin", 601, 591, 623, 612, E, {}), ("komodin", 601, 689, 623, 711, E, {}),
    ("gardirop", 663, 497, 775, 524, N, {"w": 2.42}),
    ("yatak_cift", 680, 596, 777, 673, E, {"w": 1.5, "d": 2.1}),
    ("komodin", 752, 574, 773, 596, E, {}), ("komodin", 752, 673, 773, 695, E, {}),
    ("dus", 468, 384, 530, 420, N, {"w": 1.3, "d": 0.78, "side": -1}),
    ("lavabo", 425, 429, 450, 467, W, {}),
    ("klozet", 500, 455, 520, 489, SO, {}),
]
ASYM = ("ocak", "evye", "suluk", "side", "p")   # yerel x boyunca yön taşıyan parametreler: aynada işaret değiştirir

def _place(kind, x0, y0, x1, y1, rot, params, mirror=False):
    """Kutunun sırt kenarına yasla, yanlamasına ortala; sırtsız (yuvarlak) nesneler kutu merkezine."""
    cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    back = -local_box({"kind": kind, **params})[1]         # yerel −z = sırt
    if kind in ("yemek_masasi", "sehpa_yuvarlak", "sandalye"):
        px, py = cx, cy
    else:
        # sırt kenarı: rot → plan normali (sinθ, −cosθ) ön yöndür; sırt tersinde
        fx, fy = math.sin(rot), -math.cos(rot)
        if abs(fx) > 0.5:
            edge = x0 if fx > 0 else x1
            px, py = edge + fx * back * S, cy
        else:
            edge = y1 if fy > 0 else y0          # plan +y = px'te yukarı (küçük py)
            px, py = cx, edge - fy * back * S
    if mirror:
        px, rot = mx(px), -rot
        params = {k: (-v if k in ASYM else v) for k, v in params.items()}
    x, y = P(px, py)
    return {"kind": kind, "level": LV, "x": x, "y": y, "rot": round(rot, 4), "h": 0.0, **params}


def design(els):
    objs = [_place(*it) for it in WEST_ITEMS] + [_place(*it, mirror=True) for it in WEST_ITEMS] + [_place(*it) for it in SOUTH_ITEMS]
    for i, o in enumerate(objs):
        o["id"] = f"a{i:03d}"
    floors = {}
    for e in els:
        if e["type"] != "room":
            continue
        n = e["name"]
        floors[n] = ("marble_tiles" if "Banyo" in n else "terrazzo_tiles" if "Ortak" in n
                     else "herringbone_parquet" if "Salon" in n else "oak_wood_planks")
    return {"floors": floors, "paint": "kirik_beyaz", "objects": objs}


def report(els):
    PW, PD = PARCEL
    A = PW * PD
    fp = outline()
    xs, ys = [p[0] for p in fp], [p[1] for p in fp]
    area = polygon_area([tuple(p) for p in fp])
    z = ZONING
    units = {}
    for e in els:
        if e["type"] == "room" and e.get("role") == "room":
            u = " ".join(e["name"].split("/")[1].split()[:2])
            units[u] = round(units.get(u, 0) + polygon_area([tuple(p) for p in e["points"]]), 2)
    sb, sb_detail, sb_ok = setback_checks(PW, PD, (min(xs), min(ys), max(xs), max(ys)), ZONING)
    checks = {"taks": {"value": round(area / A, 3), "limit": z["taks"], "ok": area / A <= z["taks"] + 1e-3},
              "kaks": {"value": round(area / A, 3), "limit": z["kaks"], "ok": area / A <= z["kaks"] + 1e-3},
              "floors": {"value": 1, "limit": z["max_floors"], "ok": True}, "setbacks": sb,
              "setbacks_detail": sb_detail, "setback_ok": sb_ok}
    return {"parcel_area": A, "footprint": (round(max(xs) - min(xs), 2), round(max(ys) - min(ys), 2)), "origin": (OX, OY),
            "floors": 1, "unit_type": "2+1", "unit_count": 3, "footprint_gross": round(area, 2), "gross_total": round(area, 2),
            "unit_net_area": units, "checks": checks, "warnings": setback_warnings(sb_detail), "layout": "apartment", "units_per_floor": 3,
            "note": "CAD kat planından birebir 3D — 3 daireli normal kat (2 × ayna 2+1 + güney 2+1), U merdiven + asansör "
                    "çekirdeği; pencereler ve kat yüksekliği varsayım. Şematik, mimar kontrolü gerekir."}


def scenario():
    els = elements()
    return els, report(els), design(els)
