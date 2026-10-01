"""Özet kartları ve ortak çizimler (PIL). Tasarım uzayı 1920×1080; çıktı boyutuna montajda ölçeklenir.

Kartlar yalnız `card_data` içindeki gerçek değerleri çizer; eksik alan satırı/kutusu hiç çizilmez.
"""
from __future__ import annotations

import math
import os
import textwrap
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from . import facts as F
from ..notice import AVAN_NOTE, AVAN_SHORT

SW, SH = 1920, 1080
CY = (62, 232, 255)
INK = (236, 246, 250)
MUTE = (160, 195, 210)
PANEL = (7, 16, 27)


def _font_dir():
    try:
        import matplotlib
        d = Path(matplotlib.__file__).parent / "mpl-data" / "fonts" / "ttf"
        if (d / "DejaVuSans.ttf").is_file():
            return d
    except Exception:  # noqa: BLE001
        pass
    for d in ("/usr/share/fonts/truetype/dejavu",):
        if os.path.isfile(d + "/DejaVuSans.ttf"):
            return Path(d)
    return None


_FD = _font_dir()
_fc = {}


def font(sz, bold=True):
    k = (sz, bold)
    if k not in _fc:
        if _FD is None:
            _fc[k] = ImageFont.load_default()
        else:
            _fc[k] = ImageFont.truetype(str(_FD / ("DejaVuSans-Bold.ttf" if bold else "DejaVuSans.ttf")), sz)
    return _fc[k]


def ease(x):
    u = min(1.0, max(0.0, x))
    return u * u * (3 - 2 * u)


_bg = None


def bg_grid():
    global _bg
    if _bg is None:
        y = np.linspace(0, 1, SH)[:, None]
        x = np.linspace(-1, 1, SW)[None, :]
        base = np.zeros((SH, SW, 3), np.float32)
        for c, (a, b) in enumerate(zip((5, 9, 16), (13, 26, 42))):
            base[..., c] = a + (b - a) * (1 - y) * np.ones_like(x)
        base *= (1 - 0.28 * (x ** 2 + (y - .5) ** 2 * 1.6))[..., None]
        im = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8))
        d = ImageDraw.Draw(im, "RGBA")
        for gx in range(0, SW, 80):
            d.line([(gx, 0), (gx, SH)], fill=CY + (14,), width=1)
        for gy in range(0, SH, 80):
            d.line([(0, gy), (SW, gy)], fill=CY + (14,), width=1)
        _bg = im
    return _bg.copy()


def tw(d, text, f):
    return d.textlength(text, font=f)


def fit_font(d, text, max_w, start, lo=34, bold=True):
    sz = start
    while sz > lo and tw(d, text, font(sz, bold)) > max_w:
        sz -= 4
    return font(sz, bold)


def wrap_lines(d, text, f, max_w):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if tw(d, t, f) <= max_w or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def with_alpha(color, a):
    return tuple(color[:3]) + (int(255 * max(0.0, min(1.0, a))),)


def logo_image(path, max_w, max_h):
    try:
        im = Image.open(path).convert("RGBA")
    except OSError:
        return None
    r = min(max_w / im.width, max_h / im.height)
    return im.resize((max(1, int(im.width * r)), max(1, int(im.height * r))), Image.LANCZOS)


# ------------------------------------------------------------------ veri
SUM_TILES = (
    ("gross_floor_area", "Brüt inşaat alanı", "m²", 0), ("net_room_area", "Net oda alanı", "m²", 0),
    ("wall_length", "Toplam duvar uzunluğu", "m", 0), ("window_count", "Pencere", "adet", 0),
    ("door_count", "Kapı", "adet", 0), ("roof_area", "Çatı alanı", "m²", 0),
    ("pool_area", "Havuz", "m²", 0), ("paving_area", "Peyzaj / kaplama", "m²", 0),
)


def build_card_data(f):
    """Facts → JSON'a yazılabilir kart verisi. Sıfır/eksik değerler dışarıda kalır."""
    from .plan import sheet_pick
    s = f.summary or {}
    tiles = []
    for key, lab, unit, nd in SUM_TILES:
        v = s.get(key)
        if isinstance(v, (int, float)) and v > 0:
            tiles.append({"label": lab, "value": float(v), "unit": unit, "nd": nd})
    tiles = tiles[:6]
    c = f.cost or {}
    groups = [(k, float(v)) for k, v in (c.get("groups") or {}).items() if v]
    cost = None
    if c.get("total"):
        cost = {"total": float(c["total"]), "per_m2": float(c.get("per_m2") or 0), "groups": groups,
                "subtotal": c.get("subtotal"), "overhead_pct": c.get("overhead_pct"), "profit_pct": c.get("profit_pct"),
                "vat_pct": c.get("vat_pct"), "vat": c.get("vat"), "total_before_vat": c.get("total_before_vat"),
                "note": str(c.get("note") or "").split(" — ")[0].strip()}
    cust = (f.info.get("customer") or {}).get("name")
    return {
        "name": f.name, "headline": F.headline(f), "site": F.site_line(f), "customer": cust,
        "company_name": f.company.get("name") or "", "logo": str(f.logo) if f.logo else None,
        "contact": F.contact_lines(f), "tiles": tiles, "cost": cost, "docs": list(f.docs),
        "offer_terms": F.offer_terms_given(f), "items": len((f.cost or {}).get("rows") or []),
        "sheets": [(str(p), l) for p, l in sheet_pick(f)],
    }


# ------------------------------------------------------------------ kart çizimi
class Cards:
    def __init__(self, data):
        self.d = data
        self._logo = {}

    def logo(self, w, h):
        k = (w, h)
        if k not in self._logo:
            self._logo[k] = logo_image(self.d["logo"], w, h) if self.d.get("logo") else None
        return self._logo[k]

    def base(self):
        return bg_grid().convert("RGBA")

    def brand(self, im, a=1.0):
        """Sol üst: firma adı / sağ üst: logo — yalnız varsa."""
        d = ImageDraw.Draw(im)
        if self.d.get("company_name"):
            d.text((90, 64), self.d["company_name"].upper(), font=font(30), fill=with_alpha(MUTE, a))
        lg = self.logo(300, 90)
        if lg is not None:
            ov = lg.copy()
            ov.putalpha(ov.getchannel("A").point(lambda v: int(v * a)))
            im.alpha_composite(ov, (SW - 90 - ov.width, 52))

    def title(self, t, dur):
        im = self.base()
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        a = ease(t / 0.8)
        dy = int(26 * (1 - a))
        name = self.d["name"]
        f = fit_font(d, name, SW - 280, 150)
        lines = wrap_lines(d, name, f, SW - 280)[:2]
        lh = f.size + 18
        y = 400 - (len(lines) - 1) * lh // 2 + dy
        for i, ln in enumerate(lines):
            d.text(((SW - tw(d, ln, f)) / 2, y + i * lh), ln, font=f, fill=with_alpha((245, 250, 255), a))
        y2 = y + len(lines) * lh + 20
        d.rounded_rectangle([SW / 2 - 70, y2, SW / 2 + 70, y2 + 6], radius=3, fill=with_alpha(CY, ease((t - 0.3) / 0.6)))
        rows = [(self.d.get("headline"), 48, INK), (self.d.get("site"), 34, MUTE)]
        if self.d.get("customer"):
            rows.append((f"{self.d['customer']} için hazırlanmıştır", 34, MUTE))
        yy = y2 + 44
        for k, (txt, sz, col) in enumerate(rows):
            if not txt:
                continue
            b = ease((t - 0.6 - 0.2 * k) / 0.7)
            ff = fit_font(d, txt, SW - 280, sz, 26, bold=False)
            d.text(((SW - tw(d, txt, ff)) / 2, yy + int(12 * (1 - b))), txt, font=ff, fill=with_alpha(col, b))
            yy += sz + 22
        im = Image.alpha_composite(im, ov)
        self.brand(im, ease(t / 0.8))
        return im.convert("RGB")

    def sheets(self, t, dur):
        im = self.base()
        sh = [(Path(p), l) for p, l in self.d.get("sheets", []) if Path(p).is_file()]
        n = len(sh)
        if not n:
            return im.convert("RGB")
        H = 520 if n >= 3 else 600
        cards = []
        for p, lab in sh:
            try:
                pic = Image.open(p).convert("RGB")
            except OSError:
                continue
            pic = pic.resize((max(1, int(pic.width * H / pic.height)), H), Image.LANCZOS)
            card = Image.new("RGBA", (pic.width + 40, pic.height + 40), (0, 0, 0, 0))
            shd = Image.new("RGBA", card.size, (0, 0, 0, 0))
            ImageDraw.Draw(shd).rectangle([22, 28, pic.width + 26, pic.height + 32], fill=(0, 0, 0, 170))
            shd = shd.filter(ImageFilter.GaussianBlur(14))
            card = Image.alpha_composite(card, shd)
            card.paste(pic, (20, 20))
            cards.append((card, lab))
        gap = 36
        tot = sum(c.width for c, _ in cards) + gap * (len(cards) - 1)
        if tot > SW - 140:                    # sığmıyorsa küçült
            k = (SW - 140) / tot
            cards = [(c.resize((int(c.width * k), int(c.height * k)), Image.LANCZOS), l) for c, l in cards]
            tot = sum(c.width for c, _ in cards) + gap * (len(cards) - 1)
        x = (SW - tot) // 2
        d = ImageDraw.Draw(im)
        for k, (card, lab) in enumerate(cards):
            u = ease((t - 0.15 - 0.4 * k) / 0.55)
            if u > 0:
                y = (SH - card.height) // 2 - 70 + int(60 * (1 - u))
                c = card.copy()
                c.putalpha(c.getchannel("A").point(lambda v: int(v * u)))
                im.alpha_composite(c, (x, y))
                f = font(30, False)
                w = tw(d, lab, f)
                d.text((x + (card.width - w) / 2, y + card.height + 6), lab, font=f, fill=with_alpha(INK, u))
            x += card.width + gap
        z = 1 + 0.04 * (t / max(dur, 0.1))
        return im.convert("RGB").resize((SW, SH), Image.LANCZOS, box=(SW * (1 - 1 / z) / 2, SH * (1 - 1 / z) / 2, SW * (1 + 1 / z) / 2, SH * (1 + 1 / z) / 2))

    def heading(self, im, text, a):
        d = ImageDraw.Draw(im)
        d.text((120, 96), text.upper(), font=font(46), fill=with_alpha(CY, a))
        d.rounded_rectangle([120, 160, 250, 166], radius=3, fill=with_alpha(CY, a))

    def metraj(self, t, dur):
        im = self.base()
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        self.heading(ov, "Metraj", ease(t / 0.5))
        tiles = self.d.get("tiles", [])
        if self.d.get("items"):
            d.text((120, 190), f"{self.d['items']} kalem · proje geometrisinden otomatik", font=font(30, False), fill=with_alpha(MUTE, ease(t / 0.6)))
        cols = 3 if len(tiles) > 4 or len(tiles) == 3 else 2
        rows = max(1, math.ceil(len(tiles) / cols))
        tw_, th_, gx, gy = 520, 250, 40, 40
        x0 = (SW - (cols * tw_ + (cols - 1) * gx)) // 2
        y0 = 290 + (2 - min(rows, 2)) * 60
        for i, tl in enumerate(tiles):
            r, c = divmod(i, cols)
            u = ease((t - 0.2 - 0.12 * i) / 0.5)
            if u <= 0:
                continue
            x, y = x0 + c * (tw_ + gx), y0 + r * (th_ + gy) + int(30 * (1 - u))
            d.rounded_rectangle([x, y, x + tw_, y + th_], radius=22, fill=with_alpha(PANEL, 0.86 * u), outline=with_alpha(CY, 0.55 * u), width=2)
            d.rounded_rectangle([x + 28, y + 30, x + 36, y + th_ - 30], radius=3, fill=with_alpha(CY, u))
            v = tl["value"] * ease((t - 0.3 - 0.12 * i) / 1.1)
            vs = F.fmt_num(v, tl["nd"])
            fv = font(84)
            d.text((x + 64, y + 40), vs, font=fv, fill=with_alpha(INK, u))
            d.text((x + 64 + tw(d, vs, fv) + 14, y + 86), tl["unit"], font=font(36, False), fill=with_alpha(CY, u))
            d.text((x + 64, y + 170), tl["label"], font=font(32, False), fill=with_alpha(MUTE, u))
        im = Image.alpha_composite(im, ov)
        self.brand(im, 0.7)
        return im.convert("RGB")

    def maliyet(self, t, dur):
        im = self.base()
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        c = self.d.get("cost") or {}
        self.heading(ov, "Maliyet", ease(t / 0.5))
        a = ease((t - 0.1) / 0.6)
        total = c["total"] * ease((t - 0.2) / 1.3)
        d.text((120, 250), "GENEL TOPLAM (KDV DAHİL)", font=font(28), fill=with_alpha(MUTE, a))
        ft = fit_font(d, F.fmt_tl(c["total"]), 720, 104, 56)
        d.text((120, 296), F.fmt_tl(total), font=ft, fill=with_alpha(INK, a))
        yy = 296 + ft.size + 40
        if c.get("per_m2"):
            d.text((120, yy), "m² BİRİM MALİYET", font=font(26), fill=with_alpha(MUTE, a))
            d.text((120, yy + 36), F.fmt_tl(c["per_m2"]), font=font(52), fill=with_alpha(CY, a))
            yy += 130
        pc = []
        for key, lab in (("overhead_pct", "Genel gider"), ("profit_pct", "Kâr"), ("vat_pct", "KDV")):
            if c.get(key) is not None:
                pc.append(f"{lab} %{F.fmt_num(c[key], 0)}")
        if pc:
            d.text((120, yy), "  ·  ".join(pc), font=font(30, False), fill=with_alpha(MUTE, a))
            yy += 56
        if c.get("note"):
            for i, ln in enumerate(wrap_lines(d, c["note"], font(24, False), 780)[:3]):
                d.text((120, SH - 150 + i * 32), ln, font=font(24, False), fill=with_alpha((130, 165, 180), a))
        groups = c.get("groups") or []
        if groups:
            gx0, gx1 = 1000, SW - 120
            mx = max(v for _, v in groups)
            d.text((gx0, 250), "KALEM GRUPLARI (KDV HARİÇ)", font=font(26), fill=with_alpha(MUTE, a))
            by = 310
            bh = min(84, int(560 / len(groups)))
            for i, (name, v) in enumerate(groups[:7]):
                u = ease((t - 0.35 - 0.1 * i) / 0.8)
                y = by + i * (bh + 18)
                d.text((gx0, y), name, font=font(28, False), fill=with_alpha(INK, u))
                bw = (gx1 - gx0) * (v / mx) * u
                d.rounded_rectangle([gx0, y + 40, gx0 + max(8, bw), y + 40 + bh - 40 + 14], radius=8, fill=with_alpha(CY, 0.85 * u))
                lab = F.fmt_tl(v)
                lf = font(26)
                tx = gx0 + max(8, bw) + 14
                if tx + tw(d, lab, lf) > SW - 40:
                    tx = gx0 + max(8, bw) - tw(d, lab, lf) - 12
                    d.text((tx, y + 42), lab, font=lf, fill=with_alpha((5, 12, 20), u))
                else:
                    d.text((tx, y + 42), lab, font=lf, fill=with_alpha(INK, u))
        im = Image.alpha_composite(im, ov)
        self.brand(im, 0.7)
        return im.convert("RGB")

    def teklif(self, t, dur):
        im = self.base()
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        self.heading(ov, "Teklif ve belgeler", ease(t / 0.5))
        docs = self.d.get("docs", [])
        n = len(docs)
        cw, chh, gap = 480, 420, 50
        x0 = (SW - (n * cw + (n - 1) * gap)) // 2
        for i, lab in enumerate(docs):
            u = ease((t - 0.2 - 0.25 * i) / 0.6)
            if u <= 0:
                continue
            x, y = x0 + i * (cw + gap), 260 + int(40 * (1 - u))
            d.rounded_rectangle([x, y, x + cw, y + chh], radius=22, fill=with_alpha(PANEL, 0.88 * u), outline=with_alpha(CY, 0.6 * u), width=2)
            px, py = x + cw // 2 - 70, y + 50
            d.polygon([(px, py), (px + 110, py), (px + 140, py + 30), (px + 140, py + 190), (px, py + 190)], outline=with_alpha(CY, u), fill=with_alpha((15, 30, 46), u))
            for k in range(5):
                d.line([(px + 20, py + 60 + k * 24), (px + 120, py + 60 + k * 24)], fill=with_alpha(MUTE, 0.7 * u), width=3)
            f = fit_font(d, lab, cw - 50, 36, 24)
            d.text((x + (cw - tw(d, lab, f)) / 2, y + 290), lab, font=f, fill=with_alpha(INK, u))
        c = self.d.get("cost") or {}
        yy = 260 + chh + 60
        a = ease((t - 0.9) / 0.6)
        parts = []
        if c.get("total"):
            parts.append(("Teklif bedeli (KDV dahil)", F.fmt_tl(c["total"])))
        parts += [(k, v) for k, v in self.d.get("offer_terms", [])]
        if parts:
            tot_w = sum(tw(d, k, font(24, False)) + 24 + tw(d, v, font(40)) + 60 for k, v in parts) - 60
            x = (SW - tot_w) / 2
            for k, v in parts:
                d.text((x, yy + 10), k, font=font(24, False), fill=with_alpha(MUTE, a))
                kw = tw(d, k, font(24, False)) + 24
                d.text((x + kw, yy), v, font=font(40), fill=with_alpha(CY, a))
                x += kw + tw(d, v, font(40)) + 60
        im = Image.alpha_composite(im, ov)
        self.brand(im, 0.7)
        return im.convert("RGB")

    def company(self, t, dur):
        im = self.base()
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        a = ease(t / 0.7)
        y = 250
        lg = self.logo(520, 190)
        if lg is not None:
            c = lg.copy()
            c.putalpha(c.getchannel("A").point(lambda v: int(v * a)))
            ov.alpha_composite(c, ((SW - c.width) // 2, y))
            y += c.height + 50
        name = self.d.get("company_name")
        if name:
            f = fit_font(d, name, SW - 300, 84, 40)
            d.text(((SW - tw(d, name, f)) / 2, y), name, font=f, fill=with_alpha(INK, a))
            y += f.size + 30
        d.rounded_rectangle([SW / 2 - 60, y, SW / 2 + 60, y + 5], radius=3, fill=with_alpha(CY, a))
        y += 40
        for i, (lab, val) in enumerate(self.d.get("contact", [])):
            b = ease((t - 0.4 - 0.18 * i) / 0.6)
            f1, f2 = font(26), font(36, False)
            line_w = tw(d, lab.upper(), f1) + 28 + tw(d, val, f2)
            x = (SW - line_w) / 2
            d.text((x, y + 8), lab.upper(), font=f1, fill=with_alpha(CY, b))
            d.text((x + tw(d, lab.upper(), f1) + 28, y), val, font=f2, fill=with_alpha(INK, b))
            y += 64
        return Image.alpha_composite(im, ov).convert("RGB")

    def end(self, t, dur):
        im = self.base()
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        a = ease(t / 0.7)
        name = self.d["name"]
        f = fit_font(d, name, SW - 300, 110, 48)
        d.text(((SW - tw(d, name, f)) / 2, 250), name, font=f, fill=with_alpha((245, 250, 255), a))
        if self.d.get("company_name"):
            cn = self.d["company_name"]
            d.text(((SW - tw(d, cn, font(40, False))) / 2, 250 + f.size + 30), cn, font=font(40, False), fill=with_alpha(MUTE, a))
        e = ease((t - 0.8) / 0.8)
        fb = font(34)
        d.text(((SW - tw(d, AVAN_SHORT, fb)) / 2, 560), AVAN_SHORT, font=fb, fill=with_alpha(CY, e))
        fn = font(28, False)
        for i, ln in enumerate(wrap_lines(d, AVAN_NOTE, fn, 1360)):
            d.text(((SW - tw(d, ln, fn)) / 2, 625 + i * 42), ln, font=fn, fill=with_alpha(INK, 0.9 * e))
        ft = font(24, False)
        d.text(((SW - tw(d, "ArchAI ile hazırlandı", ft)) / 2, SH - 90), "ArchAI ile hazırlandı", font=ft, fill=with_alpha((120, 155, 170), e))
        return Image.alpha_composite(im, ov).convert("RGB")

    def render(self, kind, t, dur):
        return getattr(self, kind)(t, dur)
