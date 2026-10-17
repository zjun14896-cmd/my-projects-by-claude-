// 逐帧渲染 overlay.html 的图形层（透明 PNG）与片头遮罩。
// 用法：node render.js <输出目录> <字体CSS> [帧列表，如 0,30,60 或 all]
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const [,, outDir, fontCss, which = 'all'] = process.argv;
const FPS = 30, TOTAL = 450, MATTE_END = 62;
(async () => {
  fs.mkdirSync(path.join(outDir, 'ov'), { recursive: true });
  fs.mkdirSync(path.join(outDir, 'mt'), { recursive: true });
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--allow-file-access-from-files'] });
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await p.goto('file://' + path.resolve(__dirname, 'overlay.html'));
  await p.addStyleTag({ content: fs.readFileSync(fontCss, 'utf8') });
  await p.evaluate(() => document.fonts.ready);
  await p.evaluate(async () => { await document.fonts.load('800 100px Inter'); await document.fonts.load('700 100px "PingFang SC"', '五天把路走通'); });
  const frames = which === 'all' ? [...Array(TOTAL).keys()] : which.split(',').map(Number);
  for (const f of frames) {
    const t = f / FPS;
    await p.evaluate(([t]) => renderFrame(t, 'overlay'), [t]);
    await p.screenshot({ path: path.join(outDir, 'ov', `${String(f).padStart(4, '0')}.png`), omitBackground: true });
    if (f <= MATTE_END) {
      await p.evaluate(([t]) => renderFrame(t, 'matte'), [t]);
      await p.screenshot({ path: path.join(outDir, 'mt', `${String(f).padStart(4, '0')}.png`) });
    }
  }
  await b.close();
})();
