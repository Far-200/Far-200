#!/usr/bin/env python3
"""
generate_profile_art.py

Emits a purple dot-matrix `</>` glyph made entirely of SVG <circle> elements,
sized to sit in the left column of assets/profile-terminal.svg.

The glyph is constructed geometrically -- three groups of thick line segments
rasterised onto the same 48x48 dot grid the hero has always used. There is no
source image and no thresholding step, so the output is fully deterministic
and cannot drift back to whatever raster happens to sit in assets/.

Why circles instead of a <path> or an embedded raster:
GitHub sanitizes README SVGs and strips a lot of exotic markup, and a raster
<image> tag baked into a profile SVG is both against the design brief and
fragile across renderers. Vector circles are cheap, always render, and give
the "terminal halftone" look we want.

Dependencies: Python standard library only.

Usage:
    python3 generate_profile_art.py

Reads:
    nothing
Writes:
    ../assets/profile-art.svg   (a standalone <g> fragment, viewBox-aligned,
                                  consumed by assemble_hero.py)
"""

import math
import os
import random

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "..", "assets", "profile-art.svg")

# Grid resolution. Unchanged from the previous pipeline so the dot pitch and
# radii still match the rest of the hero's visual language.
GRID_COLS = 48
GRID_ROWS = 48

# Target footprint inside the hero SVG (matches the left column in
# profile-terminal.svg -- keep these two files in sync if you resize either).
ART_WIDTH = 540
ART_HEIGHT = 540

# Purple palette (matches the hero SVG palette so the art doesn't clash)
DOT_COLOR = "#c084fc"
DOT_COLOR_DIM = "#a855f7"

# --- glyph geometry, in art-space units ------------------------------------

# Horizontal centre of the artwork column.
GLYPH_CX = ART_WIDTH / 2.0

# Vertical centre. Nudged above the box centre (270) so the glyph optically
# aligns with the right-hand info block, which spans roughly y=178..542 in
# hero coordinates. The art group is translate(52,150) scale(0.889), so
# art-space 236 lands at hero y ~= 360, the middle of that text block.
GLYPH_CY = 236.0

# Segment spans, not the final dot footprint: dots reach half a stroke width
# past each endpoint, so the rendered bbox ends up ~34 units larger in both
# axes. 409+34 = 443 (82% of width) and 252+34 = 286 (53% of height).
GLYPH_WIDTH = 409.0
GLYPH_HEIGHT = 252.0

CHEVRON_RUN = 102.0        # horizontal run of each chevron arm
SLASH_RUN = 71.0           # horizontal run of the slash
# Remaining width splits into two equal gaps: 409 - 102 - 71 - 102 = 134,
# i.e. 67 units of clearance on each side of the slash.

STROKE_WIDTH = 34.0        # ~3 dot rows across, survives 50% downscale
EDGE_BAND = 10.0           # falloff ring just outside the core stroke

# --- dot treatment ---------------------------------------------------------

CELL = min(ART_WIDTH / GRID_COLS, ART_HEIGHT / GRID_ROWS)  # 11.25

CORE_R = (4.30, CELL * 0.46)      # 4.30 .. 5.175
CORE_OPACITY = (0.85, 1.00)
EDGE_R = (2.00, 4.00)
EDGE_OPACITY = (0.30, 0.75)

JITTER = 1.1               # organic wobble so the grid doesn't read as CAD
SEED = 20260731            # fixed: every run yields a byte-identical file

SCATTER_RATIO = 0.08       # peripheral dots, as a fraction of core-dot count
SCATTER_REACH = 32.0
SCATTER_R = (1.5, 2.6)
SCATTER_OPACITY = (0.12, 0.34)


# ---------------------------------------------------------------------------
# Glyph construction
# ---------------------------------------------------------------------------


def build_segments():
    """Return the thick line segments composing `</>`, as ((x0,y0),(x1,y1)).

    `<` is two diagonals meeting at a left-hand apex, `>` mirrors it, and `/`
    is a single diagonal rising left-to-right between them.
    """
    half_h = GLYPH_HEIGHT / 2.0
    top = GLYPH_CY - half_h
    bot = GLYPH_CY + half_h

    x_left = GLYPH_CX - GLYPH_WIDTH / 2.0
    x_right = GLYPH_CX + GLYPH_WIDTH / 2.0

    # `<` : apex on the left, arms opening to the right
    left_chevron = [
        ((x_left + CHEVRON_RUN, top), (x_left, GLYPH_CY)),
        ((x_left, GLYPH_CY), (x_left + CHEVRON_RUN, bot)),
    ]

    # `>` : mirrored
    right_chevron = [
        ((x_right - CHEVRON_RUN, top), (x_right, GLYPH_CY)),
        ((x_right, GLYPH_CY), (x_right - CHEVRON_RUN, bot)),
    ]

    # `/` : lower-left to upper-right, centred between the chevrons
    slash_x0 = GLYPH_CX - SLASH_RUN / 2.0
    slash = [((slash_x0, bot), (slash_x0 + SLASH_RUN, top))]

    return left_chevron + slash + right_chevron


def dist_to_segment(px, py, a, b):
    """Shortest distance from a point to a finite line segment."""
    (ax, ay), (bx, by) = a, b
    dx, dy = bx - ax, by - ay
    denom = dx * dx + dy * dy
    if denom == 0.0:
        return math.hypot(px - ax, py - ay)
    t = ((px - ax) * dx + (py - ay) * dy) / denom
    t = max(0.0, min(1.0, t))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


def min_dist(px, py, segments):
    return min(dist_to_segment(px, py, a, b) for a, b in segments)


def lerp(a, b, t):
    return a + (b - a) * t


# ---------------------------------------------------------------------------
# Rasteriser
# ---------------------------------------------------------------------------


def generate_dots():
    """Walk the 48x48 grid in a fixed order and classify each cell by its
    distance to the glyph: inside the stroke (core), just outside (edge), or
    too far (skipped). Returns (core, edge, scatter) lists of dot tuples."""
    rng = random.Random(SEED)
    segments = build_segments()
    half = STROKE_WIDTH / 2.0
    reach = half + EDGE_BAND

    cell_w = ART_WIDTH / GRID_COLS
    cell_h = ART_HEIGHT / GRID_ROWS

    core, edge = [], []

    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            cx = col * cell_w + cell_w / 2.0
            cy = row * cell_h + cell_h / 2.0
            jx = cx + rng.uniform(-JITTER, JITTER)
            jy = cy + rng.uniform(-JITTER, JITTER)

            d = min_dist(jx, jy, segments)
            if d > reach:
                continue

            if d <= half:
                # Solid stroke interior; taper very slightly toward the edge
                # so the glyph keeps a little organic variation.
                t = d / half
                core.append((jx, jy,
                             lerp(CORE_R[1], CORE_R[0], t),
                             lerp(CORE_OPACITY[1], CORE_OPACITY[0], t),
                             DOT_COLOR))
            else:
                t = (d - half) / EDGE_BAND      # 0 at stroke edge -> 1 outward
                edge.append((jx, jy,
                             lerp(EDGE_R[1], EDGE_R[0], t),
                             lerp(EDGE_OPACITY[1], EDGE_OPACITY[0], t),
                             DOT_COLOR_DIM))

    # Restrained peripheral scatter. Supports the glyph, never a purple cloud.
    target = int(len(core) * SCATTER_RATIO)
    scatter = []
    attempts = 0
    while len(scatter) < target and attempts < target * 400:
        attempts += 1
        px = rng.uniform(0, ART_WIDTH)
        py = rng.uniform(0, ART_HEIGHT)
        d = min_dist(px, py, segments)
        if reach < d <= reach + SCATTER_REACH:
            t = (d - reach) / SCATTER_REACH
            scatter.append((px, py,
                            lerp(SCATTER_R[1], SCATTER_R[0], t),
                            lerp(SCATTER_OPACITY[1], SCATTER_OPACITY[0], t),
                            DOT_COLOR_DIM))

    return core, edge, scatter


def circle(dot):
    cx, cy, r, opacity, color = dot
    return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
            f'fill="{color}" fill-opacity="{opacity:.2f}"/>')


def generate_svg_fragment():
    core, edge, scatter = generate_dots()
    # Draw order: faintest first so the bright stroke sits on top.
    dots = scatter + edge + core
    fragment = (
        '<g id="code-glyph-dot-matrix" aria-hidden="true">\n  '
        + "\n  ".join(circle(d) for d in dots)
        + "\n</g>\n"
    )
    return fragment, len(core), len(edge), len(scatter)


def main():
    fragment, n_core, n_edge, n_scatter = generate_svg_fragment()
    with open(OUTPUT_PATH, "w", encoding="utf-8", newline="\n") as f:
        f.write(fragment)
    print(f"Wrote {len(fragment)} bytes to {OUTPUT_PATH}")
    print(f"  core={n_core}  edge={n_edge}  scatter={n_scatter} "
          f"({n_scatter / n_core * 100:.1f}% of core)")
    print("Now run assemble_hero.py to rebuild assets/profile-terminal.svg.")


if __name__ == "__main__":
    main()
