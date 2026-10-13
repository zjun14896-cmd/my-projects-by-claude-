// Render the promo with headless Chromium.
//   node render/render.mjs frames <format> <t1,t2,...> <outDir>   → PNG stills
//   node render/render.mjs video  <format> <out.mp4> [fps]         → silent H.264
//   node render/render.mjs sfx    <out.json>                       → sound cue list
// format: 9x16 | 1x1 | 16x9
import { createRequire } from 'node:module';
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { spawn } from 'node:child_process';
import { fileURLToPath } from 'node:url';

// playwright from the local install (npm install), else from a global install
let chromium;
try { ({ chromium } = await import('playwright')); }
catch { ({ chromium } = createRequire(path.join(process.execPath, '../../lib/node_modules/'))('playwright')); }
// a pre-installed Chromium if there is one, otherwise Playwright's own (npx playwright install chromium)
const CHROMIUM = process.env.CHROMIUM_PATH || (fs.existsSync('/opt/pw-browsers/chromium') ? '/opt/pw-browsers/chromium' : undefined);
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const SIZES = { '9x16': [1080, 1920], '1x1': [1080, 1080], '16x9': [1920, 1080] };
const TYPES = { '.html': 'text/html', '.js': 'text/javascript', '.png': 'image/png', '.json': 'application/json', '.jpg': 'image/jpeg' };

function serve() {
  return new Promise(res => {
    const srv = http.createServer((req, rsp) => {
      const f = path.join(ROOT, decodeURIComponent(req.url.split('?')[0]));
      if (!f.startsWith(ROOT) || !fs.existsSync(f)) { rsp.writeHead(404); return rsp.end(); }
      rsp.writeHead(200, { 'Content-Type': TYPES[path.extname(f)] || 'application/octet-stream' });
      fs.createReadStream(f).pipe(rsp);
    }).listen(0, () => res(srv));
  });
}

async function open(format) {
  const srv = await serve();
  const browser = await chromium.launch({ executablePath: CHROMIUM });
  const page = await browser.newPage({ viewport: { width: 800, height: 800 } });
  page.on('pageerror', e => console.error('PAGE ERROR', e));
  await page.goto(`http://localhost:${srv.address().port}/src/index.html`);
  const [w, h] = SIZES[format];
  const info = await page.evaluate(([w, h]) => window.MOTION.setup(w, h), [w, h]);
  return { srv, browser, page, info };
}
async function grab(page, t) {
  const b64 = await page.evaluate(t => { window.MOTION.renderFrame(t); return document.getElementById('c').toDataURL('image/png').split(',')[1]; }, t);
  return Buffer.from(b64, 'base64');
}

const [mode, ...args] = process.argv.slice(2);
if (mode === 'frames') {
  const [format, ts, outDir] = args;
  fs.mkdirSync(outDir, { recursive: true });
  const { srv, browser, page } = await open(format);
  for (const t of ts.split(',').map(Number)) fs.writeFileSync(path.join(outDir, `${format}_${t.toFixed(3)}.png`), await grab(page, t));
  await browser.close(); srv.close();
} else if (mode === 'video') {
  const [format, out, fpsArg] = args;
  const fps = Number(fpsArg || 60);
  const { srv, browser, page } = await open(format);
  const dur = await page.evaluate(() => window.MOTION.DUR);
  const n = Math.round(dur * fps);
  const ff = spawn('ffmpeg', ['-y', '-v', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'png', '-i', '-',
    '-c:v', 'libx264', '-preset', 'slow', '-crf', '16', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', out], { stdio: ['pipe', 'inherit', 'inherit'] });
  const t0 = Date.now();
  for (let i = 0; i < n; i++) {
    const buf = await grab(page, i / fps);
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 120 === 0) console.log(`${format} frame ${i}/${n} (${((Date.now() - t0) / 1000).toFixed(0)}s)`);
  }
  ff.stdin.end();
  await new Promise(r => ff.on('close', r));
  await browser.close(); srv.close();
} else if (mode === 'sfx') {
  const { srv, browser, page } = await open('9x16');
  const data = await page.evaluate(() => ({ bpm: window.MOTION.BPM, dur: window.MOTION.DUR, sections: window.MOTION.SEC, cues: window.MOTION.SFX }));
  fs.writeFileSync(args[0], JSON.stringify(data, null, 1));
  await browser.close(); srv.close();
} else {
  console.error('usage: render.mjs frames|video|sfx ...'); process.exit(1);
}
