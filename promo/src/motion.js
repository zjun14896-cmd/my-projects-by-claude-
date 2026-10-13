/* 云拓会 · 20s motion promo. One timeline, three aspect ratios.
 * Everything is a pure function of time t (seconds), so any frame can be
 * rendered on its own. 120 BPM → one beat = 0.5s, every cue sits on the grid. */

const BPM = 120, BEAT = 60 / BPM, DUR = 20;
const C = {
  navy: '#00133D', blue: '#003CAC', blueHi: '#2A63D9', blueLo: '#00267A',
  yellow: '#FFC833', white: '#FFFFFF', paper: '#EEF3FC', ink: '#0A1D4A',
};
const SEC = { hook: [0, 3], logo: [3, 6], f1: [6, 8.5], f2: [8.5, 11], f3: [11, 13.5], metric: [13.5, 16.5], cta: [16.5, 20] };
const DISPLAY = "'Inter Display', Inter, sans-serif";
const BODY = "Inter, sans-serif";

// ---------- math ----------
const clamp = (x, a = 0, b = 1) => Math.min(b, Math.max(a, x));
const lerp = (a, b, t) => a + (b - a) * t;
const prog = (t, a, b) => clamp((t - a) / (b - a));
const E = {
  outExpo: t => (t >= 1 ? 1 : 1 - Math.pow(2, -10 * t)),
  inExpo: t => (t <= 0 ? 0 : Math.pow(2, 10 * t - 10)),
  outCubic: t => 1 - Math.pow(1 - t, 3),
  inCubic: t => t * t * t,
  inOutCubic: t => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2),
  inOutQuart: t => (t < 0.5 ? 8 * t ** 4 : 1 - Math.pow(-2 * t + 2, 4) / 2),
  outBack: (t, s = 1.9) => 1 + (s + 1) * Math.pow(t - 1, 3) + s * Math.pow(t - 1, 2),
  outElastic: t => (t <= 0 ? 0 : t >= 1 ? 1 : Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * (2 * Math.PI / 3)) + 1),
};
function rng(seed) { // mulberry32
  return () => {
    seed |= 0; seed = (seed + 0x6D2B79F5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const DEG = Math.PI / 180;

// ---------- state ----------
let cv, ctx, W, H, S, KIND, IMG = {}, LAND = [], GRAIN;
const LOGO = { // coordinates inside the original 1888×790 logo file
  mark: { x: 0, y: 0, w: 729, h: 776 },
  word: { x: 684, y: 393, w: 1199, h: 293 },
  chars: [[684, 1075], [1088, 1478], [1490, 1883]],
  full: { w: 1888, h: 790 },
};

// ---------- sound cues (read by the audio synth) ----------
const SFX = [];
const cue = (t, type, gain = 1) => SFX.push({ t: +t.toFixed(4), type, gain });
const WIPES = [3.0, 6.0, 8.5, 11.0, 13.5, 16.5];
const WIPE_DUR = 0.8;
const SLAMS = [0, 0.5, 1.0, 1.5, 2.0];
[...SLAMS].forEach((t, i) => cue(t, 'impact', i === 4 ? 1.25 : 0.9));
cue(2.0, 'glitch');
WIPES.forEach(m => cue(m - WIPE_DUR / 2, 'whoosh'));
// logo assembly (also reused in CTA at 1.7× speed)
const ASM = { layers: [0.10, 0.20, 0.30, 0.40], swoosh: 0.55, plane: [0.5, 1.0], chars: [1.0, 1.125, 1.25] };
function asmCues(t0, sp, gain) {
  ASM.layers.forEach(u => cue(t0 + u / sp, 'swish', 0.6 * gain));
  cue(t0 + ASM.plane[0] / sp, 'flyby', gain);
  cue(t0 + ASM.plane[1] / sp, 'land', gain);
  ASM.chars.forEach(u => cue(t0 + u / sp, 'pop', 0.8 * gain));
}
asmCues(3.0, 1, 1);
cue(4.5, 'tick', 0.7);
for (let i = 0; i < 12; i++) cue(4.75 + i * 0.0625, 'type', 0.35);
// F1 globe
cue(7.0, 'click'); cue(7.0, 'drop', 0.8);
const ROUTES = [
  { n: 'EUROPE', lat: 50.1, lon: 8.7, t: 7.25 },
  { n: 'MIDDLE EAST', lat: 25.2, lon: 55.3, t: 7.375 },
  { n: 'SOUTHEAST ASIA', lat: 1.35, lon: 103.8, t: 7.5 },
  { n: 'JAPAN', lat: 35.7, lon: 139.7, t: 7.625 },
];
const ARC_DUR = 0.5;
ROUTES.forEach(r => { cue(r.t, 'zap', 0.6); cue(r.t + ARC_DUR, 'blip', 0.7); });
// F2 slider
cue(9.0, 'click');
[9.25, 9.5, 9.75].forEach((t, i) => cue(t, 'blip', 0.8 + i * 0.1));
cue(10.0, 'impact', 1.0);
// F3 community
cue(11.5, 'click');
for (let i = 0; i < 6; i++) cue(11.75 + i * 0.125, 'pop', 0.55);
[12.375, 12.625, 12.875].forEach(t => cue(t, 'bubble', 0.7));
// metric
for (let t = 13.6; t < 14.45; t += 0.0625) cue(t, 'tick', 0.35);
cue(14.5, 'impact', 1.1);
[15.0, 15.25, 15.5].forEach(t => cue(t, 'pop', 0.7));
// CTA
asmCues(16.5, 1.7, 0.7);
cue(17.0, 'rise', 0.9);
cue(17.45, 'scan', 0.7);
SFX.sort((a, b) => a.t - b.t);

const IMPACTS = [[0, 12], [0.5, 9], [1.0, 9], [1.5, 11], [2.0, 26], [4.0, 6], [10.0, 16], [14.5, 18]];

// ---------- helpers ----------
const font = (w, px, fam = DISPLAY) => `${w} ${px}px ${fam}`;
function fitSize(text, weight, fam, maxW, ls = 0) {
  ctx.font = font(weight, 100, fam);
  ctx.letterSpacing = ls ? `${ls * 100}px` : '0px';
  const w = ctx.measureText(text).width;
  ctx.letterSpacing = '0px';
  return (100 * maxW) / w;
}
function measure(text, weight, size, fam = DISPLAY) { ctx.font = font(weight, size, fam); return ctx.measureText(text).width; }
const CAP = 0.727; // Inter cap height / em

function rrect(x, y, w, h, r) {
  ctx.beginPath(); ctx.roundRect(x, y, w, h, r);
}
function fillBg(c) { ctx.fillStyle = c; ctx.fillRect(-W, -H, W * 3, H * 3); }
function dotGrid(color, alpha, gap, ox = 0, oy = 0, r = 1.6) {
  ctx.save(); ctx.globalAlpha = alpha; ctx.fillStyle = color;
  const g = gap * S, rr = r * S;
  for (let y = ((oy % g) + g) % g - g; y < H + g; y += g)
    for (let x = ((ox % g) + g) % g - g; x < W + g; x += g) { ctx.beginPath(); ctx.arc(x, y, rr, 0, 7); ctx.fill(); }
  ctx.restore();
}
function glow(x, y, r, color, a) {
  const g = ctx.createRadialGradient(x, y, 0, x, y, r);
  g.addColorStop(0, color); g.addColorStop(1, 'rgba(0,0,0,0)');
  ctx.save(); ctx.globalAlpha = a; ctx.fillStyle = g; ctx.fillRect(x - r, y - r, r * 2, r * 2); ctx.restore();
}
function ring(x, y, r, color, width, a) {
  if (a <= 0) return;
  ctx.save(); ctx.globalAlpha = a; ctx.strokeStyle = color; ctx.lineWidth = width;
  ctx.beginPath(); ctx.arc(x, y, Math.max(0.1, r), 0, 7); ctx.stroke(); ctx.restore();
}
function burst(t, t0, x, y, r0, r1, color, width, dur = 0.5) {
  const p = prog(t, t0, t0 + dur); if (p <= 0 || p >= 1) return;
  ring(x, y, lerp(r0, r1, E.outExpo(p)), color, width * (1 - p), 1 - p);
}
function skewText(text, x, y) { // Inter Display Black Italic, echoing the slanted wordmark
  ctx.save(); if (!ctx.font.startsWith('italic')) ctx.font = 'italic ' + ctx.font; ctx.fillText(text, x, y); ctx.restore();
}
function pill(text, cx, cy, size, bg, fg, a = 1, scale = 1, weight = 800) {
  ctx.save(); ctx.globalAlpha *= a; ctx.translate(cx, cy); ctx.scale(scale, scale);
  ctx.font = font(weight, size, BODY); ctx.letterSpacing = `${size * 0.08}px`;
  const w = ctx.measureText(text).width + size * 1.5, h = size * 2;
  ctx.fillStyle = bg; rrect(-w / 2, -h / 2, w, h, h / 2); ctx.fill();
  ctx.fillStyle = fg; ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
  ctx.fillText(text, size * 0.04, size * 0.06);
  ctx.restore(); ctx.letterSpacing = '0px';
  return w;
}
function pillWidth(text, size, weight = 800) {
  ctx.font = font(weight, size, BODY); ctx.letterSpacing = `${size * 0.08}px`;
  const w = ctx.measureText(text).width + size * 1.5; ctx.letterSpacing = '0px'; return w;
}
function cursor(x, y, press = 0, a = 1) {
  if (a <= 0) return;
  const k = 2.6 * S * (1 - 0.14 * press);
  ctx.save(); ctx.globalAlpha = a; ctx.translate(x, y); ctx.scale(k, k);
  ctx.shadowColor = 'rgba(0,10,40,.45)'; ctx.shadowBlur = 10; ctx.shadowOffsetY = 4;
  ctx.beginPath();
  ctx.moveTo(0, 0); ctx.lineTo(0, 24); ctx.lineTo(5.8, 18.6); ctx.lineTo(9.8, 27.6);
  ctx.lineTo(13.6, 26); ctx.lineTo(9.7, 17.2); ctx.lineTo(17.2, 17.2); ctx.closePath();
  ctx.fillStyle = '#fff'; ctx.fill(); ctx.shadowColor = 'transparent';
  ctx.lineJoin = 'round'; ctx.lineWidth = 1.6; ctx.strokeStyle = C.navy; ctx.stroke();
  ctx.restore();
}
function clickFx(t, t0, x, y, color) {
  burst(t, t0, x, y, 6 * S, 70 * S, color, 6 * S, 0.45);
  burst(t, t0 + 0.06, x, y, 6 * S, 110 * S, color, 3 * S, 0.55);
}
const bezier = (p0, p1, p2, u) => [
  (1 - u) ** 2 * p0[0] + 2 * (1 - u) * u * p1[0] + u * u * p2[0],
  (1 - u) ** 2 * p0[1] + 2 * (1 - u) * u * p1[1] + u * u * p2[1],
];
const bezierD = (p0, p1, p2, u) => [2 * (1 - u) * (p1[0] - p0[0]) + 2 * u * (p2[0] - p1[0]), 2 * (1 - u) * (p1[1] - p0[1]) + 2 * u * (p2[1] - p1[1])];

// ---------- layout ----------
let LAY;
function layout() {
  const P = KIND === 'portrait', L = KIND === 'landscape';
  const m = P ? 0.075 * W : L ? 0.07 * W : 0.08 * W;
  const lay = { m };
  // hook lines
  lay.hookLines = P ? [['GOING'], ['GLOBAL'], ['FEELS'], ['TOO'], ['HARD?']]
    : L ? [['GOING', 'GLOBAL'], ['FEELS', 'TOO'], ['HARD?']]
      : [['GOING'], ['GLOBAL'], ['FEELS', 'TOO'], ['HARD?']];
  const maxH = P ? H * 0.66 : H * 0.8;
  const contentW = L ? W * 0.62 : W - 2 * m;
  let sizes = lay.hookLines.map(l => fitSize(l.join(' '), 900, DISPLAY, contentW));
  const gapK = 0.2;
  const total = s => s.reduce((a, b) => a + b * CAP, 0) + gapK * Math.min(...s) * CAP * (s.length - 1);
  if (total(sizes) > maxH) { const f = maxH / total(sizes); sizes = sizes.map(s => s * f); }
  const gap = gapK * Math.min(...sizes) * CAP;
  let y = (H - total(sizes)) / 2;
  let wi = 0;
  lay.hook = lay.hookLines.map((words, li) => {
    const size = sizes[li]; y += size * CAP;
    ctx.font = font(900, size); const sp = ctx.measureText(' ').width;
    const ws = words.map(w => ctx.measureText(w).width);
    const lw = ws.reduce((a, b) => a + b, 0) + sp * (words.length - 1);
    let x = (W - lw) / 2 + size * CAP * 0.065;
    const out = words.map((w, i) => { const o = { w, x, wd: ws[i], t: SLAMS[wi++] }; x += ws[i] + sp; return o; });
    const line = { size, base: y, words: out };
    y += gap; return line;
  });
  // logo scene
  if (L) {
    const k = (0.6 * W) / LOGO.full.w, x0 = (W - LOGO.full.w * k) / 2, y0 = H * 0.39 - (LOGO.full.h * k) / 2;
    lay.logo = { mx: x0, my: y0, mk: k, wx: x0 + LOGO.word.x * k, wy: y0 + LOGO.word.y * k, wk: k, ty: y0 + LOGO.full.h * k + H * 0.1 };
  } else {
    const mw = P ? 0.56 * W : 0.38 * W, ww = P ? 0.64 * W : 0.5 * W;
    const mk = mw / LOGO.mark.w, wk = ww / LOGO.word.w;
    const my = (P ? 0.31 : 0.25) * H - (LOGO.mark.h * mk) / 2;
    const wy = my + LOGO.mark.h * mk + (P ? 0.045 : 0.05) * H;
    const ty = wy + LOGO.word.h * wk + (P ? 0.075 : 0.08) * H;
    const bottom = ty + Math.min(W, H) * (0.05 * 0.9 + 0.034 * 3.1);
    const dy = H * 0.5 - (my + bottom) / 2;
    lay.logo = { mx: (W - mw) / 2, my: my + dy, mk, wx: (W - ww) / 2, wy: wy + dy, wk, ty: ty + dy };
  }
  // feature scenes
  lay.illus = P ? { cx: W / 2, cy: 0.33 * H, R: 0.34 * W } : L ? { cx: 0.745 * W, cy: 0.5 * H, R: 0.33 * H } : { cx: W / 2, cy: 0.27 * H, R: 0.215 * H };
  lay.text = P ? { x: m, y: 0.62 * H, w: W - 2 * m, max: 0.135 * W } : L ? { x: 0.07 * W, y: null, w: 0.4 * W, max: 0.07 * W } : { x: m, y: 0.555 * H, w: W - 2 * m, max: 0.09 * W };
  // metric
  lay.metric = P ? { cx: W / 2, cy: 0.34 * H, R: 0.38 * W, tx: W / 2, ty: 0.34 * H + 0.38 * W + 0.075 * H, align: 'center' }
    : L ? { cx: 0.31 * W, cy: 0.5 * H, R: 0.37 * H, tx: 0.57 * W, ty: 0.36 * H, align: 'left' }
      : { cx: W / 2, cy: 0.35 * H, R: 0.27 * H, tx: W / 2, ty: 0.35 * H + 0.27 * H + 0.09 * H, align: 'center' };
  // CTA
  if (P) {
    const k = (0.8 * W) / LOGO.full.w;
    lay.cta = { lx: 0.1 * W, ly: 0.1 * H, lk: k, qcx: W / 2, qcy: 0.5 * H, qs: 0.5 * W, tx: W / 2, ty: 0.775 * H, tw: 0.84 * W };
  } else if (L) {
    const k = (0.42 * W) / LOGO.full.w;
    lay.cta = { lx: 0.08 * W, ly: 0.4 * H - (LOGO.full.h * k) / 2, lk: k, qcx: 0.76 * W, qcy: 0.5 * H, qs: 0.56 * H, tx: 0.08 * W + 0.21 * W, ty: 0.72 * H, tw: 0.42 * W };
  } else {
    const k = (0.56 * W) / LOGO.full.w;
    lay.cta = { lx: 0.22 * W, ly: 0.05 * H, lk: k, qcx: W / 2, qcy: 0.56 * H, qs: 0.38 * W, tx: W / 2, ty: 0.88 * H, tw: 0.8 * W };
  }
  return lay;
}

// ---------- shared: animated logo ----------
function layer(name, x, y, k, a = 1) {
  if (a <= 0) return;
  const m = LOGO.mark;
  ctx.save(); ctx.globalAlpha *= a;
  ctx.drawImage(IMG[name], m.x, m.y, m.w, m.h, x, y, m.w * k, m.h * k);
  ctx.restore();
}
/** Assemble the mark piece by piece. u = local time in "assembly units" (1 unit = 1s at speed 1). */
function drawMark(u, mx, my, mk) {
  const order = [['blue_top', -1], ['yellow_mid', 1], ['blue_bot', -1], ['yellow_bot', 1]];
  const land = ASM.plane[1];
  const pulse = u > land ? 1 + 0.06 * Math.exp(-(u - land) * 9) * Math.cos((u - land) * 18) : 1;
  const cx = mx + (LOGO.mark.w * mk) / 2, cy = my + (LOGO.mark.h * mk) / 2;
  ctx.save(); ctx.translate(cx, cy); ctx.scale(pulse, pulse); ctx.translate(-cx, -cy);
  order.forEach(([nm, dir], i) => {
    const a = ASM.layers[i], e = E.outExpo(prog(u, a, a + 0.45));
    const dx = dir * (1 - e) * 1000, dy = -dx * 0.2;
    layer(nm, mx + dx * mk, my + dy * mk, mk, prog(u, a, a + 0.06));
  });
  // top swoosh: reveal along its sweep (left → right)
  const sw = E.outCubic(prog(u, ASM.swoosh, ASM.swoosh + 0.4));
  if (sw > 0) {
    ctx.save(); ctx.beginPath(); ctx.rect(mx, my - 50 * mk, (LOGO.mark.w * sw + 10) * mk, LOGO.mark.h * mk); ctx.clip();
    layer('yellow_top', mx, my, mk); ctx.restore();
  }
  // plane flies in along an arc and lands in place
  const [pa, pb] = ASM.plane, pu = prog(u, pa, pb);
  if (pu > 0) {
    const e = E.outCubic(pu);
    const P0 = [-1400, 900], P1 = [-420, -260], P2 = [0, 0];
    const pivot = [590, 125];
    const tail = Math.max(0, e - 0.4);
    // vapour trail
    if (pu < 1 || u < pb + 0.5) {
      const fade = 1 - prog(u, pb, pb + 0.5);
      ctx.save(); ctx.lineCap = 'round';
      for (let i = 0; i < 18; i++) {
        const s0 = lerp(tail, e, i / 18), s1 = lerp(tail, e, (i + 1) / 18);
        const q0 = bezier(P0, P1, P2, s0), q1 = bezier(P0, P1, P2, s1);
        ctx.globalAlpha = (i / 18) * 0.85 * fade; ctx.strokeStyle = C.yellow; ctx.lineWidth = (6 + 22 * (i / 18)) * mk;
        ctx.beginPath(); ctx.moveTo(mx + (pivot[0] + q0[0]) * mk, my + (pivot[1] + q0[1]) * mk);
        ctx.lineTo(mx + (pivot[0] + q1[0]) * mk, my + (pivot[1] + q1[1]) * mk); ctx.stroke();
      }
      ctx.restore();
    }
    const p = bezier(P0, P1, P2, e), d = bezierD(P0, P1, P2, Math.min(e, 0.999)), dEnd = bezierD(P0, P1, P2, 1);
    const rot = Math.atan2(d[1], d[0]) - Math.atan2(dEnd[1], dEnd[0]);
    const sc = lerp(0.55, 1, e);
    ctx.save();
    ctx.translate(mx + (pivot[0] + p[0]) * mk, my + (pivot[1] + p[1]) * mk); ctx.rotate(rot); ctx.scale(sc, sc);
    ctx.translate(-(mx + pivot[0] * mk), -(my + pivot[1] * mk));
    layer('plane', mx, my, mk, prog(u, pa, pa + 0.05));
    ctx.restore();
  }
  ctx.restore();
  burst(u, land, mx + 590 * mk, my + 125 * mk, 20 * mk, 260 * mk, C.yellow, 16 * mk, 0.5);
}
function drawWordmark(u, wx, wy, wk) {
  LOGO.chars.forEach(([x0, x1], i) => {
    const a = ASM.chars[i], p = prog(u, a, a + 0.45);
    if (p <= 0) return;
    const e = E.outBack(p, 2.2), dy = (1 - e) * 160;
    const sx = (x0 - LOGO.word.x) * wk;
    const sq = 1 + 0.25 * (1 - E.outExpo(p));
    const cw = (x1 - x0) * wk, ch = LOGO.word.h * wk;
    ctx.save(); ctx.globalAlpha *= prog(u, a, a + 0.08);
    ctx.translate(wx + sx + cw / 2, wy + ch + dy * wk);
    ctx.scale(1 / sq, sq);
    ctx.drawImage(IMG.wordmark, x0, LOGO.word.y, x1 - x0, LOGO.word.h, -cw / 2, -ch, cw, ch);
    ctx.restore();
  });
}

// ---------- transitions ----------
function wipe(t, mid, colors) {
  const p = prog(t, mid - WIPE_DUR / 2, mid + WIPE_DUR / 2);
  if (p <= 0 || p >= 1) return;
  const n = colors.length, st = 0.11, D = Math.hypot(W, H) * 1.15;
  ctx.save(); ctx.translate(W / 2, H / 2); ctx.rotate(-11 * DEG);
  const bh = D / n;
  for (let i = 0; i < n; i++) {
    const k = (n - 1) * st;
    let xL, xR;
    if (p < 0.5) { const q = clamp((p * 2 - i * st) / (1 - k)); xL = -D / 2; xR = lerp(-D / 2, D / 2, E.inOutQuart(q)); }
    else { const q = clamp(((p - 0.5) * 2 - i * st) / (1 - k)); xL = lerp(-D / 2, D / 2, E.inOutQuart(q)); xR = D / 2; }
    if (xR <= xL) continue;
    ctx.fillStyle = colors[i];
    ctx.fillRect(xL, -D / 2 + i * bh - 1, xR - xL, bh + 2);
  }
  ctx.restore();
}

// ---------- scenes ----------
function sceneHook(t) {
  fillBg(C.navy);
  glow(W / 2, H * 0.5, Math.max(W, H) * 0.7, C.blue, 0.55);
  dotGrid('#fff', 0.08, 36, -t * 30 * S, -t * 50 * S);
  const exitP = E.inCubic(prog(t, 2.55, 3.0));
  ctx.save();
  ctx.translate(W / 2, H / 2); ctx.scale(1 + exitP * 0.25, 1 + exitP * 0.25); ctx.translate(-W / 2, -H / 2);
  ctx.translate(0, hookCam(t));
  LAY.hook.forEach((line, li) => {
    line.words.forEach(wd => {
      if (t < wd.t) return;
      const a = prog(t, wd.t, wd.t + 0.24), e = E.outExpo(a);
      const s = lerp(2.1, 1, e);
      const last = wd.w === 'HARD?';
      const cx = wd.x + wd.wd / 2, cy = line.base - (line.size * CAP) / 2;
      const draw = (scale, alpha, color, ox = 0) => {
        ctx.save(); ctx.globalAlpha = alpha; ctx.fillStyle = color; ctx.font = font(900, line.size);
        ctx.translate(cx + ox, cy); ctx.scale(scale, scale); ctx.translate(-cx, -cy);
        skewText(wd.w, wd.x, line.base); ctx.restore();
      };
      // motion ghosts on the slam
      if (a < 1) for (let g = 3; g >= 1; g--) draw(s * (1 + g * 0.18 * (1 - e)), 0.18 * (1 - a), last ? C.yellow : '#fff');
      // later words push the stack: earlier lines breathe on every new slam
      const breathe = SLAMS.reduce((acc, ts) => acc + (t > ts && ts > wd.t ? 0.035 * Math.exp(-(t - ts) * 12) : 0), 0);
      const col = last ? C.yellow : '#fff';
      if (last && t >= 2.0 && t < 2.42) { // RGB-split glitch
        const g = (1 - prog(t, 2.0, 2.42)) * 28 * S * (Math.sin(t * 190) > -0.3 ? 1 : -0.6);
        draw(s, 0.9, C.blueHi, -g); draw(s, 0.9, '#fff', g * 0.6);
      }
      draw(s + breathe, clamp((t - wd.t) / 0.04), col);
    });
  });
  // underline strike under the last line
  const ul = E.outExpo(prog(t, 2.25, 2.55));
  if (ul > 0) {
    const l = LAY.hook[LAY.hook.length - 1], w0 = l.words[0].x, w1 = l.words[l.words.length - 1].x + l.words[l.words.length - 1].wd;
    ctx.fillStyle = C.yellow; ctx.fillRect(w0, l.base + l.size * 0.09, (w1 - w0) * ul, l.size * 0.06);
  }
  ctx.restore();
  const fl = 1 - prog(t, 2.0, 2.12);
  if (t >= 2.0 && fl > 0) { ctx.fillStyle = `rgba(255,255,255,${0.35 * fl})`; ctx.fillRect(-W, -H, W * 3, H * 3); }
}

// keep the visible part of the stack centred: the camera eases down on every slam
function hookCam(t) {
  const centre = k => { // centre of lines that contain words 0..k
    const lines = LAY.hook.filter(l => l.words[0].t <= SLAMS[k]);
    const top = lines[0].base - lines[0].size * CAP, bot = lines[lines.length - 1].base;
    return H / 2 - (top + bot) / 2;
  };
  let off = centre(0);
  for (let k = 1; k < SLAMS.length; k++) off = lerp(off, centre(k), E.outExpo(prog(t, SLAMS[k], SLAMS[k] + 0.3)));
  return off;
}

function logoBg(t) {
  fillBg(C.white);
  const g = ctx.createLinearGradient(0, 0, 0, H); g.addColorStop(0, '#FFFFFF'); g.addColorStop(1, C.paper);
  ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  // brand stripes drifting in the background, very light
  ctx.save(); ctx.translate(W / 2, H / 2); ctx.rotate(-11 * DEG); ctx.globalAlpha = 0.06;
  const D = Math.hypot(W, H);
  for (let i = -3; i <= 3; i++) {
    ctx.fillStyle = i % 2 ? C.blue : C.yellow;
    const off = ((t * 60 * S + i * 400 * S) % (D * 1.4)) - D * 0.7;
    ctx.fillRect(off - D, i * 0.16 * D - 0.035 * D, D * 0.9, 0.07 * D);
  }
  ctx.restore();
}

function sceneLogo(t) {
  logoBg(t);
  const u = t - SEC.logo[0], L = LAY.logo;
  drawMark(u, L.mx, L.my, L.mk);
  drawWordmark(u, L.wx, L.wy, L.wk);
  // English name + tagline
  const size = Math.min(W, H) * 0.05;
  const np = E.outExpo(prog(u, 1.5, 1.95));
  ctx.textAlign = 'center';
  if (np > 0) {
    ctx.save(); ctx.beginPath(); ctx.rect(0, L.ty - size * 1.1, W, size * 1.4); ctx.clip();
    ctx.fillStyle = C.blue; ctx.font = font(800, size); ctx.letterSpacing = `${size * 0.42}px`;
    ctx.fillText('YUNTUOHUI', W / 2 + size * 0.21, L.ty + (1 - np) * size * 1.3);
    ctx.restore(); ctx.letterSpacing = '0px';
  }
  const tag = ['CROSS-BORDER E-COMMERCE TRAINING', '& GLOBAL EXPANSION SERVICES'];
  const ts = Math.min(W, H) * (KIND === 'landscape' ? 0.03 : 0.034);
  const chars = Math.floor(prog(u, 1.75, 2.5) * (tag[0].length + tag[1].length));
  ctx.font = font(600, ts, BODY); ctx.fillStyle = C.ink; ctx.letterSpacing = `${ts * 0.08}px`;
  let left = chars;
  tag.forEach((line, i) => {
    const s = line.slice(0, Math.max(0, left)); left -= line.length;
    const full = ctx.measureText(line).width;
    ctx.textAlign = 'left';
    ctx.fillText(s, W / 2 - full / 2, L.ty + size * 0.9 + ts * 1.55 * (i + 1));
  });
  ctx.letterSpacing = '0px';
  // yellow accent bar
  const bp = E.outExpo(prog(u, 1.6, 2.1));
  if (bp > 0) { ctx.fillStyle = C.yellow; const bw = size * 2.4 * bp; ctx.fillRect(W / 2 - bw / 2, L.ty + size * 0.55, bw, size * 0.14); }
}

function featureText(t, t0, idx, lines, sub, fg, accentBg, accentFg) {
  const T = LAY.text;
  let size = Math.min(T.max, ...lines.map(l => fitSize(l, 900, DISPLAY, T.w * 0.97)));
  const ss = Math.min(W, H) * (KIND === 'landscape' ? 0.03 : 0.036);
  const subLines = wrap(sub, 600, ss, BODY, T.w);
  const pillS = Math.min(W, H) * 0.024;
  const blockH = pillS * 2 + size * 0.5 + lines.length * size * 1.0 + ss * 0.8 + subLines.length * ss * 1.4;
  let y = T.y ?? (H - blockH) / 2;
  // index pill
  const pp = E.outExpo(prog(t, t0 + 0.12, t0 + 0.5));
  const pw = pillWidth(`0${idx} / 03`, pillS);
  pill(`0${idx} / 03`, T.x + pw / 2 - (1 - pp) * 60 * S, y + pillS, pillS, accentBg, accentFg, pp);
  y += pillS * 2 + size * 0.38;
  lines.forEach((ln, i) => {
    y += size * CAP;
    const p = E.outExpo(prog(t, t0 + 0.2 + i * 0.08, t0 + 0.7 + i * 0.08));
    ctx.save(); ctx.beginPath(); ctx.rect(T.x - 20 * S, y - size * 0.95, T.w + 80 * S, size * 1.18); ctx.clip();
    ctx.fillStyle = fg; ctx.font = font(900, size);
    skewText(ln, T.x + size * 0.07, y + (1 - p) * size * 1.1);
    ctx.restore();
    y += size * (1 - CAP) + size * 0.02;
  });
  y += ss * 0.4;
  const sp = E.outCubic(prog(t, t0 + 0.45, t0 + 0.85));
  ctx.save(); ctx.globalAlpha = sp; ctx.fillStyle = fg; ctx.font = font(600, ss, BODY); ctx.textAlign = 'left';
  subLines.forEach(l => { y += ss * 1.4; ctx.globalAlpha = sp * 0.82; ctx.fillText(l, T.x, y + (1 - sp) * 20 * S); });
  ctx.restore();
}
function wrap(text, weight, size, fam, maxW) {
  ctx.font = font(weight, size, fam);
  const words = text.split(' '), out = []; let cur = '';
  words.forEach(w => { const n = cur ? cur + ' ' + w : w; if (ctx.measureText(n).width > maxW && cur) { out.push(cur); cur = w; } else cur = n; });
  if (cur) out.push(cur); return out;
}

// --- F1: Yunnan → the world
function project(lat, lon, G, h = 0) {
  const phi = lat * DEG, lam = (lon - G.lon0) * DEG, t0 = G.lat0 * DEG;
  let x = Math.cos(phi) * Math.sin(lam), y = Math.sin(phi), z = Math.cos(phi) * Math.cos(lam);
  const y2 = y * Math.cos(t0) - z * Math.sin(t0), z2 = y * Math.sin(t0) + z * Math.cos(t0);
  const k = 1 + h;
  return { x: G.cx + G.R * x * k, y: G.cy - G.R * y2 * k, z: z2 };
}
function vec(lat, lon) { const p = lat * DEG, l = lon * DEG; return [Math.cos(p) * Math.cos(l), Math.cos(p) * Math.sin(l), Math.sin(p)]; }
function slerpLL(a, b, s) {
  const va = vec(a[0], a[1]), vb = vec(b[0], b[1]);
  const d = Math.acos(clamp(va[0] * vb[0] + va[1] * vb[1] + va[2] * vb[2], -1, 1));
  const f1 = Math.sin((1 - s) * d) / Math.sin(d), f2 = Math.sin(s * d) / Math.sin(d);
  const v = va.map((c, i) => c * f1 + vb[i] * f2);
  return [Math.asin(v[2]) / DEG, Math.atan2(v[1], v[0]) / DEG, d];
}
const YUNNAN = [25.0, 101.5];
function sceneF1(t) {
  const t0 = SEC.f1[0];
  fillBg(C.blue);
  glow(LAY.illus.cx, LAY.illus.cy, LAY.illus.R * 2.2, C.blueHi, 0.6);
  dotGrid('#fff', 0.07, 40, t * 20 * S, 0);
  const I = LAY.illus;
  const ip = prog(t, t0, t0 + 0.55);
  const R = I.R * lerp(0.6, 1, E.outBack(ip, 1.4));
  const G = { cx: I.cx, cy: I.cy, R, lat0: 16, lon0: lerp(-10, 80, E.outCubic(prog(t, t0, t0 + 0.95))) + (t - t0) * 2.2 };
  ctx.save(); ctx.globalAlpha = clamp(ip * 3);
  // sphere
  const sg = ctx.createRadialGradient(G.cx - R * 0.35, G.cy - R * 0.4, R * 0.1, G.cx, G.cy, R);
  sg.addColorStop(0, '#2C6BE6'); sg.addColorStop(1, '#00226F');
  ctx.fillStyle = sg; ctx.beginPath(); ctx.arc(G.cx, G.cy, R, 0, 7); ctx.fill();
  ring(G.cx, G.cy, R, '#7FA6FF', 2 * S, 0.5);
  ring(G.cx, G.cy, R * 1.12, C.yellow, 2 * S, 0.35);
  // graticule
  ctx.strokeStyle = 'rgba(255,255,255,.12)'; ctx.lineWidth = 1.2 * S;
  for (let lat = -60; lat <= 60; lat += 30) { ctx.beginPath(); let pen = false; for (let lon = -180; lon <= 180; lon += 4) { const p = project(lat, lon, G); if (p.z > 0) { pen ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y); pen = true; } else pen = false; } ctx.stroke(); }
  for (let lon = -180; lon < 180; lon += 30) { ctx.beginPath(); let pen = false; for (let lat = -88; lat <= 88; lat += 4) { const p = project(lat, lon, G); if (p.z > 0) { pen ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y); pen = true; } else pen = false; } ctx.stroke(); }
  // land dots
  ctx.fillStyle = '#fff';
  for (const [lat, lon] of LAND) {
    const p = project(lat, lon, G); if (p.z <= 0.02) continue;
    ctx.globalAlpha = clamp(ip * 3) * (0.25 + 0.75 * p.z);
    ctx.beginPath(); ctx.arc(p.x, p.y, R * 0.0095 * (0.55 + 0.45 * p.z), 0, 7); ctx.fill();
  }
  ctx.restore();
  // routes
  const pin = project(YUNNAN[0], YUNNAN[1], G);
  ROUTES.forEach(r => {
    const p = prog(t, r.t, r.t + ARC_DUR); if (p <= 0) return;
    const head = E.inOutCubic(p), tailS = Math.max(0, head - 0.55) * (p < 1 ? 1 : 0);
    const segs = 28;
    ctx.save(); ctx.lineCap = 'round';
    for (let i = 0; i < segs; i++) {
      const s0 = lerp(tailS, head, i / segs), s1 = lerp(tailS, head, (i + 1) / segs);
      const a = slerpLL(YUNNAN, [r.lat, r.lon], s0), b = slerpLL(YUNNAN, [r.lat, r.lon], s1);
      const hk = 0.22 * a[2];
      const q0 = project(a[0], a[1], G, hk * Math.sin(Math.PI * s0)), q1 = project(b[0], b[1], G, hk * Math.sin(Math.PI * s1));
      ctx.globalAlpha = p < 1 ? 0.25 + 0.75 * (i / segs) : 0.85;
      ctx.strokeStyle = C.yellow; ctx.lineWidth = R * 0.016;
      ctx.beginPath(); ctx.moveTo(q0.x, q0.y); ctx.lineTo(q1.x, q1.y); ctx.stroke();
    }
    ctx.restore();
    const hp = slerpLL(YUNNAN, [r.lat, r.lon], head);
    const hq = project(hp[0], hp[1], G, 0.22 * hp[2] * Math.sin(Math.PI * head));
    if (p < 1) { glow(hq.x, hq.y, R * 0.12, C.yellow, 0.9); ctx.fillStyle = '#fff'; ctx.beginPath(); ctx.arc(hq.x, hq.y, R * 0.022, 0, 7); ctx.fill(); }
    const dest = project(r.lat, r.lon, G), ta = r.t + ARC_DUR;
    if (t >= ta) {
      burst(t, ta, dest.x, dest.y, R * 0.02, R * 0.2, C.yellow, 5 * S, 0.5);
      ctx.fillStyle = C.yellow; ctx.beginPath(); ctx.arc(dest.x, dest.y, R * 0.028, 0, 7); ctx.fill();
      const lp = E.outBack(prog(t, ta, ta + 0.3));
      const ls = Math.min(W, H) * 0.019;
      const side = dest.x < G.cx ? -1 : 1;
      const lw = pillWidth(r.n, ls, 800);
      pill(r.n, dest.x + side * (lw / 2 + R * 0.06), dest.y - R * 0.07, ls, '#fff', C.navy, clamp(lp), lp, 800);
    }
  });
  // cursor → click Yunnan
  const ca = E.inOutCubic(prog(t, t0 + 0.25, t0 + 0.92));
  const cStart = [I.cx + I.R * 1.25, I.cy + I.R * 1.35];
  const cx = lerp(cStart[0], pin.x, ca), cy = lerp(cStart[1], pin.y, ca);
  const press = Math.max(0, 1 - Math.abs(t - 7.0) / 0.08);
  if (t >= 7.0) {
    clickFx(t, 7.0, pin.x, pin.y, C.yellow);
    const dp = E.outBack(prog(t, 7.0, 7.3), 2.5);
    // pin marker
    ctx.save(); ctx.translate(pin.x, pin.y); ctx.scale(dp, dp);
    const pr = R * 0.07;
    ctx.fillStyle = C.yellow; ctx.beginPath(); ctx.moveTo(0, 0);
    ctx.bezierCurveTo(-pr * 1.1, -pr * 1.1, -pr, -pr * 2.4, 0, -pr * 2.4); ctx.bezierCurveTo(pr, -pr * 2.4, pr * 1.1, -pr * 1.1, 0, 0); ctx.fill();
    ctx.fillStyle = C.navy; ctx.beginPath(); ctx.arc(0, -pr * 1.55, pr * 0.42, 0, 7); ctx.fill();
    ctx.restore();
    const ls = Math.min(W, H) * 0.026, lp = E.outBack(prog(t, 7.08, 7.4));
    pill('YUNNAN', pin.x, pin.y - R * 0.07 * 2.4 - ls * 1.6, ls, C.yellow, C.navy, clamp(lp), lp, 900);
  }
  const away = E.inCubic(prog(t, 7.35, 7.9));
  cursor(cx + away * I.R * 0.9, cy + away * I.R * 1.1, press, 1 - prog(t, 7.7, 7.9));
  featureText(t, t0, 1, ['YUNNAN BRANDS,', 'GO GLOBAL'], 'Global expansion services built for local Yunnan businesses', '#fff', C.yellow, C.navy);
}

// --- F2: zero to one
function sceneF2(t) {
  const t0 = SEC.f2[0], I = LAY.illus, R = I.R;
  fillBg(C.yellow);
  glow(I.cx, I.cy, R * 2, '#FFE08A', 0.8);
  dotGrid(C.navy, 0.08, 40, 0, -t * 25 * S);
  const ip = E.outExpo(prog(t, t0, t0 + 0.5));
  const tw = KIND === 'landscape' ? R * 2.35 : W * 0.8;
  const x0 = I.cx - tw / 2, x1 = I.cx + tw / 2, ty = I.cy + R * 0.72;
  const f = prog(t, 9.0, 9.75);
  const nodes = [0, 1 / 3, 2 / 3, 1], labels = ['START', 'OPEN A STORE', 'LIST PRODUCTS', 'FIRST ORDER'];
  // big digit (0 → 1, odometer roll)
  const ds = R * 1.55, dcy = I.cy - R * 0.18;
  const roll = E.inOutCubic(prog(t, 9.72, 10.0));
  const slam = t >= 10.0 ? 1 + 0.18 * Math.exp(-(t - 10.0) * 10) : 1;
  ctx.save();
  ctx.globalAlpha = ip; ctx.translate(I.cx, dcy); ctx.scale(slam * lerp(0.7, 1, ip), slam * lerp(0.7, 1, ip));
  const boxH = ds * 0.95;
  ctx.beginPath(); ctx.rect(-ds, -boxH / 2 - ds * 0.05, ds * 2, boxH + ds * 0.1); ctx.clip();
  ctx.font = font(900, ds); ctx.textAlign = 'center'; ctx.fillStyle = C.navy;
  skewText('0', 0, ds * CAP / 2 - roll * boxH * 1.1, 0.1);
  skewText('1', 0, ds * CAP / 2 + (1 - roll) * boxH * 1.1, 0.1);
  ctx.restore();
  // confetti on the "1"
  if (t >= 10.0) {
    const r = rng(7), p = t - 10.0;
    for (let i = 0; i < 70; i++) {
      const ang = r() * Math.PI * 2, sp = (0.5 + r() * 1.3) * R * 2.2, sz = (6 + r() * 12) * S;
      const x = I.cx + Math.cos(ang) * sp * E.outExpo(clamp(p / 0.9)), y = dcy + Math.sin(ang) * sp * E.outExpo(clamp(p / 0.9)) + p * p * R * 0.9;
      ctx.save(); ctx.globalAlpha = 1 - clamp((p - 0.4) / 0.6); ctx.translate(x, y); ctx.rotate(r() * 6 + p * (r() * 12 - 6));
      ctx.fillStyle = [C.navy, C.blue, '#fff'][i % 3]; ctx.fillRect(-sz / 2, -sz / 4, sz, sz / 2); ctx.restore();
    }
  }
  // track
  const th = R * 0.06;
  ctx.save(); ctx.globalAlpha = ip;
  ctx.fillStyle = 'rgba(0,19,61,.18)'; rrect(x0, ty - th / 2, tw * E.outExpo(prog(t, t0 + 0.1, t0 + 0.6)), th, th / 2); ctx.fill();
  ctx.fillStyle = C.navy; rrect(x0, ty - th / 2, tw * f + th / 2, th, th / 2); ctx.fill();
  const ls = Math.min(W, H) * (KIND === 'square' ? 0.019 : 0.021);
  nodes.forEach((n, i) => {
    const nx = lerp(x0, x1, n), lit = f >= n - 1e-6 && t >= 9.0, lt = 9.0 + n * 0.75;
    const np = E.outBack(prog(t, t0 + 0.2 + i * 0.07, t0 + 0.5 + i * 0.07));
    const nr = R * 0.085 * np * (lit ? 1 + 0.35 * Math.exp(-(t - lt) * 10) : 1);
    ctx.fillStyle = lit ? C.navy : C.yellow; ctx.strokeStyle = C.navy; ctx.lineWidth = 4 * S;
    ctx.beginPath(); ctx.arc(nx, ty, nr, 0, 7); ctx.fill(); ctx.stroke();
    if (lit && i > 0) { // check mark
      ctx.strokeStyle = C.yellow; ctx.lineWidth = 5 * S; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
      ctx.beginPath(); ctx.moveTo(nx - nr * 0.45, ty); ctx.lineTo(nx - nr * 0.1, ty + nr * 0.35); ctx.lineTo(nx + nr * 0.5, ty - nr * 0.35); ctx.stroke();
    }
    if (lit) burst(t, lt, nx, ty, nr, nr * 3, C.navy, 4 * S, 0.4);
    ctx.font = font(lit ? 800 : 700, ls, BODY); ctx.letterSpacing = `${ls * 0.06}px`;
    ctx.textAlign = i === 0 ? 'left' : i === 3 ? 'right' : 'center';
    ctx.fillStyle = lit ? C.navy : 'rgba(0,19,61,.5)';
    ctx.globalAlpha = ip * clamp(np);
    const lx = i === 0 ? nx - R * 0.085 : i === 3 ? nx + R * 0.085 : nx;
    ctx.fillText(labels[i], lx, ty + R * 0.085 + ls * 2.0);
    ctx.globalAlpha = ip;
  });
  ctx.letterSpacing = '0px';
  ctx.restore();
  // handle + cursor drag
  const hx = lerp(x0, x1, f);
  if (t >= 9.0) { ctx.fillStyle = '#fff'; ctx.strokeStyle = C.navy; ctx.lineWidth = 5 * S; ctx.beginPath(); ctx.arc(hx, ty, R * 0.1, 0, 7); ctx.fill(); ctx.stroke(); }
  const ca = E.inOutCubic(prog(t, t0 + 0.2, t0 + 0.48));
  let cx = lerp(I.cx + R * 0.6, x0, ca), cy = lerp(ty + R * 0.9, ty, ca);
  if (t >= 9.0) { cx = hx; cy = ty; }
  const rel = E.inCubic(prog(t, 9.85, 10.3));
  const press = t >= 9.0 && t < 9.8 ? 1 : Math.max(0, 1 - Math.abs(t - 9.0) / 0.08);
  clickFx(t, 9.0, x0, ty, C.navy);
  cursor(cx + R * 0.02 + rel * R * 0.5, cy + R * 0.02 + rel * R * 0.8, press, ip * (1 - prog(t, 10.1, 10.3)));
  featureText(t, t0, 2, ['FROM ZERO', 'TO ONE'], 'Cross-border e-commerce training for total beginners', C.navy, C.navy, C.yellow);
}

// --- F3: one-year community coaching
function avatar(x, y, r, bg, fg) {
  ctx.fillStyle = bg; ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.fill();
  ctx.save(); ctx.beginPath(); ctx.arc(x, y, r, 0, 7); ctx.clip();
  ctx.fillStyle = fg; ctx.beginPath(); ctx.arc(x, y - r * 0.18, r * 0.34, 0, 7); ctx.fill();
  ctx.beginPath(); ctx.ellipse(x, y + r * 0.78, r * 0.62, r * 0.5, 0, 0, 7); ctx.fill();
  ctx.restore();
}
function sceneF3(t) {
  const t0 = SEC.f3[0], I = LAY.illus, R = I.R;
  fillBg(C.navy);
  glow(I.cx, I.cy, R * 2.1, C.blue, 0.8);
  dotGrid('#fff', 0.07, 40, -t * 20 * S, t * 10 * S);
  const ip = E.outExpo(prog(t, t0, t0 + 0.5));
  const rr = R * 0.74;
  // 12-month ring
  const segs = 12, gap = 5 * DEG;
  ctx.save(); ctx.lineCap = 'butt'; ctx.lineWidth = R * 0.075;
  for (let i = 0; i < segs; i++) {
    const a0 = -Math.PI / 2 + i * (2 * Math.PI / segs) + gap / 2, a1 = a0 + 2 * Math.PI / segs - gap;
    const draw = E.outExpo(prog(t, t0 + 0.05 + i * 0.02, t0 + 0.45 + i * 0.02));
    ctx.globalAlpha = 0.16; ctx.strokeStyle = '#fff';
    ctx.beginPath(); ctx.arc(I.cx, I.cy, rr, a0, lerp(a0, a1, draw)); ctx.stroke();
    const lt = 11.75 + i * 0.1, lp = E.outCubic(prog(t, lt, lt + 0.15));
    if (lp > 0) { ctx.globalAlpha = 1; ctx.strokeStyle = C.yellow; ctx.beginPath(); ctx.arc(I.cx, I.cy, rr, a0, lerp(a0, a1, lp)); ctx.stroke(); }
  }
  ctx.restore();
  const ms = Math.min(W, H) * 0.02;
  const mp = prog(t, 11.75, 13.0);
  if (t >= 11.75) {
    ctx.save(); ctx.globalAlpha = clamp((t - 11.75) / 0.2); ctx.fillStyle = C.yellow; ctx.font = font(800, ms, BODY);
    ctx.textAlign = 'center'; ctx.letterSpacing = `${ms * 0.25}px`;
    ctx.fillText(`MONTH ${String(Math.min(12, 1 + Math.floor(mp * 12))).padStart(2, '0')} / 12`, I.cx + ms * 0.12, I.cy + R * 0.32);
    ctx.restore(); ctx.letterSpacing = '0px';
  }
  // JOIN button
  const clicked = t >= 11.5;
  const bp = E.outBack(prog(t, t0 + 0.15, t0 + 0.5));
  const press = Math.max(0, 1 - Math.abs(t - 11.5) / 0.08);
  const morph = E.outBack(prog(t, 11.5, 11.8));
  const bw = R * lerp(0.82, 1.02, clicked ? morph : 0), bh = R * 0.27;
  ctx.save(); ctx.translate(I.cx, I.cy - R * 0.03); ctx.scale(bp * (1 - 0.08 * press), bp * (1 - 0.08 * press));
  ctx.shadowColor = 'rgba(0,0,0,.35)'; ctx.shadowBlur = 30 * S; ctx.shadowOffsetY = 10 * S;
  ctx.fillStyle = clicked ? '#fff' : C.yellow; rrect(-bw / 2, -bh / 2, bw, bh, bh / 2); ctx.fill();
  ctx.shadowColor = 'transparent';
  const fs = bh * 0.42;
  ctx.font = font(900, fs); ctx.textAlign = 'center'; ctx.fillStyle = C.navy; ctx.letterSpacing = `${fs * 0.08}px`;
  if (!clicked) ctx.fillText('JOIN', fs * 0.04, fs * CAP / 2);
  else {
    ctx.fillText('JOINED', -fs * 0.55, fs * CAP / 2);
    const cxk = bw / 2 - bh * 0.5;
    ctx.fillStyle = C.blue; ctx.beginPath(); ctx.arc(cxk, 0, bh * 0.3, 0, 7); ctx.fill();
    ctx.strokeStyle = '#fff'; ctx.lineWidth = 4 * S; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    ctx.beginPath(); ctx.moveTo(cxk - bh * 0.13, 0); ctx.lineTo(cxk - bh * 0.03, bh * 0.1); ctx.lineTo(cxk + bh * 0.14, -bh * 0.1); ctx.stroke();
  }
  ctx.restore(); ctx.letterSpacing = '0px';
  clickFx(t, 11.5, I.cx, I.cy, C.yellow);
  // members joining around the ring
  const cols = [[C.yellow, C.navy], ['#fff', C.blue], [C.blueHi, '#fff'], ['#fff', C.navy], [C.yellow, C.blue], [C.blueHi, C.yellow]];
  const pos = [];
  for (let i = 0; i < 6; i++) {
    const ang = -Math.PI / 2 + (i + 0.5) * (Math.PI * 2 / 6);
    const x = I.cx + Math.cos(ang) * rr, y = I.cy + Math.sin(ang) * rr;
    pos.push([x, y, ang]);
    const at = 11.75 + i * 0.125, ap = E.outBack(prog(t, at, at + 0.3), 2.4);
    if (ap <= 0) continue;
    const ar = R * 0.13 * ap;
    ring(x, y, ar + 5 * S, C.navy, 10 * S, 1);
    avatar(x, y, ar, cols[i][0], cols[i][1]);
    burst(t, at, x, y, ar, ar * 2.2, C.yellow, 3 * S, 0.4);
  }
  // chat bubbles
  [[1, 12.375], [3, 12.625], [5, 12.875]].forEach(([pi, bt], k) => {
    const bpp = E.outBack(prog(t, bt, bt + 0.3), 2.2); if (bpp <= 0) return;
    const [x, y, ang] = pos[pi];
    const side = Math.cos(ang) >= 0 ? 1 : -1;
    const bw2 = R * 0.62, bh2 = R * 0.28;
    let bx = x + side * R * 0.16; const by = y - R * 0.3;
    bx = side > 0 ? Math.min(bx, W - LAY.m - bw2) : Math.max(bx, (KIND === 'landscape' ? 0.5 * W : LAY.m) + bw2);
    ctx.save(); ctx.translate(bx, by); ctx.scale(bpp, bpp);
    ctx.fillStyle = '#fff'; ctx.shadowColor = 'rgba(0,0,0,.3)'; ctx.shadowBlur = 20 * S; ctx.shadowOffsetY = 6 * S;
    const ox = side > 0 ? 0 : -bw2;
    rrect(ox, -bh2, bw2, bh2, bh2 * 0.32); ctx.fill(); ctx.shadowColor = 'transparent';
    ctx.fillStyle = 'rgba(0,19,61,.75)'; rrect(ox + bw2 * 0.12, -bh2 * 0.72, bw2 * 0.7, bh2 * 0.14, bh2 * 0.07); ctx.fill();
    ctx.fillStyle = 'rgba(0,19,61,.3)'; rrect(ox + bw2 * 0.12, -bh2 * 0.42, bw2 * (0.45 + 0.1 * k), bh2 * 0.14, bh2 * 0.07); ctx.fill();
    ctx.restore();
  });
  // cursor
  const ca = E.inOutCubic(prog(t, t0 + 0.12, t0 + 0.45));
  const away = E.inCubic(prog(t, 11.75, 12.3));
  cursor(lerp(I.cx + R * 1.2, I.cx + R * 0.12, ca) + away * R, lerp(I.cy + R * 1.4, I.cy + R * 0.02, ca) + away * R * 1.2, press, ip * (1 - prog(t, 12.1, 12.3)));
  featureText(t, t0, 3, ['A FULL YEAR', 'OF COACHING'], 'Our online community walks with you, step by step, for 12 months', '#fff', C.yellow, C.navy);
}

// --- metric: 365
function sceneMetric(t) {
  const t0 = SEC.metric[0], M = LAY.metric, R = M.R;
  fillBg(C.blue);
  glow(M.cx, M.cy, R * 2, C.blueHi, 0.7);
  dotGrid('#fff', 0.07, 40, t * 15 * S, -t * 15 * S);
  const n = 365 * E.outExpo(prog(t, 13.6, 14.5));
  // 365 ticks
  const ip = E.outExpo(prog(t, t0, t0 + 0.5));
  ctx.save(); ctx.lineCap = 'round';
  for (let i = 0; i < 365; i++) {
    const a = -Math.PI / 2 + (i / 365) * Math.PI * 2;
    const on = i < n; const tl = R * (on ? 0.085 : 0.05) * ip;
    ctx.strokeStyle = on ? C.yellow : 'rgba(255,255,255,.2)'; ctx.lineWidth = (2 * Math.PI * R / 365) * 0.55;
    ctx.beginPath(); ctx.moveTo(M.cx + Math.cos(a) * R, M.cy + Math.sin(a) * R);
    ctx.lineTo(M.cx + Math.cos(a) * (R - tl), M.cy + Math.sin(a) * (R - tl)); ctx.stroke();
  }
  ctx.restore();
  burst(t, 14.5, M.cx, M.cy, R * 0.9, R * 1.5, C.yellow, 10 * S, 0.6);
  // odometer number
  const ds = fitSize('365', 900, DISPLAY, R * 1.34);
  ctx.font = font(900, ds);
  const dw = Math.max(...'0123456789'.split('').map(d => ctx.measureText(d).width));
  const slam = t >= 14.5 ? 1 + 0.14 * Math.exp(-(t - 14.5) * 10) * Math.cos((t - 14.5) * 20) : 1;
  const ny = M.cy - R * 0.06;
  ctx.save(); ctx.translate(M.cx, ny); ctx.scale(slam * lerp(0.8, 1, ip), slam * lerp(0.8, 1, ip)); ctx.globalAlpha = ip;
  const boxH = ds * CAP * 1.35;
  ctx.beginPath(); ctx.rect(-dw * 1.6, -boxH / 2, dw * 3.2, boxH); ctx.clip();
  ctx.fillStyle = C.yellow; ctx.textAlign = 'center';
  for (let k = 0; k < 3; k++) {
    const place = 10 ** (2 - k), v = n / place, d = Math.floor(v) % 10;
    // hundreds and tens roll; the ones place flips too fast to read, so it snaps
    const x = (k - 1) * dw * 1.02;
    const step = boxH * 1.05;
    const off = k === 2 || Math.floor(v) >= Math.floor(365 / place) ? 0 : E.inOutCubic(v - Math.floor(v));
    skewText(String(d), x, ds * CAP / 2 - off * step, 0.1);
    skewText(String((d + 1) % 10), x, ds * CAP / 2 + (1 - off) * step, 0.1);
  }
  ctx.restore();
  const lsz = R * 0.13, lp = E.outExpo(prog(t, 14.5, 14.85));
  ctx.save(); ctx.globalAlpha = lp; ctx.fillStyle = '#fff'; ctx.font = font(900, lsz); ctx.textAlign = 'center'; ctx.letterSpacing = `${lsz * 0.45}px`;
  ctx.fillText('DAYS', M.cx + lsz * 0.22, ny + ds * CAP * 0.5 + lsz * 1.55 + (1 - lp) * 30 * S);
  ctx.restore(); ctx.letterSpacing = '0px';
  // copy + audience pills
  const ss = Math.min(W, H) * (KIND === 'landscape' ? 0.042 : KIND === 'portrait' ? 0.062 : 0.05);
  const sp = E.outExpo(prog(t, 14.7, 15.1));
  ctx.save(); ctx.globalAlpha = sp; ctx.fillStyle = '#fff'; ctx.textAlign = M.align;
  ctx.font = font(900, ss);
  const l1 = 'OF HANDS-ON COACHING', l2 = 'BUILT FOR EVERY STAGE';
  skewText(l1, M.tx, M.ty + (1 - sp) * 30 * S, 0.1);
  ctx.globalAlpha = sp * 0.75; ctx.font = font(600, ss * 0.62, BODY);
  ctx.fillText(l2, M.tx, M.ty + ss * 1.25);
  ctx.restore();
  const ps = Math.min(W, H) * (KIND === 'portrait' ? 0.03 : 0.024), names = ['BEGINNERS', 'SELLERS', 'ENTERPRISES'];
  const ws = names.map(nm => pillWidth(nm, ps, 800)), gapP = ps * 0.8;
  const py = M.ty + ss * 1.25 + ps * 3.4;
  if (KIND === 'landscape') {
    names.forEach((nm, i) => { const p = E.outBack(prog(t, 15.0 + i * 0.25, 15.3 + i * 0.25), 2.4); pill(nm, M.tx + ws[i] / 2, py + i * ps * 2.7, ps, C.yellow, C.navy, clamp(p), p); });
  } else {
    const tot = ws.reduce((a, b) => a + b, 0) + gapP * 2; let x = M.tx - tot / 2;
    names.forEach((nm, i) => { const p = E.outBack(prog(t, 15.0 + i * 0.25, 15.3 + i * 0.25), 2.4); pill(nm, x + ws[i] / 2, py, ps, C.yellow, C.navy, clamp(p), p); x += ws[i] + gapP; });
  }
}

// --- CTA: logo lockup + WeChat QR
function sceneCTA(t) {
  const t0 = SEC.cta[0], Q = LAY.cta;
  logoBg(t);
  const sp = 1.7, u = (t - t0) * sp;
  drawMark(u, Q.lx, Q.ly, Q.lk);
  drawWordmark(u, Q.lx + LOGO.word.x * Q.lk, Q.ly + LOGO.word.y * Q.lk, Q.lk);
  // QR card
  const qp = prog(t, 17.0, 17.45), qe = E.outBack(qp, 1.6);
  if (qp > 0) {
    const s = Q.qs, pad = s * 0.07;
    ctx.save(); ctx.globalAlpha = clamp(qp * 3);
    ctx.translate(Q.qcx, Q.qcy + (1 - E.outExpo(qp)) * H * 0.15); ctx.scale(lerp(0.85, 1, qe), lerp(0.85, 1, qe));
    ctx.shadowColor = 'rgba(0,40,120,.28)'; ctx.shadowBlur = 50 * S; ctx.shadowOffsetY = 18 * S;
    ctx.fillStyle = '#fff'; rrect(-s / 2 - pad, -s / 2 - pad, s + pad * 2, s + pad * 2, pad * 1.1); ctx.fill();
    ctx.shadowColor = 'transparent';
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(IMG.qr, -s / 2, -s / 2, s, s);
    // corner brackets
    const bl = s * 0.16, bo = s / 2 + pad * 1.9, bw = s * 0.022;
    const bpulse = t > 18 ? 1 + 0.012 * Math.max(0, Math.cos(((t - 18) / BEAT) * Math.PI * 2)) : 1;
    ctx.scale(bpulse, bpulse);
    ctx.strokeStyle = C.yellow; ctx.lineWidth = bw; ctx.lineCap = 'round';
    [[-1, -1], [1, -1], [1, 1], [-1, 1]].forEach(([sx, sy]) => {
      ctx.beginPath(); ctx.moveTo(sx * bo, sy * (bo - bl)); ctx.lineTo(sx * bo, sy * bo); ctx.lineTo(sx * (bo - bl), sy * bo); ctx.stroke();
    });
    ctx.restore();
    // one scan sweep, then the code stays perfectly clean
    const sc = prog(t, 17.45, 18.0);
    if (sc > 0 && sc < 1) {
      const y = Q.qcy - s / 2 + s * E.inOutCubic(sc);
      const g = ctx.createLinearGradient(0, y - s * 0.12, 0, y);
      g.addColorStop(0, 'rgba(255,200,51,0)'); g.addColorStop(1, 'rgba(255,200,51,.55)');
      ctx.fillStyle = g; ctx.fillRect(Q.qcx - s / 2, y - s * 0.12, s, s * 0.12);
      ctx.fillStyle = C.yellow; ctx.fillRect(Q.qcx - s / 2 - pad, y - 2 * S, s + pad * 2, 4 * S);
    }
  }
  // CTA copy
  const hp = E.outExpo(prog(t, 17.3, 17.75));
  const hs = Math.min(fitSize('FOLLOW US ON WECHAT', 900, DISPLAY, Q.tw), Math.min(W, H) * 0.085);
  ctx.save(); ctx.textAlign = 'center';
  ctx.beginPath(); ctx.rect(0, Q.ty - hs * 0.95, W, hs * 1.2); ctx.clip();
  ctx.fillStyle = C.blue; ctx.font = font(900, hs);
  skewText('FOLLOW US ON WECHAT', Q.tx + hs * 0.06, Q.ty + (1 - hp) * hs * 1.2, 0.1);
  ctx.restore();
  const ss = hs * 0.42, sp2 = E.outCubic(prog(t, 17.5, 17.9));
  ctx.save(); ctx.globalAlpha = sp2; ctx.fillStyle = C.ink; ctx.font = font(600, ss, BODY); ctx.textAlign = 'center';
  ctx.letterSpacing = `${ss * 0.06}px`;
  ctx.fillText('Scan the code · WeChat Official Account', Q.tx, Q.ty + ss * 2.1);
  ctx.restore(); ctx.letterSpacing = '0px';
  const bar = E.outExpo(prog(t, 17.6, 18.1));
  if (bar > 0) { ctx.fillStyle = C.yellow; const bw = hs * 2 * bar; ctx.fillRect(Q.tx - bw / 2, Q.ty + ss * 3.1, bw, hs * 0.08); }
}

// ---------- frame ----------
function shake(t) {
  let x = 0, y = 0;
  IMPACTS.forEach(([ti, a], i) => {
    if (t < ti) return;
    const k = a * S * Math.exp(-(t - ti) * 14);
    x += k * Math.sin(t * 97 + i * 3.1); y += k * Math.cos(t * 83 + i * 1.7);
  });
  return [x, y];
}
function makeGrain() {
  const g = document.createElement('canvas'); g.width = g.height = 256;
  const gc = g.getContext('2d'), id = gc.createImageData(256, 256), r = rng(42);
  for (let i = 0; i < id.data.length; i += 4) { const v = r() * 255; id.data[i] = id.data[i + 1] = id.data[i + 2] = v; id.data[i + 3] = 255; }
  gc.putImageData(id, 0, 0); return g;
}

function renderFrame(t) {
  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.clearRect(0, 0, W, H);
  const [sx, sy] = shake(t);
  ctx.save(); ctx.translate(sx, sy);
  if (t < SEC.logo[0]) sceneHook(t);
  else if (t < SEC.f1[0]) sceneLogo(t);
  else if (t < SEC.f2[0]) sceneF1(t);
  else if (t < SEC.f3[0]) sceneF2(t);
  else if (t < SEC.metric[0]) sceneF3(t);
  else if (t < SEC.cta[0]) sceneMetric(t);
  else sceneCTA(t);
  ctx.restore();
  const Y = C.yellow, B = C.blue, N = C.navy;
  wipe(t, 3.0, [Y, B, Y, B, N]);
  wipe(t, 6.0, [B, Y, B, N, B]);
  wipe(t, 8.5, [Y, N, Y, B, Y]);
  wipe(t, 11.0, [N, B, N, Y, N]);
  wipe(t, 13.5, [B, Y, B, N, B]);
  wipe(t, 16.5, [Y, B, Y, B, Y]);
  // film grain, kept off the QR card so it scans cleanly
  ctx.save(); ctx.globalAlpha = 0.035; ctx.globalCompositeOperation = 'overlay';
  const r = rng(Math.floor(t * 60) + 1), ox = -r() * 256, oy = -r() * 256;
  ctx.fillStyle = ctx.createPattern(GRAIN, 'repeat'); ctx.translate(ox, oy);
  if (t >= 17.0) {
    const Q = LAY.cta, s = Q.qs * 0.5 + Q.qs * 0.07;
    ctx.beginPath(); ctx.rect(-ox, -oy, W, H); ctx.rect(Q.qcx - s - ox, Q.qcy - s - oy, s * 2, s * 2); ctx.clip('evenodd');
  }
  ctx.fillRect(0, 0, W + 256, H + 256);
  ctx.restore();
}

async function setup(w, h) {
  W = w; H = h; S = Math.min(W, H) / 1080;
  KIND = H / W > 1.3 ? 'portrait' : W / H > 1.3 ? 'landscape' : 'square';
  cv = document.getElementById('c'); cv.width = W; cv.height = H;
  cv.style.width = `${W / 2}px`; cv.style.height = `${H / 2}px`;
  ctx = cv.getContext('2d');
  const load = (k, src) => new Promise((res, rej) => { const i = new Image(); i.onload = () => { IMG[k] = i; res(); }; i.onerror = rej; i.src = src; });
  const L = '../assets/logo/layer_';
  await Promise.all([
    ...['blue_top', 'blue_bot', 'yellow_top', 'yellow_mid', 'yellow_bot', 'plane', 'wordmark'].map(n => load(n, `${L}${n}.png`)),
    load('qr', '../assets/wechat-qr.png'),
    fetch('../assets/land-dots.json').then(r => r.json()).then(d => { LAND = d; }),
    document.fonts.load(font(900, 100)), document.fonts.load('italic ' + font(900, 100)), document.fonts.load(font(600, 100, BODY)), document.fonts.load(font(800, 100, BODY)),
  ]);
  GRAIN = makeGrain();
  LAY = layout();
  return { W, H, KIND };
}

window.MOTION = { setup, renderFrame, SFX, DUR, BPM, SEC };
