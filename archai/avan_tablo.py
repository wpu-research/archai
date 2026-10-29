"""Avan alan cetvelinden (onaylı avan tablosu) alan-sadık model.

Tablodaki kat alanları (brüt, dış yüz), ortak alanlar, bağımsız bölüm sayıları, sığınak ve kotlar aynen kullanılır;
bina planı (oda dağılımı) ise ŞEMATİKTİR — tablo duvar/kapı/oda yerini vermez. Onaylı çizim gelirse DXF içe aktarma
(`import_dxf`) gerçek geometriyi okur.

Kurgu (hepsi dikdörtgen, ön kenar x ekseninde):
  - normal kat: parselin yapılaşma kutusuna oturan dikdörtgen (alanı tablodaki normal kat alanı),
  - zemin ve bodrum: normal katın içeri ofsetlenmiş hali (ofset, tablodaki alanı verecek şekilde çözülür); yani üst katlar
    zemine göre çıkma yapar,
  - çatı katı: çekirdeğin üstünde tek mekân (tablodaki alan).
Normal kat: ortada çekirdek (kat holü, merdiven, asansör), iki yanda ikişer daire (ön/arka); zemin: yanlarda dükkânlar;
bodrum: sığınak, teknik/su deposu ve bodrum işyerleri.
"""
import math

from shapely.geometry import Polygon

from . import parcel as P
from .generate import (EXT_T, Rect, _door, _ext_edges, _outline, _room_polys, _shared, _stair_elements,
                       _wall_segments, roof_parapet)
from .imar import imar_summary

SLAB_T = 0.2


def _r(v):
    """Bölme koordinatı: mm hassasiyeti (generate'in 5 cm ızgarası dış sınırları kaydırır, tablo alanını bozar)."""
    return round(v, 3)

STAIR_D = 5.2
ATTIC_SETBACK = 1.5
TABLO_11903 = {
    "tapu_alani": 242.34, "mip": False, "yapi_turu": "Konut", "yapi_sinifi": "3-C",
    "bodrum": {"alan": 228.94, "ortak": 179.15, "isyeri": 2, "siginak": 111.0, "yukseklik": 2.5},
    "zemin": {"alan": 206.39, "ortak": 51.04, "isyeri": 4},
    "normal": {"adet": 6, "alan": 298.02, "ortak": 43.50, "daire": 4},
    "cati_kati": {"alan": 74.47},
    "temel_ust_kotu": -2.5, "sacak_kotu": 19.0, "mahya_kotu": 21.2,
    "konut": {"adet": 24, "alan": 1527.12}, "isyeri": {"adet": 6, "alan": 205.14},
    "toplam_insaat": 2297.92, "toplam_ortak": 565.66, "otopark_sayisi_gerekli": 8, "otopark_projede": 0,
    "su_deposu_m3": 13, "asansor_gerekli": 2,
}


def _inset(L, D, area):
    """(L-2d)(D-2d) = area → ofset d (m)."""
    a, b, c = 4.0, -2.0 * (L + D), L * D - area
    disc = b * b - 4 * a * c
    if disc < 0 or area > L * D + 1e-9:
        raise ValueError("kat alanı üst kat alanından büyük olamaz")
    return (-b - math.sqrt(disc)) / (2 * a)


LIFTS = 2      # tablo: zemin üstü 20'den fazla konut → en az 2 asansör


def _core(x0, x1, D, lifts=LIFTS):
    """Çekirdek dikdörtgenleri: önde kat holü, arkada merdiven + asansör/şaft(lar). Dönen (rects, (cx0, cx1, sy))."""
    sd = min(STAIR_D, 0.7 * D)
    sw = min(2.6, (x1 - x0) * 0.6)
    rs = [Rect(x0, 0, x1, _r(D - sd), "Kat Holü", "core"), Rect(x0, _r(D - sd), _r(x0 + sw), D, "Merdiven", "core")]
    xa, w = _r(x0 + sw), (x1 - _r(x0 + sw)) / lifts
    for i in range(lifts):
        rs.append(Rect(_r(xa + i * w), _r(D - sd), x1 if i == lifts - 1 else _r(xa + (i + 1) * w), D,
                       "Asansör/Şaft" + (f" {i + 1}" if i else ""), "core"))
    return rs, (x0, x1, _r(D - sd))


def _unit(tag, x0, x1, y0, y1, core_right):
    """Bir daire: çekirdek tarafında hol (üst) + banyo (alt), ortada salon + açık mutfak, uçta yatak odası."""
    w = x1 - x0
    a = min(2.6, w * 0.2)
    bw = (w - a) * 0.6
    hd = (y1 - y0) * 0.55
    if core_right:      # çekirdek sağda
        ca0, ca1 = x1 - a, x1
        sb0, sb1 = ca0 - bw, ca0
        yb0, yb1 = x0, sb0
    else:
        ca0, ca1 = x0, x0 + a
        sb0, sb1 = ca1, ca1 + bw
        yb0, yb1 = sb1, x1
    ym = _r(y0 + hd)
    return [Rect(_r(ca0), y0, _r(ca1), ym, f"{tag}/Hol"), Rect(_r(ca0), ym, _r(ca1), y1, f"{tag}/Banyo"),
            Rect(_r(sb0), y0, _r(sb1), y1, f"{tag}/Salon + Açık Mutfak"),
            Rect(_r(yb0), y0, _r(yb1), y1, f"{tag}/Yatak Odası 1")]


def _normal_rects(W, D, core_w, ntag=1):
    cx0 = _r((W - core_w) / 2)
    crs, core = _core(cx0, _r(cx0 + core_w), D)
    ym = _r(D / 2)
    rects = list(crs)
    rects += _unit(f"Daire {ntag}", 0, cx0, 0, ym, True) + _unit(f"Daire {ntag + 1}", 0, cx0, ym, D, True)
    rects += _unit(f"Daire {ntag + 2}", core[1], W, 0, ym, False) + _unit(f"Daire {ntag + 3}", core[1], W, ym, D, False)
    return rects, core


def _zemin_rects(W, D, core_w):
    cx0 = _r((W - core_w) / 2)
    crs, core = _core(cx0, _r(cx0 + core_w), D)
    ym = _r(D / 2)
    rects = list(crs) + [Rect(0, 0, cx0, ym, "İşyeri 1"), Rect(0, ym, cx0, D, "İşyeri 2"),
                         Rect(core[1], 0, W, ym, "İşyeri 3"), Rect(core[1], ym, W, D, "İşyeri 4")]
    return rects, core


def _bodrum_rects(W, D, core_w, teknik, isyeri_alan):
    """Çekirdek sağ uçta; soldan: sığınak (kalan alan) | teknik/su deposu | bodrum işyerleri (çekirdeğe yakın blok)."""
    cx0 = _r(W - core_w)
    crs, core = _core(cx0, W, D)
    w_is = isyeri_alan / D
    w_te = teknik / D
    x_is0 = _r(cx0 - w_is)
    x_te0 = _r(x_is0 - w_te)
    ym = _r(D / 2)
    rects = list(crs) + [Rect(0, 0, x_te0, D, "Sığınak", "room"), Rect(x_te0, 0, x_is0, D, "Teknik / Su Deposu", "room"),
                         Rect(x_is0, 0, cx0, ym, "İşyeri 5"), Rect(x_is0, ym, cx0, D, "İşyeri 6")]
    return rects, core


def _openings(rects, ground, core, shops):
    """Kural tabanlı açıklıklar: (orient, coord, s0, s1, kind)."""
    ops = []
    byname = {r.name: r for r in rects}

    def win(edge, w):
        o, c, a, b = edge
        w = min(w, b - a - 0.8)
        if w >= 0.5:
            m = (a + b) / 2
            ops.append((o, c, _r(m - w / 2), _r(m + w / 2), "window"))

    def door(a, b, width=0.9):
        e = _shared(a, b) if a is not None and b is not None else None
        d = _door(e, width) if e else None
        if d:
            ops.append(d)

    tags = sorted({r.name.split("/")[0] for r in rects if r.name.startswith("Daire ")})
    holl = byname.get("Kat Holü")
    for t in tags:
        hol, ban, sal, yat = (byname[f"{t}/{n}"] for n in ("Hol", "Banyo", "Salon + Açık Mutfak", "Yatak Odası 1"))
        door(hol, holl, 1.0)
        door(hol, sal)
        door(hol, ban, 0.8)
        door(sal, yat)
        for r, ww in ((sal, 3.0), (yat, 1.6), (ban, 0.6)):
            ext = sorted(_ext_edges(r, rects), key=lambda e: -(e[3] - e[2]))
            for e in ext[:2 if r is sal else 1]:
                win(e, ww)
    for r in rects:
        if r.kind == "room" and "/" not in r.name:
            ext = sorted(_ext_edges(r, rects), key=lambda e: -(e[3] - e[2]))
            if r.name.startswith("İşyeri") and ext:
                e = ext[0]                                       # vitrin + kapı, en uzun dış kenarda
                o, c, a, b = e
                if b - a >= 2.6:
                    m = (a + b) / 2
                    ops.append((o, c, _r(a + 0.3), _r(a + 0.3 + min(1.6, b - a - 1.6)), "window"))
                    ops.append((o, c, _r(b - 1.3), _r(b - 0.3), "door"))
                else:
                    ops.append(_door(e, 1.0))
    if ground == "zemin" and core:
        ops.append(("h", 0, _r((core[0] + core[1]) / 2 - 0.9), _r((core[0] + core[1]) / 2 + 0.9), "door"))
    elif ground == "bodrum" and core:
        door(byname.get("Sığınak"), byname.get("Teknik / Su Deposu"), 1.0)
        door(byname.get("Teknik / Su Deposu"), byname.get("İşyeri 5"), 1.0)
    if holl and core:
        for r in rects:
            if r.kind == "core" and r.name.startswith("Asansör"):
                e = _shared(r, holl)
                d = _door(e, 0.9) if e else None
                if d:
                    ops.append(d)
    return [(o, round(c, 3), a, b, k) for o, c, a, b, k in ops]      # duvar anahtarı 3 hane yuvarlanır


def _level(lvl, rects, W, D, ox, oy, z, h, ground, shops, core, elements, stairs_fh=None):
    lines = _wall_segments(rects, W, D)
    ops = _openings(rects, ground, core, shops)
    P_ = lambda x, y: [round(ox + x, 3), round(oy + y, 3)]
    outline = [P_(x, y) for x, y in _outline(rects, W, D)]
    elements.append({"type": "slab", "name": f"{lvl}/doseme", "tag": "concrete", "role": "floor", "level": lvl,
                     "points": outline, "z": z, "thickness": SLAB_T})
    wi = 0
    for (orient, c), pieces in sorted(lines.items()):
        for s0, s1, t in pieces:
            wi += 1
            mine = sorted([(a, b, k) for o, cc, a, b, k in ops if o == orient and abs(cc - c) < 1e-6
                           and a >= s0 - 1e-6 and b <= s1 + 1e-6])
            start, end = ((s0, c), (s1, c)) if orient == "h" else ((c, s0), (c, s1))
            elements.append({
                "type": "wall", "name": f"{lvl}/D{wi:02d}", "tag": "wall", "level": lvl, "exterior": t == EXT_T,
                "start": P_(*start), "end": P_(*end), "thickness": t, "height": h - SLAB_T, "base_z": z,
                "openings": [{"offset": round(a - s0, 3), "width": round(b - a, 3), "kind": k,
                              **({"sill": 0.3 if str(k) == "window" and ground else 0.9,
                                  "height": 1.6 if (b - a) < 2 else 2.2 if ground else 1.4} if k == "window"
                                 else {"height": 2.1, "leaf": True})} for a, b, k in mine]})
    for name, (kind, pts) in _room_polys(rects, lines).items():
        poly = [P_(x, y) for x, y in pts]
        common = kind == "core" or name.startswith(("Sığınak", "Teknik"))
        elements.append({"type": "room", "name": f"{lvl}/{name}", "level": lvl, "points": poly, "z": z,
                         "height": h - SLAB_T, "role": "common" if common else "room"})
    if stairs_fh and core:
        for st in _stair_elements(lvl, ox, oy, z, stairs_fh, core):
            elements.append(st)
    return outline


def build(polygon, tablo, front=0.5, side=0.0, rear=0.5, front_edge=None):
    """Parsel çokgeni + avan tablosu → (elements, report). Tablo anahtarları: TABLO_11903'e bakın."""
    zon = {"front": front, "side": side, "rear": rear}
    nrm, zem, bod, cat = tablo["normal"], tablo["zemin"], tablo["bodrum"], tablo["cati_kati"]
    f = None
    last = "yapılaşma kutusu bulunamadı"
    for rk in ([0] if front_edge is not None else range(12)):    # ön kenar verilmediyse uzun kenarı x'e gelen ilk uygun aday
        try:
            g = P.fit(polygon, zon, front_edge, rank=rk)
        except ValueError as ex:
            last = str(ex)
            break
        bx0, by0, bx1, by1 = g["box"]
        Ln_, Dn_ = bx1 - bx0, nrm["alan"] / (bx1 - bx0)
        last = f"normal kat alanı ({nrm['alan']} m²) yapılaşma kutusuna ({Ln_:.1f} × {by1 - by0:.1f} m) sığmıyor"
        if Dn_ <= (by1 - by0) + 1e-6 and (front_edge is not None or Ln_ >= 1.5 * Dn_):
            f = g
            break
    if f is None:
        raise ValueError(last)
    x0, y0, x1, y1 = f["box"]
    Ln = x1 - x0
    Dn = nrm["alan"] / Ln
    Dn_off = (y1 - y0 - Dn) / 2
    X0, Y0 = x0, y0 + Dn_off
    dz, db = _inset(Ln, Dn, zem["alan"]), _inset(Ln, Dn, bod["alan"])
    nfl = int(nrm["adet"])
    fh = tablo["sacak_kotu"] / (nfl + 1)                 # zemin + normal katlar saçağa kadar
    hb = float(bod["yukseklik"])
    h_att = tablo["mahya_kotu"] - tablo["sacak_kotu"]
    a = EXT_T                                             # tablo alanları dış yüze göre; mahal aksları yarım duvar içeride
    els = [{"type": "slab", "name": "parsel", "tag": "terrain", "role": "site", "level": "Arsa",
            "points": [[round(x, 3), round(y, 3)] for x, y in f["pts"]], "z": -0.02, "thickness": 0.3}]
    cw_n = nrm["ortak"] / Dn
    outlines = {}

    def axes(W_out, D_out):
        return W_out - a, D_out - a

    def place(lvl, rects, Wo, Do, inset, z, h, ground, shops, core, stairs=True):
        ox, oy = X0 + inset + a / 2, Y0 + inset + a / 2
        Wa, Da = axes(Wo, Do)
        outlines[lvl] = _level(lvl, rects, Wa, Da, ox, oy, z, h, ground, shops, core, els, fh if stairs else None)

    # normal katlar
    Wn, Dn_a = axes(Ln, Dn)
    rn, cn = _normal_rects(Wn, Dn_a, cw_n)
    for k in range(1, nfl + 1):
        place(f"Kat {k}", rn, Ln, Dn, 0.0, k * fh, fh, None, False, cn)
    # zemin
    Wz, Dz = Ln - 2 * dz, Dn - 2 * dz
    rz, cz = _zemin_rects(*axes(Wz, Dz), zem["ortak"] / Dz)
    place("Zemin Kat", rz, Wz, Dz, dz, 0.0, fh, "zemin", True, cz)
    # bodrum
    Wb, Db = Ln - 2 * db, Dn - 2 * db
    isy = bod["alan"] - bod["ortak"]
    core_b = nrm["ortak"]
    teknik = bod["ortak"] - bod["siginak"] - core_b
    rb, cb = _bodrum_rects(*axes(Wb, Db), core_b / Db, teknik, isy)
    place("1. Bodrum", rb, Wb, Db, db, -hb, hb, "bodrum", True, cb)
    # çatı katı: çekirdeğin üstünde tek mekân
    Dc = max(Dn - 2 * ATTIC_SETBACK, min(Dn, 3.0))   # çatı dairesi son kat konturundan ≥ 1,5 m geride (27.07.2025 plan notu)
    Wc = min(cat["alan"] / Dc, Ln - 2 * ATTIC_SETBACK)
    Dc = cat["alan"] / Wc
    cx = X0 + Ln / 2 - Wc / 2
    rc = [Rect(0, 0, *axes(Wc, Dc), "Merdiven Çıkışı / Makine Dairesi", "core")]
    ox, oy = cx + a / 2, Y0 + (Dn - Dc) / 2 + a / 2
    outlines["Çatı Katı"] = _level("Çatı Katı", rc, Wc - a, Dc - a, ox, oy, nfl * fh + fh, h_att + SLAB_T, None, False, None, els)
    # çatı döşemeleri + korkuluk
    roof_pts = outlines["Kat 1"]
    els.append({"type": "slab", "name": "cati", "tag": "roof", "role": "roof", "level": "Çatı", "points": roof_pts,
                "z": (nfl + 1) * fh, "thickness": SLAB_T})
    els += roof_parapet(roof_pts, (nfl + 1) * fh)
    ap = outlines["Çatı Katı"]
    els.append({"type": "slab", "name": "cati_kati", "tag": "roof", "role": "roof", "level": "Çatı", "points": ap,
                "z": (nfl + 1) * fh + h_att, "thickness": SLAB_T})
    return els, _report(els, tablo, f, outlines, Dn, Ln, dz, db, fh, front, side, rear)


def _area(pts):
    return Polygon([tuple(p[:2]) for p in pts]).area


def _report(els, tablo, f, outlines, Dn, Ln, dz, db, fh, front, side, rear):
    A = f["area"]
    nrm, zem, bod, cat = tablo["normal"], tablo["zemin"], tablo["bodrum"], tablo["cati_kati"]
    nfl = int(nrm["adet"])
    outline_n = outlines["Kat 1"]
    areas = {lvl: round(_area(pts), 2) for lvl, pts in outlines.items()}
    gross = round(sum(areas.values()), 2)
    fp = areas["Zemin Kat"]
    sb = P._edge_distances([tuple(p) for p in outline_n], f["pts"], f["classes"])
    lim = {"front": front, "side_left": side, "side_right": side, "rear": rear}
    detail = {k: {"value": (v if v != float("inf") else 0.0), "limit": lim[k], "ok": v >= lim[k] - 1e-6}
              for k, v in sb.items()}
    checks = {"taks": {"value": round(fp / A, 3), "limit": None, "ok": True},
              "kaks": {"value": round(gross / A, 3), "limit": None, "ok": True},
              "floors": {"value": nfl + 1, "limit": nfl + 1, "ok": True},
              "setbacks": {k: d["value"] for k, d in detail.items()}, "setbacks_detail": detail,
              "setback_ok": all(d["ok"] for d in detail.values()),
              "note": "Alan değerleri onaylı avan tablosundan; plan şematiktir."}
    tab = {"bodrum": (bod["alan"], areas["1. Bodrum"]), "zemin": (zem["alan"], areas["Zemin Kat"]),
           "normal": (nrm["alan"], areas["Kat 1"]), "cati_kati": (cat["alan"], areas["Çatı Katı"])}
    zon = {"front": front, "side": side, "rear": rear, "max_floors": nfl + 1}
    ohm = nfl * nrm["daire"]
    warn = [
        f"alan-sadık model: kat alanları onaylı avan tablosundan (bodrum {bod['alan']}, zemin {zem['alan']}, normal "
        f"{nrm['alan']} × {nfl}, çatı katı {cat['alan']} m²; toplam {tablo['toplam_insaat']} m²); oda dağılımı şematiktir",
        f"tablodaki tapu alanı {tablo['tapu_alani']} m², DXF'teki parsel {A:.1f} m² — fark teyit edilmeli",
        f"üst katlar zemine göre {dz:.2f} m, bodruma göre {db:.2f} m çıkma yapar (tablodaki alanları vermek için)",
        f"otopark: gerekli {tablo['otopark_sayisi_gerekli']}, projede {tablo['otopark_projede']} (tabloda 0): otopark çözülmemiş",
        f"zemin üstü {ohm} konut: en az {tablo['asansor_gerekli']} asansör gerekli; modelde {LIFTS} asansör kuyusu var (kabin ve kapasite hesabı yapılmadı)",
        "inşaat alanı 2000 m² üstünde: N.S.E.B. (en az B sınıfı, ≥ %10 yenilenebilir enerji) gerekli",
    ]
    rep = {"parcel_area": round(A, 2), "buildable": (round(f["box"][2] - f["box"][0], 2), round(f["box"][3] - f["box"][1], 2)),
           "footprint": (round(Ln, 2), round(Dn, 2)), "origin": (0, 0), "floors": nfl + 1, "unit_type": "1+1",
           "layout": "avan_tablo", "units_per_floor": nrm["daire"], "modules": 1, "warnings": warn,
           "footprint_gross": fp, "gross_total": gross, "unit_count": ohm, "unit_net_area": {},
           "checks": checks, "imar_ozeti": imar_summary(zon, A, checks), "kaks_used_pct": None,
           "avan_tablo": {"tablo": tablo, "model_kat_alanlari": areas,
                          "karsilastirma": {k: {"tablo": a, "model": b} for k, (a, b) in tab.items()},
                          "ofset": {"zemin": round(dz, 3), "bodrum": round(db, 3)}, "kat_yuksekligi": round(fh, 4)},
           "parcel_geom": {"polygon": [[round(x, 3), round(y, 3)] for x, y in f["pts"]],
                           "buildable": [[round(x, 3), round(y, 3)] for x, y in f["buildable"]],
                           "front_edge": f["front_edge"], "rotation_deg": f["rotation_deg"]},
           "note": "Şematik ön tasarım — alanlar onaylı avan tablosundan, oda yerleşimi şematiktir; mimar kontrolü gerekir."}
    return rep
