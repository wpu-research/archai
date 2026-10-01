"""Özgün, sentezlenmiş fon müziği (numpy): yumuşak pad akorları + hafif pentatonik arpej + yankı.

`synth(dur, seed)` stereo int16 döndürür; aynı tohum aynı müziği üretir (deterministik). Telif sorunu yoktur.
"""
from __future__ import annotations

import wave

import numpy as np

SR = 44100
PROGRESSIONS = (
    [[57, 60, 64, 67, 71], [53, 57, 60, 64, 67], [48, 55, 59, 64, 67], [55, 59, 62, 64, 71]],      # Am9 Fmaj7 Cmaj7 G6
    [[50, 57, 60, 64, 67], [46, 53, 57, 62, 65], [53, 57, 60, 64, 69], [48, 55, 59, 62, 67]],      # Dm9 Bbmaj7 F6 Cmaj7
    [[52, 59, 62, 66, 71], [48, 55, 59, 64, 67], [45, 52, 57, 60, 64], [47, 54, 59, 62, 66]],      # Em9 Cmaj7 Am7 Bm7
)
SCALES = ([69, 72, 76, 79, 81, 84, 88], [62, 65, 69, 72, 74, 77, 81], [64, 67, 71, 74, 76, 79, 83])


def hz(n):
    return 440.0 * 2 ** ((n - 69) / 12)


def synth(dur, seed=7):
    dur = float(dur)
    rng = np.random.default_rng(seed)
    t = np.arange(int(SR * dur)) / SR
    pick = seed % len(PROGRESSIONS)
    CH, SC = PROGRESSIONS[pick], SCALES[pick]
    pad = np.zeros_like(t)
    for k in range(int(dur // 8) + 2):
        ch = CH[k % 4]
        t0 = k * 8.0
        env = np.clip((t - t0) / 3.0, 0, 1) * np.clip((t0 + 11.0 - t) / 3.0, 0, 1)
        env = np.where((t >= t0) & (t < t0 + 11.0), env, 0.0)
        if not env.any():
            continue
        for j, n in enumerate(ch):
            f = hz(n) * (1 + 0.0015 * (j - 2))
            lfo = 0.6 + 0.4 * np.sin(2 * np.pi * (0.07 + 0.013 * j) * t + j)
            pad += env * lfo * (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t)) * (0.045 if n < 60 else 0.03)
    arp = np.zeros_like(t)
    step = 0.5
    for i in range(int(dur / step)):
        t0 = i * step + 0.02 * (i % 2)
        if t0 < 4 or rng.random() < 0.18:
            continue
        n = SC[(i * 3 + (i // 8) * 2) % len(SC)] - (12 if (i // 16) % 3 == 2 else 0)
        a, b = int(t0 * SR), min(len(t), int((t0 + 1.6) * SR))
        if b <= a:
            continue
        tt = t[a:b] - t0
        arp[a:b] += 0.035 * np.exp(-tt * 3.2) * np.sin(2 * np.pi * hz(n) * tt) * (1 - np.exp(-tt * 200))
    y = arp.copy()
    for dly, g in ((0.375, 0.45), (0.75, 0.3), (1.125, 0.18)):
        k = int(dly * SR)
        if k < len(arp):
            y[k:] += g * arp[:-k]
    mix = np.tanh((pad + y) * 2.2) * 0.5
    mix *= np.clip(t / 2.0, 0, 1) * np.clip((dur - t) / 3.0, 0, 1)
    L, R = mix, np.roll(mix, int(0.011 * SR))
    return (np.stack([L, R], 1) * 32767 * 0.9).astype(np.int16)


def write_wav(path, dur, seed=7):
    st = synth(dur, seed)
    with wave.open(str(path), "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(st.tobytes())
    return path
