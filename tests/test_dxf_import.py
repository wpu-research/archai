"""DXF içe aktarma sağlamlığı: birim sezgisi, INSERT/blok açma, bozuk dosya, büyük dosya, kovalı eşleştirme.

Test DXF'leri ezdxf ile burada üretilir (depoya dosya eklenmez)."""

import math
import random
import time

import ezdxf
import pytest

from archai import dxf_import as D
from archai.dxf_import import import_dxf


def _rect(space, W, D_, t, k, layer="DUVAR", poly=True, origin=(0, 0)):
    """W×D m kutu duvar: dış + iç yüz (t kalın), çizim birimi k (mm: 1000)."""
    ox, oy = origin
    for ring in ([(0, 0), (W, 0), (W, D_), (0, D_)], [(t, t), (W - t, t), (W - t, D_ - t), (t, D_ - t)]):
        pts = [((ox + x) * k, (oy + y) * k) for x, y in ring]
        if poly:
            space.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})
        else:
            for a, b in zip(pts, pts[1:] + pts[:1]):
                space.add_line(a, b, dxfattribs={"layer": layer})


def _doc(insunits=0):
    d = ezdxf.new("R2018")
    d.header["$INSUNITS"] = insunits
    return d


@pytest.mark.parametrize("k,name", [(1000, "mm"), (100, "cm"), (1, "m")])
def test_units_guess_lwpolyline(tmp_path, k, name):
    """Önce: $INSUNITS=0 + LWPOLYLINE mm plan → outline_area 80 003 600 m² (sezgi yalnız LINE'a bakıyordu)."""
    d = _doc(0)
    _rect(d.modelspace(), 10, 8, 0.2, k)
    p = tmp_path / f"u_{name}.dxf"
    d.saveas(p)
    els, rep = import_dxf(p)
    assert rep["outline_area"] == pytest.approx(80.0, abs=0.01)
    assert rep["units_scale"] == pytest.approx(1 / k)
    assert any(f"birim {name} varsayıldı" in w and "units=" in w for w in rep["warnings"]), rep["warnings"]
    assert all(e["thickness"] == pytest.approx(0.2) for e in els if e["type"] == "wall")


def test_units_explicit_and_unverifiable(tmp_path):
    d = _doc(0)
    _rect(d.modelspace(), 10, 8, 0.2, 1000)
    p = tmp_path / "mm.dxf"
    d.saveas(p)
    assert import_dxf(p, units=0.001)[1]["outline_area"] == pytest.approx(80.0, abs=0.01)
    d = _doc(6)                                 # başlık "metre" diyor ama çizim mm: 80 milyon m²
    _rect(d.modelspace(), 10, 8, 0.2, 1000)
    d.saveas(p)
    with pytest.raises(ValueError, match="birim doğrulanamadı; .*units="):
        import_dxf(p)
    assert import_dxf(p, units=0.001)[1]["outline_area"] == pytest.approx(80.0, abs=0.01)   # açık birim kazanır
    d = _doc(0)                                 # 0,5 birimlik kutu: hiçbir birimde makul bina değil
    _rect(d.modelspace(), 0.5, 0.4, 0.1, 1)
    d.saveas(p)
    with pytest.raises(ValueError, match="birim doğrulanamadı"):
        import_dxf(p)


def test_units_ambiguity_warning(tmp_path):
    """50–500 birim: m ya da cm olabilir; tek çizgi duvar (çift yok) → kapsam kuralı (m) + belirsizlik uyarısı."""
    d = _doc(0)
    msp = d.modelspace()
    for a, b in (((0, 0), (300, 0)), ((300, 0), (300, 200)), ((300, 200), (0, 200)), ((0, 200), (0, 0))):
        msp.add_line(a, b, dxfattribs={"layer": "DUVAR"})
    p = tmp_path / "amb.dxf"
    d.saveas(p)
    els, rep = import_dxf(p)
    assert rep["units_scale"] == 1.0 and any("belirsiz" in w and "cm" in w for w in rep["warnings"]), rep["warnings"]


def _block_doc(tmp_path):
    """Duvarlar iç içe blokta (katman 0 → INSERT katmanı), döndürülmüş + ölçekli INSERT; kapı bloğu ayrı katmanda."""
    d = _doc(4)
    inner = d.blocks.new("DUVAR_KUTU")
    _rect(inner, 10, 8, 0.2, 1000, layer="0", poly=False)
    outer = d.blocks.new("KAT")
    outer.add_blockref("DUVAR_KUTU", (0, 0))
    loop = d.blocks.new("DONGU")
    loop.add_blockref("DONGU", (0, 0))            # kendini içeren blok: döngü koruması
    msp = d.modelspace()
    msp.add_blockref("KAT", (5000, 5000), dxfattribs={"layer": "DUVAR", "rotation": 90, "xscale": 0.5, "yscale": 0.5})
    msp.add_blockref("DONGU", (0, 0), dxfattribs={"layer": "DUVAR"})
    p = tmp_path / "blok.dxf"
    d.saveas(p)
    return p


def test_insert_blocks_are_exploded(tmp_path):
    """Önce: bloktaki duvarlar okunmuyordu → 'DUVAR/WALL katmanında çizgi bulunamadı'."""
    els, rep = import_dxf(_block_doc(tmp_path))
    walls = [e for e in els if e["type"] == "wall"]
    assert rep["walls"] == 4 and rep["outline_area"] == pytest.approx(5 * 4, abs=0.01)    # 0,5 ölçek: 5×4 m
    assert all(e["thickness"] == pytest.approx(0.1) for e in walls)
    xs = [c[0] for e in walls for c in (e["start"], e["end"])]
    assert min(xs) == pytest.approx(5 - 4 + 0.05, abs=0.01)      # 90° döndürme: y boyu (4 m) −x yönüne
    assert any("blok" in w and "DONGU" in w for w in rep["warnings"]), rep["warnings"]


def test_block_depth_limit(tmp_path):
    d = _doc(4)
    _rect(d.blocks.new("B0"), 10, 8, 0.2, 1000, layer="0")
    for i in range(1, 8):
        d.blocks.new(f"B{i}").add_blockref(f"B{i - 1}", (0, 0))
    d.modelspace().add_blockref("B7", (0, 0), dxfattribs={"layer": "DUVAR"})
    d.modelspace().add_blockref("B3", (0, 0), dxfattribs={"layer": "DUVAR"})
    p = tmp_path / "derin.dxf"
    d.saveas(p)
    els, rep = import_dxf(p)
    assert rep["walls"] == 4 and any("derinlik" in w for w in rep["warnings"])   # B7 (8 kat) atlandı, B3 açıldı


@pytest.mark.parametrize("data", [b"bu bir dxf degil\n" * 50, bytes(random.Random(1).randrange(256) for _ in range(3000)),
                                  b"0\nSECTION\n2\nENTITIES\n0\nLINE\n8\nDUVAR\n10\nabc\n"])
def test_broken_dxf_is_value_error(tmp_path, data):
    p = tmp_path / "bozuk.dxf"
    p.write_bytes(data)
    with pytest.raises(ValueError, match="geçersiz DXF"):
        import_dxf(p)


def test_missing_file_is_value_error(tmp_path):
    with pytest.raises(ValueError, match="geçersiz DXF"):
        import_dxf(tmp_path / "yok.dxf")


# ---------------------------------------------------------------- kovalı eşleştirme = kaba tarama
def _pair_walls_bruteforce(wall_segs, t_min, t_max, default_t):
    """Önceki O(n²) sürüm (referans)."""
    info = []
    for s in wall_segs:
        if s.length < 0.05:
            continue
        ux, uy, ang = D._canon(s.dir)
        sa, na = D._proj(s.a, ux, uy)
        sb, nb = D._proj(s.b, ux, uy)
        info.append({"ang": ang, "ux": ux, "uy": uy, "n": (na + nb) / 2, "s0": min(sa, sb), "s1": max(sa, sb), "used": False})
    pieces = []
    order = sorted(range(len(info)), key=lambda i: -(info[i]["s1"] - info[i]["s0"]))
    for i in order:
        A = info[i]
        if A["used"]:
            continue
        best, best_d = None, None
        for j in order:
            B = info[j]
            if j == i or B["used"]:
                continue
            da = abs(A["ang"] - B["ang"])
            if min(da, math.pi - da) > math.radians(1.0):
                continue
            d = abs(A["n"] - B["n"])
            if not (t_min <= d <= t_max):
                continue
            ov = min(A["s1"], B["s1"]) - max(A["s0"], B["s0"])
            if ov < 0.5 * min(A["s1"] - A["s0"], B["s1"] - B["s0"]):
                continue
            if best is None or d < best_d:
                best, best_d = j, d
        if best is not None:
            B = info[best]
            A["used"] = B["used"] = True
            pieces.append(D.Piece(A["ux"], A["uy"], (A["n"] + B["n"]) / 2, max(A["s0"], B["s0"]), min(A["s1"], B["s1"]),
                                  round(best_d, 3)))
    return pieces, [x for x in info if not x["used"]]


def _snap_ends_bruteforce(pieces):
    for p in pieces:
        for end in ("s0", "s1"):
            s = getattr(p, end)
            pt = (s * p.ux - p.n * p.uy, s * p.uy + p.n * p.ux)
            best = None
            for q in pieces:
                if q is p or abs(p.ux * q.uy - p.uy * q.ux) < 0.2:
                    continue
                sq, nq = D._proj(pt, q.ux, q.uy)
                tpar = (q.n - nq) / (-p.ux * q.uy + p.uy * q.ux)
                if abs(tpar) > max(p.t, q.t) + 0.05:
                    continue
                cp = ((s + tpar) * p.ux - p.n * p.uy, (s + tpar) * p.uy + p.n * p.ux)
                cs, _ = D._proj(cp, q.ux, q.uy)
                if not (q.s0 - q.t - 0.05 <= cs <= q.s1 + q.t + 0.05):
                    continue
                if best is None or abs(tpar) < abs(best):
                    best = tpar
            if best is not None:
                setattr(p, end, s + best)
    return pieces


def _random_segs(n, seed):
    rnd = random.Random(seed)
    out = []
    for _ in range(n):
        x, y, L = rnd.uniform(0, 30), rnd.uniform(0, 30), rnd.uniform(0.3, 6)
        a = math.radians(rnd.choice([0, 90, 45, 179.6, 0.3, rnd.uniform(0, 180)]))
        t = rnd.choice([0.09, 0.1, 0.2, 0.25, 0.5, 0.55])
        ux, uy = math.cos(a), math.sin(a)
        out.append(D.Seg((x, y), (x + ux * L, y + uy * L)))
        if rnd.random() < 0.7:
            dd = rnd.uniform(-0.2, 0.2)
            out.append(D.Seg((x - uy * t + ux * dd, y + ux * t + uy * dd), (x - uy * t + ux * (L + dd), y + ux * t + uy * (L + dd))))
    return out


def _key(ps):
    return [(round(p.ux, 9), round(p.uy, 9), round(p.n, 9), round(p.s0, 9), round(p.s1, 9), p.t) for p in ps]


@pytest.mark.parametrize("seed", range(12))
def test_bucketed_pairing_matches_bruteforce(seed):
    segs = _random_segs(160, seed)
    a, sa = D._pair_walls(segs, 0.08, 0.5, 0.2)
    b, sb = _pair_walls_bruteforce(segs, 0.08, 0.5, 0.2)
    assert _key(a) == _key(b) and [x["s0"] for x in sa] == [x["s0"] for x in sb]
    ps = a + [D.Piece(x["ux"], x["uy"], x["n"], x["s0"], x["s1"], 0.2) for x in sa]
    cp = lambda: [D.Piece(p.ux, p.uy, p.n, p.s0, p.s1, p.t) for p in ps]
    assert _key(D._snap_ends(cp())) == _key(_snap_ends_bruteforce(cp()))


def _grid_dxf(path, n_rooms, c=4.0):
    """n_rooms × n_rooms oda ızgarası, çift çizgi duvar (m) → ≈ 4·n·(n+1) çizgi."""
    d = _doc(6)
    msp = d.modelspace()
    n, t = n_rooms, 0.2
    for i in range(n + 1):
        for j in range(n):
            for off in (-t / 2, t / 2):
                msp.add_line((j * c + t / 2, i * c + off), ((j + 1) * c - t / 2, i * c + off), dxfattribs={"layer": "DUVAR"})
                msp.add_line((i * c + off, j * c + t / 2), (i * c + off, (j + 1) * c - t / 2), dxfattribs={"layer": "DUVAR"})
    d.saveas(path)
    return 4 * n * (n + 1)


def test_many_lines_fast_and_capped(tmp_path, monkeypatch):
    """Önce: 4000 çizgi 2,8–5,6 s (eşleştirme + uç oturtma O(n²)); şimdi ≈ lineer. > 30 000 çizgi reddedilir."""
    p = tmp_path / "g.dxf"
    lines = _grid_dxf(p, 31)                 # 3968 çizgi
    t = time.perf_counter()
    els, rep = import_dxf(p)
    dt = time.perf_counter() - t
    assert rep["walls"] == 2 * 32 and rep["outline_area"] == pytest.approx((31 * 4 + 0.2) ** 2, rel=1e-3)
    assert dt < 2.5, (lines, dt)
    monkeypatch.setattr(D, "MAX_WALL_SEGMENTS", lines - 1)
    with pytest.raises(ValueError, match="çizgi var"):
        import_dxf(p)
