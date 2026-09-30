"""Demo senaryosu: iki katlı modern villa — plan + bahçe/havuz + döşenmiş iç mekân.

Mevcut nesne kataloğuna (interior.js ITEMS) göre kurgulandı; her mahal katalogdaki bir nesne
grubunu kullanır. Plan, apartman üreticisinin hücre→duvar mantığıyla kurulur; metraj, maliyet,
çizimler ve 3D bu projede de aynen çalışır.

Koordinatlar: plan x (sokak cephesi), y (derinlik; y=0 sokak), metre. Bina aksı OX,OY'den başlar.
"""

import math

from .generate import EXT_T, setback_checks, setback_warnings, Rect, _door, _room_poly, _shared, _wall_segments
from .quantities import polygon_area

PARCEL = (32.0, 31.0)
OX, OY = 7.0, 6.0                      # bina aks başlangıcı (sol yan ve ön çekme + yarım duvar)
W, D = 18.0, 12.0                      # bina aks ölçüsü
FH, SLAB = 3.2, 0.2
ZONING = {"taks": 0.25, "kaks": 0.50, "front": 5.5, "side": 6.5, "rear": 12.0, "max_floors": 2, "floor_height": FH}

# ---------------------------------------------------------------- mahaller (bina yerel aks koordinatı)
GROUND = [
    Rect(0, 0, 5, 6, "Çalışma Odası"), Rect(5, 0, 8.5, 6, "Giriş Holü"),
    Rect(8.5, 0, 10.5, 2, "Misafir WC"), Rect(8.5, 2, 10.5, 6, "Merdiven", "core"),
    Rect(10.5, 0, 18, 6, "Mutfak"), Rect(0, 6, 12, 12, "Salon"),
    Rect(12, 6, 16, 12, "Misafir Odası"), Rect(16, 6, 18, 12, "Misafir Banyosu"),
]
FIRST = [
    Rect(0, 0, 8.5, 5, "Aile Salonu"), Rect(8.5, 0, 10.5, 2, "Depo"), Rect(8.5, 2, 10.5, 5, "Merdiven", "core"),
    Rect(10.5, 0, 14, 5, "Ortak Banyo"), Rect(14, 0, 18, 5, "Hobi Odası"), Rect(0, 5, 18, 7, "Hol"),
    Rect(0, 7, 7, 12, "Ebeveyn Yatak Odası"), Rect(7, 7, 10, 12, "Ebeveyn Banyosu"),
    Rect(10, 7, 14, 12, "Çocuk Odası 1"), Rect(14, 7, 18, 12, "Çocuk Odası 2"),
]


def _by(rects, name):
    return next(r for r in rects if r.name == name)


def _win(orient, c, mid, w, sill=0.9, h=1.4):
    return (orient, c, round(mid - w / 2, 3), round(mid + w / 2, 3), "window", sill, h)


def _dr(rects, a, b, w=0.9, at="mid"):
    e = _shared(_by(rects, a), _by(rects, b))
    d = _door(e, w, at)
    return (*d, None, None)


def ground_openings():
    R = GROUND
    ops = [("h", 0, 6.1, 7.3, "door", None, None)]                          # bina girişi (Giriş Holü)
    ops += [_dr(R, "Giriş Holü", "Çalışma Odası", 0.9, "start"), _dr(R, "Giriş Holü", "Misafir WC", 0.8),
            _dr(R, "Giriş Holü", "Salon", 1.6), _dr(R, "Merdiven", "Salon", 1.0),
            ("h", 6, 11.0, 12.0, "door", None, None),                         # salon ↔ mutfak (geniş geçiş)
            _dr(R, "Salon", "Misafir Odası", 0.9, "start"), _dr(R, "Misafir Odası", "Misafir Banyosu", 0.8, "start")]
    ops += [_win("h", 0, 2.5, 2.0), _win("v", 0, 3.0, 1.6), _win("h", 0, 9.5, 0.6, 1.5, 0.6),
            _win("h", 0, 14.2, 2.4), _win("v", 18, 3.0, 1.6),
            _win("h", 12, 2.2, 2.8, 0.05, 2.5), _win("h", 12, 5.6, 2.8, 0.05, 2.5), _win("h", 12, 9.0, 2.8, 0.05, 2.5),
            _win("v", 0, 9.0, 2.4, 0.05, 2.5), _win("h", 12, 14.0, 2.0, 0.6, 2.0), _win("h", 12, 17.0, 0.7, 1.5, 0.7)]
    return ops


def first_openings():
    R = FIRST
    ops = [_dr(R, "Hol", "Aile Salonu", 1.4), _dr(R, "Aile Salonu", "Depo", 0.8), _dr(R, "Hol", "Merdiven", 1.0),
           _dr(R, "Hol", "Ortak Banyo", 0.8), _dr(R, "Hol", "Hobi Odası", 0.9),
           ("h", 7, 5.6, 6.5, "door", None, None),                             # ebeveyn yatak odası girişi (doğu ucu)
           _dr(R, "Ebeveyn Yatak Odası", "Ebeveyn Banyosu", 0.8, "start"),
           ("h", 7, 12.9, 13.8, "door", None, None), ("h", 7, 14.4, 15.3, "door", None, None)]
    ops += [_win("h", 0, 2.4, 2.6, 0.6, 2.0), _win("v", 0, 2.5, 1.8), _win("h", 0, 12.2, 1.0, 1.5, 0.7),
            _win("h", 0, 16.0, 1.8), _win("v", 18, 2.5, 1.4),
            _win("h", 12, 3.5, 3.0, 0.05, 2.5), _win("v", 0, 9.5, 1.6), _win("h", 12, 8.5, 0.9, 1.5, 0.7),
            _win("h", 12, 12.0, 1.8), _win("h", 12, 16.0, 1.8), _win("v", 18, 9.5, 1.4)]
    return ops


def _floor_elements(rects, ops, level, z):
    lines = _wall_segments(rects, W, D)
    P = lambda x, y: [round(OX + x, 3), round(OY + y, 3)]
    els, wi = [], 0
    for (orient, c), pieces in sorted(lines.items()):
        for s0, s1, t in pieces:
            wi += 1
            mine = sorted([o for o in ops if o[0] == orient and abs(o[1] - c) < 1e-6 and o[2] >= s0 - 1e-6 and o[3] <= s1 + 1e-6],
                          key=lambda o: o[2])
            start, end = ((s0, c), (s1, c)) if orient == "h" else ((c, s0), (c, s1))
            ext = (orient == "h" and c in (0, D)) or (orient == "v" and c in (0, W))
            els.append({"type": "wall", "name": f"{level}/D{wi:02d}", "tag": "wall", "level": level, "exterior": ext,
                        "start": P(*start), "end": P(*end), "thickness": t, "height": FH - SLAB, "base_z": z,
                        "openings": [{"offset": round(a - s0, 3), "width": round(b - a, 3), "kind": k,
                                      **({"sill": sl, "height": h} if k == "window" else {"height": 2.1, "leaf": True})}
                                     for _, _, a, b, k, sl, h in mine]})
    for r in rects:
        els.append({"type": "room", "name": f"{level}/{r.name}", "level": level, "points": [P(x, y) for x, y in _room_poly(r, lines)],
                    "z": z, "height": FH - SLAB, "role": "common" if r.kind == "core" else "room"})
    st = _by(rects, "Merdiven")
    els.append({"type": "stairs", "name": f"{level}/merdiven", "tag": "stone", "level": level,
                "origin": [OX + st.x1 - 0.1, OY + st.y0 + 0.1, z], "width": 1.0, "steps": 15, "rise": FH / 16, "run": 0.25,
                "rotation_z": 90})
    return els, lines


def _slab(name, pts, z, t, tag, role, level):
    return {"type": "slab", "name": name, "tag": tag, "role": role, "level": level, "points": pts, "z": z, "thickness": t}


def elements():
    PW, PD = PARCEL
    rect = lambda x0, y0, x1, y1: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    h = EXT_T / 2
    fp = rect(OX - h, OY - h, OX + W + h, OY + D + h)
    els = [
        _slab("parsel", rect(0, 0, PW, PD), -0.02, 0.3, "terrain", "site", "Arsa"),
        _slab("giris_yolu", rect(OX + 6.1, 0, OX + 7.3, OY - h), 0.02, 0.05, "stone", "paving", "Arsa"),
        _slab("otopark", rect(OX + 11, 0, OX + 17, OY - 1.0), 0.02, 0.05, "stone", "paving", "Arsa"),
        _slab("teras", rect(OX - h, OY + D + h, OX + W + h, OY + D + 3.2), 0.05, 0.12, "wood", "deck", "Arsa"),
        # havuz: su yüzeyi + dört yanda taş kenar (su görünür kalsın diye üst üste binmez)
        _slab("havuz", rect(10.5, 23.0, 22.5, 27.0), -0.06, 0.05, "water", "pool", "Arsa"),
        _slab("havuz_kenar_g", rect(9.3, 21.8, 23.7, 23.0), 0.03, 0.1, "stone", "paving", "Arsa"),
        _slab("havuz_kenar_k", rect(9.3, 27.0, 23.7, 28.4), 0.03, 0.1, "stone", "paving", "Arsa"),
        _slab("havuz_kenar_b", rect(9.3, 23.0, 10.5, 27.0), 0.03, 0.1, "stone", "paving", "Arsa"),
        _slab("havuz_kenar_d", rect(22.5, 23.0, 23.7, 27.0), 0.03, 0.1, "stone", "paving", "Arsa"),
        _slab("terastan_havuza", rect(15.4, OY + D + 3.2, 17.6, 21.8), 0.03, 0.1, "stone", "paving", "Arsa"),
    ]
    # pergola: terasın batı yarısı üstünde
    for i, x in enumerate([OX + 0.3, OX + 4.3, OX + 8.3]):
        els.append({"type": "box", "name": f"pergola_kolon{i}", "tag": "metal", "level": "Arsa",
                    "origin": [x, OY + D + 2.8, 0.05], "size": [0.12, 0.12, 2.75]})
    els.append({"type": "box", "name": "pergola_kiris", "tag": "metal", "level": "Arsa", "origin": [OX + 0.2, OY + D + 2.75, 2.8], "size": [8.4, 0.2, 0.12]})
    for i in range(13):
        els.append({"type": "box", "name": f"pergola_lata{i}", "tag": "wood", "level": "Arsa",
                    "origin": [OX + 0.3 + i * 0.66, OY + D + h, 2.92], "size": [0.08, 2.9, 0.06]})
    for i, (p, hgt) in enumerate([([3, 4], 7), ([29, 4], 6), ([2.5, 16], 8), ([29.5, 15], 9), ([3.5, 27], 7), ([28.5, 27.5], 8), ([6, 29], 6)]):
        els.append({"type": "tree", "name": f"agac{i}", "level": "Arsa", "position": p, "height": hgt})
    for f, (rects, ops, lvl) in enumerate([(GROUND, ground_openings(), "Zemin Kat"), (FIRST, first_openings(), "Kat 1")]):
        z = f * FH
        els.append(_slab(f"{lvl}/doseme", fp, z, SLAB, "concrete", "floor", lvl))
        e, _ = _floor_elements(rects, ops, lvl, z)
        els += e
    top = 2 * FH
    els.append(_slab("cati", fp, top, SLAB, "roof", "roof", "Çatı"))
    for i, (o, s) in enumerate([([OX - h, OY - h], [W + EXT_T, EXT_T]), ([OX - h, OY + D - h], [W + EXT_T, EXT_T]),
                                ([OX - h, OY - h], [EXT_T, D + EXT_T]), ([OX + W - h, OY - h], [EXT_T, D + EXT_T])]):
        els.append({"type": "box", "name": f"parapet{i}", "tag": "wall", "level": "Çatı", "origin": [o[0], o[1], top], "size": [s[0], s[1], 0.6]})
    return els


# ---------------------------------------------------------------- iç mekân düzeni
ROT = {"S": math.pi, "N": 0.0, "W": math.pi / 2, "E": -math.pi / 2}   # kenara sırtını veren nesnenin önü oda içine


def design(els):
    rooms = {e["name"]: e for e in els if e["type"] == "room"}

    def B(level, name):
        pts = rooms[f"{level}/{name}"]["points"]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    objs = []

    def put(kind, level, x, y, rot=0.0, h=0.0):
        objs.append({"id": f"v{len(objs):03d}", "kind": kind, "level": level, "x": round(x, 3), "y": round(y, 3), "rot": round(rot, 4), "h": h})

    def wall(kind, level, room, edge, t, depth, gap=0.02):
        x0, y0, x1, y1 = B(level, room)
        if edge == "S": put(kind, level, x0 + (x1 - x0) * t, y0 + depth / 2 + gap, ROT["S"])
        elif edge == "N": put(kind, level, x0 + (x1 - x0) * t, y1 - depth / 2 - gap, ROT["N"])
        elif edge == "W": put(kind, level, x0 + depth / 2 + gap, y0 + (y1 - y0) * t, ROT["W"])
        else: put(kind, level, x1 - depth / 2 - gap, y0 + (y1 - y0) * t, ROT["E"])

    Z, K = "Zemin Kat", "Kat 1"
    # --- Salon: oturma grubu batıda (TV batı duvarında), yemek alanı doğuda mutfağa yakın
    x0, y0, x1, y1 = B(Z, "Salon")
    cy = (y0 + y1) / 2
    wall("tv_unitesi", Z, "Salon", "W", .5, .42)
    wall("tv", Z, "Salon", "W", .5, .1)
    put("hali", Z, x0 + 2.6, cy, ROT["W"])
    put("modern_coffee_table_01", Z, x0 + 2.25, cy, ROT["W"])
    put("kanepe_l", Z, x0 + 4.35, cy + .2, ROT["E"])
    put("mid_century_lounge_chair", Z, x0 + 1.4, y1 - 1.0, math.pi * .8)
    put("modern_arm_chair_01", Z, x0 + 1.4, y0 + 1.1, math.pi * .2)
    put("potted_plant_04", Z, x0 + .5, y1 - .5)
    put("potted_plant_02", Z, x1 - .5, y1 - .5)
    tx, ty = x0 + 9.0, cy + .3
    put("yemek_masasi", Z, tx, ty, 0)
    for dx in (-.55, .55):
        put("sandalye", Z, tx + dx, ty - .75, ROT["S"])
        put("sandalye", Z, tx + dx, ty + .75, ROT["N"])
    put("dining_chair_02", Z, tx - 1.35, ty, ROT["W"])
    put("dining_chair_02", Z, tx + 1.35, ty, ROT["E"])
    # --- Mutfak: tezgâh + buzdolabı doğu duvarında, ada ortada, bar tabureleri batı yüzünde
    x0, y0, x1, y1 = B(Z, "Mutfak")
    wall("mutfak", Z, "Mutfak", "E", .5, .62)
    wall("buzdolabi", Z, "Mutfak", "E", .9, .72)
    put("ada", Z, x1 - 2.6, (y0 + y1) / 2, ROT["E"])
    for dy in (-.7, 0, .7):
        put("bar_taburesi", Z, x1 - 3.75, (y0 + y1) / 2 + dy)
    put("potted_plant_02", Z, x0 + .5, y0 + .5)
    # --- Çalışma odası
    wall("calisma_masasi", Z, "Çalışma Odası", "W", .45, .7)
    x0, y0, x1, y1 = B(Z, "Çalışma Odası")
    put("dining_chair_02", Z, x0 + 1.05, y0 + (y1 - y0) * .45, ROT["E"])
    wall("kitaplik", Z, "Çalışma Odası", "N", .45, .35)
    put("modern_arm_chair_01", Z, x1 - .9, y1 - 1.6, math.pi * .15)
    put("potted_plant_02", Z, x0 + .5, y0 + .5)
    # --- Giriş holü, WC
    wall("Ottoman_01", Z, "Giriş Holü", "E", .75, .62)
    wall("potted_plant_04", Z, "Giriş Holü", "W", .85, .66)
    wall("klozet", Z, "Misafir WC", "E", .55, .64)
    wall("lavabo", Z, "Misafir WC", "N", .35, .48)
    # --- Misafir odası + banyosu
    wall("yatak_cift", Z, "Misafir Odası", "E", .55, 2.18)
    x0, y0, x1, y1 = B(Z, "Misafir Odası")
    for dy in (-1.2, 1.2):
        put("side_table_01", Z, x1 - .25, y0 + (y1 - y0) * .55 + dy, ROT["E"])
    wall("gardirop", Z, "Misafir Odası", "S", .55, .63)
    wall("dus", Z, "Misafir Banyosu", "N", .5, .93)
    wall("klozet", Z, "Misafir Banyosu", "E", .45, .64)
    wall("lavabo", Z, "Misafir Banyosu", "E", .2, .48)
    # --- 1. kat: aile salonu
    x0, y0, x1, y1 = B(K, "Aile Salonu")
    wall("kanepe", K, "Aile Salonu", "W", .5, .92)
    wall("tv_unitesi", K, "Aile Salonu", "E", .5, .42)
    wall("tv", K, "Aile Salonu", "E", .5, .1)
    put("hali", K, (x0 + x1) / 2 - .3, (y0 + y1) / 2, ROT["W"])
    put("modern_coffee_table_01", K, x0 + 2.2, (y0 + y1) / 2, ROT["W"])
    put("mid_century_lounge_chair", K, x1 - 1.3, y0 + .9, -math.pi * .25)
    put("potted_plant_04", K, x1 - .5, y1 - .5)
    # --- ortak banyo: küvet ön cephede, klozet + lavabo doğu duvarında
    wall("kuvet", K, "Ortak Banyo", "S", .5, .75)
    wall("klozet", K, "Ortak Banyo", "E", .6, .64)
    wall("lavabo", K, "Ortak Banyo", "E", .82, .48)
    # --- hobi odası
    wall("calisma_masasi", K, "Hobi Odası", "E", .45, .7)
    x0, y0, x1, y1 = B(K, "Hobi Odası")
    put("dining_chair_02", K, x1 - 1.05, y0 + (y1 - y0) * .45, ROT["W"])
    wall("kitaplik", K, "Hobi Odası", "W", .45, .35)
    # --- ebeveyn
    wall("yatak_cift", K, "Ebeveyn Yatak Odası", "W", .5, 2.18)
    x0, y0, x1, y1 = B(K, "Ebeveyn Yatak Odası")
    for dy in (-1.2, 1.2):
        put("side_table_01", K, x0 + .25, (y0 + y1) / 2 + dy, ROT["W"])
    wall("gardirop", K, "Ebeveyn Yatak Odası", "S", .35, .63)
    put("modern_arm_chair_01", K, x1 - .8, y1 - .9, math.pi * .8)
    put("hali", K, x0 + 2.4, (y0 + y1) / 2, ROT["W"])
    wall("dus", K, "Ebeveyn Banyosu", "N", .25, .93)
    wall("lavabo", K, "Ebeveyn Banyosu", "E", .3, .48)
    wall("klozet", K, "Ebeveyn Banyosu", "E", .62, .64)
    # --- çocuk odaları
    for room in ("Çocuk Odası 1", "Çocuk Odası 2"):
        wall("yatak_tek", K, room, "E", .72, 2.18)
        wall("calisma_masasi", K, room, "N", .3, .7)
        x0, y0, x1, y1 = B(K, room)
        put("sandalye", K, x0 + (x1 - x0) * .3, y1 - 1.05, ROT["S"])
        wall("gardirop", K, room, "W", .38, .63)
        put("hali", K, x0 + 1.9, y0 + 1.6, 0)
    # --- dış mekân (zemin kotunda): teras masası, havuz şezlongları, saksılar
    put("outdoor_table_chair_set_01", Z, OX + 3.5, OY + D + 1.6, 0)
    for i in range(4):
        put("sezlong", Z, 12.2 + i * 2.2, 27.7, 0)
    for x in (OX + 9.5, OX + W - .6):
        put("potted_plant_04", Z, x, OY + D + 2.7)

    floors = {}
    for name in rooms:
        n = name.split("/")[-1]
        floors[name] = ("herringbone_parquet" if n in ("Salon", "Aile Salonu") else
                        "marble_tiles" if n in ("Mutfak", "Giriş Holü", "Hol", "Merdiven") else
                        "large_grey_tiles" if ("Banyo" in n or "WC" in n) else
                        "terrazzo_tiles" if n == "Depo" else "oak_wood_planks")
    return {"floors": floors, "paint": "kirik_beyaz", "objects": objs}


def report(els):
    PW, PD = PARCEL
    A = PW * PD
    fp = (W + EXT_T) * (D + EXT_T)
    gross = fp * 2
    h = EXT_T / 2
    sb, sb_detail, sb_ok = setback_checks(PW, PD, (OX - h, OY - h, OX + W + h, OY + D + h), ZONING)
    z = ZONING
    checks = {"taks": {"value": round(fp / A, 3), "limit": z["taks"], "ok": fp / A <= z["taks"] + 1e-3},
              "kaks": {"value": round(gross / A, 3), "limit": z["kaks"], "ok": gross / A <= z["kaks"] + 1e-3},
              "floors": {"value": 2, "limit": z["max_floors"], "ok": True}, "setbacks": sb,
              "setbacks_detail": sb_detail, "setback_ok": sb_ok}
    net = sum(polygon_area([tuple(p) for p in e["points"]]) for e in els if e["type"] == "room")
    return {"parcel_area": A, "footprint": (W, D), "origin": (OX, OY), "floors": 2, "unit_type": "Villa 4+2",
            "unit_count": 1, "footprint_gross": round(fp, 2), "gross_total": round(gross, 2), "unit_net_area": {"Villa": round(net, 2)},
            "checks": checks, "warnings": setback_warnings(sb_detail), "layout": "villa", "units_per_floor": 1,
            "note": "Demo senaryosu — iki katlı müstakil villa; şematik ön tasarım, mimar kontrolü gerekir."}


def scenario():
    els = elements()
    return els, report(els), design(els)
