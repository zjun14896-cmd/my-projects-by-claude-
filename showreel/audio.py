"""Synthesizes the showreel soundtrack (numpy only), synced to the scene cuts.
Usage: python3 audio.py  -> out/soundtrack.wav
"""
import os
import wave

import numpy as np

SR = 48000
DUR = 15.0
N = int(SR * DUR)
CUTS = [1.8, 3.7, 5.6, 7.7, 9.6, 11.5, 12.7]
BPM = 128
BEAT = 60 / BPM
rng = np.random.default_rng(5)
t = np.arange(N) / SR
L = np.zeros(N)
R = np.zeros(N)


def add(sig, start, pan=0.0, gain=1.0):
    i = int(start * SR)
    if i >= N:
        return
    sig = sig[: N - i] * gain
    L[i:i + len(sig)] += sig * np.sqrt(0.5 * (1 - pan))
    R[i:i + len(sig)] += sig * np.sqrt(0.5 * (1 + pan))


def lowpass(x, cutoff):
    """One-pole lowpass; cutoff may be an array (sweeps)."""
    cutoff = np.broadcast_to(cutoff, x.shape)
    a = 1 - np.exp(-2 * np.pi * cutoff / SR)
    y = np.empty_like(x)
    acc = 0.0
    for i in range(len(x)):
        acc += a[i] * (x[i] - acc)
        y[i] = acc
    return y


def env(n, attack, decay):
    k = np.arange(n) / SR
    return np.minimum(1, k / max(attack, 1e-4)) * np.exp(-k / decay)


def kick(dur=0.45, f0=150, f1=42, gain=1.0):
    n = int(dur * SR)
    k = np.arange(n) / SR
    freq = f1 + (f0 - f1) * np.exp(-k * 28)
    ph = 2 * np.pi * np.cumsum(freq) / SR
    return np.tanh(2.2 * np.sin(ph) * env(n, 0.001, dur / 3.5)) * gain


def noise(dur):
    return rng.uniform(-1, 1, int(dur * SR))


def hat(dur=0.06):
    n = noise(dur)
    n = n - lowpass(n, 7000)
    return n * env(len(n), 0.0005, 0.018)


def whoosh(dur=0.45):
    n = noise(dur)
    k = np.arange(len(n)) / len(n)
    f = 300 + 7000 * k ** 2
    s = lowpass(n, f) * (k ** 2.2)
    return s / (np.abs(s).max() + 1e-9)


def impact():
    s = kick(1.1, 120, 32, 1.0)
    n = noise(0.6)
    n = lowpass(n, 2500) * env(len(n), 0.001, 0.08)
    s[: len(n)] += n * 0.8
    return s


def tone(freq, dur, kind='saw', detune=0.0):
    n = int(dur * SR)
    k = np.arange(n) / SR
    out = np.zeros(n)
    for d in (-detune, 0, detune):
        ph = (freq * (1 + d) * k) % 1
        out += (2 * ph - 1) if kind == 'saw' else np.sin(2 * np.pi * ph)
    return out / 3


def midi(m):
    return 440 * 2 ** ((m - 69) / 12)


# ── intro: riser into the dot explosion, then boom ──
riser = whoosh(0.34)
add(riser, 0.0, gain=0.35)
add(tone(midi(45), 0.34, 'sine') * np.linspace(0, 1, int(0.34 * SR)) ** 2, 0.0, gain=0.3)
add(impact(), 0.34, gain=0.9)

# ── pad: Am – F – C – G (one chord per ~1.85s) ──
chords = [[57, 60, 64, 69], [53, 57, 60, 65], [48, 55, 60, 64], [55, 59, 62, 67],
          [57, 60, 64, 69], [53, 57, 60, 65]]
pad = np.zeros(N)
for ci, ch in enumerate(chords):
    st, dur = 0.34 + ci * 1.86, 2.2
    for m in ch:
        s = tone(midi(m), dur, 'saw', 0.004)
        s *= np.minimum(1, np.arange(len(s)) / (0.25 * SR)) * np.minimum(1, (len(s) - np.arange(len(s))) / (0.4 * SR))
        i = int(st * SR)
        pad[i:i + len(s)] += s[: N - i] * 0.09
pad = lowpass(pad, 900 + 500 * np.sin(t * 1.3) ** 2)
pad[t > 11.5] *= np.exp(-(t[t > 11.5] - 11.5) * 6)
L += pad
R += pad

# ── groove from first cut to the montage ──
bt = CUTS[0]
while bt < CUTS[5] - 0.05:
    add(kick(0.35, 140, 45), bt, gain=0.75)
    add(hat(), bt + BEAT / 2, pan=0.4, gain=0.35)
    add(hat(0.03), bt + BEAT * 0.75, pan=-0.4, gain=0.18)
    bt += BEAT
# bass pulse on 16ths following chord roots
roots = [33, 29, 36, 31, 33, 29]
s16 = BEAT / 4
bt = CUTS[0]
while bt < CUTS[5] - 0.05:
    ci = min(len(roots) - 1, int((bt - 0.34) / 1.86))
    b = tone(midi(roots[ci] + 12), s16 * 0.9, 'saw', 0.002)
    b = lowpass(b, 600) * env(len(b), 0.002, 0.06)
    add(b, bt, gain=0.55)
    bt += s16

# ── whoosh into every transition, impact on it ──
for c in CUTS[:5]:
    add(whoosh(0.45), c - 0.4, pan=-0.5 + 0.25 * CUTS.index(c), gain=0.45)
    add(impact(), c, gain=0.55)

# ── montage: stutter hits every 0.15s, climbing in pitch ──
for k in range(8):
    st = CUTS[5] + k * 0.15
    add(kick(0.14, 180 + k * 30, 60 + k * 12), st, gain=0.7)
    z = noise(0.08)
    z = (z - lowpass(z, 3000)) * env(len(z), 0.0005, 0.03)
    add(z, st, pan=(-1) ** k * 0.6, gain=0.5)
add(whoosh(0.5), CUTS[6] - 0.48, gain=0.6)

# ── signature: deep impact + big chord swell + shimmer arpeggio ──
sig = CUTS[6]
add(impact(), sig, gain=1.0)
final = [45, 57, 60, 64, 67, 71, 76]  # Am(add9)-ish voicing
for m in final:
    s = tone(midi(m), DUR - sig, 'saw', 0.005)
    n = len(s)
    k = np.arange(n) / SR
    s = lowpass(s, 400 + 3000 * (1 - np.exp(-k * 2)))
    s *= (1 - np.exp(-k * 8)) * np.exp(-k * 0.35)
    add(s, sig, gain=0.07)
arp = [76, 79, 83, 88, 91, 95, 88, 83]
for i, m in enumerate(arp):
    s = tone(midi(m), 1.2, 'sine') + 0.3 * tone(midi(m) * 2.01, 1.2, 'sine')
    s *= env(len(s), 0.002, 0.35)
    add(s, sig + 0.3 + i * 0.11, pan=np.sin(i) * 0.7, gain=0.16)
# dot-pop "tick" when the period lands (signature lt ≈ 1.0)
add(tone(midi(96), 0.15, 'sine') * env(int(0.15 * SR), 0.001, 0.04), sig + 1.0, gain=0.35)

# ── cheap stereo reverb: decaying multi-taps ──
def reverb(x, taps):
    y = x.copy()
    for d, g in taps:
        i = int(d * SR)
        y[i:] += x[:-i] * g
    return y


L = reverb(L, [(0.031, .35), (0.067, .28), (0.113, .22), (0.171, .16), (0.239, .1), (0.33, .06)])
R = reverb(R, [(0.037, .35), (0.071, .28), (0.127, .22), (0.181, .16), (0.251, .1), (0.35, .06)])

# master: soft clip, normalize, fade
mix = np.stack([L, R], axis=1)
mix = np.tanh(mix * 1.1)
mix /= np.abs(mix).max() / 0.92
fade = np.minimum(1, (DUR - t) / 0.6)[:, None]
mix *= np.clip(fade, 0, 1)

os.makedirs(os.path.join(os.path.dirname(__file__), 'out'), exist_ok=True)
with wave.open(os.path.join(os.path.dirname(__file__), 'out', 'soundtrack.wav'), 'wb') as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes((mix * 32767).astype('<i2').tobytes())
print('wrote soundtrack.wav')
