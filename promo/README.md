# 云拓会 · 20s motion promo

One timeline (`src/motion.js`), rendered to 9:16, 1:1 and 16:9. Every frame is a
pure function of time, and every sound cue is exported from the same timeline,
so picture and sound stay locked to the 120 BPM grid.

| Beat | Time | Content |
|---|---|---|
| 1 Hook | 0–3s | "GOING GLOBAL FEELS TOO HARD?", one word slammed per beat |
| 2 Product | 3–6s | Logo assembles from its real layers (stripes, orbit, plane, wordmark) |
| 3a | 6–8.5s | Cursor clicks Yunnan on a dotted globe, routes fly to Europe / Middle East / SE Asia / Japan |
| 3b | 8.5–11s | Cursor drags 0 → 1: Open a store → List products → First order |
| 3c | 11–13.5s | Cursor clicks JOIN, members and chat join a 12-month ring |
| 4 Number | 13.5–16.5s | 365 days of coaching · Beginners / Sellers / Enterprises |
| 5 CTA | 16.5–20s | Logo lockup + WeChat QR, "Follow us on WeChat" |

## Assets (`assets/`)
- `source/logo-original.png`: the logo as supplied
- `logo/layer_*.png`: the logo split by colour region into animatable layers (same canvas, so they stack exactly)
- `wechat-qr.png`: the supplied QR code, cropped (decodes to the same link as the original)
- `land-dots.json`: land/sea dot grid for the globe (from `global-land-mask`)

## Render
```sh
node render/render.mjs sfx build/sfx.json            # sound cue list from the timeline
python3 render/audio.py build/sfx.json build/audio.wav
node render/render.mjs frames 9x16 2.45,5.5 build/sheet   # stills
node render/render.mjs video 9x16 build/9x16.mp4 60       # silent video
ffmpeg -i build/9x16.mp4 -i build/audio.wav -c:v copy -c:a aac -b:a 256k -af loudnorm=I=-14:TP=-1 out.mp4
```
Needs Chromium via Playwright, ffmpeg, Python with numpy + Pillow.
