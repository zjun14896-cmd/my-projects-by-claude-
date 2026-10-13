#!/usr/bin/env bash
# Full build: cue list → soundtrack → silent videos → final mp4s (+ optional voiceover).
#
#   ./render/build.sh                                  # render everything
#   ./render/build.sh --voice vo.wav                   # add a voiceover, music ducks under it
#   ./render/build.sh --voice vo.wav --voice-offset 0.5 --voice-gain 1.2
#   ./render/build.sh --remux --voice vo.wav           # reuse the rendered pictures, only redo sound
#   ./render/build.sh --formats "9x16" --fps 30        # quicker draft
#
# Outputs land in output/yuntuohui-promo-<format>.mp4
set -euo pipefail
cd "$(dirname "$0")/.."

FORMATS="9x16 1x1 16x9"; FPS=60; VOICE=""; VOFF=0; VGAIN=1.0; REMUX=0
while [ $# -gt 0 ]; do
  case "$1" in
    --voice) VOICE="$2"; shift 2;;
    --voice-offset) VOFF="$2"; shift 2;;
    --voice-gain) VGAIN="$2"; shift 2;;
    --formats) FORMATS="$2"; shift 2;;
    --fps) FPS="$2"; shift 2;;
    --remux) REMUX=1; shift;;
    *) echo "unknown option $1"; exit 1;;
  esac
done
mkdir -p build output

node render/render.mjs sfx build/sfx.json
python3 render/audio.py build/sfx.json build/audio.wav

if [ "$REMUX" = 0 ]; then
  pids=()
  for f in $FORMATS; do
    node render/render.mjs video "$f" "build/$f-silent.mp4" "$FPS" > "build/log-$f.txt" 2>&1 & pids+=($!)
  done
  for p in "${pids[@]}"; do wait "$p"; done
fi

for f in $FORMATS; do
  out="output/yuntuohui-promo-$f.mp4"
  if [ -n "$VOICE" ]; then
    delay=$(python3 -c "print(int(float('$VOFF')*1000))")
    ffmpeg -v error -y -i "build/$f-silent.mp4" -i build/audio.wav -i "$VOICE" -filter_complex \
      "[2:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=$VGAIN,adelay=$delay:all=1,apad,asplit=2[vsc][vmix];\
       [1:a][vsc]sidechaincompress=threshold=0.02:ratio=8:attack=15:release=400:makeup=1[duck];\
       [duck][vmix]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[a]" \
      -map 0:v -map "[a]" -c:v copy -c:a aac -b:a 256k -ar 48000 -shortest -movflags +faststart "$out"
  else
    ffmpeg -v error -y -i "build/$f-silent.mp4" -i build/audio.wav -map 0:v -map 1:a -c:v copy \
      -af loudnorm=I=-14:TP=-1.5:LRA=11 -c:a aac -b:a 256k -ar 48000 -shortest -movflags +faststart "$out"
  fi
  echo "wrote $out"
done

# the QR code must still scan in the last frame
python3 - "$FORMATS" <<'EOF' || echo "(QR check skipped: pip install zxing-cpp pillow)"
import subprocess, sys, zxingcpp
from PIL import Image
for f in sys.argv[1].split():
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-ss', '19.8', '-i', f'output/yuntuohui-promo-{f}.mp4', '-frames:v', '1', f'build/end-{f}.png'], check=True)
    codes = [c.text for c in zxingcpp.read_barcodes(Image.open(f'build/end-{f}.png'))]
    print(f'QR {f}:', codes or 'NOT FOUND')
EOF
