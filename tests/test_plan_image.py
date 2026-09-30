"""Resim plan tanıma: test planı (3 daireli kat, tests/data/plan_3daire.jpg) elle kurulmuş modelle
(archai/apartment.py) karşılaştırılır. Eşikler, bugünkü doğruluğun biraz altında regresyon bekçisidir.

Görsel repoda yok (üçüncü taraf çizim): onun testleri yoksa atlanır. Depo içi eşdeğer: scripts/make_test_plan.py
DXF'i ezdxf.addons.drawing + matplotlib (Agg) ile PNG'ye çizilir (sentetik plan), import_dxf çıktısıyla
plan_eval.align/compare karşılaştırılır — bu testler her ortamda çalışır."""

import math
from pathlib import Path

import pytest
from PIL import Image, ImageOps

from archai import plan_eval as pe
from archai import plan_image as pi

ROOT = Path(__file__).resolve().parents[1]
PLAN = str(ROOT / "tests" / "data" / "plan_3daire.jpg")
TRUE_S = 46.2   # arka plan ızgarası 23,1 px = 0,5 m
needs_plan = pytest.mark.skipif(not Path(PLAN).exists(), reason="test planı görseli yerelde yok")


def _metrics(path):
    els, rep = pi.recognize(path)
    ref = pe.apartment_reference(rep["px_per_m"], Image.open(path).height)
    return rep, pe.compare(els, ref, "Zemin", "Normal Kat")


@needs_plan
def test_recognize_plan_without_hints():
    rep, m = _metrics(PLAN)
    assert abs(rep["px_per_m"] - TRUE_S) / TRUE_S < 0.01, rep["scale_method"]   # ölçek ipucusuz bulunur
    assert m["wall_precision"] >= 0.95 and m["wall_recall"] >= 0.95, m
    assert m["doors_matched"] >= 14 and m["doors_found"] <= m["doors_ref"] + 3, m
    assert m["rooms_found"] >= 15, m


@needs_plan
def test_light_background_same_result(tmp_path):
    inv = tmp_path / "inv.png"
    ImageOps.invert(Image.open(PLAN).convert("RGB")).save(inv)   # beyaz zemin, siyah çizgi
    rep, m = _metrics(inv)
    assert abs(rep["px_per_m"] - TRUE_S) / TRUE_S < 0.01
    assert m["wall_precision"] >= 0.95 and m["wall_recall"] >= 0.95, m


@needs_plan
def test_given_scale_is_used():
    els, rep = pi.recognize(PLAN, px_per_m=50.0)
    assert rep["px_per_m"] == 50.0 and rep["scale_method"] == "verilen ölçek"


@needs_plan
def test_image_project_end_to_end(tmp_path):
    from archai import project
    res, els = project.run_image(PLAN, {"name": "Resim Plan", "image": {}}, tmp_path)
    assert res["report"]["source"] == "image" and res["report"]["walls"] > 20
    assert (tmp_path / "tanima_onay.png").exists() and "tanima_onay_png" in res["files"]
    assert res["summary"]["gross_floor_area"] > 200 and res["cost"]["total"] > 0


def test_villa_sheet_roundtrip(tmp_path):
    """Farklı stil: ArchAI'nin kendi 1/100 paftası (taralı duvar, ölçü zinciri, aks, antet, kapı yayı).
    Resimden okunan 1. kat, paftanın üretildiği modelle karşılaştırılır. Görsel repoya gerekmez."""
    from archai import project
    res, els = project.run_villa(tmp_path)
    png = tmp_path / "cizimler" / "03_normal_kat_plani.png"
    found, rep = pi.recognize(png)
    lv = next(e["level"] for e in els if e["type"] == "slab" and e.get("role") == "floor" and e["z"] > 1)
    al, k = pe.align(found, els, "Zemin", lv)
    assert abs(k - 1) < 0.05, k                                   # kapı genişliğinden ölçek ≈ doğru
    m = pe.compare(al, els, "Zemin", lv, tol=0.2)
    assert m["wall_precision"] >= 0.9 and m["wall_recall"] >= 0.9, m
    assert m["rooms_found"] >= m["rooms_ref"] - 1, m
    assert pe.windows(found, "Zemin") >= pe.windows(els, lv) - 1


# ---------------------------------------------------------------- çözünürlük değişmezliği (fikstür)
def _scaled(src, f, out):
    im = Image.open(src).convert("RGB")
    im.resize((round(im.width * f), round(im.height * f)), Image.LANCZOS).save(out)
    return out


@needs_plan
@pytest.mark.parametrize("f", [0.5, 0.75, 1.5, 2.0, 4.0])
def test_scale_invariance_fixture(tmp_path, f):
    """Aynı plan büyütülüp küçültülünce ölçek ve geometri aynı bulunur (önce: 2× → 30,5 px/m, doğrusu 92,4; 4× → 41).
    Düşük çözünürlük (0,5× = 23 px/m, 446 px, çizgiler < 1 px): gri tonda 2× büyütme + çizgi çekirdeği + çubuk boy
    oranı. Ölçülen (2026-09-30) isabet/kapsam, kapı, mahal: 0,5× 0,94/0,94, 15, 15; 0,75× 0,95/0,94, 15, 15
    (önce 0,965/0,873, 11, 9 ve 0,928/0,91, 15, 14); 1,5× 0,98/0,96; 2× 0,97/0,96; 4× 0,98/0,94."""
    p = _scaled(PLAN, f, tmp_path / f"p{f}.png")
    els, rep = pi.recognize(p)
    assert abs(rep["px_per_m"] / (TRUE_S * f) - 1) <= 0.05, rep["scale_method"]
    m = pe.compare(els, pe.apartment_reference(rep["px_per_m"] / f, Image.open(PLAN).height), "Zemin", "Normal Kat")
    assert m["wall_precision"] >= 0.93 and m["wall_recall"] >= 0.93, m
    assert abs(m["rooms_found"] - 17) <= 2 and m["doors_matched"] >= 0.7 * m["doors_ref"], m   # 1×: 17 mahal
    assert m["doors_found"] <= m["doors_ref"] + 3, m


def _degrid(src, out):
    """Fikstürün soluk arka plan ızgarasını sil (zemine yakın, kontrastı < 45 pikseller zemin rengine)."""
    import numpy as np
    a = np.asarray(Image.open(src).convert("RGB")).astype(np.int16)
    bg = np.median(a.reshape(-1, 3), 0)
    a[np.abs(a - bg).max(2) < 45] = bg
    Image.fromarray(a.astype(np.uint8)).save(out)
    return out


@needs_plan
@pytest.mark.parametrize("f", [1.0, 2.0])
def test_fixture_scale_without_grid(tmp_path, f):
    """Izgarasız kopya: ölçek kapı genişliği (≈ 0,95 m) + çift çizgi iç duvar kalınlığı (≈ 0,10 m) birleşiminden.
    Ölçülen: 1× +%4,4, 2× +%3,2 (yalnız kapıyla +%9,9 / +%6,5); 0,75× +%1,4; 1,5× +%1,7; 4× +%4,0;
    0,5× +%18 (iç duvar 2,3 px, çizgiler < 1 px: kalınlık ölçülemiyor — test dışı)."""
    p = _scaled(_degrid(PLAN, tmp_path / "ng.png"), f, tmp_path / f"ng{f}.png")
    els, rep = pi.recognize(p)
    assert rep["grid_px"] is None and "iç duvar" in rep["scale_method"], rep["scale_method"]
    assert abs(rep["px_per_m"] / (TRUE_S * f) - 1) <= 0.05, rep["scale_method"]
    m = pe.compare(els, pe.apartment_reference(rep["px_per_m"] / f, Image.open(PLAN).height), "Zemin", "Normal Kat")
    assert m["wall_precision"] >= 0.93 and m["wall_recall"] >= 0.9, m


# ---------------------------------------------------------------- sentetik plan (depo içi, her ortamda)
SYN_S = 100.0   # sentetik PNG ölçeği (px/m); 0,5× hâli 50 px/m


def _render_dxf(dxf, out, S=SYN_S, dark=True, grid=0.5, margin=1.5):
    """DXF (DUVAR/PENCERE/KAPI + mahal adları) → PNG, S px/m. Dış duvar (≥ 0,2 m) CAD alışkanlığıyla taralı (poşe);
    pencere/kapı boşluğu taranmaz. Arka planda grid (m) aralıklı soluk ızgara (CAD ekran görüntüsü gibi)."""
    import importlib.util

    import ezdxf
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from ezdxf.addons.drawing import Frontend, RenderContext
    from ezdxf.addons.drawing.config import BackgroundPolicy, ColorPolicy, Configuration, LineweightPolicy
    from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
    from matplotlib.patches import Polygon as MPoly

    spec = importlib.util.spec_from_file_location("make_test_plan", ROOT / "scripts" / "make_test_plan.py")
    mtp = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mtp)
    doc = ezdxf.readfile(str(dxf))
    x0, y0 = -mtp.EXT / 2 - margin, -mtp.EXT / 2 - margin
    x1, y1 = 12 + mtp.EXT / 2 + margin, 9 + mtp.EXT / 2 + margin
    W, H, dpi = (x1 - x0) * S, (y1 - y0) * S, 100
    bg, fg = ("#000000", "#ffffff") if dark else ("#ffffff", "#000000")
    with matplotlib.rc_context({"hatch.linewidth": 1.2, "hatch.color": fg}):
        fig = plt.figure(figsize=(W / dpi, H / dpi), dpi=dpi, facecolor=bg)
        ax = fig.add_axes([0, 0, 1, 1])
        ax.set_axis_off()
        ax.set_facecolor(bg)
        if grid:
            gc = "#262626" if dark else "#dcdcdc"
            for k in range(math.floor(x0 / grid), math.ceil(x1 / grid) + 1):
                ax.axvline(k * grid * 1000, color=gc, lw=0.6, zorder=0)
            for k in range(math.floor(y0 / grid), math.ceil(y1 / grid) + 1):
                ax.axhline(k * grid * 1000, color=gc, lw=0.6, zorder=0)
        for _, a, b, t, ops in mtp.WALLS:
            if t < 0.2:
                continue
            L = math.dist(a, b)
            ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
            cur, spans = -t / 2, []
            for o, w, _ in sorted(ops):
                spans.append((cur, o))
                cur = o + w
            spans.append((cur, L + t / 2))
            for s0, s1 in spans:
                pts = [((a[0] + ux * s - uy * n) * 1000, (a[1] + uy * s + ux * n) * 1000)
                       for s, n in ((s0, -t / 2), (s1, -t / 2), (s1, t / 2), (s0, t / 2))]
                ax.add_patch(MPoly(pts, closed=True, fill=False, hatch="////", lw=0, zorder=1))
        cfg = Configuration(background_policy=BackgroundPolicy.CUSTOM, custom_bg_color=bg,
                            color_policy=ColorPolicy.CUSTOM, custom_fg_color=fg,
                            lineweight_policy=LineweightPolicy.ABSOLUTE, min_lineweight=1.5)
        be = MatplotlibBackend(ax)
        ents = [e for e in doc.modelspace() if e.dxf.layer.upper() in ("DUVAR", "PENCERE", "KAPI") or e.dxftype() == "TEXT"]
        Frontend(RenderContext(doc), be, config=cfg).draw_entities(ents)
        be.finalize()
        fig.set_size_inches(W / dpi, H / dpi)          # finalize figür boyutunu değiştirir
        ax.set_position([0, 0, 1, 1])
        ax.set_xlim(x0 * 1000, x1 * 1000)
        ax.set_ylim(y0 * 1000, y1 * 1000)
        fig.savefig(out, dpi=dpi, facecolor=bg)
        plt.close(fig)
    return out


@pytest.fixture(scope="module")
def syn(test_dxf, tmp_path_factory):
    from archai.dxf_import import import_dxf
    d = tmp_path_factory.mktemp("syn")
    ref, _ = import_dxf(test_dxf, add_roof=False)
    return {"ref": ref, "dark": _render_dxf(test_dxf, d / "dark.png"),
            "light": _render_dxf(test_dxf, d / "light.png", dark=False),
            "nogrid": _render_dxf(test_dxf, d / "nogrid.png", dark=False, grid=None), "dir": d}


def _syn_metrics(path, ref, **kw):
    els, rep = pi.recognize(path, **kw)
    al, k = pe.align(els, ref, "Zemin", "Zemin")
    return rep, k, pe.compare(al, ref, "Zemin", "Zemin")


@pytest.mark.parametrize("style", ["dark", "light"])
def test_synthetic_plan_accuracy(syn, style):
    """Ölçülen (2026-09-30): duvar isabet/kapsam 1,00/1,00, kapı 5/5, mahal 5/5, ölçek hatası < %0,1."""
    rep, k, m = _syn_metrics(syn[style], syn["ref"])
    assert abs(rep["px_per_m"] / SYN_S - 1) <= 0.03 and abs(k - 1) <= 0.03, rep["scale_method"]
    assert m["wall_precision"] >= 0.95 and m["wall_recall"] >= 0.95, m
    assert m["doors_matched"] >= 0.7 * m["doors_ref"] and m["rooms_found"] == m["rooms_ref"], m
    _, _, mg = _syn_metrics(syn[style], syn["ref"], grid_m=0.5)      # ölçek ızgaradan
    assert mg == m


@pytest.mark.parametrize("f", [0.5, 1.0, 2.0])
def test_synthetic_plan_door_scale_without_grid(syn, f):
    """Izgarasız: ölçek kapı genişliği medyanı (≈ 0,95 m; bu planda kapılar 0,8–1,0 m → tek başına %7–10 hata) ile
    çift çizgi iç duvar kalınlığı (0,10 m) tahmininin birleşimi. Ölçülen: 0,5× −%2,5, 1× −%2,4, 2× −%2,0
    (yalnız kapıyla −%9,5 / −%9,4 / −%7,4)."""
    p = _scaled(syn["nogrid"], f, syn["dir"] / f"nogrid_{f}.png")
    rep, k, m = _syn_metrics(p, syn["ref"])
    assert abs(rep["px_per_m"] / (SYN_S * f) - 1) <= 0.04, rep["scale_method"]
    assert not any("tutarsız" in x for x in rep["warnings"]), rep["warnings"]
    assert m["wall_precision"] >= 0.95 and m["wall_recall"] >= 0.95, m


def test_scale_estimates_inconsistent_warns():
    """Kapı ve duvar kalınlığı tahminleri ±%20 dışında ayrışırsa kapı tahmini kalır ve uyarı döner."""
    img = Image.new("RGB", (800, 600))
    prev = type("P", (), {"k": 1.0, "img": img})()
    orig = pi._run, pi._door_widths
    try:
        def fake_run(w, S, mo, final=False):
            w.tstats = [(9.0, 3.0)] * 6          # 9 px iç duvar → 90 px/m, kapı tahmini 50 px/m
            return []
        pi._run, pi._door_widths = fake_run, lambda walls: [0.95] * 6
        S, n, note, bad = pi._estimate_scale(img, prev, 1.4)
    finally:
        pi._run, pi._door_widths = orig
    assert bad and "tutarsız" in bad and f"{S:.1f} px/m" in bad and "iç duvar" not in note


@pytest.mark.parametrize("f", [0.25, 0.375, 0.5, 0.75, 1.5, 2.0, 4.0])
def test_synthetic_scale_invariance(syn, f):
    """0,25× / 0,375× = 25 / 37,5 px/m: fikstürün 0,5× / 0,75× hâliyle aynı düşük çözünürlük (büyütülerek işlenir)."""
    p = _scaled(syn["dark"], f, syn["dir"] / f"dark_{f}.png")
    rep, k, m = _syn_metrics(p, syn["ref"])
    assert abs(rep["px_per_m"] / (SYN_S * f) - 1) <= 0.05 and abs(k - 1) <= 0.05, rep["scale_method"]
    assert m["wall_precision"] >= 0.93 and m["wall_recall"] >= 0.93, m
    assert abs(m["rooms_found"] - m["rooms_ref"]) <= 2 and m["doors_matched"] >= 0.7 * m["doors_ref"], m


def test_given_scale_consistent_across_resolution(syn, tmp_path):
    """Verilen px_per_m orijinal piksele göredir; iç normalizasyon metre sonucunu değiştirmez."""
    p2 = _scaled(syn["dark"], 2.0, tmp_path / "x2.png")
    a, ra = pi.recognize(syn["dark"], px_per_m=SYN_S)
    b, rb = pi.recognize(p2, px_per_m=2 * SYN_S)
    assert ra["px_per_m"] == SYN_S and rb["px_per_m"] == 2 * SYN_S
    assert abs(ra["outline_area"] - rb["outline_area"]) <= 0.02 * ra["outline_area"], (ra["outline_area"], rb["outline_area"])
    out = pi.overlay(p2, b, rb, tmp_path / "ov.png")           # overlay orijinal çözünürlükte
    assert Image.open(out).size == Image.open(p2).size


# ---------------------------------------------------------------- sağlamlık
def test_bad_and_huge_images_raise_value_error(tmp_path, monkeypatch):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    with pytest.raises(ValueError, match="resim okunamadı"):
        pi.recognize(bad)
    trunc = tmp_path / "trunc.jpg"
    Image.new("RGB", (400, 300), "white").save(trunc)
    trunc.write_bytes(trunc.read_bytes()[:200])
    with pytest.raises(ValueError, match="resim okunamadı"):
        pi.recognize(trunc)
    big = tmp_path / "big.png"
    Image.new("1", (8000, 8000)).save(big)                      # 64 MP > 60 MP: çözülmeden reddedilir
    with pytest.raises(ValueError, match="resim çok büyük"):
        pi.recognize(big)
    blank = tmp_path / "blank.png"
    Image.new("RGB", (600, 400), "white").save(blank)
    with pytest.raises(ValueError, match="duvar bulunamadı"):
        pi.recognize(blank)
