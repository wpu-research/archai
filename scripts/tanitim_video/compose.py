"""Tanıtım videosu montajı: sahneleri 1920×1080 / 24 fps kare dizisine birleştirir (başlık, altyazı, imleç, geçişler)."""
import sys, os, json, math, glob, shutil
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter
W = os.environ.get("ARCHAI_PROMO_DIR") or os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "out", "promo"))
FPS, SW, SH = 24, 1920, 1080
FB = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"; FR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
_fc = {}
def font(sz, bold=True):
    k = (sz, bold)
    if k not in _fc: _fc[k] = ImageFont.truetype(FB if bold else FR, sz)
    return _fc[k]
ease = lambda x: (lambda u: u * u * (3 - 2 * u))(min(1.0, max(0.0, x)))
CY = (62, 232, 255)

# ------------------------------------------------------------------ ortak çizimler
_bg = None
def bg_grid():
    global _bg
    if _bg is None:
        y = np.linspace(0, 1, SH)[:, None]; x = np.linspace(-1, 1, SW)[None, :]
        base = np.zeros((SH, SW, 3), np.float32)
        for c, (a, b) in enumerate(zip((5, 9, 16), (13, 26, 42))): base[..., c] = a + (b - a) * (1 - y) * np.ones_like(x)
        base *= (1 - 0.28 * (x ** 2 + (y - .5) ** 2 * 1.6))[..., None]
        im = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8)); d = ImageDraw.Draw(im, "RGBA")
        for gx in range(0, SW, 80): d.line([(gx, 0), (gx, SH)], fill=(62, 232, 255, 14), width=1)
        for gy in range(0, SH, 80): d.line([(0, gy), (SW, gy)], fill=(62, 232, 255, 14), width=1)
        _bg = im
    return _bg.copy()

def caption(img, text, sub=None, a=1.0, slide=0.0):
    """Sol alt: yarı saydam çubuk + camgöbeği şerit. a: opaklık, slide: yukarıdan kayma [0..1]."""
    if a <= 0.01: return img
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
    f1, f2 = font(46), font(26, False)
    w1 = d.textlength(text, font=f1); w2 = d.textlength(sub, font=f2) if sub else 0
    pad, bw = 34, max(w1, w2)
    x0, y1 = 70, SH - 70 + int(24 * (1 - slide)); h = 46 + 24 + (34 if sub else 0) + pad
    y0 = y1 - h
    d.rounded_rectangle([x0, y0, x0 + bw + pad * 2 + 10, y1], radius=18, fill=(5, 9, 16, int(205 * a)))
    d.rounded_rectangle([x0, y0 + 14, x0 + 7, y1 - 14], radius=3, fill=CY + (int(255 * a),))
    d.text((x0 + pad + 8, y0 + 18), text, font=f1, fill=(255, 255, 255, int(255 * a)))
    if sub: d.text((x0 + pad + 8, y0 + 18 + 62), sub, font=f2, fill=(160, 205, 220, int(240 * a)))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")

def cap_alpha(t, t0, t1, fin=0.35, fout=0.3):
    if t < t0 or t > t1: return 0.0, 0.0
    return min(1.0, ease((t - t0) / fin), ease((t1 - t) / fout)), ease((t - t0) / fin)

def load(path, size=(SW, SH)):
    im = Image.open(path).convert("RGB")
    return im if im.size == size else im.resize(size, Image.LANCZOS)

def ken_burns(path_or_img, u, z0=1.0, z1=1.08, pan=(0.0, 0.0)):
    im = path_or_img if isinstance(path_or_img, Image.Image) else Image.open(path_or_img).convert("RGB")
    iw, ih = im.size; z = z0 + (z1 - z0) * u
    cw, ch = iw / z, ih / z
    cx = iw / 2 + pan[0] * (iw - cw) / 2 * (u * 2 - 1); cy = ih / 2 + pan[1] * (ih - ch) / 2 * (u * 2 - 1)
    box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
    if iw / ih != SW / SH:                                   # 16:9 dışı görüntüyü kırp
        r = SW / SH; ccw = ch * r; box = (cx - ccw / 2, box[1], cx + ccw / 2, box[3])
    return im.resize((SW, SH), Image.LANCZOS, box=box)

# ------------------------------------------------------------------ sahne sınıfları
class Scene:
    caps = []                                   # [(t0, t1, text, sub)] yerel saniye
    def __init__(s, n): s.n = n
    def raw(s, i): raise NotImplementedError
    def frame(s, i):
        im = s.raw(min(max(i, 0), s.n - 1)); t = i / FPS
        for c in s.caps:
            a, sl = cap_alpha(t, c[0], c[1])
            if a > 0: im = caption(im, c[2], c[3] if len(c) > 3 else None, a, sl)
        return im

class Seq(Scene):
    def __init__(s, d, n=None, hold=0, caps=()):
        s.files = sorted(glob.glob(f"{W}/frames/{d}/*.jpg")); s.hold = hold; s.caps = list(caps)
        super().__init__((n or len(s.files)) + hold)
    def raw(s, i): return load(s.files[min(i, len(s.files) - 1)])

class Stills(Scene):
    def __init__(s, d, per, caps=(), zoom=0.03):
        s.files = sorted(glob.glob(f"{W}/frames/{d}/*.jpg")); s.per = per; s.caps = list(caps); s.zoom = zoom
        super().__init__(per * len(s.files))
    def raw(s, i):
        k, j = divmod(i, s.per); return ken_burns(s.files[k], j / s.per, 1.0, 1.0 + s.zoom)

class Cycles(Scene):
    def __init__(s, items, per, caps=()):
        s.items, s.per, s.caps = items, per, list(caps); super().__init__(per * len(items))
    def raw(s, i):
        k, j = divmod(i, s.per); name, label, pan = s.items[k]
        im = ken_burns(f"{W}/cycles/{name}.jpg", j / s.per, 1.0, 1.1, pan)
        d = ImageDraw.Draw(im, "RGBA"); f = font(30)
        t = label.upper(); w = d.textlength(t, font=f); x = SW - w - 90
        d.rounded_rectangle([x - 22, 56, SW - 60, 56 + 54], radius=14, fill=(5, 9, 16, 190)); d.text((x, 62), t, font=f, fill=CY)
        return im
    def frame(s, i):                                       # her görüntüye kendi altyazısı
        im = s.raw(min(max(i, 0), s.n - 1)); k, j = divmod(min(i, s.n - 1), s.per)
        a, sl = cap_alpha(j / FPS, 0.1, s.per / FPS - 0.1)
        return caption(im, "Gerçek render", "Blender Cycles · RTX 4070 · yaklaşık 30–100 sn", a, sl)

class UI(Scene):
    def __init__(s, data, t0, t1, caps=None):
        s.d, s.t0, s.t1 = data, t0, t1; s.fr = data["frames"]; s.kn = data["knots"]; s.cl = data["clicks"]
        s.caps = []; s.ui_caps = data["caps"]; super().__init__(int((t1 - t0) * FPS))
        s.arrow = Image.new("RGBA", (40, 56), (0, 0, 0, 0)); d = ImageDraw.Draw(s.arrow)
        pts = [(2, 2), (2, 40), (11, 31), (18, 46), (25, 43), (18, 29), (30, 29)]
        d.polygon([(x + 2, y + 2) for x, y in pts], fill=(0, 0, 0, 90)); d.polygon(pts, fill=(255, 255, 255, 255), outline=(10, 14, 22, 255))
    def cursor(s, t):
        kn = s.kn
        if not kn or t < kn[0][0]: return None
        i = max(k for k in range(len(kn)) if kn[k][0] <= t)
        if i % 2 == 0 and i + 1 < len(kn) and kn[i + 1][0] > kn[i][0]:
            u = ease((t - kn[i][0]) / (kn[i + 1][0] - kn[i][0])); return (kn[i][1] + (kn[i + 1][1] - kn[i][1]) * u, kn[i][2] + (kn[i + 1][2] - kn[i][2]) * u)
        return (kn[i][1], kn[i][2])
    def raw(s, i):
        t = s.t0 + i / FPS
        k = max([j for j, f in enumerate(s.fr) if f["t"] <= t] or [0])
        im = load(s.fr[k]["img"]).convert("RGBA")
        for c in s.cl:
            u = (t - c) / 0.45
            if 0 <= u < 1:
                p = s.cursor(c) or (0, 0); ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov); r = 14 + 70 * u
                d.ellipse([p[0] * 1.2 - r, p[1] * 1.2 - r, p[0] * 1.2 + r, p[1] * 1.2 + r], outline=CY + (int(230 * (1 - u)),), width=5); im = Image.alpha_composite(im, ov)
        p = s.cursor(t)
        if p: im.alpha_composite(s.arrow, (int(p[0] * 1.2) - 4, int(p[1] * 1.2) - 4))
        return im.convert("RGB")
    def frame(s, i):
        im = s.raw(min(max(i, 0), s.n - 1)); t = s.t0 + i / FPS
        for c in s.ui_caps:
            a, sl = cap_alpha(t, c["t0"], c["t1"])
            if a > 0: im = caption(im, c["text"], None, a, sl)
        return im

class Docs(Scene):
    def __init__(s, n):
        super().__init__(n)
        specs = [("teklif-1.png", "Teklif mektubu", 690), ("teknik_sartname-1.png", "Teknik şartname", 690), ("metraj_maliyet-01.png", "Metraj · maliyet (Excel)", 470)]
        s.cards = []
        for f, lab, h in specs:
            im = Image.open(f"{W}/docs/{f}").convert("RGB"); im = im.resize((int(im.width * h / im.height), h), Image.LANCZOS)
            card = Image.new("RGBA", (im.width + 40, im.height + 40), (0, 0, 0, 0)); sh = Image.new("RGBA", card.size, (0, 0, 0, 0))
            ImageDraw.Draw(sh).rectangle([22, 28, im.width + 26, im.height + 32], fill=(0, 0, 0, 170)); sh = sh.filter(ImageFilter.GaussianBlur(14))
            card = Image.alpha_composite(card, sh); card.paste(im, (20, 20)); s.cards.append((card, lab))
        tot = sum(c.width for c, _ in s.cards) + 30 * 2; s.x0 = (SW - tot) // 2
        s.caps = [(0.3, n / FPS - 0.2, "Teklif, şartname ve metraj hazır", "Word (.docx) ve Excel (.xlsx) — firma bilgisi ve şartlar düzenlenebilir")]
    def raw(s, i):
        im = bg_grid().convert("RGBA"); t = i / FPS; x = s.x0
        for k, (card, lab) in enumerate(s.cards):
            u = ease((t - 0.15 - 0.4 * k) / 0.55)
            if u > 0:
                y = (SH - card.height) // 2 - 40 + int(60 * (1 - u)); c = card.copy(); c.putalpha(c.getchannel("A").point(lambda v: int(v * u)))
                im.alpha_composite(c, (x, y)); d = ImageDraw.Draw(im); f = font(28, False); w = d.textlength(lab, font=f)
                d.text((x + (card.width - w) / 2, y + card.height + 4), lab, font=f, fill=(190, 225, 235, int(255 * u)))
            x += card.width + 30
        z = 1 + 0.04 * (i / s.n); return im.convert("RGB").resize((SW, SH), Image.LANCZOS, box=(SW * (1 - 1 / z) / 2, SH * (1 - 1 / z) / 2, SW * (1 + 1 / z) / 2, SH * (1 + 1 / z) / 2))

class Recog(Scene):
    def __init__(s, n):
        super().__init__(n); s.a = Image.open(f"{W}/rec_in.png").convert("RGB"); s.b = Image.open(f"{W}/rec_out.png").convert("RGB")
        k = 1000 / s.a.height; s.a = s.a.resize((int(s.a.width * k), 1000)); s.b = s.b.resize(s.a.size)
        s.x, s.y = (SW - s.a.width) // 2, 40
        s.caps = [(0.2, n / FPS - 0.2, "Resimden plan tanıma", "DXF ve PNG/JPG: duvar, kapı, pencere ve mahal otomatik bulunur")]
    def raw(s, i):
        t = i / FPS; im = bg_grid(); u = ease((t - 0.8) / 2.4); cut = int(s.a.width * u)
        p = s.a.copy(); p.paste(s.b.crop((0, 0, cut, s.b.height)), (0, 0)); im.paste(p, (s.x, s.y))
        d = ImageDraw.Draw(im, "RGBA")
        if 0 < u < 1: d.rectangle([s.x + cut - 2, s.y, s.x + cut + 2, s.y + s.a.height], fill=CY + (255,))
        d.rectangle([s.x - 3, s.y - 3, s.x + s.a.width + 3, s.y + s.a.height + 3], outline=CY + (110,), width=2)
        a = ease((t - 3.2) / 0.6)
        if a > 0:
            leg = [("duvar", (255, 200, 0)), ("kapı", (255, 40, 40)), ("pencere", (30, 200, 255)), ("mahal", (70, 140, 255))]
            x = SW - 290; y = 120
            d.rounded_rectangle([x - 24, y - 20, x + 250, y + len(leg) * 52 + 12], radius=14, fill=(5, 9, 16, int(200 * a)))
            for k, (lab, col) in enumerate(leg):
                d.rectangle([x, y + k * 52 + 6, x + 26, y + k * 52 + 32], fill=col + (int(255 * a),)); d.text((x + 42, y + k * 52 + 2), lab, font=font(30, False), fill=(235, 245, 250, int(255 * a)))
        return im

class Title(Scene):
    def __init__(s, n): super().__init__(n)
    def raw(s, i):
        t = i / FPS; im = bg_grid().convert("RGBA"); ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        a = ease(t / 0.9); dy = int(26 * (1 - a)); f = font(230)
        w1 = d.textlength("Arch", font=f); w2 = d.textlength("AI", font=f); x = (SW - w1 - w2) / 2; y = 300 + dy
        d.text((x, y), "Arch", font=f, fill=(245, 250, 255, int(255 * a))); d.text((x + w1, y), "AI", font=f, fill=CY + (int(255 * a),))
        b = ease((t - 0.7) / 0.8); d.text((SW / 2 - d.textlength("Arsadan teklife, dakikalar içinde", font=font(64, False)) / 2, 600 + dy), "Arsadan teklife, dakikalar içinde", font=font(64, False), fill=(200, 225, 235, int(255 * b)))
        c = ease((t - 1.5) / 0.8); line = "Plan  ·  Çizim  ·  Metraj  ·  Teklif  ·  3D  ·  Gerçek render"
        d.text((SW / 2 - d.textlength(line, font=font(34)) / 2, 720), line, font=font(34), fill=CY + (int(230 * c),))
        return Image.alpha_composite(im, ov).convert("RGB")

class End(Scene):
    def __init__(s, n): super().__init__(n)
    def raw(s, i):
        t = i / FPS; im = bg_grid().convert("RGBA"); ov = Image.new("RGBA", im.size, (0, 0, 0, 0)); d = ImageDraw.Draw(ov)
        a = ease(t / 0.7); f = font(170); w1 = d.textlength("Arch", font=f); w2 = d.textlength("AI", font=f); x = (SW - w1 - w2) / 2
        d.text((x, 190), "Arch", font=f, fill=(245, 250, 255, int(255 * a))); d.text((x + w1, 190), "AI", font=f, fill=CY + (int(255 * a),))
        steps = ["Arsa", "Plan", "Metraj", "Teklif", "3D", "Gerçek render"]; fs = font(40); gap = 30
        widths = [d.textlength(sname, font=fs) + 56 for sname in steps]; tot = sum(widths) + gap * (len(steps) - 1) + 44 * (len(steps) - 1); x = (SW - tot) / 2
        for k, (sname, wd) in enumerate(zip(steps, widths)):
            u = ease((t - 0.6 - 0.28 * k) / 0.4)
            d.rounded_rectangle([x, 520, x + wd, 520 + 78], radius=39, fill=(9, 22, 36, int(235 * u)), outline=CY + (int(255 * u),), width=3)
            d.text((x + 28, 536), sname, font=fs, fill=(235, 248, 252, int(255 * u)))
            if k < len(steps) - 1: d.text((x + wd + 14, 535), "→", font=fs, fill=CY + (int(255 * u),))
            x += wd + gap + 44
        e = ease((t - 2.6) / 0.8)
        d.text((SW / 2 - d.textlength("Avan (ön tasarım) seviyesinde otomasyon", font=font(38)) / 2, 700), "Avan (ön tasarım) seviyesinde otomasyon", font=font(38), fill=(220, 235, 242, int(255 * e)))
        n1 = "Ruhsat / uygulama projesi değildir. Statik, tesisat ve ruhsat için yetkili mimar ve mühendis onayı gerekir."
        d.text((SW / 2 - d.textlength(n1, font=font(26, False)) / 2, 780), n1, font=font(26, False), fill=(150, 185, 200, int(255 * e)))
        return Image.alpha_composite(im, ov).convert("RGB")

# ------------------------------------------------------------------ zaman çizelgesi
def build():
    ui = json.load(open(f"{W}/ui_a.json")); m = ui["marks"]
    S = []   # (sahne, geçiş kare sayısı)
    S.append((Title(int(3.4 * FPS)), 0))
    S.append((UI(ui, 0.0, m["belge"]), 10))
    S.append((Docs(int(6.2 * FPS)), 10))
    S.append((Seq("intro", hold=18, caps=[(0.2, 3.1, "Plandan 3D modele", "Kat planı, kütle ve mobilyalı bina — otomatik")]), 10))
    S.append((Seq("orbit", caps=[(0.2, 3.7, "Binayı her açıdan incele")]), 6))
    S.append((Stills("modes", 15, caps=[(0.1, 2.4, "Tel kafes · X-ray · Katı · Gerçekçi")]), 6))
    S.append((Stills("floors", 16, caps=[(0.1, 2.6, "Kat kat kesit")]), 6))
    S.append((UI(ui, m["belge"], ui["duration"]), 10))
    S.append((Seq("walk", caps=[(0.4, 7.0, "İçinde gez: kapıyı aç, odaları dolaş", "birinci şahıs gezinti · F ile kapı"), (9.0, 16.5, "Süpürgelik, kapı kanatları, pencereler — hepsi modelde")]), 10))
    S.append((Seq("daynight", caps=[(0.2, 3.8, "Gün ışığı ve gece aydınlatması", "güneş saatini kaydır")]), 8))
    S.append((Cycles([("maket", "Maket", (0, 0)), ("dis", "Dış cephe", (0.6, 0)), ("salon", "Salon", (-0.5, 0)), ("mutfak", "Mutfak", (0.5, 0)), ("yatak", "Yatak odası", (-0.4, 0))], per=int(2.7 * FPS)), 10))
    S.append((Recog(int(6.6 * FPS)), 10))
    S.append((End(int(5.0 * FPS)), 12))
    return S

def timeline(S):
    starts, pos = [], 0
    for k, (sc, tr) in enumerate(S):
        pos = pos - tr if k else 0; starts.append(pos); pos += sc.n
    return starts, pos

def render(out, a=None, b=None):
    S = build(); starts, total = timeline(S); os.makedirs(out, exist_ok=True)
    print("toplam kare", total, "süre", round(total / FPS, 1), "sn", flush=True)
    a = 0 if a is None else a; b = total if b is None else min(b, total)
    for f in range(a, b):
        act = [(k, sc) for k, (sc, tr) in enumerate(S) if starts[k] <= f < starts[k] + sc.n]
        base = None
        for k, sc in act:
            im = sc.frame(f - starts[k]); tr = S[k][1]
            if base is None: base = im
            else:
                u = ease((f - starts[k] + 0.5) / max(1, tr)); base = Image.blend(base, im, u)
        base.save(f"{out}/{f:05d}.jpg", quality=95)
        if f % 150 == 0: print("kare", f, "/", total, flush=True)
    return total

if __name__ == "__main__":
    out = sys.argv[1]; a = int(sys.argv[2]) if len(sys.argv) > 2 else None; b = int(sys.argv[3]) if len(sys.argv) > 3 else None
    render(out, a, b)
