#!/usr/bin/env python3
"""
generate_profile_art.py

Converts assets/profile-source.png (the Quackrates mascot artwork) into a
purple dot-matrix halftone made entirely of SVG <circle> elements, sized to
sit in the left column of assets/profile-terminal.svg.

Why circles instead of embedding the raster image directly:
GitHub sanitizes README SVGs and strips a lot of exotic markup, and a raster
<image> tag baked into a profile SVG is both against the design brief and
fragile across renderers. Vector circles are cheap, always render, and give
the "terminal halftone" look we want.

Usage:
    python3 generate_profile_art.py

Reads:
    ../assets/profile-source.png
Writes:
    ../assets/profile-art.svg   (a standalone <g> fragment, viewBox-aligned,
                                  meant to be pasted into profile-terminal.svg)
"""

import sys
import os

try:
    from PIL import Image
except ImportError:
    sys.exit(
        "Pillow is required. Install with: pip install Pillow --break-system-packages"
    )

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_PATH = os.path.join(SCRIPT_DIR, "..", "assets", "profile-source.png")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "..", "assets", "profile-art.svg")

# Grid resolution. Higher = more detail but bigger file.
GRID_COLS = 48
GRID_ROWS = 48

# Target footprint inside the hero SVG (matches the left column in
# profile-terminal.svg -- keep these two files in sync if you resize either).
ART_WIDTH = 540
ART_HEIGHT = 540

# Purple palette (matches the hero SVG palette so the art doesn't clash)
DOT_COLOR = "#c084fc"
DOT_COLOR_DIM = "#a855f7"

# Dots below this brightness threshold (0-255, after inversion) are skipped
# entirely so the background stays clean instead of full-bleed grey.
MIN_VISIBLE_LEVEL = 18


def load_and_flatten(path):
    """Load the source PNG and flatten transparency onto a dark background
    so alpha-heavy edges don't turn into stray light dots."""
    if not os.path.exists(path):
        sys.exit(
            f"Source image not found at {path}\n"
            "Expected assets/profile-source.png (the Quackrates artwork). "
            "Add the file and re-run."
        )
    im = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", im.size, (13, 17, 23, 255))  # #0d1117
    flattened = Image.alpha_composite(bg, im).convert("L")
    return flattened


def build_grid(im, cols, rows):
    """Downsample to a cols x rows brightness grid (0-255)."""
    small = im.resize((cols, rows), Image.LANCZOS)
    return list(small.getdata()), small.width, small.height


def brightness_to_radius(level, cell_size):
    """Darker source pixels (the subject) become bigger dots; light
    background pixels shrink toward nothing. `level` is inverted brightness
    (0 = background, 255 = subject)."""
    max_r = cell_size * 0.46
    min_r = cell_size * 0.06
    t = level / 255.0
    return min_r + (max_r - min_r) * t


def generate_svg_fragment(cols=GRID_COLS, rows=GRID_ROWS):
    im = load_and_flatten(SOURCE_PATH)
    pixels, w, h = build_grid(im, cols, rows)

    cell_w = ART_WIDTH / cols
    cell_h = ART_HEIGHT / rows

    circles = []
    for row in range(rows):
        for col in range(cols):
            raw = pixels[row * cols + col]
            # The source is flattened onto the same dark tone as the hero
            # canvas, so transparent background pixels are already dark.
            # Brighter pixels are the subject (Quackrates is a light duck
            # with dark linework) -- no inversion needed, dots simply
            # follow brightness.
            level = raw
            if level < MIN_VISIBLE_LEVEL:
                continue
            cx = col * cell_w + cell_w / 2
            cy = row * cell_h + cell_h / 2
            r = brightness_to_radius(level, min(cell_w, cell_h))
            color = DOT_COLOR if level > 150 else DOT_COLOR_DIM
            opacity = round(min(1.0, 0.25 + (level / 255.0) * 0.75), 2)
            circles.append(
                f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
                f'fill="{color}" fill-opacity="{opacity}"/>'
            )

    fragment = (
        f'<g id="quackrates-dot-matrix" aria-hidden="true">\n  '
        + "\n  ".join(circles)
        + "\n</g>\n"
    )
    return fragment


def main():
    fragment = generate_svg_fragment()
    with open(OUTPUT_PATH, "w") as f:
        f.write(fragment)
    print(f"Wrote {len(fragment)} bytes to {OUTPUT_PATH}")
    print("Paste the <g id=\"quackrates-dot-matrix\">...</g> block into "
          "profile-terminal.svg's left column, or re-run the hero assembly "
          "step if you have one.")


if __name__ == "__main__":
    main()
