"""Sentetik 2+1 daire planı (DXF, mm) + doğru cevap (ground truth) eleman listesi.

Mimari çizim alışkanlıklarıyla: duvarlar çift çizgi, açıklıklarda kesik; pencerelerde 3
paralel çizgi, kapılarda kanat çizgisi + yay; mahaller kapalı polyline + isim.

    uv run python scripts/make_test_plan.py  →  references/test_plan_2+1.dxf, test_plan_2+1.truth.json
    ARCHAI_REF_OUT=/tmp/x uv run python scripts/make_test_plan.py  →  aynı dosyalar /tmp/x altına
"""

import json
import math
import os
from pathlib import Path

import ezdxf

ROOT = Path(__file__).resolve().parents[1]
# çıktı dizini: varsayılan references/; testler ARCHAI_REF_OUT ile geçici dizine yazar (repo değişmez)
REF_OUT = Path(os.environ.get("ARCHAI_REF_OUT") or ROOT / "references")
EXT, INT = 0.25, 0.10

# aks çizgileri (m) ve açıklıklar: (offset, width, kind)
WALLS = [
    ("S", (0, 0), (12, 0), EXT, [(1.0, 2.5, "window"), (4.5, 1.5, "window"), (8.5, 1.0, "door"), (10.0, 1.2, "window")]),
    ("E", (12, 0), (12, 9), EXT, [(6.0, 1.5, "window")]),
    ("N", (12, 9), (0, 9), EXT, [(1.0, 2.0, "window"), (6.0, 0.7, "window"), (9.5, 1.5, "window")]),
    ("W", (0, 9), (0, 0), EXT, [(5.5, 1.5, "window")]),
    ("I1", (0, 5), (12, 5), INT, [(2.0, 0.9, "door"), (5.0, 0.8, "door"), (9.0, 0.9, "door")]),
    ("I2", (7, 0), (7, 5), INT, [(2.0, 0.9, "door")]),
    ("I3", (4.5, 5), (4.5, 9), INT, []),
    ("I4", (7, 5), (7, 9), INT, []),
]
# mahaller aks dikdörtgeni olarak (x0, y0, x1, y1); çizimde duvar yüzlerine göre içeri alınır
ROOMS = [("Salon", (0, 0, 7, 5)), ("Mutfak", (7, 0, 12, 5)), ("Yatak Odası 1", (0, 5, 4.5, 9)),
         ("Banyo", (4.5, 5, 7, 9)), ("Yatak Odası 2", (7, 5, 12, 9))]


def half_t_at(x, y, axis):
    """Mahal kenarındaki duvarın yarı kalınlığı (dış kenarlarda EXT, içeride INT)."""
    if axis == "x":
        return EXT / 2 if x in (0, 12) else INT / 2
    return EXT / 2 if y in (0, 9) else INT / 2


def room_poly(x0, y0, x1, y1):
    a, b = x0 + half_t_at(x0, 0, "x"), x1 - half_t_at(x1, 0, "x")
    c, d = y0 + half_t_at(0, y0, "y"), y1 - half_t_at(0, y1, "y")
    return [[a, c], [b, c], [b, d], [a, d]]


def main():
    doc = ezdxf.new("R2018")
    doc.header["$INSUNITS"] = 4  # mm
    for n in ("DUVAR", "PENCERE", "KAPI", "MAHAL"):
        doc.layers.add(n)
    msp = doc.modelspace()
    mm = lambda p: (p[0] * 1000, p[1] * 1000)

    for name, a, b, t, ops in WALLS:
        L = math.dist(a, b)
        ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
        nx, ny = -uy, ux
        at = lambda s, n: (a[0] + ux * s + nx * n, a[1] + uy * s + ny * n)
        # yüz çizgilerinin başlangıç/bitişi: dış duvarlarda dış yüz köşeye kadar, iç yüz iç köşeye
        if name in ("S", "E", "N", "W"):
            # (n, uzatma_bas, uzatma_son). Sol normal içeri bakar (saat yönünün tersi çevre): +n iç yüz → kısalır, -n dış yüz → uzar
            faces = [(+t / 2, -t / 2, -t / 2), (-t / 2, +t / 2, +t / 2)]
        else:
            s_end = {"I1": (EXT / 2, EXT / 2), "I2": (EXT / 2, INT / 2), "I3": (INT / 2, EXT / 2), "I4": (INT / 2, EXT / 2)}[name]
            faces = [(+t / 2, -s_end[0], -s_end[1]), (-t / 2, -s_end[0], -s_end[1])]
        cuts = [(o, o + w) for o, w, _ in ops]
        for n, e0, e1 in faces:
            s, parts = -e0, []
            for c0, c1 in cuts:
                parts.append((s, c0))
                s = c1
            parts.append((s, L + e1))
            for s0, s1 in parts:
                msp.add_line(mm(at(s0, n)), mm(at(s1, n)), dxfattribs={"layer": "DUVAR"})
        for o, w, kind in ops:
            if kind == "window":
                for n in (-t / 4, 0, t / 4):
                    msp.add_line(mm(at(o, n)), mm(at(o + w, n)), dxfattribs={"layer": "PENCERE"})
                for s in (o, o + w):
                    msp.add_line(mm(at(s, -t / 2)), mm(at(s, t / 2)), dxfattribs={"layer": "PENCERE"})
            else:
                hinge = at(o, t / 2)
                tip = at(o, t / 2 + w)
                msp.add_line(mm(hinge), mm(tip), dxfattribs={"layer": "KAPI"})
                ang0 = math.degrees(math.atan2(ny, nx))
                ang1 = math.degrees(math.atan2(uy, ux))
                lo, hi = sorted([ang0, ang1])
                if hi - lo > 180:
                    lo, hi = hi, lo + 360
                msp.add_arc(mm(hinge), w * 1000, lo, hi, dxfattribs={"layer": "KAPI"})

    for rname, (x0, y0, x1, y1) in ROOMS:
        poly = room_poly(x0, y0, x1, y1)
        msp.add_lwpolyline([mm(p) for p in poly], close=True, dxfattribs={"layer": "MAHAL"})
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        msp.add_text(rname, height=250, dxfattribs={"layer": "MAHAL"}).set_placement(mm((cx, cy)))

    REF_OUT.mkdir(parents=True, exist_ok=True)
    out = REF_OUT / "test_plan_2+1.dxf"
    doc.saveas(out)

    # doğru cevap: aks çizgileri + dış kontur + mahaller
    truth = [{"type": "slab", "name": "doseme", "role": "floor", "tag": "concrete",
              "points": [[-EXT / 2, -EXT / 2], [12 + EXT / 2, -EXT / 2], [12 + EXT / 2, 9 + EXT / 2], [-EXT / 2, 9 + EXT / 2]],
              "z": 0, "thickness": 0.2}]
    for name, a, b, t, ops in WALLS:
        truth.append({"type": "wall", "name": name, "start": list(a), "end": list(b), "thickness": t, "height": 2.8,
                      "openings": [{"offset": o, "width": w, "kind": k} for o, w, k in ops]})
    for rname, box in ROOMS:
        truth.append({"type": "room", "name": rname, "points": room_poly(*box), "height": 2.8})
    (REF_OUT / "test_plan_2+1.truth.json").write_text(json.dumps(truth, indent=1, ensure_ascii=False))
    print(out)


if __name__ == "__main__":
    main()
