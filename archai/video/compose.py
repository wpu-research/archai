"""Montaj: çekilen kareler + kartlar + altyazılar → mp4 (ffmpeg'e ham kare akışı; ara dosya yok).

Tasarım uzayı 1920×1080'dir; çıktı 720p ise son adımda küçültülür. Kareler çok süreçle üretilir (sıra korunur).
"""
from __future__ import annotations

import concurrent.futures as cf
import glob
import multiprocessing as mp
import os
import re
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw

from . import cards
from .cards import SH, SW, CY, INK, MUTE, ease, font, tw, with_alpha
from .plan import FPS, Plan, plan_from_dict

SEQ = {"intro", "orbit", "daynight", "walk"}
STILLS = {"modes", "floors"}
CARDS = {"title", "sheets", "metraj", "maliyet", "teklif", "company", "end"}
CAP_MAX_W = 1420
_G = {}


def srt_time(t):
    ms = int(round(t * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def write_srt(plan: Plan, path):
    lines = []
    for i, (a, b, text, sub, _) in enumerate(plan.captions("main"), 1):
        lines += [str(i), f"{srt_time(a)} --> {srt_time(b)}", text + (f"\n{sub}" if sub else ""), ""]
    Path(path).write_text("\n".join(lines), encoding="utf-8")
    return path


def load_rgb(path):
    im = Image.open(path).convert("RGB")
    return im if im.size == (SW, SH) else im.resize((SW, SH), Image.LANCZOS)


def ken_burns(im, u, z0=1.0, z1=1.06, pan=(0.0, 0.0)):
    iw, ih = im.size
    z = z0 + (z1 - z0) * u
    cw, ch = iw / z, ih / z
    cx = iw / 2 + pan[0] * (iw - cw) / 2 * (u * 2 - 1)
    cy = ih / 2 + pan[1] * (ih - ch) / 2 * (u * 2 - 1)
    box = (cx - cw / 2, cy - ch / 2, cx + cw / 2, cy + ch / 2)
    if abs(iw / ih - SW / SH) > 0.01:                     # 16:9 dışı görüntüyü kırp
        r = SW / SH
        ccw = ch * r
        box = (cx - ccw / 2, box[1], cx + ccw / 2, box[3])
    return im.resize((SW, SH), Image.LANCZOS, box=box)


def caption_overlay(img, text, sub, a, slide):
    if a <= 0.01:
        return img
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    sz1 = 46
    f1 = font(sz1)
    while tw(d, text, f1) > CAP_MAX_W and sz1 > 28:
        sz1 -= 2
        f1 = font(sz1)
    sz2 = 26
    f2 = font(sz2, False)
    while sub and tw(d, sub, f2) > CAP_MAX_W and sz2 > 18:
        sz2 -= 1
        f2 = font(sz2, False)
    w1 = tw(d, text, f1)
    w2 = tw(d, sub, f2) if sub else 0
    pad, bw = 34, max(w1, w2)
    x0, y1 = 70, SH - 70 + int(24 * (1 - slide))
    h = sz1 + 24 + (34 if sub else 0) + pad
    y0 = y1 - h
    d.rounded_rectangle([x0, y0, x0 + bw + pad * 2 + 10, y1], radius=18, fill=(5, 9, 16, int(205 * a)))
    d.rounded_rectangle([x0, y0 + 14, x0 + 7, y1 - 14], radius=3, fill=CY + (int(255 * a),))
    d.text((x0 + pad + 8, y0 + 18), text, font=f1, fill=(255, 255, 255, int(255 * a)))
    if sub:
        d.text((x0 + pad + 8, y0 + 18 + sz1 + 16), sub, font=f2, fill=(160, 205, 220, int(240 * a)))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def tag_overlay(img, text, sub, a):
    if a <= 0.01:
        return img
    ov = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(ov)
    f1, f2 = font(38), font(26, False)
    t = text.upper()
    w = max(tw(d, t, f1), tw(d, sub or "", f2)) + 56
    x0, y0 = 70, 64
    d.rounded_rectangle([x0, y0, x0 + w, y0 + (112 if sub else 76)], radius=16, fill=(5, 9, 16, int(190 * a)))
    d.rounded_rectangle([x0, y0 + 12, x0 + 6, y0 + (100 if sub else 64)], radius=3, fill=CY + (int(255 * a),))
    d.text((x0 + 30, y0 + 14), t, font=f1, fill=(240, 250, 255, int(255 * a)))
    if sub:
        d.text((x0 + 30, y0 + 62), sub, font=f2, fill=CY + (int(235 * a),))
    return Image.alpha_composite(img.convert("RGBA"), ov).convert("RGB")


def cap_alpha(t, t0, t1, fin=0.3, fout=0.3):
    if t < t0 or t > t1:
        return 0.0, 0.0
    return min(ease((t - t0) / fin), ease((t1 - t) / fout)), ease((t - t0) / fin)


class Compositor:
    def __init__(self, plan: Plan, card_data, workdir, cap_info=None, subtitles=True):
        self.plan = plan
        self.cards = cards.Cards(card_data)
        self.work = Path(workdir)
        self.step = int((cap_info or {}).get("step") or 1)
        self.subtitles = subtitles
        self.files = {}
        for s in plan.scenes:
            if s.kind in SEQ or s.kind in STILLS:
                fs = sorted(glob.glob(str(self.work / "frames" / s.id / "*.jpg")))
                self.files[s.id] = {int(re.search(r"(\d+)\.jpg$", p).group(1)): p for p in fs}
        self.starts = [int(round(s.start * FPS)) for s in plan.scenes]
        self.n = plan.total_frames
        self.caps = plan.captions()
        self.logo = None
        lp = card_data.get("logo")
        if lp:
            self.logo = cards.logo_image(lp, 220, 70)
            if self.logo is not None:
                self.logo.putalpha(self.logo.getchannel("A").point(lambda v: int(v * 0.8)))
        self.cache = {}

    # ---- sahne kareleri
    def seq_frame(self, s, i):
        fl = self.files.get(s.id) or {}
        if not fl:
            return None
        idx = sorted(fl)
        i = min(max(i, 0), idx[-1])
        if self.step == 1 or i in fl:
            k = i if i in fl else max(j for j in idx if j <= i)
            return load_rgb(fl[k])
        lo = max([j for j in idx if j <= i] or [idx[0]])
        hi = min([j for j in idx if j > i] or [idx[-1]])
        a = load_rgb(fl[lo])
        if hi == lo:
            return a
        return Image.blend(a, load_rgb(fl[hi]), (i - lo) / (hi - lo))

    def still_frame(self, s, i):
        fl = self.files.get(s.id) or {}
        keys = sorted(fl)
        if not keys:
            return None
        per = s.frames / len(keys)
        k = min(int(i / per), len(keys) - 1)
        u = (i - k * per) / per
        im = ken_burns(load_rgb(fl[keys[k]]), u, 1.0, 1.06)
        if k > 0 and (i - k * per) < 5:                           # kısa çapraz geçiş
            prev = ken_burns(load_rgb(fl[keys[k - 1]]), 1.0, 1.0, 1.06)
            im = Image.blend(prev, im, ease((i - k * per + 0.5) / 5))
        return im

    def cycles_frame(self, s, i):
        p = self.work / "cycles" / (s.data["name"] + ".jpg")
        key = ("cy", s.id)
        if key not in self.cache:
            self.cache[key] = Image.open(p).convert("RGB")
        pan = {"dis": (0.5, 0), "ic1": (-0.4, 0), "ic2": (0.4, 0)}.get(s.data["name"], (0, 0))
        return ken_burns(self.cache[key], i / max(1, s.frames - 1), 1.0, 1.1, pan)

    def scene_frame(self, k, i):
        s = self.plan.scenes[k]
        i = min(max(i, 0), s.frames - 1)
        t = i / FPS
        if s.kind in CARDS:
            return self.cards.render(s.kind, t, s.dur)
        if s.kind == "cycles":
            im = self.cycles_frame(s, i)
        elif s.kind in SEQ:
            im = self.seq_frame(s, i)
        else:
            im = self.still_frame(s, i)
        if im is None:
            im = cards.bg_grid()
        if self.logo is not None:
            im = im.convert("RGBA")
            im.alpha_composite(self.logo, (SW - 60 - self.logo.width, SH - 56 - self.logo.height))
            im = im.convert("RGB")
        return im

    def frame(self, f):
        act = [k for k, s in enumerate(self.plan.scenes) if self.starts[k] <= f < self.starts[k] + s.frames]
        if not act:
            act = [len(self.plan.scenes) - 1]
        base = None
        for k in act:
            im = self.scene_frame(k, f - self.starts[k])
            if base is None:
                base = im
            else:
                tr = max(1, int(round(self.plan.scenes[k].trans * FPS)))
                base = Image.blend(base, im, ease((f - self.starts[k] + 0.5) / tr))
        t = f / FPS
        for (a0, a1, text, sub, track) in self.caps:
            if track == "main" and not self.subtitles:
                continue
            a, sl = cap_alpha(t, a0, a1)
            if a > 0:
                base = caption_overlay(base, text, sub, a, sl) if track == "main" else tag_overlay(base, text, sub, a)
        tail = self.plan.total - t
        if tail < 0.5:
            base = Image.blend(base, Image.new("RGB", base.size), 1 - max(0.0, tail / 0.5))
        return base

    def cover(self):
        """Kapak karesi: dış mekân görüntüsü + proje adı (yoksa başlık kartı)."""
        pick = next((k for k, s in enumerate(self.plan.scenes) if s.kind == "orbit" and self.files.get(s.id)), None)
        if pick is None:
            pick = next((k for k, s in enumerate(self.plan.scenes) if s.kind == "modes" and self.files.get(s.id)), None)
        if pick is None:
            return self.cards.render("title", 3.0, 3.0)
        s = self.plan.scenes[pick]
        im = self.scene_frame(pick, s.frames // 3).convert("RGBA")
        ov = Image.new("RGBA", im.size, (0, 0, 0, 0))
        d = ImageDraw.Draw(ov)
        for y in range(SH - 460, SH):
            d.line([(0, y), (SW, y)], fill=(4, 8, 14, int(215 * ((y - (SH - 460)) / 460) ** 1.4)))
        name = self.cards.d["name"]
        f = cards.fit_font(d, name, SW - 240, 112, 48)
        d.text((100, SH - 260), name, font=f, fill=(255, 255, 255, 255))
        hl = self.cards.d.get("headline")
        if hl:
            d.text((104, SH - 130), hl, font=font(42, False), fill=CY + (255,))
        if self.cards.d.get("company_name"):
            d.text((104, 70), self.cards.d["company_name"].upper(), font=font(32), fill=(235, 245, 250, 235))
        return Image.alpha_composite(im, ov).convert("RGB")


def _init(plan_d, card_data, workdir, cap_info, subtitles, size):
    _G["c"] = Compositor(plan_from_dict(plan_d), card_data, workdir, cap_info, subtitles)
    _G["size"] = tuple(size)


def _frame_bytes(f):
    im = _G["c"].frame(f)
    if im.size != _G["size"]:
        im = im.resize(_G["size"], Image.LANCZOS)
    return im.tobytes()


def _frame_chunk(idx):
    return [_frame_bytes(i) for i in idx]


def encode(plan: Plan, plan_d, card_data, workdir, out_mp4, cap_info=None, subtitles=True, audio=None,
           progress=None, workers=None, ffmpeg="ffmpeg", should_cancel=None):
    """Kareleri üretip ffmpeg'e akıtır. Dönen: (mp4 yolu, kare sayısı)."""
    w, h = plan.size
    n = plan.total_frames
    cmd = [ffmpeg, "-y", "-loglevel", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(FPS), "-i", "-"]
    if audio:
        cmd += ["-i", str(audio)]
    cmd += ["-c:v", "libx264", "-preset", "medium", "-crf", "20", "-pix_fmt", "yuv420p", "-movflags", "+faststart"]
    if audio:
        cmd += ["-c:a", "aac", "-b:a", "160k", "-shortest"]
    cmd += [str(out_mp4)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
    workers = workers or max(1, min(8, (os.cpu_count() or 2) - 1))
    ex = cf.ProcessPoolExecutor(workers, mp_context=mp.get_context("spawn"), initializer=_init,
                                initargs=(plan_d, card_data, str(workdir), cap_info, subtitles, (w, h)))
    try:
        chunk, window = 6, workers * 3
        spans = [list(range(a, min(n, a + chunk))) for a in range(0, n, chunk)]
        pending, nxt, done = [], 0, 0
        while done < len(spans):
            while nxt < len(spans) and len(pending) < window:
                pending.append(ex.submit(_frame_chunk, spans[nxt]))
                nxt += 1
            for b in pending.pop(0).result(timeout=300):      # ölü/asılı işçi → hata (sonsuz bekleme yok)
                proc.stdin.write(b)
            done += 1
            if progress:
                progress(min(1.0, done * chunk / n))
            if should_cancel and should_cancel():
                raise InterruptedError("iptal edildi")
        proc.stdin.close()
        err = proc.stderr.read().decode(errors="replace")
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg başarısız: " + err[-400:])
    except BaseException:
        try:
            proc.kill()
        except OSError:
            pass
        raise
    finally:
        ex.shutdown(wait=False, cancel_futures=True)
    return out_mp4, n
