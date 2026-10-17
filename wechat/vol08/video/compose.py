#!/usr/bin/env python3
"""第 8 期 18 秒短片合成（第二版，亮色 / 粒子 / 炫光）。

时间线（120 BPM，一小节 2 秒，共 9 小节）：
  0.0–2.0   亮色背景上，粒子旋转汇聚成「08」→ 字形填色 → 光线划过 → 1.98s 炫光爆开
  2.0–4.0   五段视频在 3D 倾斜的拼贴墙上同时播放，依次弹入；3.3s 起镜头推进主画面
  4.0–14.0  五段现场各 2 秒，毛玻璃字幕卡；6/8/10/12s 依次为横扫炫光、中心爆闪、斜向光斑、反向棱镜炫光
  14.0–16.6 镜头拉回拼贴墙，五段再次同时播放，随后逐块燃烧化为粒子飘散
  16.0–18.0 亮色背景落款：五天，把路走通。/ 第 9 期 · 招生中 / logo
所有粒子与动画都是时间 t 的解析函数，可以分段并行渲染。
用法：python3 -I compose.py <sdr/> <frames/> <music.wav> <out.mp4> [--workers 4] [--frames 0,60]
"""
import argparse
import math
import pathlib
import subprocess
import sys

import cv2
import numpy as np

W, H, FPS, TOTAL = 1920, 1080, 30, 540
F = 1700.0


def C(h):
    return np.array([int(h[i:i + 2], 16) for i in (1, 3, 5)], np.float32) / 255


BLUE, BLUE2, CYAN, YELLOW, GOLD = C("#003CAC"), C("#2F6BFF"), C("#7CC4FF"), C("#FFC833"), C("#FFB21E")
WHITE = np.ones(3, np.float32)
FLASH = np.array([0.975, 0.985, 1.0], np.float32)


def clamp(x, a=0.0, b=1.0):
    return min(b, max(a, x))


def prog(t, a, b):
    return clamp((t - a) / (b - a))


def ease_io(x):
    return 4 * x ** 3 if x < 0.5 else 1 - (-2 * x + 2) ** 3 / 2


def ease_in(x):
    return x ** 3


def ease_out(x):
    return 1 - (1 - x) ** 3


def out_back(x, c=1.7):
    return 1 + (c + 1) * (x - 1) ** 3 + c * (x - 1) ** 2


def bell(t, c, w):
    return math.exp(-((t - c) / w) ** 2)


# ── 素材 ─────────────────────────────────────────────────
CLIPS = ["s1", "s2", "s3", "s4", "s5"]
SEG0, SEGLEN, SPEED = 4.0, 2.0, 1.25
SEG_TIN = [2.2, 1.0, 0.8, 0.6, 0.5]
SEG_FOCUS = [(0.55, 0.42), (0.58, 0.40), (0.47, 0.40), (0.62, 0.36), (0.56, 0.40)]
SEG_ZOOM = [(1.0, 1.12), (1.04, 1.16), (1.05, 1.18), (1.08, 1.26), (1.04, 1.14)]
WALL_IN_SRC = [0.2, 0.0, 0.0, 0.0, 0.0]      # src = a + (t - 2)
WALL_OUT_SRC = [0.3, 1.6, 2.0, 1.8, 3.0]     # src = b + (t - 14)；第 5 段与正片衔接
CUTS = [(6.0, "sweepL"), (8.0, "burst"), (10.0, "leak"), (12.0, "sweepR")]


class Clip:
    def __init__(self, path):
        self.cap = cv2.VideoCapture(str(path))
        self.n = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.cache, self.pos = {}, 0

    def frame(self, i):
        i = int(clamp(i, 0, self.n - 1))
        if i in self.cache:
            return self.cache[i]
        if i < self.pos or i > self.pos + 90:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, i)
            self.pos = i
        while self.pos <= i:
            ok, fr = self.cap.read()
            if not ok:
                fr = self.cache[max(self.cache)] if self.cache else np.zeros((H, W, 3), np.uint8)
            else:
                fr = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
            self.cache[self.pos] = fr
            self.pos += 1
        for k in [k for k in self.cache if k < i - 4 or k > i + 4]:
            del self.cache[k]
        return self.cache[i]

    def at(self, sec):
        x = max(0.0, sec) * FPS
        a = int(math.floor(x))
        f = x - a
        fa = self.frame(a).astype(np.float32) / 255
        if f < 0.08 or a + 1 >= self.n:
            return fa
        return fa * (1 - f) + (self.frame(a + 1).astype(np.float32) / 255) * f


def crop_zoom(img, z, cx, cy, extra=1.0):
    z *= extra
    h, w = img.shape[:2]
    cw, ch = w / z, h / z
    x0 = clamp(cx * w - cw / 2, 0, w - cw)
    y0 = clamp(cy * h - ch / 2, 0, h - ch)
    m = np.array([[z, 0, -x0 * z], [0, z, -y0 * z]], np.float32)
    return cv2.warpAffine(img, m, (w, h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


LUMA = np.array([0.2126, 0.7152, 0.0722], np.float32)


def grade(x):
    """明亮通透：提中间调、略增饱和、偏冷的干净白。"""
    x = cv2.pow(np.clip(x, 0, 1), 0.84)
    lum = (x @ LUMA)[..., None]
    x = lum + (x - lum) * 1.14
    x = x * np.array([0.985, 1.0, 1.03], np.float32) + 0.022
    return np.clip(x, 0, 1)


def bloom(img, k=0.28):
    s = cv2.resize(img, (480, 270), interpolation=cv2.INTER_AREA)
    s = np.maximum(s - 0.74, 0) * 3.2
    s = cv2.GaussianBlur(s, (0, 0), 9)
    return img + cv2.resize(s, (W, H)) * k * np.array([1.0, 0.97, 0.92], np.float32)


# ── 背景 / 光斑 / 炫光 ────────────────────────────────────
LX, LY = np.meshgrid(np.linspace(0, 1, 240, dtype=np.float32), np.linspace(0, 1, 135, dtype=np.float32))


def blob(cx, cy, r, aspect=1.78):
    return np.exp(-(((LX - cx) * aspect) ** 2 + (LY - cy) ** 2) / (2 * r * r))[..., None]


def make_dots():
    """科技感点阵：40px 间距、径向淡出。"""
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    gx = (xx % 40) - 20
    gy = (yy % 40) - 20
    d = np.sqrt(gx * gx + gy * gy)
    dots = np.clip(1.8 - d, 0, 1)
    r = np.sqrt(((xx - W / 2) / (W * 0.62)) ** 2 + ((yy - H / 2) / (H * 0.62)) ** 2)
    return (dots * np.clip(1 - r, 0, 1) ** 1.2 * 0.13)[..., None]


DOTS = None


def background(t):
    top, bot = np.array([0.99, 0.995, 1.0], np.float32), np.array([0.925, 0.948, 1.0], np.float32)
    g = top + (bot - top) * LY[..., None] ** 1.2
    for (cx, cy, r, col, a) in [
        (0.16 + 0.05 * math.sin(0.5 * t), 0.22 + 0.04 * math.cos(0.4 * t), 0.30, np.array([0.45, 0.62, 1.0], np.float32), 0.42),
        (0.86 + 0.04 * math.cos(0.45 * t), 0.78 + 0.05 * math.sin(0.35 * t), 0.36, np.array([0.62, 0.86, 1.0], np.float32), 0.45),
        (0.70 + 0.06 * math.sin(0.3 * t + 1), 0.12, 0.22, np.array([1.0, 0.86, 0.5], np.float32), 0.32),
    ]:
        b = blob(cx, cy, r) * a
        g = g * (1 - b) + col * b
    img = cv2.resize(g, (W, H), interpolation=cv2.INTER_CUBIC)
    return img * (1 - DOTS) + BLUE2 * DOTS


def leaks(t, strength):
    g = np.zeros((135, 240, 3), np.float32)
    for (cx, cy, r, col) in [
        (0.1 + 0.25 * math.sin(0.7 * t), 0.15 + 0.1 * math.cos(0.5 * t), 0.28, np.array([1.0, 0.85, 0.5], np.float32)),
        (0.9 - 0.2 * math.sin(0.6 * t + 2), 0.8, 0.32, np.array([0.55, 0.8, 1.0], np.float32)),
        (0.55 + 0.3 * math.cos(0.4 * t), 0.05, 0.2, np.array([1.0, 0.95, 0.85], np.float32)),
    ]:
        g += blob(cx, cy, r) * col
    return cv2.resize(g, (W, H), interpolation=cv2.INTER_LINEAR) * strength


def screen(img, light):
    return 1 - (1 - img) * (1 - np.clip(light, 0, 1))


HX, HY = np.meshgrid(np.arange(960, dtype=np.float32), np.arange(540, dtype=np.float32))


def flare(cx, cy, I, streak=1.0, rays=0.0, ghosts=True, tint=(0.55, 0.78, 1.0)):
    """镜头炫光（半分辨率计算后放大）：核心、辉光、横向光条、星芒、鬼影。"""
    cx2, cy2 = cx / 2, cy / 2
    dx, dy = HX - cx2, HY - cy2
    r2 = dx * dx + dy * dy
    r = np.sqrt(r2)
    out = np.exp(-r2 / (2 * 16 ** 2))[..., None] * np.array([1.0, 1.0, 1.0], np.float32)
    out += np.exp(-r / 120)[..., None] * np.array([1.0, 0.93, 0.8], np.float32) * 0.5
    st = np.exp(-(dy * dy) / (2 * 2.6 ** 2)) * np.exp(-np.abs(dx) / 520)
    st += np.exp(-(dy * dy) / (2 * 14 ** 2)) * np.exp(-np.abs(dx) / 300) * 0.25
    out += st[..., None] * np.array(tint, np.float32) * streak
    if rays > 0:
        th = np.arctan2(dy, dx)
        ray = np.abs(np.cos(th * 4)) ** 40 + 0.6 * np.abs(np.cos(th * 4 + 0.39)) ** 60
        out += (ray * np.exp(-r / 230))[..., None] * np.array([1.0, 0.95, 0.85], np.float32) * rays * 0.7
    if ghosts:
        vx, vy = 480 - cx2, 270 - cy2
        for k, rad, col, a in [(0.55, 34, (0.6, 0.85, 1.0), 0.16), (1.25, 18, (1.0, 0.85, 0.5), 0.22),
                               (1.6, 60, (0.7, 0.6, 1.0), 0.09), (2.1, 26, (0.5, 1.0, 0.9), 0.14)]:
            gx, gy = cx2 + vx * k, cy2 + vy * k
            d = np.sqrt((HX - gx) ** 2 + (HY - gy) ** 2)
            ring = np.clip((rad - d) / 6, 0, 1) * (0.55 + 0.45 * np.clip(d / rad, 0, 1) ** 4)
            out += ring[..., None] * np.array(col, np.float32) * a
    return cv2.resize(out * I, (W, H), interpolation=cv2.INTER_LINEAR)


def chroma(img, amt):
    if amt < 4e-4:
        return img
    out = img.copy()
    for ch, s in ((0, 1 + amt), (2, 1 - amt)):
        m = np.array([[s, 0, (1 - s) * W / 2], [0, s, (1 - s) * H / 2]], np.float32)
        out[..., ch] = cv2.warpAffine(np.ascontiguousarray(img[..., ch]), m, (W, H), flags=cv2.INTER_LINEAR,
                                      borderMode=cv2.BORDER_REFLECT)
    return out


# ── 粒子渲染 ──────────────────────────────────────────────
def splat(img, x, y, col, a, sigma, gain=1.0, half=False):
    """把粒子按透明度混合进画面。half=True 时在半分辨率上画大颗柔光点。"""
    if len(x) == 0:
        return img
    s = 0.5 if half else 1.0
    w, h = int(W * s), int(H * s)
    acc = np.zeros((h, w, 4), np.float32)
    xs, ys = x * s, y * s
    x0, y0 = np.floor(xs).astype(np.int64), np.floor(ys).astype(np.int64)
    fx, fy = (xs - x0).astype(np.float32), (ys - y0).astype(np.float32)
    vals = np.concatenate([col * a[:, None], a[:, None]], 1).astype(np.float32)
    for dx, dy, wt in ((0, 0, (1 - fx) * (1 - fy)), (1, 0, fx * (1 - fy)), (0, 1, (1 - fx) * fy), (1, 1, fx * fy)):
        xi, yi = x0 + dx, y0 + dy
        m = (xi >= 0) & (xi < w) & (yi >= 0) & (yi < h)
        np.add.at(acc, (yi[m], xi[m]), vals[m] * wt[m, None])
    acc = cv2.GaussianBlur(acc, (0, 0), sigma) * (2 * math.pi * sigma * sigma * gain)
    if half:
        acc = cv2.resize(acc, (W, H), interpolation=cv2.INTER_LINEAR)
    A = acc[..., 3:4]
    over = np.maximum(A, 1.0)
    return img * (1 - np.minimum(A, 1.0)) + acc[..., :3] / over


def palette(rng, n, weights):
    cols = np.array([c for c, _ in weights], np.float32)
    p = np.array([w for _, w in weights], np.float64)
    return cols[rng.choice(len(cols), n, p=p / p.sum())]


class Intro:
    """粒子旋转汇聚成「08」，1.98s 向外炸开。"""

    def __init__(self, glyph_png):
        rng = np.random.default_rng(80)
        g = cv2.imread(str(glyph_png), 0)
        m = (g > 128).astype(np.uint8)
        edge = cv2.morphologyEx(m, cv2.MORPH_GRADIENT, np.ones((3, 3), np.uint8))
        ey, ex = np.nonzero(edge)
        iy, ix = np.nonzero(cv2.erode(m, np.ones((9, 9), np.uint8)))
        ne, ni = 2600, 1800
        a = rng.choice(len(ex), ne)
        b = rng.choice(len(ix), ni)
        self.T = np.concatenate([np.stack([ex[a], ey[a]], 1), np.stack([ix[b], iy[b]], 1)]).astype(np.float32)
        self.T += rng.normal(0, 0.6, self.T.shape)
        n = len(self.T)
        self.c = np.array([960, 560], np.float32)
        r0 = 280 + 1050 * rng.random(n) ** 0.6
        th = rng.random(n) * 2 * np.pi
        self.S = self.c + np.stack([np.cos(th) * r0, np.sin(th) * r0 * 0.6], 1)
        self.delay = rng.random(n) * 0.28
        self.spin = 2.0 + rng.random(n) * 1.4
        self.col = palette(rng, n, [(BLUE2, 45), (BLUE, 25), (CYAN, 18), (YELLOW, 12)])
        self.big = rng.random(n) < 0.22
        self.tw = rng.random(n) * 6.28
        d = self.T - self.c
        d /= np.linalg.norm(d, axis=1, keepdims=True) + 1e-6
        self.dir = d + rng.normal(0, 0.35, d.shape)
        self.vel = 500 + rng.random(n) * 1900

    def draw(self, img, t):
        if t > 3.1:
            return img
        p = np.clip((t - 0.12 - self.delay) / 1.0, 0, 1)
        p = np.where(p < 0.5, 4 * p ** 3, 1 - (-2 * p + 2) ** 3 / 2)[:, None]
        ang = 0.5 * t
        ca, sa = math.cos(ang), math.sin(ang)
        S = self.S - self.c
        S = self.c + np.stack([S[:, 0] * ca - S[:, 1] * sa, S[:, 0] * sa + S[:, 1] * ca], 1)
        off = S - self.T
        phi = (1 - p[:, 0]) * self.spin
        cph, sph = np.cos(phi), np.sin(phi)
        off = np.stack([off[:, 0] * cph - off[:, 1] * sph, off[:, 0] * sph + off[:, 1] * cph], 1) * (1 - p)
        pos = self.T + off
        alpha = np.full(len(pos), clamp(t / 0.35) * 0.9, np.float32)
        alpha *= np.where(t > 1.25, 0.55 + 0.35 * np.sin(9 * t + self.tw), 1.0).astype(np.float32)
        tb = 1.98
        if t > tb:
            a = t - tb
            pos = self.T + self.dir * (self.vel * (1 - math.exp(-2.6 * a)) / 2.6)[:, None]
            alpha *= max(0.0, 1 - a / 1.1) ** 1.6
        trail = []
        if t < 1.3:   # 汇聚途中画 3 个历史位置作拖尾
            for k, dt in enumerate((0.035, 0.07, 0.105)):
                trail.append((self._pos(t - dt), alpha * (0.45 - 0.12 * k)))
        for P, al in trail + [(pos, alpha)]:
            for big, sig in ((False, 1.35), (True, 2.6)):
                m = self.big == big
                img = splat(img, P[m, 0], P[m, 1], self.col[m], al[m] * (0.85 if big else 1.0), sig, gain=1.25)
        return img

    def _pos(self, t):
        p = np.clip((t - 0.12 - self.delay) / 1.0, 0, 1)
        p = np.where(p < 0.5, 4 * p ** 3, 1 - (-2 * p + 2) ** 3 / 2)[:, None]
        ang = 0.5 * t
        ca, sa = math.cos(ang), math.sin(ang)
        S = self.S - self.c
        S = self.c + np.stack([S[:, 0] * ca - S[:, 1] * sa, S[:, 0] * sa + S[:, 1] * ca], 1)
        off = S - self.T
        phi = (1 - p[:, 0]) * self.spin
        cph, sph = np.cos(phi), np.sin(phi)
        off = np.stack([off[:, 0] * cph - off[:, 1] * sph, off[:, 0] * sph + off[:, 1] * cph], 1) * (1 - p)
        return self.T + off


class Dust:
    """全程漂浮的柔光颗粒。"""

    def __init__(self):
        rng = np.random.default_rng(81)
        n = 170
        self.x0, self.y0 = rng.random(n) * W, rng.random(n) * (H + 200)
        self.v = 20 + rng.random(n) * 60
        self.ph = rng.random(n) * 6.28
        self.amp = 10 + rng.random(n) * 30
        self.col = palette(rng, n, [(WHITE, 50), (CYAN, 25), (YELLOW, 25)])
        self.a = 0.18 + rng.random(n) * 0.25

    def draw(self, img, t, strength):
        if strength <= 0.01:
            return img
        y = (self.y0 - self.v * t) % (H + 200) - 100
        x = self.x0 + self.amp * np.sin(0.6 * t + self.ph)
        tw = 0.6 + 0.4 * np.sin(2.3 * t + self.ph * 3)
        return splat(img, x, y, self.col, self.a * tw * strength, 3.0, half=True)


class Sparks:
    """中心爆闪的火花：从 (cx, cy) 向外喷射并减速。"""

    def __init__(self, seed, n=420):
        rng = np.random.default_rng(seed)
        th = rng.random(n) * 6.28
        self.d = np.stack([np.cos(th), np.sin(th) * 0.75], 1)
        self.v = 400 + rng.random(n) ** 0.7 * 2200
        self.life = 0.5 + rng.random(n) * 0.6
        self.col = palette(rng, n, [(WHITE, 55), (YELLOW, 30), (CYAN, 15)])

    def draw(self, img, t, t0, cx, cy):
        a = t - t0
        if a <= 0 or a > 1.2:
            return img
        dist = self.v * (1 - np.exp(-3.2 * a)) / 3.2
        pos = np.array([cx, cy], np.float32) + self.d * dist[:, None]
        alpha = np.clip(1 - a / self.life, 0, 1) ** 1.3 * 0.95
        return splat(img, pos[:, 0], pos[:, 1], self.col, alpha, 1.3)


# ── 3D 拼贴墙 ─────────────────────────────────────────────
G = 40.0
BW, BH = 1600.0, 900.0
SH = (BH - G) / 2
SW = SH * 16 / 9
HALF = (BW + G + 2 * SW + G) / 2
FOCUS_TZ = F * BW / W


def layout(mirror):
    """返回 [(x0, y0, x1, y1)]：第 0 个是大画面，其余是 2×2 小画面（左上、右上、左下、右下）。"""
    bx0 = -HALF
    big = (bx0, -BH / 2, bx0 + BW, BH / 2)
    sx0 = bx0 + BW + G
    small = [(sx0, -BH / 2, sx0 + SW, -BH / 2 + SH), (sx0 + SW + G, -BH / 2, sx0 + 2 * SW + G, -BH / 2 + SH),
             (sx0, BH / 2 - SH, sx0 + SW, BH / 2), (sx0 + SW + G, BH / 2 - SH, sx0 + 2 * SW + G, BH / 2)]
    rects = [big] + small
    if mirror:
        rects = [(-x1, y0, -x0, y1) for (x0, y0, x1, y1) in rects]
        rects = [rects[0], rects[2], rects[1], rects[4], rects[3]]
    return rects


RECTS_IN, RECTS_OUT = layout(False), layout(True)
ORDER_IN = [0, 1, 2, 3, 4]    # 大画面 = 第 1 段
ORDER_OUT = [4, 0, 1, 2, 3]   # 大画面 = 第 5 段


def project(px, py, cam):
    rx, ry, tx, ty, tz = cam
    y1, z1 = py * np.cos(rx), py * np.sin(rx)
    x2 = px * np.cos(ry) + z1 * np.sin(ry)
    z2 = -px * np.sin(ry) + z1 * np.cos(ry)
    X, Y, Z = x2 + tx, y1 + ty, z2 + tz
    return F * X / Z + W / 2, F * Y / Z + H / 2, Z


def lerp_cam(a, b, p):
    return tuple(a[i] + (b[i] - a[i]) * p for i in range(4)) + (a[4] * (b[4] / a[4]) ** p,)


def cam_in(t):
    d = prog(t, 2.0, 3.6)
    wall = (0.16, -0.40 + 0.07 * d, 250.0, 20.0, 3450.0 - 300 * d)
    focus = (0.0, 0.0, HALF - BW / 2, 0.0, FOCUS_TZ)
    return lerp_cam(wall, focus, ease_io(prog(t, 3.3, 4.0)))


def cam_out(t):
    d = prog(t, 14.6, 16.6)
    wall = (-0.12, 0.38 - 0.07 * d, -250.0, -10.0, 3400.0 - 260 * d)
    focus = (0.0, 0.0, -(HALF - BW / 2), 0.0, FOCUS_TZ)
    return lerp_cam(focus, wall, ease_io(prog(t, 14.0, 14.75)))


_masks = {}


def rrect(cw, ch, r):
    key = (cw, ch, int(round(r)))
    if key not in _masks:
        if key[2] < 1:
            m = np.ones((ch, cw), np.float32)
        else:
            rr = key[2]
            yy, xx = np.mgrid[0:ch, 0:cw].astype(np.float32) + 0.5
            qx = np.maximum(np.abs(xx - cw / 2) - (cw / 2 - rr), 0)
            qy = np.maximum(np.abs(yy - ch / 2) - (ch / 2 - rr), 0)
            m = np.clip(rr + 0.5 - np.sqrt(qx * qx + qy * qy), 0, 1).astype(np.float32)
        _masks[key] = m
    return _masks[key]


def warp_onto(img, rgb, alpha, quad):
    """把 (rgb, alpha) 透视贴到画面上的四边形 quad，只在包围盒内计算。"""
    h, w = alpha.shape
    x0, y0 = np.floor(quad.min(0)).astype(int)
    x1, y1 = np.ceil(quad.max(0)).astype(int)
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
    if x1 - x0 < 2 or y1 - y0 < 2:
        return img
    src = np.array([[0, 0], [w, 0], [w, h], [0, h]], np.float32)
    M = cv2.getPerspectiveTransform(src, (quad - [x0, y0]).astype(np.float32))
    rgba = np.dstack([rgb * alpha[..., None], alpha])
    out = cv2.warpPerspective(rgba, M, (x1 - x0, y1 - y0), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)
    sl = img[y0:y1, x0:x1]
    img[y0:y1, x0:x1] = sl * (1 - out[..., 3:4]) + out[..., :3]
    return img


def noise_tex(seed, w, h):
    rng = np.random.default_rng(seed)
    n = np.zeros((h, w), np.float32)
    for s, a in ((10, 1.0), (24, 0.5), (60, 0.22)):
        g = rng.random((max(2, int(s * h / w)), s)).astype(np.float32)
        n += cv2.resize(g, (w, h), interpolation=cv2.INTER_CUBIC) * a
    n = (n - n.min()) / (n.max() - n.min())
    return n


class Wall:
    def __init__(self, footage):
        self.f = footage
        self.noise = {}
        self.dp = {}

    # ── 进场墙 2–4s ──
    def draw_in(self, img, t):
        cam = cam_in(t)
        p_focus = ease_io(prog(t, 3.3, 4.0))
        panels = []
        for slot, k in enumerate(ORDER_IN):
            t0 = 2.02 + 0.1 * slot
            pp = prog(t, t0, t0 + 0.55)
            if pp <= 0:
                continue
            s = 0.78 + 0.22 * out_back(pp)
            a = clamp(pp * 2.5)
            r = 30 * (1 - p_focus) if slot == 0 else 30
            src_t = WALL_IN_SRC[k] + (t - 2.0)
            panels.append((slot, k, RECTS_IN[slot], s, a, r, src_t, None, pp))
        return self._draw(img, cam, panels, t)

    # ── 收尾墙 14–16.6s：燃烧化为粒子 ──
    def dissolve_t0(self, slot):
        return 15.55 if slot == 0 else 14.95 + 0.13 * (slot - 1)

    def draw_out(self, img, t):
        cam = cam_out(t)
        p_back = ease_io(prog(t, 14.0, 14.75))
        panels = []
        for slot, k in enumerate(ORDER_OUT):
            d0 = self.dissolve_t0(slot)
            if t > d0 + 1.05:
                continue
            r = 30 * p_back if slot == 0 else 30
            src_t = WALL_OUT_SRC[k] + (t - 14.0)
            panels.append((slot, k, RECTS_OUT[slot], 1.0, 1.0, r, src_t, d0, 1.0))
        img = self._draw(img, cam, panels, t)
        return self.particles(img, t)

    def content(self, slot, k, src_t, outro):
        big = slot == 0
        res = (W, H) if big else (960, 540)
        fr = self.f.clips[k].at(src_t)
        if outro and big:
            fx, fy = SEG_FOCUS[4]
            fr = crop_zoom(fr, SEG_ZOOM[4][1], fx, fy)
        if not big:
            fr = cv2.resize(fr, res, interpolation=cv2.INTER_AREA)
        return grade(fr)

    def _draw(self, img, cam, panels, t):
        if not panels:
            return img
        quads, depth = [], []
        for (slot, k, (x0, y0, x1, y1), s, a, r, src_t, d0, pp) in panels:
            cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
            px = np.array([x0, x1, x1, x0], np.float32)
            py = np.array([y0, y0, y1, y1], np.float32)
            px, py = cx + (px - cx) * s, cy + (py - cy) * s
            u, v, Z = project(px, py, cam)
            quads.append(np.stack([u, v], 1))
            depth.append(Z.mean())
        # 柔和投影
        sh = np.zeros((270, 480), np.float32)
        for q, pnl in zip(quads, panels):
            d0 = pnl[7]
            k = 1.0 if d0 is None else (1 - prog(t, d0 - 0.1, d0 + 0.5)) ** 2   # 化为粒子时投影随之消失
            cv2.fillConvexPoly(sh, ((q + [0, 26]) / 4).astype(np.int32), float(pnl[4]) * k)
        sh = cv2.GaussianBlur(sh, (0, 0), 9)
        sh = cv2.resize(sh, (W, H))[..., None]
        img = img * (1 - sh * np.array([0.2, 0.17, 0.09], np.float32))
        outro = panels[0][7] is not None
        for i in np.argsort(depth)[::-1]:
            slot, k, rect, s, a, r, src_t, d0, pp = panels[i]
            rgb = self.content(slot, k, src_t, outro)
            h, w = rgb.shape[:2]
            alpha = rrect(w, h, r * w / (rect[2] - rect[0])) * a
            if pp < 1:   # 弹入时的高光扫过
                yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
                band = np.exp(-(((xx / w) * 0.75 + (yy / h) * 0.25 - (-0.2 + 1.5 * pp)) / 0.07) ** 2)
                rgb = screen(rgb, band[..., None] * 0.55)
            if d0 is not None:
                rgb, alpha = self.burn(slot, rgb, alpha, t, d0)
            img = warp_onto(img, rgb, alpha, quads[i])
        return img

    def burn(self, slot, rgb, alpha, t, d0):
        h, w = alpha.shape
        if slot not in self.noise:
            self.noise[slot] = noise_tex(90 + slot, w, h)
        n = self.noise[slot]
        d = -0.08 + 1.16 * (t - d0) / 1.0
        if d <= -0.08:
            return rgb, alpha
        vis = np.clip((n - d) / 0.025, 0, 1)
        g = np.exp(-((n - d) / 0.03) ** 2)[..., None]
        rgb = screen(rgb, g * (GOLD * 1.1) + g ** 3 * 0.8)
        return rgb, alpha * np.maximum(vis, g[..., 0] * 0.95)

    def particles(self, img, t):
        for slot, k in enumerate(ORDER_OUT):
            d0 = self.dissolve_t0(slot)
            if t < d0 - 0.1 or t > d0 + 3.0:
                continue
            if slot not in self.dp:
                self.dp[slot] = self._make_particles(slot, k, d0)
            P = self.dp[slot]
            a = t - P["t"]
            m = (a > 0) & (a < P["life"])
            if not m.any():
                continue
            a = a[m]
            x = P["sx"][m] + P["vx"][m] * a + 16 * np.sin(2.2 * a + P["ph"][m])
            y = P["sy"][m] + P["vy"][m] * a - 90 * a * a + 10 * np.cos(1.7 * a + P["ph"][m])
            al = (1 - a / P["life"][m]) ** 1.3 * 0.95
            if t > 16.3:
                al *= max(0.0, 1 - (t - 16.3) / 0.9)
            big = P["big"][m]
            for b, sig in ((False, 1.0), (True, 1.9)):
                mm = big == b
                img = splat(img, x[mm], y[mm], P["col"][m][mm], al[mm], sig)
        return img

    def _make_particles(self, slot, k, d0):
        rng = np.random.default_rng(200 + slot)
        n = 2600 if slot == 0 else 1300
        u, v = rng.random(n), rng.random(n)
        w, h = (W, H) if slot == 0 else (960, 540)
        if slot not in self.noise:
            self.noise[slot] = noise_tex(90 + slot, w, h)
        nv = self.noise[slot][(v * (h - 1)).astype(int), (u * (w - 1)).astype(int)]
        tr = d0 + (nv + 0.08) / 1.16
        x0, y0, x1, y1 = RECTS_OUT[slot]
        px, py = x0 + u * (x1 - x0), y0 + v * (y1 - y0)
        sx, sy = np.zeros(n), np.zeros(n)
        for i, ti in enumerate(tr):
            cam = cam_out(float(ti))
            u_, v_, _ = project(np.array([px[i]]), np.array([py[i]]), cam)
            sx[i], sy[i] = u_[0], v_[0]
        fr = self.content(slot, k, WALL_OUT_SRC[k] + (d0 - 14.0), True)
        hh, ww = fr.shape[:2]
        col = fr[(v * (hh - 1)).astype(int), (u * (ww - 1)).astype(int)] * 0.72 + 0.28
        accent = rng.random(n)
        col[accent < 0.16] = YELLOW
        col[(accent >= 0.16) & (accent < 0.26)] = CYAN
        out_dir = np.sign(sx - W / 2)
        return dict(t=tr, sx=sx, sy=sy, vx=rng.normal(0, 70, n) + out_dir * rng.random(n) * 60,
                    vy=-(50 + rng.random(n) * 180), life=1.0 + rng.random(n) * 0.9, ph=rng.random(n) * 6.28,
                    col=col.astype(np.float32), big=rng.random(n) < 0.3)


# ── 正片五段 ──────────────────────────────────────────────
YY, XX = np.mgrid[0:H, 0:W].astype(np.float32)
DIAG = (XX / W) * 0.7 + (YY / H) * 0.3


class Footage:
    def __init__(self, src):
        self.clips = [Clip(pathlib.Path(src) / f"{c}.mp4") for c in CLIPS]

    def beat(self, t):
        if t < 4.0 or t >= 14.0:
            return 0.0
        k = math.floor((t - 4.0) / 0.5)
        return 0.0 if k % 2 == 0 else 0.02 * math.exp(-(t - (4.0 + k * 0.5)) / 0.11)

    def view(self, k, t, extra=1.0):
        s0 = SEG0 + SEGLEN * k
        p = ease_io(prog(t, s0, s0 + SEGLEN))
        z0, z1 = SEG_ZOOM[k]
        fx, fy = SEG_FOCUS[k]
        z = (z0 + (z1 - z0) * p) * (1 + self.beat(t))
        img = self.clips[k].at(SEG_TIN[k] + (t - s0) * SPEED)
        return crop_zoom(img, z, 0.5 + (fx - 0.5) * p, 0.5 + (fy - 0.5) * p, extra)

    def segment(self, t):
        k = int(clamp((t - SEG0) // SEGLEN, 0, 4))
        for b, kind in CUTS:
            if kind == "leak" and b - 0.36 <= t < b + 0.36:
                a, c = self.view(int((b - SEG0) // SEGLEN) - 1, t), self.view(int((b - SEG0) // SEGLEN), t)
                u = -0.3 + 1.6 * ease_io(prog(t, b - 0.36, b + 0.36))
                m = np.clip((u - DIAG) / 0.1 + 0.5, 0, 1)[..., None]
                return a * (1 - m) + c * m
            if b - 0.3 <= t < b:
                return self.view(k, t, 1 + 0.07 * ease_in(prog(t, b - 0.3, b)))
            if b <= t < b + 0.4:
                return self.view(k, t, 1 + 0.09 * (1 - ease_out(prog(t, b, b + 0.4))))
        return self.view(k, t)


# ── 特效时间表 ────────────────────────────────────────────
def effects(t):
    fl, white, chrom, leak = [], 0.0, 0.0, 0.0
    if 1.3 < t < 1.95:   # 光线划过「08」
        p = prog(t, 1.3, 1.95)
        fl.append((W * (0.18 + 0.64 * ease_io(p)), 560, 0.8 * math.sin(math.pi * p), dict(streak=1.6, rays=0.2, ghosts=False)))
    b = bell(t, 1.98, 0.11)
    if b > 0.01:
        fl.append((960, 560, 2.4 * b, dict(streak=2.2, rays=1.1)))
        white = max(white, 0.96 * bell(t, 1.99, 0.075))
        chrom = max(chrom, 0.008 * b)
    b = bell(t, 4.0, 0.12)
    if b > 0.01:
        fl.append((W * (0.6 + 0.3 * prog(t, 3.7, 4.3)), H * 0.22, 1.0 * b, dict(streak=1.8, rays=0.4)))
        white = max(white, 0.32 * bell(t, 4.0, 0.06))
    for c, kind in CUTS:
        if abs(t - c) > 0.45:
            continue
        b = bell(t, c, 0.17)
        if kind == "sweepL":
            p = prog(t, c - 0.36, c + 0.36)
            fl.append((W * (-0.2 + 1.4 * ease_io(p)), H * 0.4, 1.6 * b, dict(streak=2.0, rays=0.3)))
            white = max(white, 0.82 * bell(t, c, 0.065))
            chrom = max(chrom, 0.006 * b)
        elif kind == "burst":
            fl.append((W / 2, H * 0.46, 2.0 * b, dict(streak=1.6, rays=1.3)))
            white = max(white, 0.86 * bell(t, c, 0.06))
            chrom = max(chrom, 0.007 * b)
        elif kind == "leak":
            u = -0.3 + 1.6 * ease_io(prog(t, c - 0.36, c + 0.36))
            fl.append((W * clamp((u - 0.3 * 0.4) / 0.7, -0.2, 1.2), H * 0.4, 1.3 * b, dict(streak=1.8, rays=0.5, tint=(1.0, 0.8, 0.5))))
            white = max(white, 0.35 * bell(t, c, 0.08))
            leak = max(leak, 1.0 * b)
        elif kind == "sweepR":
            p = prog(t, c - 0.36, c + 0.36)
            fl.append((W * (1.2 - 1.4 * ease_io(p)), H * 0.58, 1.6 * b, dict(streak=2.0, rays=0.3, tint=(0.7, 0.75, 1.0))))
            white = max(white, 0.8 * bell(t, c, 0.065))
            chrom = max(chrom, 0.012 * b)
    b = bell(t, 14.0, 0.12)
    if b > 0.01:
        fl.append((W * 0.3, H * 0.3, 1.0 * b, dict(streak=1.8, rays=0.4)))
        white = max(white, 0.3 * bell(t, 14.0, 0.06))
    if 16.1 < t < 17.0:  # 光线划过落款
        p = prog(t, 16.1, 17.0)
        fl.append((W * (0.15 + 0.7 * ease_io(p)), 400, 0.55 * math.sin(math.pi * p), dict(streak=1.5, rays=0.15, ghosts=False)))
    return fl, white, chrom, leak


# ── 逐帧 ─────────────────────────────────────────────────
class Renderer:
    def __init__(self, src, frames):
        global DOTS
        DOTS = make_dots()
        self.frames = pathlib.Path(frames)
        self.foot = Footage(src)
        self.wall = Wall(self.foot)
        self.intro = Intro(self.frames / "glyph.png")
        self.dust = Dust()
        self.sparks = Sparks(82)
        self.grain = [np.random.default_rng(300 + i).normal(0, 0.0045, (H, W, 1)).astype(np.float32) for i in range(6)]

    def load(self, sub, f, gray=False):
        p = self.frames / sub / f"{f:04d}.png"
        if not p.exists():
            return None
        return cv2.imread(str(p), cv2.IMREAD_GRAYSCALE if gray else cv2.IMREAD_UNCHANGED)

    def frame(self, f):
        t = f / FPS
        if t < 2.0:
            img = self.intro.draw(background(t), t)
            dust_k = 0.6
        elif t < 4.0:
            img = self.wall.draw_in(background(t), t)
            img = self.intro.draw(img, t)
            dust_k = 1.0
        elif t < 14.0:
            img = bloom(grade(self.foot.segment(t)))
            img = screen(img, leaks(t, 0.14))
            img = self.sparks.draw(img, t, 8.0, W / 2, H * 0.46)
            dust_k = 0.9
        else:
            img = self.wall.draw_out(background(t), t)
            dust_k = 1.0
        img = self.dust.draw(img, t, dust_k)

        fl, white, chrom, leak = effects(t)
        if leak > 0.01:
            u = -0.3 + 1.6 * ease_io(prog(t, 9.64, 10.36))
            band = np.exp(-((DIAG - u) / 0.09) ** 2)[..., None]
            band2 = np.exp(-((DIAG - u + 0.12) / 0.06) ** 2)[..., None]
            img = screen(img, (band * (YELLOW * 0.65 + 0.35) + band2 * CYAN * 0.6) * leak)
        for (cx, cy, I, kw) in fl:
            if I > 0.01:
                img = screen(img, flare(cx, cy, I, **kw))
        img = chroma(img, chrom)
        if white > 0.003:
            img = img * (1 - white) + FLASH * white

        gl = self.load("gl", f, gray=True)
        if gl is not None and gl.max() > 0:
            m = (gl.astype(np.float32) / 255)[..., None]
            s = cv2.GaussianBlur(cv2.resize(img, (480, 270), interpolation=cv2.INTER_AREA), (0, 0), 7)
            frost = cv2.resize(s, (W, H)) * 0.32 + np.array([0.98, 0.988, 1.0], np.float32) * 0.68
            img = img * (1 - m) + frost * m
        ov = self.load("ov", f)
        if ov is not None:
            a = ov[..., 3:4].astype(np.float32) / 255
            rgb = cv2.cvtColor(ov[..., :3], cv2.COLOR_BGR2RGB).astype(np.float32) / 255
            img = img * (1 - a) + rgb * a
        img = img + self.grain[f % 6]
        return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def encode_range(args, a, b, out):
    r = Renderer(args.src, args.frames)
    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
           "-c:v", "libx264", "-preset", "medium", "-crf", "10", out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(a, b):
        proc.stdin.write(r.frame(f).tobytes())
        if (f - a) % 30 == 0:
            print(f"  [{a}-{b}] {f}", flush=True)
    proc.stdin.close()
    proc.wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("frames")
    ap.add_argument("music")
    ap.add_argument("out")
    ap.add_argument("--frames", dest="only", default=None)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--range", default=None)
    args = ap.parse_args()

    if args.only:
        r = Renderer(args.src, args.frames)
        out = pathlib.Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for f in map(int, args.only.split(",")):
            cv2.imwrite(str(out / f"{f:04d}.jpg"), cv2.cvtColor(r.frame(f), cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
        return
    if args.range:
        a, b = map(int, args.range.split(":"))
        encode_range(args, a, b, args.out)
        return

    out = pathlib.Path(args.out)
    tmp = out.parent / (out.stem + "_parts")
    tmp.mkdir(exist_ok=True)
    n = args.workers
    bounds = [round(TOTAL * i / n) for i in range(n + 1)]
    procs, parts = [], []
    for i in range(n):
        part = tmp / f"part{i}.mp4"
        parts.append(part)
        procs.append(subprocess.Popen([sys.executable, "-I", __file__, args.src, args.frames, args.music, str(part),
                                       "--range", f"{bounds[i]}:{bounds[i + 1]}"]))
    if any(p.wait() for p in procs):
        raise SystemExit("渲染进程失败")
    lst = tmp / "list.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in parts))
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "concat", "-safe", "0", "-i", str(lst), "-i", args.music,
                    "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high", "-level", "4.1",
                    "-pix_fmt", "yuv420p", "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(out)], check=True)
    print("done", out)


if __name__ == "__main__":
    main()
