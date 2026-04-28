#!/usr/bin/env python3
"""
generate_icons.py — Creates all extension icons programmatically.

Generates:
  icons/icon16.png   — 16x16  toolbar icon
  icons/icon48.png   — 48x48  extension management icon
  icons/icon128.png  — 128x128 Chrome Web Store icon

Requires: pip install Pillow --break-system-packages
Run from extension/ directory: python generate_icons.py
"""
import os
import math
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    print("Installing Pillow...")
    os.system("pip install Pillow --break-system-packages -q")
    from PIL import Image, ImageDraw, ImageFont


ICONS_DIR = Path(__file__).parent / "icons"
ICONS_DIR.mkdir(exist_ok=True)

# Brand colours
BG_COLOR     = (30, 30, 46)       # #1e1e2e  dark background
BLUE         = (137, 180, 250)     # #89b4fa  primary blue
WHITE        = (255, 255, 255)
DARK         = (30, 30, 46)

def draw_icon(size: int) -> Image.Image:
    """Draw the AI Trade Validator camera + chart icon."""
    img  = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    pad  = size * 0.06

    # ── Background rounded rect ──────────────────────────────────
    r = size * 0.22
    draw.rounded_rectangle(
        [pad, pad, size - pad, size - pad],
        radius=r,
        fill=BG_COLOR,
    )

    # ── Camera body ──────────────────────────────────────────────
    cx   = size * 0.5
    cy   = size * 0.55
    bw   = size * 0.60
    bh   = size * 0.36
    bl   = cx - bw / 2
    bt   = cy - bh / 2

    draw.rounded_rectangle(
        [bl, bt, bl + bw, bt + bh],
        radius=size * 0.06,
        fill=BLUE,
    )

    # Camera viewfinder bump
    bump_w = bw * 0.32
    bump_h = size * 0.10
    draw.rounded_rectangle(
        [cx - bump_w / 2, bt - bump_h, cx + bump_w / 2, bt + 2],
        radius=size * 0.04,
        fill=BLUE,
    )

    # Camera lens
    lens_r = bh * 0.30
    draw.ellipse(
        [cx - lens_r, cy - lens_r, cx + lens_r, cy + lens_r],
        fill=BG_COLOR,
    )
    inner_r = lens_r * 0.55
    draw.ellipse(
        [cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r],
        fill=BLUE,
    )

    # ── Chart bars (bottom-left of camera) ───────────────────────
    if size >= 48:
        bar_x  = bl + bw * 0.08
        bar_y  = bt + bh - size * 0.05
        bar_w  = size * 0.055
        heights = [0.14, 0.22, 0.10, 0.18]
        colors  = [WHITE, WHITE, WHITE, WHITE]
        gap = bar_w * 1.4
        for i, (h, c) in enumerate(zip(heights, colors)):
            bx = bar_x + i * gap
            bh2 = size * h
            draw.rectangle(
                [bx, bar_y - bh2, bx + bar_w, bar_y],
                fill=(255, 255, 255, 180),
            )

    return img


def save_icon(size: int):
    img  = draw_icon(size)
    path = ICONS_DIR / f"icon{size}.png"
    img.save(path, "PNG")
    print(f"  ✅ icons/icon{size}.png  ({size}×{size})")


if __name__ == "__main__":
    print("Generating extension icons…")
    for sz in [16, 48, 128]:
        save_icon(sz)
    print(f"\nAll icons saved to {ICONS_DIR}")
    print("You can replace these with custom artwork before publishing.")
