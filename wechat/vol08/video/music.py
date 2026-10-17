#!/usr/bin/env python3
"""第 8 期 18 秒短片配乐（第二版，明亮大调）：原创电子节拍，全部由代码合成（无采样、无版权素材）。

120 BPM，一拍 0.5 秒，一小节 2 秒，共 9 小节，与画面一一对应（F 大调）：
  0–2s    粒子汇聚：Fmaj9 铺底渐强 + 高音闪烁琶音 + 噪声上扬，1.98s 爆开
  2–4s    拼贴墙：半拍底鼓 + 十六分琶音 + 上扬，最后半小节军鼓滚奏
  4–14s   五段现场：四拍底鼓、二四拍拍手、反拍踩镲、侧链贝斯、琶音、和弦 F C Dm Bb C
          切换点 6/8/10/12s 前有扫频「唰」，切点上有冲击音
  14–16s  拉回拼贴墙并化为粒子：鼓组退出，Bb → C 铺底 + 闪烁琶音 + 上扬
  16–18s  落款：F(add9) 大和弦重拍 + 亮音 + 混响尾音
用法：python3 music.py out.wav
"""
import sys
import wave

import numpy as np
from scipy import signal

SR = 44100
BPM = 120
BEAT = 60 / BPM
DUR = 18.0
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
def impact():
    """切点冲击：高通噪声爆 + 短促正弦下滑。"""
    sec = 0.7
    t = t_axis(sec)
    n = hp(rng.standard_normal(len(t)), 1500) * np.exp(-t / 0.18) * 0.35
    f = 220 * np.exp(-t / 0.08) + 60
    tone = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-t / 0.25) * 0.5
    return n + tone


def compose():
    drums = np.zeros(N)
    music = np.zeros(N)
    low = np.zeros(N)
    fx = np.zeros(N)

    # F 大调：F C Dm Bb C（4–14s），铺底与琶音用高八度，整体明亮
    chords = [[53, 57, 60, 64], [48, 52, 55, 62], [50, 53, 57, 60], [46, 50, 53, 57], [48, 52, 55, 60]]
    roots = [41, 36, 38, 34, 36]

    def arp(t0, notes, steps=16, oct_=24, gain=0.5):
        seq = [0, 1, 2, 3, 2, 1, 3, 2]
        for k in range(steps):
            n_ = notes[seq[k % 8]] + oct_
            place(music, pluck(note(n_)), t0 + k * BEAT / 4, gain * (1.0 + 0.4 * (k % 4 == 0)))

    # 0–2s 粒子汇聚
    place(music, pad([note(n) for n in (53, 60, 64, 67, 69)], 2.1, attack=1.4, release=0.3, bright=2600), 0.0, 0.9)
    for k in range(8):
        place(music, chime(note([77, 81, 84, 88, 84, 81, 88, 91][k])), 0.25 + k * 0.2, 0.35 + 0.05 * k)
    t = t_axis(1.95)
    place(fx, bp(rng.standard_normal(len(t)), 800, 9000) * (t / 1.95) ** 2.4 * 0.45, 0.0)
    place(fx, np.sin(2 * np.pi * np.cumsum(330 * 2 ** (2.0 * t / 1.95)) / SR) * (t / 1.95) ** 2 * 0.1, 0.0)
    place(low, sub_boom(1.6, 43.65), 0.0, 0.5)

    # 1.98s 爆开
    place(drums, kick(big=True), 1.98, 1.0)
    place(drums, crash(2.2), 1.98, 1.0)
    place(fx, impact(), 1.98, 0.9)
    place(low, sub_boom(1.2, 43.65), 1.98, 0.7)

    # 2–4s 拼贴墙：半拍底鼓 + 琶音 + 滚奏
    for b in (0, 2):
        if b:
            place(drums, kick(), 2.0 + b * BEAT, 0.85)
    place(drums, clap(), 2.0 + 3 * BEAT, 0.6)
    arp(2.0, chords[0], gain=0.42)
    place(music, pad([note(n) for n in chords[0]], 2.0, attack=0.2, release=0.3, bright=2400), 2.0, 0.5)
    for k in range(8):
        place(drums, clap(), 3.0 + k * BEAT / 4, 0.25 + 0.06 * k)
    t = t_axis(1.0)
    place(fx, bp(rng.standard_normal(len(t)), 1000, 9000) * (t / 1.0) ** 2 * 0.4, 3.0)
    place(fx, whoosh(0.45), 3.55, 0.9)

    # 4–14s 五段现场
    place(drums, kick(big=True), 4.0, 1.0)
    place(drums, crash(1.8), 4.0, 0.8)
    for bar in range(5):
        t0 = 4.0 + bar * 2.0
        for b in range(4):
            tb = t0 + b * BEAT
            if not (bar == 0 and b == 0):
                place(drums, kick(), tb, 0.92)
            if b in (1, 3):
                place(drums, clap(), tb, 0.75)
            place(drums, hat(), tb + BEAT / 2, 0.75)
            place(drums, hat(), tb + BEAT / 4, 0.2)
            place(drums, hat(), tb + 3 * BEAT / 4, 0.2)
            place(low, bass(note(roots[bar]), BEAT / 2 - 0.02), tb + BEAT / 2, 1.0)
            place(low, bass(note(roots[bar] + 12), BEAT / 4 - 0.02), tb + 3 * BEAT / 4, 0.45)
        arp(t0, chords[bar], gain=0.5)
        place(music, pad([note(n + 12) for n in chords[bar][:3]], 2.0, attack=0.12, release=0.3, bright=3000), t0, 0.5)
        if bar < 4:
            place(fx, whoosh(0.45), t0 + 2.0 - 0.45, 0.95)
            place(fx, impact(), t0 + 2.0, 0.7)
            place(drums, crash(1.0), t0 + 2.0, 0.3)

    # 14–16s 拉回、化为粒子
    place(fx, impact(), 14.0, 0.8)
    place(drums, crash(2.4), 14.0, 0.6)
    place(low, sub_boom(1.6, 46.25), 14.0, 0.6)
    place(music, pad([note(n) for n in (46, 53, 58, 62, 65)], 1.0, attack=0.05, release=0.4, bright=2400), 14.0, 0.8)
    place(music, pad([note(n) for n in (48, 55, 60, 64, 67)], 1.0, attack=0.05, release=0.4, bright=2800), 15.0, 0.8)
    for k in range(16):
        place(music, chime(note([82, 86, 89, 94, 89, 86, 91, 96][k % 8])), 14.0 + k * BEAT / 4, 0.18 + 0.012 * k)
    t = t_axis(1.95)
    place(fx, bp(rng.standard_normal(len(t)), 900, 10000) * (t / 1.95) ** 2.6 * 0.45, 14.05)
    place(fx, whoosh(0.5), 15.5, 1.0)

    # 16–18s 落款
    place(drums, kick(big=True), 16.0, 1.0)
    place(low, sub_boom(2.2, 43.65), 16.0, 0.9)
    place(drums, crash(2.4), 16.0, 1.0)
    place(fx, impact(), 16.0, 0.6)
    place(music, pad([note(n) for n in (41, 53, 60, 64, 67, 72)], 2.0, attack=0.04, release=1.4, bright=3200), 16.0, 1.0)
    for k, n_ in enumerate([77, 81, 84, 88, 89, 84]):
        place(music, pluck(note(n_), 0.5), 16.0 + k * BEAT / 2, 0.5 * (0.85 ** k))
    place(fx, chime(note(93)), 16.75, 1.0)
    place(fx, chime(note(88)), 16.75, 0.6)

    # 侧链：五段现场每拍压低铺底与贝斯
    duck = np.ones(N)
    for k in range(20):
        i = int((4.0 + k * BEAT) * SR)
        n_ = int(0.22 * SR)
        duck[i:i + n_] = np.minimum(duck[i:i + n_], 0.35 + 0.65 * np.linspace(0, 1, n_) ** 1.5)
    music *= duck
    low *= np.maximum(duck, 0.55)

    music = delay(music, BEAT * 0.75, fb=0.3, mix=0.25)
    music = reverb(music, 2.4, wet=0.3)
    drums = drums + reverb(drums * 0.3, 1.0, wet=1.0) * 0.15
    fx = reverb(fx, 2.0, wet=0.3)

    mix = drums * 0.9 + music * 0.95 + low * 0.8 + fx * 0.8
    mix = hp(mix, 30)
    fade = np.ones(N)
    a = int(17.0 * SR)
    fade[a:] = np.linspace(1, 0, N - a) ** 1.6
    mix *= fade
    wide = music * 0.9
    d = int(0.012 * SR)
    left = mix + 0.15 * wide
    right = mix + 0.15 * np.concatenate([np.zeros(d), wide[:-d]])
    st = np.stack([left, right], axis=1)
    st = np.tanh(st * 1.2) / np.tanh(1.2)
    st *= 0.89 / np.max(np.abs(st))
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
