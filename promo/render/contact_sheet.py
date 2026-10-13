"""Tile rendered stills into a labelled contact sheet.

usage: python3 contact_sheet.py OUT.png TILE_HEIGHT COLS "label|path" ...
"""
import sys
from PIL import Image, ImageDraw, ImageFont

out, tile_h, cols = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
items = [a.split('|', 1) for a in sys.argv[4:]]
ims = [Image.open(p).convert('RGB') for _, p in items]
tw = round(ims[0].width * tile_h / ims[0].height)
pad, lab = 16, 44
rows = (len(ims) + cols - 1) // cols
sheet = Image.new('RGB', (cols * (tw + pad) + pad, rows * (tile_h + lab + pad) + pad), '#14161c')
d = ImageDraw.Draw(sheet)
try:
    f = ImageFont.truetype('/usr/share/fonts/opentype/inter/Inter-SemiBold.otf', 22)
except OSError:
    f = ImageFont.load_default()
for i, ((label, _), im) in enumerate(zip(items, ims)):
    x = pad + (i % cols) * (tw + pad)
    y = pad + (i // cols) * (tile_h + lab + pad)
    d.text((x, y + 8), label, fill='#e8ecf4', font=f)
    sheet.paste(im.resize((tw, tile_h), Image.LANCZOS), (x, y + lab))
sheet.save(out)
