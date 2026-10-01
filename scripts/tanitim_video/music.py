"""Özgün, sentezlenmiş fon müziği: yumuşak pad akorları + hafif pentatonik arpej + atış (kick-less ambient)."""
import os
import numpy as np, wave, sys
SR = 44100; DUR = float(sys.argv[1]) if len(sys.argv) > 1 else 125.0
rng = np.random.default_rng(7)
t = np.arange(int(SR * DUR)) / SR
def hz(n): return 440.0 * 2 ** ((n - 69) / 12)
# akor dizisi (MIDI): Am9 – Fmaj7 – Cmaj7 – G6, her biri 8 sn
CH = [[57, 60, 64, 67, 71], [53, 57, 60, 64, 67], [48, 55, 59, 64, 67], [55, 59, 62, 64, 71]]
pad = np.zeros_like(t)
for k in range(int(DUR // 8) + 2):
    ch = CH[k % 4]; t0 = k * 8.0
    env = np.clip((t - t0) / 3.0, 0, 1) * np.clip((t0 + 11.0 - t) / 3.0, 0, 1)          # 3 sn atak, 3 sn sönüm (çakışarak geçiş)
    env = np.where((t >= t0) & (t < t0 + 11.0), env, 0.0)
    for j, n in enumerate(ch):
        f = hz(n) * (1 + 0.0015 * (j - 2))
        lfo = 0.6 + 0.4 * np.sin(2 * np.pi * (0.07 + 0.013 * j) * t + j)
        pad += env * lfo * (np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * 2 * f * t)) * (0.045 if n < 60 else 0.03)
# arpej: pentatonik, 8. notalar, hafif gecikmeli
SC = [69, 72, 76, 79, 81, 84, 88]
arp = np.zeros_like(t)
step = 0.5
for i in range(int(DUR / step)):
    t0 = i * step + 0.02 * (i % 2)
    if t0 < 6 or rng.random() < 0.18: continue
    n = SC[(i * 3 + (i // 8) * 2) % len(SC)] - (12 if (i // 16) % 3 == 2 else 0)
    idx = slice(int(t0 * SR), min(len(t), int((t0 + 1.6) * SR)))
    tt = t[idx] - t0
    arp[idx] += 0.035 * np.exp(-tt * 3.2) * np.sin(2 * np.pi * hz(n) * tt) * (1 - np.exp(-tt * 200))
# yankı: basit çok-tap gecikme
def echo(x, taps):
    y = x.copy()
    for d, g in taps:
        k = int(d * SR); y[k:] += g * x[:-k]
    return y
mix = pad + echo(arp, [(0.375, 0.45), (0.75, 0.3), (1.125, 0.18)])
mix = np.tanh(mix * 2.2) * 0.5
fade = np.clip(t / 2.0, 0, 1) * np.clip((DUR - t) / 4.0, 0, 1)
mix *= fade
L = mix; R = np.roll(mix, int(0.011 * SR))
st = (np.stack([L, R], 1) * 32767 * 0.9).astype(np.int16)
w = wave.open(sys.argv[2] if len(sys.argv) > 2 else "music.wav", "wb"); w.setnchannels(2); w.setsampwidth(2); w.setframerate(SR); w.writeframes(st.tobytes()); w.close()
print("müzik", DUR, "sn")
