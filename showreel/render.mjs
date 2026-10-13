// Renders showreel.html frame-by-frame in headless Chromium and pipes JPEG frames into ffmpeg.
// Usage:
//   node render.mjs                  -> out/showreel_silent.mp4 (1920x1080 @ 60fps)
//   node render.mjs --stills 0.5,3   -> out/still_0.50.png ...
import { spawn, execSync } from 'node:child_process';
import { createRequire } from 'node:module';
import { mkdirSync, writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

// resolve playwright locally, or fall back to the global install
const require = createRequire(import.meta.url);
let pw;
try { pw = require('playwright'); } catch { pw = require(path.join(execSync('npm root -g').toString().trim(), 'playwright')); }
const { chromium } = pw;

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.join(here, 'out');
mkdirSync(outDir, { recursive: true });

const FPS = 60, DURATION = 15;
const args = process.argv.slice(2);
const stillsIdx = args.indexOf('--stills');

const browser = await chromium.launch({ executablePath: process.env.CHROMIUM || '/opt/pw-browsers/chromium' }).catch(() => chromium.launch());
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
page.on('pageerror', e => { console.error('PAGE ERROR', e); process.exit(1); });
await page.goto('file://' + path.join(here, 'showreel.html') + '?headless');
await page.evaluate(() => window.READY);

const grab = (t, type) => page.evaluate(([t, type]) => {
  window.render(t);
  return document.getElementById('c').toDataURL(type, 0.95);
}, [t, type]);

if (stillsIdx >= 0) {
  for (const s of args[stillsIdx + 1].split(',').map(Number)) {
    const url = await grab(s, 'image/png');
    writeFileSync(path.join(outDir, `still_${s.toFixed(2)}.png`), Buffer.from(url.split(',')[1], 'base64'));
  }
} else {
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'mjpeg', '-i', '-',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart',
    path.join(outDir, 'showreel_silent.mp4')], { stdio: ['pipe', 'inherit', 'inherit'] });
  const total = FPS * DURATION, t0 = Date.now();
  for (let f = 0; f < total; f++) {
    const url = await grab(f / FPS, 'image/jpeg');
    if (!ff.stdin.write(Buffer.from(url.split(',')[1], 'base64'))) await new Promise(r => ff.stdin.once('drain', r));
    if (f % 60 === 0) console.log(`frame ${f}/${total}  ${((Date.now() - t0) / 1000).toFixed(1)}s`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
}
await browser.close();
