import sys, math, random, subprocess
import numpy as np, cv2
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from ai_edge_litert.interpreter import Interpreter

S = sys.argv[1]
SRC = S + '/src/in.mp4'
OUT = sys.argv[2]
W, H, FPS = 720, 1280, 30
FREEZE_AT = 11.55          # hand reaches for the phone after this; freeze frame
TOTAL = 12.6
FONT = '/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc'
EMOJI_FONT = '/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf'
BG_SWITCH = 9.75

# ---------- easing ----------
def clamp(x, a=0., b=1.): return max(a, min(b, x))
def back_out(x, s=2.2):
    x = clamp(x) - 1; return x * x * ((s + 1) * x + s) + 1
def elastic_out(x):
    x = clamp(x)
    if x in (0, 1): return x
    return 2 ** (-10 * x) * math.sin((x * 10 - 0.75) * (2 * math.pi / 3)) + 1
def ease_in(x): x = clamp(x); return x * x * x

# ---------- sprite builders ----------
_emoji_font = ImageFont.truetype(EMOJI_FONT, 109)
_cache = {}
def emoji(ch, size):
    k = ('e', ch, size)
    if k not in _cache:
        im = Image.new('RGBA', (160, 160), (0, 0, 0, 0))
        ImageDraw.Draw(im).text((80, 80), ch, font=_emoji_font, embedded_color=True, anchor='mm')
        im = im.crop(im.getbbox())
        sc = size / max(im.size)
        im = im.resize((max(1, int(im.width * sc)), max(1, int(im.height * sc))), Image.LANCZOS)
        # white sticker outline + shadow
        a = im.split()[3]
        pad = 14
        base = Image.new('RGBA', (im.width + pad * 2, im.height + pad * 2), (0, 0, 0, 0))
        big = Image.new('L', base.size, 0); big.paste(a, (pad, pad))
        outline = big.filter(ImageFilter.MaxFilter(13))
        shadow = outline.filter(ImageFilter.GaussianBlur(5))
        base.paste((0, 0, 0, 90), (4, 6), Image.eval(shadow, lambda v: v * 0.5).crop((0, 0, base.width - 4, base.height - 6)))
        base.paste((255, 255, 255, 255), (0, 0), outline)
        base.alpha_composite(im, (pad, pad))
        _cache[k] = base
    return _cache[k]

def flower_text(txt, size, colors, stroke=(40, 20, 90), stroke_w=None, shadow=True):
    """Colorful 'variety-show' text: vertical gradient fill, thick stroke, white rim, drop shadow."""
    k = ('t', txt, size, tuple(map(tuple, colors)), stroke)
    if k in _cache: return _cache[k]
    f = ImageFont.truetype(FONT, size)
    sw = stroke_w or max(4, size // 9)
    l, t, r, b = ImageDraw.Draw(Image.new('L', (1, 1))).textbbox((0, 0), txt, font=f, stroke_width=sw)
    pad = sw * 3 + 10
    w, h = r - l + pad * 2, b - t + pad * 2
    org = (pad - l, pad - t)
    fill = Image.new('L', (w, h), 0); ImageDraw.Draw(fill).text(org, txt, font=f, fill=255)
    strk = Image.new('L', (w, h), 0); ImageDraw.Draw(strk).text(org, txt, font=f, fill=255, stroke_width=sw)
    rim = strk.filter(ImageFilter.MaxFilter(7))
    # gradient
    grad = np.zeros((h, w, 3), np.float32)
    ys = np.linspace(0, 1, h)[:, None]
    c = np.array(colors, np.float32)
    seg = ys * (len(c) - 1)
    i0 = np.clip(seg.astype(int), 0, len(c) - 2)
    fr = seg - i0
    grad[:] = (c[i0] * (1 - fr[..., None]) + c[i0 + 1] * fr[..., None])
    gimg = Image.fromarray(grad.astype(np.uint8)).convert('RGBA')
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    if shadow:
        sh = rim.filter(ImageFilter.GaussianBlur(4))
        out.paste((0, 0, 0, 110), (5, 8), sh.crop((0, 0, w - 5, h - 8)))
    out.paste((255, 255, 255, 255), (0, 0), rim)
    out.paste(stroke + (255,), (0, 0), strk)
    out.paste(gimg, (0, 0), fill)
    # glossy highlight on top half of glyphs
    hl = Image.new('L', (w, h), 0)
    hl.paste(Image.eval(fill, lambda v: v * 0.35), (0, 0))
    mask_top = Image.new('L', (w, h), 0); ImageDraw.Draw(mask_top).rectangle((0, 0, w, h * 0.45), fill=255)
    hl = Image.fromarray((np.array(hl, np.float32) * np.array(mask_top, np.float32) / 255).astype(np.uint8))
    out.paste((255, 255, 255, 255), (0, 0), hl)
    _cache[k] = out
    return out

def caption(pieces, max_w=660, size=50):
    """Subtitle line made of (text, fill_rgb) pieces, white rim + dark stroke."""
    k = ('c', tuple(pieces))
    if k in _cache: return _cache[k]
    while True:
        f = ImageFont.truetype(FONT, size)
        widths = [ImageDraw.Draw(Image.new('L', (1, 1))).textlength(p, font=f) for p, _ in pieces]
        if sum(widths) <= max_w - 30 or size <= 30: break
        size -= 2
    sw = 6
    w, h = int(sum(widths)) + 40, size + 40
    im = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    x = 20
    for (p, col), pw in zip(pieces, widths):
        d.text((x + 3, 24), p, font=f, fill=(0, 0, 0, 120), stroke_width=sw, stroke_fill=(0, 0, 0, 120))
        d.text((x, 20), p, font=f, fill=col, stroke_width=sw, stroke_fill=(30, 20, 60))
        x += pw
    _cache[k] = im
    return im

def put(canvas, spr, cx, cy, scale=1., rot=0., alpha=1.):
    if scale <= 0.01 or alpha <= 0.01: return
    s = spr
    if scale != 1: s = s.resize((max(1, int(s.width * scale)), max(1, int(s.height * scale))), Image.BILINEAR)
    if rot: s = s.rotate(rot, resample=Image.BICUBIC, expand=True)
    if alpha < 1:
        a = s.split()[3].point(lambda v: int(v * alpha)); s = s.copy(); s.putalpha(a)
    x, y = int(cx - s.width / 2), int(cy - s.height / 2)
    canvas.alpha_composite(s, (max(0, x), max(0, y)), (max(0, -x), max(0, -y)))

def pop(t, t0, t1, out_dur=0.18):
    """scale curve: bouncy in at t0, quick shrink out at t1"""
    if t < t0 or t > t1 + out_dur: return 0.
    if t > t1: return 1 - ease_in((t - t1) / out_dur)
    return back_out((t - t0) / 0.32)

# ---------- new background: rotating sunburst ----------
R = 1500
yy, xx = np.mgrid[-R // 2:R // 2, -R // 2:R // 2].astype(np.float32)
ang = np.arctan2(yy, xx)
rays = (np.floor((ang + np.pi) / (2 * np.pi) * 24) % 2).astype(np.float32)
dist = np.sqrt(xx ** 2 + yy ** 2) / (R / 2)
c1 = np.array([255, 214, 64], np.float32); c2 = np.array([255, 150, 70], np.float32)
sun = c1 * rays[..., None] + c2 * (1 - rays[..., None])
glow = np.clip(1 - dist * 1.1, 0, 1)[..., None]
sun = sun * (0.75 + 0.25 * glow) + np.array([255, 255, 230]) * (glow ** 3) * 0.5
SUN = Image.fromarray(np.clip(sun, 0, 255).astype(np.uint8))
def new_bg(t):
    r = SUN.rotate(t * 18, resample=Image.BILINEAR)
    cx, cy = R // 2, R // 2 + 120
    bg = np.array(r.crop((cx - W // 2, cy - H // 2, cx + W // 2, cy + H // 2)), np.float32)
    # halftone dots for a pop-art feel
    gy, gx = np.mgrid[0:H, 0:W]
    dots = (((gx % 36) - 18) ** 2 + ((gy % 36) - 18) ** 2 < 16).astype(np.float32)[..., None]
    bg = bg * (1 - dots * 0.12) + 255 * dots * 0.12
    return bg

# ---------- confetti ----------
rng = random.Random(7)
CONF_COLS = [(255, 77, 109), (64, 196, 255), (120, 230, 90), (255, 230, 60), (190, 110, 255), (255, 255, 255)]
confetti = [dict(x=rng.uniform(0, W), y=rng.uniform(-900, -20), vx=rng.uniform(-60, 60), vy=rng.uniform(260, 520),
                 w=rng.uniform(10, 18), h=rng.uniform(6, 10), r0=rng.uniform(0, 360), vr=rng.uniform(-400, 400),
                 col=rng.choice(CONF_COLS)) for _ in range(90)]
def draw_confetti(canvas, dt, burst_y=None):
    d = ImageDraw.Draw(canvas)
    for p in confetti:
        x = p['x'] + p['vx'] * dt; y = p['y'] + p['vy'] * dt
        if y > H + 30: continue
        ang_ = math.radians(p['r0'] + p['vr'] * dt)
        hw, hh = p['w'] / 2, p['h'] / 2 * abs(math.cos(ang_ * 1.7))
        pts = [(x + ca * math.cos(ang_) - sa * math.sin(ang_), y + ca * math.sin(ang_) + sa * math.cos(ang_))
               for ca, sa in ((-hw, -hh), (hw, -hh), (hw, hh), (-hw, hh))]
        d.polygon(pts, fill=p['col'] + (255,))

# ---------- segmentation ----------
it = Interpreter(S + '/models/selfie_segmentation.tflite'); it.allocate_tensors()
inp, outp = it.get_input_details()[0]['index'], it.get_output_details()[0]['index']
def person_mask(rgb):
    x = cv2.resize(rgb, (256, 256)).astype(np.float32) / 255.
    it.set_tensor(inp, x[None]); it.invoke()
    m = it.get_tensor(outp)[0, :, :, 0]
    return cv2.resize(m, (W, H), interpolation=cv2.INTER_LINEAR)

# ---------- timeline ----------
CAPS = [
    (0.20, 2.95, [('现在你在', (255, 255, 255)), ('屏幕前', (120, 230, 255)), ('看到的这些', (255, 255, 255)), ('动画', (255, 225, 70))]),
    (2.95, 5.85, [('全都是', (255, 255, 255)), ('AI', (255, 110, 200)), ('辅助我做的', (255, 255, 255))]),
    (6.05, 8.05, [('这里上面是一个', (255, 255, 255)), ('苹果', (255, 90, 90))]),
    (8.05, 9.70, [('上面又是一个', (255, 255, 255)), ('香蕉', (255, 225, 60))]),
    (9.70, TOTAL, [('我现在整个人', (255, 255, 255)), ('换一个背景', (120, 255, 140))]),
]
CAP_Y = 960

def zoom_factor(t):
    z = 1.0
    for t0, amp in ((3.0, 0.07), (9.75, 0.06)):
        if t >= t0: z += amp * math.exp(-(t - t0) * 6) * (1 if t - t0 > 0.06 else (t - t0) / 0.06)
    return z

def overlay(canvas, t):
    # --- 0: "这些动画" sparkle intro ---
    s = pop(t, 0.25, 2.85)
    if s:
        put(canvas, flower_text('看这些动画!', 82, [(255, 245, 120), (255, 160, 40)]), W / 2, 200, s, math.sin(t * 5) * 3)
        put(canvas, emoji('👀', 110), 600, 330, pop(t, 0.5, 2.85) * (1 + 0.06 * math.sin(t * 12)), math.sin(t * 6) * 10)
        for i, (x, y, ph) in enumerate(((90, 300, 0), (640, 140, 1.7), (120, 120, 3.1))):
            put(canvas, emoji('✨', 70), x, y, pop(t, 0.6 + i * 0.25, 2.85) * (0.8 + 0.2 * math.sin(t * 8 + ph)), t * 60 + ph * 40)
    # --- 1: 全都是AI做的 ---
    s = pop(t, 3.0, 5.75)
    if s:
        put(canvas, flower_text('全是AI做的!', 96, [(255, 160, 230), (255, 70, 150), (200, 40, 220)]), W / 2, 210,
            elastic_out((t - 3.0) / 0.7) if t < 5.75 else s, math.sin(t * 4) * 2.5)
        put(canvas, emoji('🤖', 130), 120, 360, pop(t, 3.25, 5.75), -12 + math.sin(t * 7) * 8)
        put(canvas, emoji('💯', 100), 610, 370, pop(t, 3.6, 5.75), 10 + math.sin(t * 7 + 1) * 8)
        put(canvas, emoji('⚡', 70), 640, 90, pop(t, 3.9, 5.75), math.sin(t * 9) * 15)
    # --- 2: 苹果 (above raised hand, frame-left) ---
    s = pop(t, 6.0, 9.55, 0.25)
    if s:
        bob = math.sin(t * 5) * 10
        drop = (1 - back_out((t - 6.0) / 0.45)) * -260 if t < 6.45 else 0
        put(canvas, emoji('🍎', 190), 170, 330 + bob + drop, s, math.sin(t * 3) * 8)
        put(canvas, flower_text('苹果!', 60, [(255, 140, 140), (230, 30, 50)]), 170, 470 + bob, pop(t, 6.4, 9.55, 0.25), -8)
    # --- 3: 香蕉 (above raised hand, frame-right) ---
    s = pop(t, 8.0, 9.55, 0.25)
    if s:
        bob = math.sin(t * 5 + 2) * 10
        drop = (1 - back_out((t - 8.0) / 0.45)) * -260 if t < 8.45 else 0
        put(canvas, emoji('🍌', 190), 560, 320 + bob + drop, s, math.sin(t * 3 + 1) * 10)
        put(canvas, flower_text('香蕉!', 60, [(255, 245, 140), (255, 190, 0)]), 560, 460 + bob, pop(t, 8.4, 9.55, 0.25), 8)
    # --- 4: 换背景 ---
    s = pop(t, 9.9, TOTAL)
    if s:
        put(canvas, flower_text('一键换背景!', 92, [(170, 255, 170), (40, 200, 120), (20, 150, 200)]), W / 2, 200,
            elastic_out((t - 9.9) / 0.7), math.sin(t * 4) * 3)
        put(canvas, emoji('🎉', 120), 110, 360, pop(t, 10.1, TOTAL), -15 + math.sin(t * 6) * 10)
        put(canvas, emoji('🪄', 110), 615, 360, pop(t, 10.3, TOTAL), 15 + math.sin(t * 6 + 1) * 10)
    if t >= BG_SWITCH:
        draw_confetti(canvas, t - BG_SWITCH)
    # --- outro on freeze ---
    s = pop(t, 11.75, TOTAL)
    if s:
        put(canvas, emoji('👍', 150), 605, 720, s, 12 + math.sin(t * 8) * 8)
    # --- captions ---
    for t0, t1, pieces in CAPS:
        if t0 <= t < t1:
            k = clamp((t - t0) / 0.22)
            put(canvas, caption(pieces), W / 2, CAP_Y + (1 - back_out(k)) * 40, 0.85 + 0.15 * back_out(k), 0, clamp(k * 2))

def transition_ring(canvas, t):
    """white flash ring expanding at the background switch"""
    x = (t - BG_SWITCH) / 0.45
    if not 0 <= x <= 1: return
    d = ImageDraw.Draw(canvas)
    r = 40 + x * 1100
    wdt = int(60 * (1 - x)) + 4
    d.ellipse((W / 2 - r, 560 - r, W / 2 + r, 560 + r), outline=(255, 255, 255, int(255 * (1 - x))), width=wdt)

# ---------- main loop ----------
dec = subprocess.Popen(['ffmpeg', '-v', 'error', '-i', SRC, '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], stdout=subprocess.PIPE)
enc = subprocess.Popen(['ffmpeg', '-v', 'error', '-y', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', f'{W}x{H}', '-r', str(FPS), '-i', '-',
                        '-i', SRC, '-map', '0:v', '-map', '1:a', '-af', f'apad', '-t', str(TOTAL),
                        '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '160k',
                        '-movflags', '+faststart', OUT], stdin=subprocess.PIPE)
n_total = int(TOTAL * FPS)
mask_prev = None
frame = None; held = None
for i in range(n_total):
    t = i / FPS
    if t <= FREEZE_AT or held is None:
        raw = dec.stdout.read(W * H * 3)
        if len(raw) == W * H * 3:
            frame = np.frombuffer(raw, np.uint8).reshape(H, W, 3)
        if t <= FREEZE_AT:
            held = (frame, None)
    rgb = frame if t <= FREEZE_AT else held[0]
    img = rgb.astype(np.float32)
    if t >= BG_SWITCH - 0.05:
        if t <= FREEZE_AT or mask_prev is None:
            m = person_mask(rgb)
            m = m if mask_prev is None else 0.55 * m + 0.45 * mask_prev
            mask_prev = m
        m = cv2.GaussianBlur(np.clip((mask_prev - 0.25) / 0.5, 0, 1), (0, 0), 2.0)[..., None]
        bg = new_bg(t)
        comp = img * m + bg * (1 - m)
        # circular reveal of new background
        x = clamp((t - BG_SWITCH) / 0.45)
        if x < 1:
            gy, gx = np.ogrid[0:H, 0:W]
            r = 40 + back_out(x, 1.2) * 1100
            reveal = np.clip((r - np.sqrt((gx - W / 2) ** 2 + (gy - 560) ** 2)) / 25, 0, 1)[..., None]
            comp = comp * reveal + img * (1 - reveal)
        img = comp
    # punch zoom
    z = zoom_factor(t)
    if z > 1.001:
        M = cv2.getRotationMatrix2D((W / 2, 520), 0, z)
        img = cv2.warpAffine(img, M, (W, H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    canvas = Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).convert('RGBA')
    transition_ring(canvas, t)
    overlay(canvas, t)
    enc.stdin.write(np.array(canvas.convert('RGB')).tobytes())
    if i % 60 == 0: print(f'{t:.1f}s', flush=True)
dec.stdout.close(); dec.kill()
enc.stdin.close(); enc.wait()
print('done')
