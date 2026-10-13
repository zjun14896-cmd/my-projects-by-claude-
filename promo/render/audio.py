"""Original 120 BPM soundtrack + UI sound design, synthesized from scratch.

Reads the cue list exported from the motion timeline (render.mjs sfx) so every
click, whoosh and impact lands on the exact frame it belongs to.

usage: python3 audio.py build/sfx.json build/audio.wav
"""
import json
import sys
import wave

import numpy as np

SR = 48000
cues_doc = json.load(open(sys.argv[1]))
OUT = sys.argv[2]
BPM = cues_doc['bpm']
BEAT = 60 / BPM
DUR = cues_doc['dur']
N = int(SR * (DUR + 0.05))
rng = np.random.default_rng(1203)

music = np.zeros((N, 2))
fx = np.zeros((N, 2))
drums = np.zeros((N, 2))  # not sidechained
send = np.zeros((N, 2))  # reverb bus


def t_axis(d):
    return np.arange(int(d * SR)) / SR


def add(buf, start, sig, gain=1.0, pan=0.0):
    """Mix a mono or stereo signal into buf at time `start` (s). pan -1..1."""
    i = int(round(start * SR))
    if sig.ndim == 1:
        l, r = np.cos((pan + 1) * np.pi / 4), np.sin((pan + 1) * np.pi / 4)
        sig = np.stack([sig * l, sig * r], 1) * np.sqrt(2)
    if i < 0:
        sig, i = sig[-i:], 0
    j = min(N, i + len(sig))
    if j > i:
        buf[i:j] += sig[: j - i] * gain


def env(n, a=0.002, d=0.2, curve=6.0):
    t = np.arange(n) / SR
    att = np.clip(t / max(a, 1e-4), 0, 1)
    return att * np.exp(-curve * np.clip(t - a, 0, None) / d)


def fft_filter(x, lo=None, hi=None, order=2):
    """Zero-phase spectral band filter (static)."""
    n = len(x)
    X = np.fft.rfft(x, n * 2)
    f = np.fft.rfftfreq(n * 2, 1 / SR)
    g = np.ones_like(f)
    if hi:
        g /= np.sqrt(1 + (f / hi) ** (2 * order))
    if lo:
        g /= np.sqrt(1 + (lo / np.maximum(f, 1e-3)) ** (2 * order))
    return np.fft.irfft(X * g)[:n]


def swept_noise(d, f0, f1, q=1.2, shape=None):
    """Noise through a band-pass whose centre glides f0→f1 (block-wise STFT)."""
    n = int(d * SR)
    x = rng.standard_normal(n + 2048)
    blk, hop = 1024, 256
    win = np.hanning(blk)
    out = np.zeros(n + 2048)
    freqs = np.fft.rfftfreq(blk, 1 / SR)
    for s in range(0, n, hop):
        u = s / n
        fc = f0 * (f1 / f0) ** u
        bw = fc / q
        g = np.exp(-0.5 * ((freqs - fc) / bw) ** 2)
        seg = np.fft.irfft(np.fft.rfft(x[s:s + blk] * win) * g)
        out[s:s + blk] += seg * win
    out = out[:n]
    out /= np.max(np.abs(out)) + 1e-9
    if shape is not None:
        out *= shape(np.arange(n) / n)
    return out


def saw(freq, d, cutoff=None, cutoff_env=None, detune=0.0, phase=0.0):
    """Band-limited additive sawtooth with optional time-varying low-pass."""
    t = t_axis(d)
    nh = int(min(60, (SR / 2) / freq))
    out = np.zeros_like(t)
    fc = cutoff * (cutoff_env(t) if cutoff_env is not None else 1) if cutoff else None
    for k in range(1, nh + 1):
        g = 1.0 / k
        if fc is not None:
            g = g / np.sqrt(1 + (k * freq / fc) ** 4)
        out += g * np.sin(2 * np.pi * k * freq * (1 + detune) * t + phase * k)
    return out * 0.55


def note_hz(name):
    names = {'C': -9, 'C#': -8, 'D': -7, 'D#': -6, 'E': -5, 'F': -4, 'F#': -3, 'G': -2, 'G#': -1, 'A': 0, 'A#': 1, 'B': 2}
    n, o = name[:-1], int(name[-1])
    return 440.0 * 2 ** ((names[n] + 12 * (o - 4)) / 12)


# ---------------------------------------------------------------- drums
def kick(g=1.0, long=False):
    d = 0.6 if long else 0.38
    t = t_axis(d)
    f = 48 + 110 * np.exp(-t * 32)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t * (4.5 if long else 8))
    click = fft_filter(rng.standard_normal(len(t)), lo=1500) * np.exp(-t * 300) * 0.25
    return np.tanh((body + click) * 1.6) * g


def clap():
    d = 0.3
    n = int(d * SR)
    t = np.arange(n) / SR
    noise = fft_filter(rng.standard_normal(n), lo=900, hi=6000)
    e = np.zeros(n)
    for o in (0, 0.009, 0.018):
        e += np.where(t >= o, np.exp(-(t - o) * 90), 0) * 0.6
    e += np.where(t >= 0.025, np.exp(-(t - 0.025) * 16), 0)
    return noise * e * 0.5


def hat(open_=False):
    d = 0.22 if open_ else 0.05
    n = int(d * SR)
    x = fft_filter(rng.standard_normal(n), lo=7000)
    return x * env(n, 0.001, d * 0.5) * (0.22 if open_ else 0.16)


def crash():
    d = 2.2
    n = int(d * SR)
    x = fft_filter(rng.standard_normal(n), lo=3500)
    return x * env(n, 0.002, 1.1) * 0.35


# ---------------------------------------------------------------- arrangement
GROOVE_START = 3.0
BAR = 4 * BEAT
CHORDS = [  # A minor: i – VI – III – VII
    ('A1', ['A3', 'C4', 'E4'], ['A4', 'C5', 'E5', 'C5']),
    ('F1', ['F3', 'A3', 'C4'], ['F4', 'A4', 'C5', 'A4']),
    ('C2', ['C4', 'E4', 'G4'], ['C5', 'E5', 'G5', 'E5']),
    ('G1', ['G3', 'B3', 'D4'], ['G4', 'B4', 'D5', 'B4']),
]
END_HIT = 19.0

# sidechain envelope: duck pads/bass on every kick
duck = np.ones(N)
kick_times = [GROOVE_START + i * BEAT for i in range(int((END_HIT - GROOVE_START) / BEAT))]
for kt in kick_times:
    i = int(kt * SR)
    n = int(0.3 * SR)
    tt = np.arange(n) / SR
    seg = 1 - 0.75 * np.exp(-tt * 14)
    j = min(N, i + n)
    duck[i:j] = np.minimum(duck[i:j], seg[: j - i])

# intro (0–3 s): low drone + riser into the drop
d = GROOVE_START
drone = saw(note_hz('A1'), d, cutoff=180, cutoff_env=lambda t: 1 + 3 * (t / d) ** 2)
drone += saw(note_hz('A1'), d, cutoff=180, cutoff_env=lambda t: 1 + 3 * (t / d) ** 2, detune=0.006)
drone *= np.clip(t_axis(d) / 0.05, 0, 1) * 0.25
add(music, 0, drone)
riser = swept_noise(1.4, 400, 9000, q=1.5, shape=lambda u: u ** 2.2) * 0.22
add(music, GROOVE_START - 1.4, riser, pan=0)
# snare-roll build on the last beat of the intro
for k in range(8):
    add(music, GROOVE_START - BEAT + k * BEAT / 8, clap(), 0.25 + 0.08 * k)

# groove
for bi, bt in enumerate(np.arange(GROOVE_START, END_HIT, BAR)):
    root, pad, arp = CHORDS[bi % 4]
    bar_len = min(BAR, END_HIT - bt)
    # pad (supersaw, sidechained)
    for nn in pad:
        for det, pan in ((-0.007, -0.6), (0.0, 0.0), (0.007, 0.6)):
            p = saw(note_hz(nn), bar_len + 0.05, cutoff=1400 + 500 * (bi % 2), detune=det)
            p *= env(len(p), 0.03, 3.0, 1.0)
            add(music, bt, p, 0.05, pan)
    # bass: off-beat 8ths
    for k in range(8):
        st = bt + k * BEAT / 2
        if st >= bt + bar_len:
            break
        if k % 2 == 1 or k == 0:
            b = saw(note_hz(root) * 2, BEAT / 2 * 0.9, cutoff=500, cutoff_env=lambda t: 0.4 + 2.5 * np.exp(-t * 18))
            b += np.sin(2 * np.pi * note_hz(root) * t_axis(BEAT / 2 * 0.9)) * 0.6
            b *= env(len(b), 0.004, 0.2, 3)
            add(music, st, b, 0.42)
    # pluck arp: 16ths, enters after the logo
    if bt >= 5.0:
        for k in range(16):
            st = bt + k * BEAT / 4
            if st >= bt + bar_len:
                break
            f = note_hz(arp[k % 4]) * (2 if k % 8 >= 6 else 1)
            pl = saw(f, 0.22, cutoff=f * 2.2, cutoff_env=lambda t: 0.5 + 4 * np.exp(-t * 30))
            pl *= env(len(pl), 0.002, 0.12, 5)
            add(music, st, pl, 0.09, pan=0.35 * np.sin(k * 1.3))
            add(send, st, pl, 0.05, pan=-0.3)

# drums
for i, kt in enumerate(kick_times):
    add(drums, kt, kick(0.95))
    if i % 2 == 1:
        add(drums, kt, clap(), 0.55)
        add(send, kt, clap(), 0.25)
    add(drums, kt + BEAT / 2, hat(open_=True), 1.0, pan=0.25)
    for s in (0.25, 0.75):
        add(drums, kt + BEAT * s, hat(), 0.8, pan=-0.3)
# crashes on section downbeats
for ct in (3.0, 6.0, 11.0, 14.5):
    add(drums, ct, crash(), 0.6)
    add(send, ct, crash(), 0.2)

# sidechain: pads, bass and arp pump against the kick
music *= duck[:, None]

# ending: big final hit + sustained A minor chord
add(drums, END_HIT, kick(1.2, long=True))
add(drums, END_HIT, crash(), 0.9)
add(send, END_HIT, crash(), 0.5)
for nn in ('A2', 'A3', 'C4', 'E4', 'A4'):
    for det, pan in ((-0.006, -0.7), (0.006, 0.7)):
        p = saw(note_hz(nn), DUR - END_HIT, cutoff=1800, cutoff_env=lambda t: 1 / (1 + t * 1.5), detune=det)
        p *= env(len(p), 0.01, 0.9, 2.2)
        add(music, END_HIT, p, 0.07, pan)
        add(send, END_HIT, p, 0.05, pan)


# ---------------------------------------------------------------- sound design
def s_impact(g):
    t = t_axis(1.2)
    f = 38 + 120 * np.exp(-t * 18)
    boom = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t * 3.2)
    hit = fft_filter(rng.standard_normal(len(t)), lo=200, hi=5000) * np.exp(-t * 22) * 0.6
    sig = np.tanh((boom * 1.3 + hit) * 1.4) * 0.8 * g
    return sig


def s_whoosh(g, d=0.8, f0=300, f1=4500):
    shape = lambda u: np.sin(np.pi * u) ** 2 * (u < 1)
    x = swept_noise(d, f0, f1, q=1.1, shape=shape) * 0.5 * g
    n = len(x)
    pan = np.linspace(-0.9, 0.9, n)
    return np.stack([x * np.cos((pan + 1) * np.pi / 4), x * np.sin((pan + 1) * np.pi / 4)], 1) * np.sqrt(2)


def s_click(g):
    t = t_axis(0.06)
    tr = fft_filter(rng.standard_normal(len(t)), lo=2500) * np.exp(-t * 900) * 0.7
    tone = np.sin(2 * np.pi * 1900 * t) * np.exp(-t * 160) * 0.5
    t2 = t_axis(0.05)
    rel = np.sin(2 * np.pi * 2600 * t2) * np.exp(-t2 * 220) * 0.25
    out = np.zeros(int(0.12 * SR))
    out[: len(t)] += tr + tone
    o = int(0.055 * SR)
    out[o:o + len(t2)] += rel
    return out * g


def s_pop(g, f0=520, f1=980, d=0.09):
    t = t_axis(d)
    f = f0 + (f1 - f0) * (1 - np.exp(-t * 60))
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(t), 0.002, d * 0.6, 4) * 0.5 * g


def s_tick(g):
    t = t_axis(0.015)
    return np.sin(2 * np.pi * 3200 * t) * np.exp(-t * 500) * 0.35 * g


def s_type(g):
    n = int(0.012 * SR)
    return fft_filter(rng.standard_normal(n), lo=2500, hi=7000) * env(n, 0.0005, 0.004) * 0.6 * g


def s_blip(g):
    t = t_axis(0.25)
    f = 1046.5 * (1 + 0.25 * (g - 0.7))
    s = np.sin(2 * np.pi * f * t) + 0.35 * np.sin(2 * np.pi * f * 2.01 * t) + 0.15 * np.sin(2 * np.pi * f * 3.98 * t)
    return s * env(len(t), 0.002, 0.1, 5) * 0.28 * g


def s_zap(g):
    t = t_axis(0.18)
    f = 1500 * np.exp(-t * 14) + 250
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(t), 0.002, 0.12, 4) * 0.22 * g


def s_drop(g):
    t = t_axis(0.25)
    f = 420 * np.exp(-t * 9) + 120
    return np.sin(2 * np.pi * np.cumsum(f) / SR) * env(len(t), 0.003, 0.18, 4) * 0.5 * g


def s_land(g):
    t = t_axis(1.0)
    thump = np.sin(2 * np.pi * (60 + 80 * np.exp(-t * 30)) * t) * np.exp(-t * 9) * 0.6
    bell = sum(np.sin(2 * np.pi * note_hz(n) * t) * a for n, a in (('A5', 0.3), ('E6', 0.2), ('A6', 0.12)))
    return (thump + bell * np.exp(-t * 4)) * 0.6 * g


def s_glitch(g):
    n = int(0.32 * SR)
    x = rng.standard_normal(n)
    x = np.round(x * 3) / 3  # crush
    gate = (np.sin(np.arange(n) / SR * 2 * np.pi * 26) > 0).astype(float)
    tone = np.sign(np.sin(2 * np.pi * 180 * np.arange(n) / SR)) * 0.3
    return fft_filter((x * 0.4 + tone) * gate, hi=6000) * env(n, 0.001, 0.25, 3) * 0.4 * g


def s_bubble(g):
    a = s_pop(1, 400, 700, 0.07)
    b = s_pop(1, 700, 1200, 0.08)
    out = np.zeros(int(0.16 * SR))
    out[: len(a)] += a
    o = int(0.06 * SR)
    out[o:o + len(b)] += b
    return out * g


def s_rise(g):
    return s_whoosh(g * 0.8, d=0.5, f0=500, f1=6000)


def s_scan(g):
    t = t_axis(0.6)
    f = 2000 + 3000 * t / 0.6
    s = np.sin(2 * np.pi * np.cumsum(f) / SR) * 0.12 + swept_noise(0.6, 3000, 9000, q=2) * 0.15
    return s * np.sin(np.pi * t / 0.6) * g


def s_swish(g):
    return s_whoosh(g, d=0.28, f0=1200, f1=5000)


def s_flyby(g):
    x = s_whoosh(g * 1.1, d=0.55, f0=250, f1=2500)
    return x


SYN = {
    'impact': s_impact, 'whoosh': s_whoosh, 'click': s_click, 'pop': s_pop, 'tick': s_tick, 'type': s_type,
    'blip': s_blip, 'zap': s_zap, 'drop': s_drop, 'land': s_land, 'glitch': s_glitch, 'bubble': s_bubble,
    'rise': s_rise, 'scan': s_scan, 'swish': s_swish, 'flyby': s_flyby,
}
for c in cues_doc['cues']:
    sig = SYN[c['type']](c['gain'])
    pan = 0.0 if sig.ndim == 2 else float(rng.uniform(-0.25, 0.25))
    add(fx, c['t'], sig, 0.9, pan)
    if c['type'] in ('impact', 'land', 'blip', 'pop', 'bubble'):
        add(send, c['t'], sig, 0.3, pan)


# ---------------------------------------------------------------- reverb + master
def reverb(x, d=1.6):
    n = int(d * SR)
    t = np.arange(n) / SR
    out = np.zeros_like(x)
    for ch in range(2):
        ir = rng.standard_normal(n) * np.exp(-t * 4.2)
        ir = fft_filter(ir, lo=200, hi=7000)
        L = len(x) + n
        y = np.fft.irfft(np.fft.rfft(x[:, ch], L) * np.fft.rfft(ir, L), L)[: len(x)]
        out[:, ch] = y
    return out / (np.max(np.abs(out)) + 1e-9) * np.max(np.abs(x)) * 0.8


mix = music * 0.8 + drums * 0.8 + fx * 0.85 + reverb(send) * 0.5
mix = fft_filter(mix[:, 0], lo=25)[:, None] * [1, 0] + fft_filter(mix[:, 1], lo=25)[:, None] * [0, 1]
# fade the tail, soft-clip, normalise
fade = np.clip((DUR - np.arange(N) / SR) / 0.35, 0, 1)
mix *= fade[:, None]
mix = np.tanh(mix / (np.max(np.abs(mix)) + 1e-9) * 1.6) / np.tanh(1.6)
mix *= 0.89
pcm = (mix[: int(DUR * SR)] * 32767).astype('<i2')
with wave.open(OUT, 'wb') as w:
    w.setnchannels(2)
    w.setsampwidth(2)
    w.setframerate(SR)
    w.writeframes(pcm.tobytes())
print(f'wrote {OUT}: {DUR}s, {len(cues_doc["cues"])} cues')
