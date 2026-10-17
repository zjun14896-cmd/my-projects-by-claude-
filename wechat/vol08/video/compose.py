#!/usr/bin/env python3
"""第 8 期 15 秒短片合成：现场素材 + 图形层 + 配乐 → 1920×1080 / 30fps / H.264。

时间线（与 music.py 的 120 BPM 节拍对齐）：
  0.00–2.00  片头：午夜蓝底，「08」描边 → 字形里透出第一段画面 → 镜头推进穿过字形
  2.00–12.0  五段现场，每段 2 秒（一小节）：缓慢推镜 + 二四拍轻微冲击缩放
             切换点 4/6/8/10s 依次用：缩放模糊、横向甩镜、斜向光扫、纵向甩镜
  12.0–15.0  片尾：最后一段放慢、虚化、压暗，文字与 logo 出现
用法：python3 -I compose.py <素材目录 sdr/> <图形帧目录 frames/> <music.wav> <输出.mp4> [--frames 0,60,...]
"""
import argparse
import math
import pathlib
import subprocess

import cv2
import numpy as np

W, H, FPS, TOTAL = 1920, 1080, 30, 450
NIGHT = np.array([5, 10, 24], np.float32) / 255
BLUE = np.array([0, 60, 172], np.float32) / 255
GLOW = np.array([0.75, 0.86, 1.0], np.float32)

# (素材, 入点秒, 焦点 x/y, 起止缩放)
SEG = [
    ("s1", 0.0, (0.55, 0.42), (1.04, 1.16)),
    ("s2", 0.3, (0.58, 0.40), (1.06, 1.18)),
    ("s3", 0.3, (0.47, 0.40), (1.06, 1.20)),
    ("s4", 0.3, (0.62, 0.34), (1.10, 1.32)),
    ("s5", 0.3, (0.56, 0.38), (1.06, 1.18)),
]
SPEED = 1.25
TRANS = {4.0: "zoom", 6.0: "whip_h", 8.0: "sweep", 10.0: "whip_v"}
HALF = 0.2  # 转场半长


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


class Clip:
    """顺序读取 + 小缓存；支持相邻两帧混合（慢放更顺滑）。"""

    def __init__(self, path):
        self.cap = cv2.VideoCapture(str(path))
        self.n = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.cache, self.pos = {}, 0

    def frame(self, i):
        i = int(clamp(i, 0, self.n - 1))
        if i in self.cache:
            return self.cache[i]
        if i < self.pos:
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
        for k in [k for k in self.cache if k < i - 6]:
            del self.cache[k]
        return self.cache[i]

    def at(self, sec):
        x = sec * FPS
        a = int(math.floor(x))
        f = x - a
        fa = self.frame(a).astype(np.float32)
        if f < 0.05:
            return fa / 255
        fb = self.frame(a + 1).astype(np.float32)
        return (fa * (1 - f) + fb * f) / 255


def crop_zoom(img, z, cx, cy, dx=0.0, dy=0.0):
    """以 (cx, cy)（0–1）为中心放大 z 倍，再平移 (dx, dy) 像素。"""
    cw, ch = W / z, H / z
    x0 = clamp(cx * W - cw / 2, 0, W - cw)
    y0 = clamp(cy * H - ch / 2, 0, H - ch)
    m = np.array([[z, 0, -x0 * z + dx], [0, z, -y0 * z + dy]], np.float32)
    return cv2.warpAffine(img, m, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)


def zoom_blur(img, z, cx, cy, amount):
    if amount < 0.004:
        return crop_zoom(img, z, cx, cy)
    acc = np.zeros_like(img)
    k = 7
    for i in range(k):
        acc += crop_zoom(img, z * (1 + amount * i / (k - 1)), cx, cy)
    return acc / k


def dir_blur(img, px, horizontal=True):
    px = int(px)
    if px < 3:
        return img
    ksize = (px, 1) if horizontal else (1, px)
    return cv2.blur(img, ksize)


def beat_pulse(t):
    """二、四拍（拍手）时画面轻微冲击放大。"""
    if t < 2.0 or t >= 12.0:
        return 0.0
    k = math.floor((t - 2.0) / 0.5)
    tb = 2.0 + k * 0.5
    if k % 2 == 0:
        return 0.0
    return 0.022 * math.exp(-(t - tb) / 0.11)


class Footage:
    def __init__(self, src):
        self.clips = [Clip(pathlib.Path(src) / f"{name}.mp4") for name, *_ in SEG]

    def src_time(self, k, t):
        name, tin, *_ = SEG[k]
        if k == 0:
            return (t - 0.85) if t < 2.0 else 1.15 + (t - 2.0) * SPEED
        s0 = 2.0 + 2 * k
        base = tin + (t - s0) * SPEED
        if k == 4 and t > 12.0:
            return tin + 2.0 * SPEED + (t - 12.0) * 0.35
        return base

    def seg_view(self, k, t, extra_zoom=1.0, dx=0.0, dy=0.0, blur=0.0):
        _, _, (fx, fy), (z0, z1) = SEG[k]
        s0 = 0.85 if k == 0 else 2.0 + 2 * k
        s1 = 4.0 + 2 * k if k < 4 else 15.0
        p = ease_io(prog(t, s0, s1 if k < 4 else 12.0))
        z = (z0 + (z1 - z0) * p) * (1 + beat_pulse(t))
        if k == 4 and t > 12.0:
            z *= 1 + 0.05 * prog(t, 12.0, 15.0)
        cx = 0.5 + (fx - 0.5) * (0.4 + 0.6 * p)
        cy = 0.5 + (fy - 0.5) * (0.4 + 0.6 * p)
        img = self.clips[k].at(self.src_time(k, t))
        z *= extra_zoom
        if blur > 0:
            return zoom_blur(img, z, cx, cy, blur)
        return crop_zoom(img, z, cx, cy, dx, dy)

    def at(self, t):
        for b, kind in TRANS.items():
            if b - HALF <= t < b + HALF:
                return self.transition(kind, b, t)
        k = 0 if t < 4.0 else min(4, int((t - 2.0) // 2))
        return self.seg_view(k, t)

    def transition(self, kind, b, t):
        k = int((b - 2.0) // 2) - 1
        p = prog(t, b - HALF, b + HALF)
        if kind == "zoom":
            a = self.seg_view(k, t, extra_zoom=1 + 0.45 * ease_in(p), blur=0.12 * ease_in(p))
            c = self.seg_view(k + 1, t, extra_zoom=1 + 0.45 * (1 - ease_out(p)), blur=0.12 * (1 - ease_out(p)))
            m = clamp((p - 0.38) / 0.24)
            return a * (1 - m) + c * m
        if kind in ("whip_h", "whip_v"):
            e = ease_io(p)
            size = W if kind == "whip_h" else H
            off = size * e
            vel = size * 6 * p * (1 - p)  # 中段最快
            horiz = kind == "whip_h"
            a = self.seg_view(k, t, dx=-off if horiz else 0, dy=0 if horiz else -off)
            c = self.seg_view(k + 1, t, dx=size - off if horiz else 0, dy=0 if horiz else size - off)
            img = a.copy()
            if horiz:
                cut = int(clamp(W - off, 0, W))
                img[:, cut:] = c[:, cut:]
            else:
                cut = int(clamp(H - off, 0, H))
                img[cut:, :] = c[cut:, :]
            return dir_blur(img, vel * 0.18, horiz)
        if kind == "sweep":
            a = self.seg_view(k, t)
            c = self.seg_view(k + 1, t)
            yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
            d = (xx / W) * 0.72 + (yy / H) * 0.28
            u = -0.25 + 1.5 * ease_io(p)
            m = np.clip((u - d) / 0.06 + 0.5, 0, 1)[..., None]
            band = np.exp(-((d - u) / 0.035) ** 2)[..., None]
            img = a * (1 - m) + c * m
            return np.clip(img + band * GLOW * 0.85, 0, 1)
        raise ValueError(kind)


def grade(x):
    lum = (x[..., 0] * 0.2126 + x[..., 1] * 0.7152 + x[..., 2] * 0.0722)[..., None]
    x = 0.5 + (x - 0.5) * 1.07
    x = x + (1 - lum) ** 3 * np.array([-0.012, 0.0, 0.03], np.float32)
    x = x + lum ** 3 * np.array([0.02, 0.008, -0.016], np.float32)
    x = lum + (x - lum) * 1.08
    x = x * 0.965 + 0.008
    return np.clip(x, 0, 1)


def make_vignette():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W / 2)) ** 2 + ((yy - H / 2) / (H / 2)) ** 2) / math.sqrt(2)
    return (1 - 0.32 * r ** 2.2)[..., None]


def make_intro_bg():
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r = np.sqrt(((xx - W / 2) / (W * 0.55)) ** 2 + ((yy - H * 0.55) / (H * 0.6)) ** 2)
    g = np.clip(1 - r, 0, 1)[..., None] ** 1.8
    return NIGHT + (BLUE * 0.85 - NIGHT) * g * 0.7


def load_rgba(path):
    im = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    if im is None:
        return None
    if im.shape[2] == 4:
        rgb = cv2.cvtColor(im[..., :3], cv2.COLOR_BGR2RGB).astype(np.float32) / 255
        a = im[..., 3:4].astype(np.float32) / 255
        return rgb, a
    return cv2.cvtColor(im, cv2.COLOR_BGR2RGB).astype(np.float32) / 255, None


def frame_at(f, foot, frames_dir, vign, intro_bg, rng):
    t = f / FPS
    img = grade(foot.at(t)) if t >= 0.8 else intro_bg.copy()
    if 0.8 <= t < 2.0:
        mt = load_rgba(pathlib.Path(frames_dir) / "mt" / f"{f:04d}.png")
        m = mt[0][..., :1] if mt else np.zeros((H, W, 1), np.float32)
        img = intro_bg * (1 - m) + img * m
    if t >= 12.0:  # 片尾：虚化 + 压暗
        p = ease_out(prog(t, 12.0, 12.8))
        sig = 0.1 + 16 * p
        img = cv2.GaussianBlur(img, (0, 0), sig)
        img = img * (1 - 0.74 * p) + NIGHT * 0.74 * p
    if t >= 0.8:
        img = img * vign
    # 落点与切换点的闪光
    for tb, amp, tau in [(2.0, 0.55, 0.12), (4.0, 0.22, 0.06), (8.0, 0.12, 0.05), (12.0, 0.35, 0.1)]:
        if t >= tb:
            img = img + (1 - img) * amp * math.exp(-(t - tb) / tau)
    ov = load_rgba(pathlib.Path(frames_dir) / "ov" / f"{f:04d}.png")
    if ov:
        rgb, a = ov
        img = img * (1 - a) + rgb * a
    img = img + rng.normal(0, 0.006, (H, W, 1)).astype(np.float32)
    return (np.clip(img, 0, 1) * 255 + 0.5).astype(np.uint8)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src")
    ap.add_argument("frames")
    ap.add_argument("music")
    ap.add_argument("out")
    ap.add_argument("--frames", dest="only", default=None, help="只输出这些帧为 PNG（检查用）")
    args = ap.parse_args()

    foot = Footage(args.src)
    vign, intro_bg = make_vignette(), make_intro_bg()
    rng = np.random.default_rng(8)

    if args.only:
        out = pathlib.Path(args.out)
        out.mkdir(parents=True, exist_ok=True)
        for f in map(int, args.only.split(",")):
            fr = frame_at(f, foot, args.frames, vign, intro_bg, rng)
            cv2.imwrite(str(out / f"{f:04d}.jpg"), cv2.cvtColor(fr, cv2.COLOR_RGB2BGR), [cv2.IMWRITE_JPEG_QUALITY, 90])
        return

    cmd = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS),
           "-i", "-", "-i", args.music,
           "-vf", "scale=out_color_matrix=bt709:out_range=tv,format=yuv420p",
           "-c:v", "libx264", "-preset", "slow", "-crf", "17", "-profile:v", "high", "-level", "4.1",
           "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
           "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", args.out]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for f in range(TOTAL):
        proc.stdin.write(frame_at(f, foot, args.frames, vign, intro_bg, rng).tobytes())
        if f % 50 == 0:
            print(f"  {f}/{TOTAL}", flush=True)
    proc.stdin.close()
    proc.wait()
    print("done", args.out)


if __name__ == "__main__":
    main()
