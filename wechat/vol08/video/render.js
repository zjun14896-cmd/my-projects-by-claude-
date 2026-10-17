// 逐帧渲染 overlay.html：图形层（透明 PNG）、毛玻璃遮罩、「08」字形遮罩。
// 用法：node render.js <输出目录> <字体CSS> [帧列表，如 0,30,60 或 all]
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path');
const [,, outDir, fontCss, which = 'all'] = process.argv;
const FPS = 30, TOTAL = 540;
const GLASS = [118, 422];            // 4–14s 的 HUD 区间（多留两帧余量）
(async () => {
  for (const d of ['ov', 'gl']) fs.mkdirSync(path.join(outDir, d), { recursive: true });
  const b = await chromium.launch({ executablePath: '/opt/pw-browsers/chromium-1194/chrome-linux/chrome', args: ['--allow-file-access-from-files'] });
  const p = await b.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  await p.goto('file://' + path.resolve(__dirname, 'overlay.html'));
  await p.addStyleTag({ content: fs.readFileSync(fontCss, 'utf8') });
  await p.evaluate(async () => {
    await document.fonts.ready;
    await document.fonts.load('800 100px Inter');
    await document.fonts.load('700 100px "PingFang SC"', '五天把路走通第期招生中讲一步做对你的情况从拍摄到剪辑教学用新工具跨境整件事头梳理遍');
  });
  await p.evaluate(() => renderFrame(0, 'glyph'));
  await p.screenshot({ path: path.join(outDir, 'glyph.png') });
  const frames = which === 'all' ? [...Array(TOTAL).keys()] : which.split(',').map(Number);
  for (const f of frames) {
    const t = f / FPS, name = `${String(f).padStart(4, '0')}.png`;
    await p.evaluate(([t]) => renderFrame(t, 'overlay'), [t]);
    await p.screenshot({ path: path.join(outDir, 'ov', name), omitBackground: true });
    if (f >= GLASS[0] && f <= GLASS[1]) {
      await p.evaluate(([t]) => renderFrame(t, 'glass'), [t]);
      await p.screenshot({ path: path.join(outDir, 'gl', name) });
    }
  }
  await b.close();
})();
