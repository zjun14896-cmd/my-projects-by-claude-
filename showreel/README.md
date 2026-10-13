# Showreel — "Made by Brooke"

`showreel.mp4`: a 15-second 1920×1080 @ 60fps motion graphics reel with a synthesized soundtrack.

Every frame is generated in code: `showreel.html` exposes a pure `render(t)` canvas function, and you can open the file in a browser for a live loop.

| Time | Scene |
|---|---|
| 0.0–1.8 | Intro: the dot bursts into a shockwave, then **MOTION** |
| 1.8–3.7 | Kinetic type with a live cubic-bezier graph |
| 3.7–5.6 | Shape morphs with echo trails over a ripple field |
| 5.6–7.7 | 4,200 particles assemble into **KINETIC**, then explode |
| 7.7–9.6 | 3D point cloud: sphere, then torus, then knot |
| 9.6–11.5 | Procedural ridge lines (**FLOW**) |
| 11.5–12.7 | Rapid-cut montage |
| 12.7–15.0 | Signature card: **Made by Brooke** |

## Rebuild
```sh
node render.mjs                 # frames → out/showreel_silent.mp4 (headless Chromium + ffmpeg)
python3 audio.py                # out/soundtrack.wav (numpy)
ffmpeg -i out/showreel_silent.mp4 -i out/soundtrack.wav -c:v libx264 -preset slow -crf 24 \
  -pix_fmt yuv420p -c:a aac -b:a 256k -shortest -movflags +faststart showreel.mp4
```
