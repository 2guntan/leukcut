#!/usr/bin/env python3
"""Create 18 placeholder stills for the leukcut acceptance test (SPEC.md par.7)."""
from pathlib import Path
import yaml
from PIL import Image, ImageDraw

here = Path(__file__).parent
m = yaml.safe_load((here / "SHORT_01.manifest.yaml").read_text())
out = here / "SHORT_01_LA_LUNE" / "01_STORYBOARD"
out.mkdir(parents=True, exist_ok=True)
colors = [(31,42,90),(19,26,58),(224,166,78),(192,91,51),(110,118,69)]
for i, s in enumerate(m["shots"]):
    im = Image.new("RGB", (1080, 1920), colors[i % len(colors)])
    d = ImageDraw.Draw(im)
    d.text((60, 60), f"{s['id']}  {s['t_in']} -> {s['t_out']}", fill=(255,255,255))
    im.save(out / f"{s['id']}_v01.png")
print(f"18 placeholders in {out}")
