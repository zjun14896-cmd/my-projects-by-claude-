#!/usr/bin/env python3
"""第 8 期 15 秒短片配乐：原创电子节拍，全部由代码合成（无采样、无版权素材）。

120 BPM，一拍 0.5 秒，一小节 2 秒，与画面结构一一对应：
  0–2s   片头：低频轰鸣 + 噪声上扬 + 军鼓滚奏，1.95s 留 50ms 空拍
  2s     落点：重拍（底鼓 + 次低频 + 镲片）
  2–12s  五段现场：四拍底鼓、二四拍拍手、反拍踩镲、侧链贝斯、十六分琶音、柔和铺底
          和弦 Am → F → C → G → E，每 2 秒换一次，切换点前有扫频「唰」声
  12s    收束重拍，鼓组停止，Am(add9) 长音铺底 + 混响尾音
  13s    「第 9 期 · 招生中」出现时一声亮音
用法：python3 music.py out.wav
"""
import sys
import wave

import numpy as np
from scipy import signal

SR = 44100
BPM = 120
BEAT = 60 / BPM
DUR = 15.0
N = int(SR * DUR)
rng = np.random.default_rng(8)


def t_axis(sec):
    return np.arange(int(sec * SR)) / SR


def place(buf, x, at, gain=1.0):
    i = int(at * SR)
    if i >= len(buf):
        return
    x = x[: len(buf) - i]
    buf[i:i + len(x)] += x * gain


def env_exp(sec, decay):
    t = t_axis(sec)
    return np.exp(-t / decay)


def adsr(sec, a=0.005, r=0.1):
    n = int(sec * SR)
    e = np.ones(n)
    na, nr = max(1, int(a * SR)), max(1, int(r * SR))
    e[:na] = np.linspace(0, 1, na)
    e[-nr:] *= np.linspace(1, 0, nr)
    return e


def lp(x, fc, order=2):
    b, a = signal.butter(order, min(fc / (SR / 2), 0.99), "low")
    return signal.lfilter(b, a, x)


def hp(x, fc, order=2):
    b, a = signal.butter(order, fc / (SR / 2), "high")
    return signal.lfilter(b, a, x)


def bp(x, lo, hi, order=2):
    b, a = signal.butter(order, [lo / (SR / 2), min(hi / (SR / 2), 0.99)], "band")
    return signal.lfilter(b, a, x)


def saw(freq, sec, detune=0.0):
    t = t_axis(sec)
    out = np.zeros_like(t)
    for d in (-detune, 0, detune) if detune else (0,):
        f = freq * (1 + d)
        out += 2 * ((t * f) % 1.0) - 1
    return out / (3 if detune else 1)


def note(n):
    """MIDI 音符号 → 频率。"""
    return 440.0 * 2 ** ((n - 69) / 12)


def reverb(x, sec=2.2, wet=0.3):
    ir_t = t_axis(sec)
    ir = rng.standard_normal(len(ir_t)) * np.exp(-ir_t / (sec / 5))
    ir = lp(ir, 6000)
    ir /= np.sqrt(np.sum(ir ** 2))
    y = signal.fftconvolve(x, ir)[: len(x)]
    return x * (1 - wet) + y * wet


def delay(x, sec, fb=0.35, mix=0.3):
    d = int(sec * SR)
    y = x.copy()
    for k in range(1, 5):
        if d * k >= len(x):
            break
        y[d * k:] += x[: len(x) - d * k] * (fb ** k) * mix / 0.35
    return y


# ── 音色 ─────────────────────────────────────────────────
def kick(big=False):
    sec = 0.6 if big else 0.35
    t = t_axis(sec)
    f = 45 + 110 * np.exp(-t / 0.035)
    ph = 2 * np.pi * np.cumsum(f) / SR
    body = np.sin(ph) * np.exp(-t / (0.22 if big else 0.12))
    click = hp(rng.standard_normal(len(t)), 3000) * np.exp(-t / 0.004) * 0.3
    return np.tanh((body + click) * (1.8 if big else 1.4))


def clap():
    sec = 0.4
    t = t_axis(sec)
    n = bp(rng.standard_normal(len(t)), 900, 5000)
    e = np.zeros_like(t)
    for off in (0, 0.011, 0.022):
        i = int(off * SR)
        e[i:] += np.exp(-(t[: len(t) - i]) / 0.012)
    e += np.exp(-t / 0.12) * 0.6
    return n * e * 0.5


def hat(open_=False):
    sec = 0.25 if open_ else 0.06
    t = t_axis(sec)
    return hp(rng.standard_normal(len(t)), 7000) * np.exp(-t / (0.08 if open_ else 0.015)) * 0.35


def crash(sec=1.8):
    t = t_axis(sec)
    return hp(rng.standard_normal(len(t)), 4000) * np.exp(-t / 0.5) * 0.35


def sub_boom(sec=1.4, f0=55):
    t = t_axis(sec)
    return np.sin(2 * np.pi * f0 * t) * np.exp(-t / 0.45) * (1 - np.exp(-t / 0.004))


def whoosh(sec=0.45):
    t = t_axis(sec)
    n = rng.standard_normal(len(t))
    # 中心频率从 300Hz 扫到 8000Hz：分块带通近似
    out = np.zeros_like(n)
    blocks = 24
    for k in range(blocks):
        a, b = int(len(n) * k / blocks), int(len(n) * (k + 1) / blocks)
        fc = 300 * (8000 / 300) ** (k / blocks)
        seg = bp(n, fc * 0.7, fc * 1.4)[a:b]
        out[a:b] = seg
    e = (t / sec) ** 2
    return out * e * 0.6


def pluck(freq, sec=0.22):
    t = t_axis(sec)
    x = saw(freq, sec, detune=0.006)
    cut = 600 + 5000 * np.exp(-t / 0.05)
    # 时变低通：分块
    y = np.zeros_like(x)
    blocks = 8
    for k in range(blocks):
        a, b = int(len(x) * k / blocks), int(len(x) * (k + 1) / blocks)
        y[a:b] = lp(x, cut[a])[a:b]
    return y * np.exp(-t / 0.09) * 0.35


def pad(freqs, sec, attack=0.4, release=0.8, bright=1800):
    x = sum(saw(f, sec, detune=0.004) for f in freqs) / len(freqs)
    x = lp(x, bright, order=2)
    e = adsr(sec, attack, release)
    return x * e * 0.25


def bass(freq, sec):
    t = t_axis(sec)
    x = saw(freq, sec) * 0.6 + np.sin(2 * np.pi * freq * t) * 0.6
    return lp(x, 380) * adsr(sec, 0.004, 0.04) * 0.55


def chime(freq, sec=2.0):
    t = t_axis(sec)
    x = (np.sin(2 * np.pi * freq * t) + 0.4 * np.sin(2 * np.pi * freq * 2.01 * t)
         + 0.2 * np.sin(2 * np.pi * freq * 3.0 * t))
    return x * np.exp(-t / 0.6) * (1 - np.exp(-t / 0.003)) * 0.18


# ── 编曲 ─────────────────────────────────────────────────
def compose():
    drums = np.zeros(N)
    music = np.zeros(N)
    low = np.zeros(N)
    fx = np.zeros(N)

    # 和弦（MIDI）：Am F C G E，每小节 2 秒
    chords = [[57, 60, 64], [53, 57, 60], [48, 52, 55], [55, 59, 62], [52, 56, 59]]
    roots = [45, 41, 48, 43, 40]

    # 片头 0–2s
    place(low, sub_boom(1.8, 55), 0.0, 0.9)
    place(music, pad([note(n) for n in (57, 64, 71)], 2.0, attack=1.2, release=0.3, bright=1200), 0.0, 0.8)
    t = t_axis(1.95)
    riser = bp(rng.standard_normal(len(t)), 500, 7000) * (t / 1.95) ** 2.2 * 0.5
    place(fx, riser, 0.0)
    rise = np.sin(2 * np.pi * np.cumsum(220 * 2 ** (2.2 * t / 1.95)) / SR) * (t / 1.95) ** 2 * 0.12
    place(fx, rise, 0.0)
    for k in range(4):                       # 1.0–1.5s：八分
        place(drums, clap() * 0.35, 1.0 + k * BEAT / 4, 0.35 + 0.05 * k)
    for k in range(8):                       # 1.5–1.95s：十六分
        place(drums, clap() * 0.4, 1.5 + k * BEAT / 8 * 0.9, 0.5 + 0.06 * k)

    # 落点 2.0s
    place(drums, kick(big=True), 2.0, 1.0)
    place(low, sub_boom(1.2, 45), 2.0, 0.8)
    place(drums, crash(2.0), 2.0, 1.0)

    # 主体 2–12s
    for bar in range(5):
        t0 = 2.0 + bar * 2.0
        for b in range(4):
            tb = t0 + b * BEAT
            if not (bar == 0 and b == 0):
                place(drums, kick(), tb, 0.95)
            if b in (1, 3):
                place(drums, clap(), tb, 0.8)
            place(drums, hat(), tb + BEAT / 2, 0.8)
            place(drums, hat(), tb + BEAT / 4, 0.22)
            place(drums, hat(), tb + 3 * BEAT / 4, 0.22)
            # 贝斯：反拍进入（侧链感）
            place(low, bass(note(roots[bar]), BEAT / 2 - 0.02), tb + BEAT / 2, 1.0)
            place(low, bass(note(roots[bar] + 12), BEAT / 4 - 0.02), tb + 3 * BEAT / 4, 0.5)
        # 十六分琶音
        arp = chords[bar] + [chords[bar][0] + 12]
        for k in range(16):
            n_ = arp[[0, 1, 2, 3, 2, 1, 2, 3][k % 8]] + 12
            place(music, pluck(note(n_)), t0 + k * BEAT / 4, 0.55 + 0.25 * (k % 4 == 0))
        place(music, pad([note(n) for n in chords[bar]], 2.0, attack=0.15, release=0.3), t0, 0.55)
        # 小节切换：唰 + 轻镲
        if bar < 4:
            place(fx, whoosh(0.45), t0 + 2.0 - 0.45, 0.9)
            place(drums, crash(1.0), t0 + 2.0, 0.28)
        if bar == 4:                          # 收束前：空半拍
            pass

    # 收束 12–15s
    place(drums, kick(big=True), 12.0, 1.0)
    place(low, sub_boom(2.6, 55), 12.0, 0.9)
    place(drums, crash(2.8), 12.0, 1.1)
    place(fx, whoosh(0.5), 11.5, 1.0)
    place(music, pad([note(n) for n in (45, 57, 60, 64, 71)], 3.0, attack=0.05, release=1.6, bright=2600), 12.0, 1.0)
    for k, n_ in enumerate([69, 72, 76, 79, 81, 76]):
        place(music, pluck(note(n_), 0.5), 12.0 + k * BEAT / 2, 0.5 * (0.85 ** k))
    place(fx, chime(note(88)), 13.0, 1.0)
    place(fx, chime(note(83)), 13.0, 0.6)

    # 侧链：主体段内每拍压低铺底与贝斯
    duck = np.ones(N)
    for k in range(20):
        tb = 2.0 + k * BEAT
        i = int(tb * SR)
        n_ = int(0.22 * SR)
        duck[i:i + n_] = np.minimum(duck[i:i + n_], 0.35 + 0.65 * np.linspace(0, 1, n_) ** 1.5)
    music *= duck
    low *= np.maximum(duck, 0.55)

    music = delay(music, BEAT * 0.75, fb=0.3, mix=0.25)
    music = reverb(music, 2.4, wet=0.28)
    drums = drums + reverb(drums * 0.3, 1.0, wet=1.0) * 0.15
    fx = reverb(fx, 2.0, wet=0.3)

    mix = drums * 0.9 + music * 0.9 + low * 0.85 + fx * 0.8
    mix = hp(mix, 28)
    # 结尾淡出
    fade = np.ones(N)
    a, b = int(13.8 * SR), N
    fade[a:b] = np.linspace(1, 0, b - a) ** 1.6
    mix *= fade
    # 立体声：轻微哈斯展宽（只作用于琶音/铺底）
    wide = music * 0.9
    d = int(0.012 * SR)
    left = mix + 0.15 * wide
    right = mix + 0.15 * np.concatenate([np.zeros(d), wide[:-d]])
    st = np.stack([left, right], axis=1)
    st = np.tanh(st * 1.2) / np.tanh(1.2)       # 软削波
    st *= 0.89 / np.max(np.abs(st))              # 峰值约 -1 dBFS
    return st


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "music.wav"
    st = compose()
    pcm = (st * 32767).astype(np.int16)
    with wave.open(out, "wb") as w:
        w.setnchannels(2)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(pcm.tobytes())
    rms = 20 * np.log10(np.sqrt(np.mean(st ** 2)))
    print(f"{out}: {DUR}s, RMS {rms:.1f} dBFS")


if __name__ == "__main__":
    main()
