"""Demo senaryosu: küçük tomruk dağ evi — ~100 m², zemin kat + asma kat, ön veranda.

Referans: "Küçük ve İşlevsel Dağ Evi" teknik plan seti (10 × 6.5 m gövde, 10 × 3.5 m veranda,
Amerikan mutfak + salon + taş şömine, ebeveyn banyosu (kompost tuvalet) + küçük sauna,
asma katta log yatak + gömme dolap, ayaklı temel). Villa senaryosuyla aynı hücre→duvar mantığı;
metraj, maliyet, çizimler ve 3D aynen çalışır. Duvarlar tomruk ("wood" etiketi → DUV-03),
çatı beşik (roof elemanı → CAT-02), veranda saçağı tek eğimli.

Koordinatlar: plan x (sokak cephesi), y (derinlik; y=0 sokak), metre. Bina aksı OX,OY'den başlar.
"""

import math

from .generate import EXT_T, setback_checks, setback_warnings, INT_T, Rect, _door, _room_poly, _shared, _wall_segments
from .quantities import polygon_area

PARCEL = (30.0, 28.0)
OX, OY = 10.0, 9.0                     # bina aks başlangıcı
W, D = 10.0, 6.5                       # gövde aks ölçüsü
LOFT_Y = 3.0                           # asma kat bu derinlikten arkaya kadar
FH, LOFT_H, SLAB = 3.0, 2.4, 0.2
Z0 = 0.5                               # ayaklı temel: zemin döşemesi üst kotu
VER_D, VER_H = 3.5, 2.4                # veranda derinliği, sütun yüksekliği
RIDGE, EAVE = 2.2, 0.5                 # beşik çatı mahya yüksekliği, saçak çıkması
ZONING = {"taks": 0.10, "kaks": 0.15, "front": 5.0, "side": 5.0, "rear": 5.0, "max_floors": 2, "floor_height": FH}

SALON = "Amerikan Mutfak ve Salon"
GROUND = [
    Rect(0, 0, 6.5, 6.5, SALON), Rect(6.5, 0, 10, 2.2, "Ebeveyn Banyosu"),
    Rect(6.5, 2.2, 10, 4.0, "Küçük Sauna"), Rect(6.5, 4.0, 8.5, 6.5, "Merdiven", "core"),
    Rect(8.5, 4.0, 10, 6.5, "Kiler"),
]
LOFT = [
    Rect(0, LOFT_Y, 6.5, 6.5, "Ebeveyn Yatak Odası"), Rect(6.5, LOFT_Y, 10, 4.0, "Hol"),
    Rect(6.5, 4.0, 8.5, 6.5, "Merdiven", "core"), Rect(8.5, 4.0, 10, 6.5, "Gömme Dolap"),
]
# asma katta duvar yerine korkuluk olan kenarlar: (orient, coord, s0, s1)
LOFT_OPEN = [("h", LOFT_Y, 0.0, 10.0), ("h", 4.0, 6.5, 8.5), ("v", 6.5, 4.0, 6.5)]


def _by(rects, name):
    return next(r for r in rects if r.name == name)


def _win(orient, c, mid, w, sill=0.9, h=1.2):
    return (orient, c, round(mid - w / 2, 3), round(mid + w / 2, 3), "window", sill, h)


def _dr(rects, a, b, w=0.9, at="mid"):
    d = _door(_shared(_by(rects, a), _by(rects, b)), w, at)
    return (*d, None, None)


def ground_openings():
    R = GROUND
    ops = [("h", 0, 5.2, 6.1, "door", None, None)]                                   # veranda → salon
    ops += [_dr(R, SALON, "Ebeveyn Banyosu", 0.8), _dr(R, "Ebeveyn Banyosu", "Küçük Sauna", 0.7, "start"),
            _dr(R, SALON, "Merdiven", 1.0), _dr(R, "Merdiven", "Kiler", 0.8)]
    ops += [_win("h", 0, 2.2, 2.0), _win("v", 0, 2.0, 1.6), _win("v", 0, 5.0, 1.2),
            _win("h", 6.5, 3.2, 1.8, 1.1, 1.0), _win("h", 6.5, 9.25, 0.7, 1.5, 0.6),
            _win("h", 0, 8.25, 0.7, 1.5, 0.6), _win("v", 10, 3.1, 0.6, 1.5, 0.6)]
    return ops


def loft_openings():
    R = LOFT
    ops = [_dr(R, "Ebeveyn Yatak Odası", "Hol", 0.8), _dr(R, "Hol", "Gömme Dolap", 0.8)]
    ops += [_win("h", 6.5, 3.25, 1.2, 0.9, 1.0), _win("v", 0, 4.75, 1.0, 0.9, 1.0)]
    return ops


def _is_open(orient, c, s0, s1):
    return any(o == orient and abs(cc - c) < 1e-6 and a - 1e-6 <= s0 and s1 <= b + 1e-6 for o, cc, a, b in LOFT_OPEN)


def _floor_elements(rects, ops, level, z, height, open_edges=False):
    lines = _wall_segments(rects, W, D)
    if open_edges:
        lines = {k: [p for p in v if not _is_open(k[0], k[1], p[0], p[1])] for k, v in lines.items()}
    P = lambda x, y: [round(OX + x, 3), round(OY + y, 3)]
    els, wi = [], 0
    for (orient, c), pieces in sorted(lines.items()):
        for s0, s1, t in pieces:
            wi += 1
            mine = sorted([o for o in ops if o[0] == orient and abs(o[1] - c) < 1e-6 and o[2] >= s0 - 1e-6 and o[3] <= s1 + 1e-6],
                          key=lambda o: o[2])
            start, end = ((s0, c), (s1, c)) if orient == "h" else ((c, s0), (c, s1))
            ext = (orient == "h" and c in (0, D)) or (orient == "v" and c in (0, W))
            els.append({"type": "wall", "name": f"{level}/D{wi:02d}", "tag": "wood", "level": level, "exterior": ext,
                        "start": P(*start), "end": P(*end), "thickness": t, "height": height, "base_z": z,
                        "openings": [{"offset": round(a - s0, 3), "width": round(b - a, 3), "kind": k,
                                      **({"sill": sl, "height": h} if k == "window" else {"height": 2.1, "leaf": True})}
                                     for _, _, a, b, k, sl, h in mine]})
    for r in rects:
        els.append({"type": "room", "name": f"{level}/{r.name}", "level": level, "points": [P(x, y) for x, y in _room_poly(r, lines)],
                    "z": z, "height": height, "role": "common" if r.kind == "core" else "room"})
    return els


def _slab(name, pts, z, t, tag, role, level):
    return {"type": "slab", "name": name, "tag": tag, "role": role, "level": level, "points": pts, "z": z, "thickness": t}


def _box(name, origin, size, tag, level):
    return {"type": "box", "name": name, "tag": tag, "level": level, "origin": [round(v, 3) for v in origin], "size": size}


def elements():
    PW, PD = PARCEL
    rect = lambda x0, y0, x1, y1: [[x0, y0], [x1, y0], [x1, y1], [x0, y1]]
    h = EXT_T / 2
    x0, x1 = OX - h, OX + W + h
    y0, y1 = OY - h, OY + D + h
    vy = OY - VER_D                                       # veranda ön kenarı
    Z, K = "Zemin Kat", "Asma Kat"
    els = [
        _slab("parsel", rect(0, 0, PW, PD), -0.02, 0.3, "terrain", "site", "Arsa"),
        _slab("giris_yolu", rect(OX + 4.9, 0, OX + 6.4, vy - 0.9), 0.02, 0.05, "stone", "paving", "Arsa"),
        _slab("otopark", rect(OX + 11.5, 0, OX + 16.5, 6.0), 0.02, 0.05, "stone", "paving", "Arsa"),
        _slab("veranda", rect(x0, vy, x1, y0), Z0, 0.15, "wood", "deck", "Arsa"),
        # veranda saçağı: tek eğimli, arkada (bina duvarında) yüksek
        {"type": "roof", "name": "veranda_cati", "tag": "wood", "level": "Arsa", "x0": round(x0 - 0.3, 3), "y0": round(vy - 0.4, 3),
         "x1": round(x1 + 0.3, 3), "y1": round(y0, 3), "z": Z0 + VER_H, "ridge": 0.9, "ridge_at": 1.0, "axis": "x", "thickness": 0.15},
    ]
    # ayaklı temel: taş takozlar
    pi = 0
    for py in (vy + 0.15, y0, OY + 3.25, y1 - 0.3):
        for px in (x0, OX + 2.4, OX + 4.85, OX + 7.3, x1 - 0.3):
            els.append(_box(f"ayak{pi:02d}", (px, py, -0.1), [0.3, 0.3, Z0 - SLAB + 0.1], "concrete", "Arsa"))
            pi += 1
    # veranda: sütunlar, korkuluk, giriş basamağı
    for i, px in enumerate((x0, OX + 3.2, OX + 6.6, x1 - 0.15)):
        els.append(_box(f"veranda_sutun{i}", (px, vy, Z0), [0.15, 0.15, VER_H], "wood", "Arsa"))
    for i, (a, b) in enumerate(((x0, OX + 5.2), (OX + 6.1, x1))):
        els.append({**_box(f"veranda_korkuluk{i}", (a, vy, Z0), [round(b - a, 3), 0.08, 0.9], "wood", "Arsa"), "style": "baluster"})
    for i, px in enumerate((x0, x1 - 0.08)):
        els.append({**_box(f"veranda_korkuluk_yan{i}", (px, vy, Z0), [0.08, round(y0 - vy, 3), 0.9], "wood", "Arsa"), "style": "baluster"})
    els.append({"type": "stairs", "name": "veranda_basamak", "tag": "wood", "level": "Arsa",
                "origin": [OX + 6.1, vy - 0.9, 0.0], "width": 0.9, "steps": 3, "rise": 0.17, "run": 0.3, "rotation_z": 90})
    for i, p in enumerate([([3, 3], 9), ([27, 4], 11), ([2.5, 14], 8), ([27.5, 16], 10), ([5, 25], 12), ([24, 26], 9), ([14, 26.5], 8)]):
        els.append({"type": "tree", "name": f"agac{i}", "level": "Arsa", "position": p[0], "height": p[1]})

    # zemin kat
    fp = rect(x0, y0, x1, y1)
    els.append({**_slab(f"{Z}/doseme", fp, Z0, SLAB, "wood", "floor", Z), "foundation": "piers"})  # ayaklı temel
    els += _floor_elements(GROUND, ground_openings(), Z, Z0, FH - SLAB)
    els.append({"type": "stairs", "name": f"{Z}/merdiven", "tag": "wood", "level": Z,
                "origin": [OX + 7.5, OY + 4.2, Z0], "width": 0.9, "steps": 11, "rise": round(FH / 12, 4), "run": 0.2, "rotation_z": 90})
    # taş şömine: salonun doğu duvarında, baca mahyayı geçer
    els.append(_box("somine_baca", (OX + 6.5 - INT_T / 2 - 0.6, OY + 2.5, Z0), [0.6, 1.4, FH + LOFT_H + RIDGE + 0.6], "stone", Z))
    els.append(_box("somine_ocak", (OX + 6.5 - INT_T / 2 - 1.1, OY + 2.7, Z0), [0.5, 1.0, 0.45], "stone", Z))
    els.append(_box("sauna_sedir", (OX + 9.4, OY + 2.35, Z0), [0.5, 1.5, 0.45], "wood", Z))
    els.append(_box("sauna_soba", (OX + 6.7, OY + 3.5, Z0), [0.4, 0.4, 0.6], "metal", Z))

    # asma kat: merdiven boşluğu döşemede açık
    zk = Z0 + FH
    loft = [[x0, OY + LOFT_Y], [x1, OY + LOFT_Y], [x1, y1], [OX + 8.5, y1], [OX + 8.5, OY + 4.0],
            [OX + 6.5, OY + 4.0], [OX + 6.5, y1], [x0, y1]]
    els.append(_slab(f"{K}/doseme", [[round(a, 3), round(b, 3)] for a, b in loft], zk, SLAB, "wood", "floor", K))
    els += _floor_elements(LOFT, loft_openings(), K, zk, LOFT_H - SLAB, open_edges=True)
    for i, (o, c, a, b) in enumerate(LOFT_OPEN):
        org = (OX + a, OY + c - 0.04, zk) if o == "h" else (OX + c - 0.04, OY + a, zk)
        size = [round(b - a, 3), 0.08, 1.0] if o == "h" else [0.08, round(b - a, 3), 1.0]
        els.append({**_box(f"korkuluk{i}", org, size, "wood", K), "style": "baluster"})

    els.append({"type": "roof", "name": "cati", "tag": "wood", "level": "Çatı", "x0": round(x0 - EAVE, 3), "y0": round(y0 - EAVE, 3),
                "x1": round(x1 + EAVE, 3), "y1": round(y1 + EAVE, 3), "z": zk + LOFT_H, "ridge": RIDGE, "ridge_at": 0.5,
                "axis": "x", "thickness": SLAB, "structure": "open"})
    # alınlıklar: saçaktan mahyaya üçgen tomruk duvar (batı ve doğu)
    for i, xx in enumerate((OX, OX + W)):
        els.append({"type": "wall", "name": f"Çatı/alinlik{i}", "tag": "wood", "level": "Çatı", "start": [xx, round(y0, 3)], "end": [xx, round(y1, 3)],
                    "thickness": EXT_T, "height": RIDGE, "base_z": zk + LOFT_H, "profile": "gable", "openings": [],
                    "exterior": True})
    return els


# ---------------------------------------------------------------- iç mekân düzeni
ROT = {"S": math.pi, "N": 0.0, "W": math.pi / 2, "E": -math.pi / 2}


def design(els):
    rooms = {e["name"]: e for e in els if e["type"] == "room"}

    def B(level, name):
        pts = rooms[f"{level}/{name}"]["points"]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        return min(xs), min(ys), max(xs), max(ys)

    objs = []

    def put(kind, level, x, y, rot=0.0, h=0.0):
        objs.append({"id": f"c{len(objs):03d}", "kind": kind, "level": level, "x": round(x, 3), "y": round(y, 3), "rot": round(rot, 4), "h": h})

    def wall(kind, level, room, edge, t, depth, gap=0.02):
        x0, y0, x1, y1 = B(level, room)
        if edge == "S": put(kind, level, x0 + (x1 - x0) * t, y0 + depth / 2 + gap, ROT["S"])
        elif edge == "N": put(kind, level, x0 + (x1 - x0) * t, y1 - depth / 2 - gap, ROT["N"])
        elif edge == "W": put(kind, level, x0 + depth / 2 + gap, y0 + (y1 - y0) * t, ROT["W"])
        else: put(kind, level, x1 - depth / 2 - gap, y0 + (y1 - y0) * t, ROT["E"])

    Z, K = "Zemin Kat", "Asma Kat"
    # --- salon + Amerikan mutfak: tezgâh kuzey duvarında, oturma grubu şömineye (doğu) dönük, yemek masası batıda
    x0, y0, x1, y1 = B(Z, SALON)
    cy = (y0 + y1) / 2
    wall("mutfak", Z, SALON, "N", .35, .62)
    wall("buzdolabi", Z, SALON, "N", .75, .72)
    put("kanepe", Z, x0 + 2.9, cy, ROT["W"])
    put("hali", Z, x0 + 4.0, cy, ROT["W"])
    put("modern_coffee_table_01", Z, x0 + 4.3, cy, ROT["W"])
    put("modern_arm_chair_01", Z, x0 + 4.2, y0 + 1.2, math.pi * .3)
    tx, ty = x0 + 1.3, y0 + 4.4
    put("yemek_masasi", Z, tx, ty, 0)
    for dx in (-.55, .55):
        put("sandalye", Z, tx + dx, ty - .75, ROT["S"])
        put("sandalye", Z, tx + dx, ty + .75, ROT["N"])
    put("potted_plant_02", Z, x0 + .5, y0 + .5)
    # --- ebeveyn banyosu: duş kuzeyde, kompost tuvalet doğuda, lavabo kuzeydoğuda
    wall("dus", Z, "Ebeveyn Banyosu", "N", .5, .93)
    wall("klozet", Z, "Ebeveyn Banyosu", "E", .3, .64)
    wall("lavabo", Z, "Ebeveyn Banyosu", "N", .8, .48)
    wall("kitaplik", Z, "Kiler", "E", .5, .35)
    # --- asma kat: log yatak batı duvarında, gömme dolap ayrı mahal
    wall("yatak_cift", K, "Ebeveyn Yatak Odası", "W", .5, 2.18)
    x0, y0, x1, y1 = B(K, "Ebeveyn Yatak Odası")
    for dy in (-1.2, 1.2):
        put("side_table_01", K, x0 + .25, (y0 + y1) / 2 + dy, ROT["W"])
    put("hali", K, x0 + 3.5, (y0 + y1) / 2, ROT["W"])
    put("modern_arm_chair_01", K, x0 + 4.5, y0 + 1.0, math.pi * .8)
    wall("gardirop", K, "Ebeveyn Yatak Odası", "N", .8, .63)
    # --- veranda
    put("outdoor_table_chair_set_01", Z, OX + 2.5, OY - 1.8, 0)
    put("potted_plant_04", Z, OX + 9.3, OY - 1.0)

    floors = {name: ("large_grey_tiles" if "Banyo" in name else "oak_wood_planks") for name in rooms}
    return {"floors": floors, "paint": "kirik_beyaz", "objects": objs}


def report(els):
    PW, PD = PARCEL
    A = PW * PD
    h = EXT_T / 2
    fp = (W + EXT_T) * (D + EXT_T)
    gross = sum(polygon_area([tuple(p) for p in e["points"]]) for e in els if e["type"] == "slab" and e["role"] == "floor")
    sb, sb_detail, sb_ok = setback_checks(PW, PD, (OX - h, OY - h, OX + W + h, OY + D + h), ZONING)
    z = ZONING
    checks = {"taks": {"value": round(fp / A, 3), "limit": z["taks"], "ok": fp / A <= z["taks"] + 1e-3},
              "kaks": {"value": round(gross / A, 3), "limit": z["kaks"], "ok": gross / A <= z["kaks"] + 1e-3},
              "floors": {"value": 2, "limit": z["max_floors"], "ok": True}, "setbacks": sb,
              "setbacks_detail": sb_detail, "setback_ok": sb_ok}
    net = sum(polygon_area([tuple(p) for p in e["points"]]) for e in els if e["type"] == "room")
    return {"parcel_area": A, "footprint": (W, D), "origin": (OX, OY), "floors": 2, "unit_type": "Dağ Evi 1+1",
            "unit_count": 1, "footprint_gross": round(fp, 2), "gross_total": round(gross, 2), "unit_net_area": {"Dağ Evi": round(net, 2)},
            "checks": checks, "warnings": setback_warnings(sb_detail), "layout": "cabin", "units_per_floor": 1,
            "note": "Demo senaryosu — tomruk dağ evi (zemin + asma kat, ön veranda, ayaklı temel, beşik çatı); "
                    "şematik ön tasarım, mimar kontrolü gerekir."}


def scenario():
    els = elements()
    return els, report(els), design(els)
