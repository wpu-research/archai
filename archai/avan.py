"""Avan programı: tipik kat üreticisinin (generate) çıktısını 1. bodrum + zemin katta işyeri + çatı katıyla tamamlar.

`generate` aynı planı her katta tekrarlar (zemin dahil). Avan projelerinde ise:
  - zemin kat işyeridir (konut planı atılır, çekirdek korunur, kalan alan dükkânlara bölünür),
  - zemin altında tek bodrum vardır (sığınak, otopark, teknik/su deposu; çekirdek bodruma iner),
  - çekirdeğin üstünde çatı katı (merdiven çıkışı / makine dairesi) bulunur.

Girdi `program["avan"] = {"basement": bool, "shops": int, "attic_area": m²}`; hepsi isteğe bağlıdır. Çekirdek ve dış
hat üreticinin kat elemanlarından okunur, yani `generate` değişmez ve avan olmayan projeler etkilenmez.
"""

import math

from .generate import EXT_T
from .quantities import polygon_area

CORE_WALL_T = 0.20
SHOP_WALL_T = 0.20
BASEMENT_WALL_T = 0.30
SLAB_T = 0.2
SHELTER_REQUIRED = 100.0         # avan sığınak hesabı: 24 konut için ≈100 m² (sığınak sol şeridin tamamıdır)
PARKING_AREA_PER_CAR = 25.0      # rampa/dolaşım dahil yaklaşık m²/araç
PARKING_PER_UNITS = 3            # dairelerde 0–80 m² için 1 otopark / 3 konut (avan hesabı)


def _bbox(points):
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    return min(xs), min(ys), max(xs), max(ys)


def _wall(lvl, name, a, b, t, z, h, openings=(), exterior=False):
    return {"type": "wall", "name": f"{lvl}/{name}", "tag": "wall", "level": lvl, "exterior": exterior,
            "start": [round(a[0], 3), round(a[1], 3)], "end": [round(b[0], 3), round(b[1], 3)], "thickness": t,
            "height": h, "base_z": z, "openings": list(openings)}


def _door(offset, width=1.0):
    return {"offset": round(offset, 3), "width": width, "kind": "door", "height": 2.1, "leaf": True}


def _window(offset, width, sill=0.9, height=1.4):
    return {"offset": round(offset, 3), "width": round(width, 3), "kind": "window", "sill": sill, "height": height}


def _room(lvl, name, rect, z, h, role="room"):
    x0, y0, x1, y1 = rect
    return {"type": "room", "name": f"{lvl}/{name}", "level": lvl, "points": [[round(x0, 3), round(y0, 3)],
            [round(x1, 3), round(y0, 3)], [round(x1, 3), round(y1, 3)], [round(x0, 3), round(y1, 3)]],
            "z": z, "height": h, "role": role}


def _shell(lvl, axes, t, z, h, front_ops=(), back_ops=(), left_ops=(), right_ops=()):
    """Dikdörtgen dış kabuk: aks dikdörtgeni (x0, y0, x1, y1) üzerinde dört duvar."""
    x0, y0, x1, y1 = axes
    return [_wall(lvl, "D_on", (x0, y0), (x1, y0), t, z, h, front_ops, True),
            _wall(lvl, "D_sag", (x1, y0), (x1, y1), t, z, h, right_ops, True),
            _wall(lvl, "D_arka", (x0, y1), (x1, y1), t, z, h, back_ops, True),
            _wall(lvl, "D_sol", (x0, y0), (x0, y1), t, z, h, left_ops, True)]


def _split(lo, hi, n):
    step = (hi - lo) / n
    return [lo + i * step for i in range(n + 1)]


def _core(elements, lvl):
    """Üreticinin zemin kat çekirdeği: Kat Holü / Merdiven / Asansör odalarının sınır kutusu."""
    pts = [p for e in elements if e["type"] == "room" and e.get("level") == lvl and e.get("role") == "common"
           for p in e["points"]]
    return _bbox(pts) if pts else None


def _clone(e, lvl_from, lvl_to, dz):
    c = dict(e)
    c["name"] = e["name"].replace(f"{lvl_from}/", f"{lvl_to}/", 1)
    c["level"] = lvl_to
    if "origin" in c:
        c["origin"] = [c["origin"][0], c["origin"][1], round(c["origin"][2] + dz, 3)]
    if "z" in c:
        c["z"] = round(c["z"] + dz, 3)
    return c


def _ground_shops(elements, outline, core, fh, n_shops):
    """Zemin kat: konut duvar/mahallerini at, dış kabuk + çekirdek kabuğu + dükkân bölmelerini kur."""
    lvl = "Zemin Kat"
    keep = [e for e in elements if not (e.get("level") == lvl and (e["type"] == "wall"
            or (e["type"] == "room" and e.get("role") != "common")))]
    x0, y0, x1, y1 = outline
    h = EXT_T / 2
    ax = (x0 + h, y0 + h, x1 - h, y1 - h)               # dış duvar aksları
    cx0, cy0, cx1, cy1 = core
    cy1 = min(cy1, ax[3] - 3.0)
    H = fh - SLAB_T
    new_walls, rooms = [], []

    # bölgeler: sol şerit, sağ şerit, çekirdek arkası (varsa)
    left = (ax[0], ax[1], cx0, ax[3])
    right = (cx1, ax[1], ax[2], ax[3])
    rear = (cx0, cy1, cx1, ax[3]) if ax[3] - cy1 >= 3.0 else None
    n_rear = 2 if (rear and n_shops >= 6) else (1 if rear else 0)
    n_side = n_shops - n_rear
    n_left, n_right = n_side - n_side // 2, n_side // 2
    n_left, n_right = max(1, n_left), max(1, n_right)

    front_ops, back_ops, left_ops, right_ops = [], [], [], []
    shops = []
    for side_name, zone, n in (("sol", left, n_left), ("sag", right, n_right)):
        ys = _split(zone[1], zone[3], n)
        for i in range(n):
            shops.append({"rect": (zone[0], ys[i], zone[2], ys[i + 1]), "side": side_name, "idx": i, "n": n})
        for y in ys[1:-1]:
            new_walls.append(_wall(lvl, f"B_{side_name}{len(new_walls)}", (zone[0], y), (zone[2], y),
                                   SHOP_WALL_T, 0.0, H))
    if rear:
        xs = _split(rear[0], rear[2], n_rear)
        for i in range(n_rear):
            shops.append({"rect": (xs[i], rear[1], xs[i + 1], rear[3]), "side": "arka", "idx": i, "n": n_rear})
        for x in xs[1:-1]:
            new_walls.append(_wall(lvl, f"B_arka{len(new_walls)}", (x, rear[1]), (x, rear[3]), SHOP_WALL_T, 0.0, H))

    # çekirdek kabuğu: sol, sağ ve arka duvar (ön cephe ana girişe açık)
    core_ops = {"sol": [], "sag": [], "arka": []}
    for i, s in enumerate(shops):
        r = s["rect"]
        w = r[2] - r[0]
        dep = r[3] - r[1]
        if s["side"] == "sol":
            if s["idx"] == 0:                                           # ön dükkân: cepheden giriş + vitrin
                front_ops.append(_window(max(0.4, (w - 3.0) / 2 - 1.0), min(3.0, w - 1.0), 0.3, 2.2))
                front_ops.append(_door(r[0] - ax[0] + w - 1.4, 1.0))
            else:
                left_ops.append(_door(r[1] - ax[1] + dep / 2 - 0.5, 1.0))
            if s["idx"] == 0:
                left_ops.append(_window(r[1] - ax[1] + 0.8, max(1.2, dep - 1.6), 0.3, 2.2))
        elif s["side"] == "sag":
            if s["idx"] == 0:
                front_ops.append(_door(r[0] - ax[0] + 0.4, 1.0))
                front_ops.append(_window(r[0] - ax[0] + 1.8, min(3.0, w - 2.2), 0.3, 2.2))
            else:
                right_ops.append(_door(r[1] - ax[1] + dep / 2 - 0.5, 1.0))
            if s["idx"] == 0:
                right_ops.append(_window(r[1] - ax[1] + 0.8, max(1.2, dep - 1.6), 0.3, 2.2))
        else:                                                           # çekirdek arkası dükkân: holden giriş, arkadan vitrin
            core_ops["arka"].append(_door(r[0] - cx0 + (r[2] - r[0]) / 2 - 0.5, 1.0))
            back_ops.append(_window(r[0] - ax[0] + 0.5, max(1.0, w - 1.0), 0.3, 2.2))
    # ana giriş: çekirdek önündeki dış duvar bölümü
    front_ops.append(_door((cx0 + cx1) / 2 - ax[0] - 0.9, 1.8))
    front_ops.sort(key=lambda o: o["offset"])
    new_walls += _shell(lvl, ax, EXT_T, 0.0, H, front_ops, back_ops, left_ops, right_ops)
    new_walls.append(_wall(lvl, "C_sol", (cx0, ax[1]), (cx0, cy1), CORE_WALL_T, 0.0, H,
                           [_door(3.0, 1.0)]))
    new_walls.append(_wall(lvl, "C_sag", (cx1, ax[1]), (cx1, cy1), CORE_WALL_T, 0.0, H, [_door(3.0, 1.0)]))
    if rear:
        new_walls.append(_wall(lvl, "C_arka", (cx0, cy1), (cx1, cy1), CORE_WALL_T, 0.0, H, core_ops["arka"]))
    for k, s in enumerate(shops, 1):
        rooms.append(_room(lvl, f"İşyeri {k}", s["rect"], 0.0, H))
    areas = [polygon_area([tuple(p) for p in r["points"]]) for r in rooms]
    return keep + new_walls + rooms, ax, areas


def _basement(elements, outline, ax, core, fh):
    lvl = "1. Bodrum"
    z = -fh
    H = fh - SLAB_T
    x0, y0, x1, y1 = outline
    cx0, cy0, cx1, cy1 = core
    cy1 = min(cy1, ax[3] - 3.0)
    out = [{"type": "slab", "name": f"{lvl}/doseme", "tag": "concrete", "role": "floor", "level": lvl,
            "points": [[x0, y0], [x1, y0], [x1, y1], [x0, y1]], "z": z, "thickness": SLAB_T}]
    # sığınak: sol şeridin tamamı; otopark: sağ şerit; teknik / su deposu: çekirdek arkası
    rear = ax[3] - cy1 >= 3.0
    rooms = [("Sığınak", (ax[0], ax[1], cx0, ax[3])), ("Otopark", (cx1, ax[1], ax[2], ax[3]))]
    if rear:
        rooms.append(("Teknik / Su Deposu", (cx0, cy1, cx1, ax[3])))
    walls = _shell(lvl, ax, BASEMENT_WALL_T, z, H)
    walls.append(_wall(lvl, "C_sol", (cx0, ax[1]), (cx0, ax[3]), CORE_WALL_T, z, H, [_door(3.0, 1.0)]))
    walls.append(_wall(lvl, "C_sag", (cx1, ax[1]), (cx1, ax[3]), CORE_WALL_T, z, H, [_door(3.0, 1.0)]))
    if rear:
        walls.append(_wall(lvl, "C_arka", (cx0, cy1), (cx1, cy1), CORE_WALL_T, z, H, [_door(1.8, 1.0)]))
    rms = [_room(lvl, n, r, z, H, "common") for n, r in rooms]
    commons = [_clone(e, "Zemin Kat", lvl, -fh) for e in elements
               if e.get("level") == "Zemin Kat" and (e["type"] in ("stairs", "box")
                                                      or (e["type"] == "room" and e.get("role") == "common"))]
    areas = {n: round(polygon_area([tuple(p) for p in room["points"]]), 2) for (n, _), room in zip(rooms, rms)}
    return out + walls + rms + commons, areas


def _attic(elements, ax, core, fh, floors, area):
    """Çatı katı: çekirdeğin üstünde, `area` m² (merdiven çıkışı + makine dairesi); kendi düz çatısı üstte."""
    lvl = "Çatı Katı"
    z = floors * fh
    cx0, cy0, cx1, cy1 = core
    w = cx1 - cx0
    d = min(area / w, ax[3] - cy0 - 1.0)
    rect = (cx0, cy0, cx1, cy0 + d)
    H = fh - SLAB_T
    ops_f = [_window(1.0, w - 2.0, 0.9, 1.4)]
    walls = _shell(lvl, rect, EXT_T, z, H, front_ops=ops_f)
    room = _room(lvl, "Merdiven Çıkışı / Makine Dairesi", rect, z, H, "common")
    roof = {"type": "slab", "name": "cati_kati", "tag": "roof", "role": "roof", "level": "Çatı",
            "points": [[rect[0], rect[1]], [rect[2], rect[1]], [rect[2], rect[3]], [rect[0], rect[3]]],
            "z": z + fh, "thickness": SLAB_T}
    return walls + [room, roof], round(polygon_area([(rect[0], rect[1]), (rect[2], rect[1]), (rect[2], rect[3]),
                                                      (rect[0], rect[3])]), 2)


def apply(elements, report, parcel, zoning, program):
    """Avan programını uygular: (elements, report). `program["avan"]` yoksa girdiyi aynen döndürür."""
    cfg = program.get("avan")
    if not cfg:
        return elements, report
    fh = zoning.get("floor_height", 3.0)
    floors = report["floors"]
    zs = next((e for e in elements if e["type"] == "slab" and e["name"] == "Zemin Kat/doseme"), None)
    core = _core(elements, "Zemin Kat")
    if zs is None or core is None or len(zs["points"]) != 4:
        report["warnings"].append("avan programı uygulanamadı: kat çekirdeği veya dikdörtgen oturum bulunamadı")
        return elements, report
    outline = _bbox(zs["points"])
    n_shops = int(cfg.get("shops", 6))
    n_units = report["units_per_floor"] * (floors - 1)
    els, ax, shop_areas = _ground_shops(elements, outline, core, fh, n_shops)
    fp = report["footprint_gross"]
    extra = {"floors_above": floors, "shops": n_shops, "shop_area": round(sum(shop_areas), 2),
             "dwelling_count": n_units}
    gross = report["gross_total"]
    if cfg.get("basement", True):
        b, areas = _basement(els, outline, ax, core, fh)
        els += b
        gross += fp
        if areas.get("Sığınak", 0) < SHELTER_REQUIRED:
            report["warnings"].append(f"sığınak {areas.get('Sığınak', 0):.0f} m² < gerekli ≈{SHELTER_REQUIRED:.0f} m²: "
                                      "bu kat şemasında bodrum bölmeleri yetmiyor, sığınak yeniden düzenlenmeli")
        extra["basement"] = {"area": round(fp, 2), "rooms": areas,
                             "shelter_required": SHELTER_REQUIRED, "parking_required": math.ceil(n_units / PARKING_PER_UNITS),
                             "parking_capacity": int(areas["Otopark"] // PARKING_AREA_PER_CAR),
                             "note": "Araç rampası / otopark yerleşimi çizilmedi; otopark odası alan olarak ayrıldı. "
                                     "Kapasite yaklaşık (≈25 m²/araç); yetmezse mekanik otopark veya otopark bedeli gerekir."}
    if cfg.get("attic_area"):
        a, a_area = _attic(els, ax, core, fh, floors, float(cfg["attic_area"]))
        els += a
        gross += a_area
        extra["attic_area"] = a_area
    report["gross_total"] = round(gross, 2)
    report["unit_count"] = n_units
    report["avan"] = extra
    report["warnings"].append(
        f"avan programı: zemin kat {n_shops} işyeri, kat başı {report['units_per_floor']} daire × {floors - 1} kat = "
        f"{n_units} konut; toplam inşaat alanı {report['gross_total']:.0f} m² (bodrum ve çatı katı dahil). "
        "TAKS/KAKS kontrolü yalnız tipik katlar içindir; bodrum/çatı katı hakkı ve dönüşüm emsali ayrıca doğrulanmalıdır.")
    return els, report
