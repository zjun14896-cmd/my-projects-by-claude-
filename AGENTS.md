# AGENTS.md — 云拓会 (Yuntuohui) promo video

This repo holds a 20-second brand promo for 云拓会, a cross-border e-commerce
training and global-expansion company from Yunnan. Everything is code. There
is no editing-software project file: the picture is drawn on an HTML canvas,
the music is synthesized in Python, and ffmpeg assembles the MP4s. Edit the
code, then re-run the build.

The project lives in `promo/`. Ignore the unrelated `.mp4` at the repo root.

## Layout

```
promo/
  src/motion.js        the whole animation: one timeline, three aspect ratios
  src/index.html       page that hosts the canvas
  render/render.mjs    headless Chromium: renders stills, silent videos, exports sound cues
  render/audio.py      original 120 BPM soundtrack + UI sound effects (numpy)
  render/build.sh      one-command build, incl. optional voiceover with music ducking
  render/contact_sheet.py  tiles stills into a review sheet
  assets/logo/         the real logo, split into layers (stripes, swoosh, plane, wordmark)
  assets/wechat-qr.png the WeChat Official Account QR code (rebuilt sharp from assets/source/)
  assets/land-dots.json  dot grid for the globe
  output/              final MP4s: yuntuohui-promo-{9x16,1x1,16x9}.mp4
  preview/             contact sheets (one frame per story beat)
```

## Setup (once)

```sh
cd promo
npm install                          # playwright
npx playwright install chromium      # skip if CHROMIUM_PATH points at a Chromium
pip install -r requirements.txt      # numpy, pillow, zxing-cpp
# also needs ffmpeg on PATH
```

## Build

```sh
cd promo
./render/build.sh                                        # everything, about 5 min
./render/build.sh --formats 9x16 --fps 30                # quick draft
./render/build.sh --voice vo.wav --voice-offset 0.3      # add a voiceover
./render/build.sh --remux --voice vo.wav                 # sound-only change: reuse rendered pictures
node render/render.mjs frames 9x16 2.45,5.5,19.5 build/stills   # check a few frames as PNGs
```

`--remux` reuses `build/*-silent.mp4`, so it only works after a full render in
the same checkout. `build/` is git-ignored.

## How to change things

- **Text.** All on-screen copy is in the `COPY` object at the top of
  `src/motion.js`. The hook must stay exactly 5 words, one per beat; each
  format lists its own line breaks. Text sizes fit automatically.
- **Colors.** The `C` object (brand blue `#003CAC`, yellow `#FFC833`, navy `#00133D`).
- **Timing.** `SEC` holds the section boundaries. Wipes sit at those boundaries
  (`WIPES`). Sound cues are pushed with `cue(t, type, gain)` right next to the
  visuals they belong to. Keep times on the 120 BPM grid (multiples of 0.125s)
  so picture and music stay locked. `render.mjs sfx` exports the cues, and
  `audio.py` reads them, so sound follows automatically.
- **Scenes.** `sceneHook`, `sceneLogo`, `sceneF1` (globe), `sceneF2` (0→1 slider),
  `sceneF3` (community ring), `sceneMetric` (365), `sceneCTA` (logo + QR).
  Each one is a pure function of time `t`, so any frame can be rendered alone.
- **Layout per format.** `layout()` computes positions for portrait (9:16),
  square (1:1) and landscape (16:9). After any visual change, check all three.
- **Music.** `render/audio.py` holds the chord progression (`CHORDS`), drums and
  arrangement. The `SYN` map holds the sound-effect synths.
- **Voiceover.** Pass a WAV/MP3 to `build.sh --voice`. The music is
  sidechain-ducked under the voice and the mix is normalised to -14 LUFS.
  `--voice-offset` (seconds) positions it; `--voice-gain` sets its level.

## Rules

- Never redraw the logo. Use the layers in `assets/logo/`.
- The QR code must stay scannable. `build.sh` decodes the last frame of each
  output and prints the link; it must read
  `http://weixin.qq.com/r/mp/jyf07BfEEUpurVOP93Kd`. Nothing may overlap the QR
  card after 18s, and film grain is masked off it.
- Do not invent statistics, testimonials or client names. Copy may only claim
  what the company offers: cross-border e-commerce training, global expansion
  services for Yunnan enterprises, beginner 0→1 training, and 12 months of
  online community coaching (陪跑).
- Before re-rendering everything, render stills of the changed beats and look at them.
