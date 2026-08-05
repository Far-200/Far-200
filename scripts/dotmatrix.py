#!/usr/bin/env python3
"""
dotmatrix.py

Shared primitives for every piece of dot-matrix artwork that can sit in the
left column of assets/profile-terminal.svg.

A "dot" is a plain tuple: (cx, cy, r, opacity, colour). Every subject module
(art_code.py, art_portrait.py) does nothing but produce lists of those; this
module owns the art-space dimensions, the palette, and the SVG emission, so
the subjects can never drift out of sync with each other or with the hero.

Dependencies: Python standard library only.
"""

import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.join(SCRIPT_DIR, "..", "assets")

# ---------------------------------------------------------------------------
# Art-space geometry
# ---------------------------------------------------------------------------
# The hero embeds this fragment with transform="translate(52,150) scale(0.889)",
# so art-space (0,0)-(540,540) maps to hero-space (52,150)-(532,630).
# Keep these in sync with assemble_hero.py if either side is ever resized.

ART_WIDTH = 540
ART_HEIGHT = 540

HERO_SCALE = 0.889
HERO_OFFSET = (52, 150)

# ---------------------------------------------------------------------------
# Palette (matches assemble_hero.py so artwork never clashes with the chrome)
# ---------------------------------------------------------------------------

DOT_COLOR = "#c084fc"       # bright purple, focal detail
DOT_COLOR_DIM = "#a855f7"   # dimmer purple, supporting mass


def lerp(a, b, t):
    return a + (b - a) * t


def clamp(v, lo=0.0, hi=1.0):
    return lo if v < lo else hi if v > hi else v


def circle(dot):
    """Render one dot tuple as an SVG <circle>."""
    cx, cy, r, opacity, color = dot
    return (f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" '
            f'fill="{color}" fill-opacity="{opacity:.2f}"/>')


def fragment(dots, group_id, band=None):
    """Wrap dots in the <g> fragment that assemble_hero.py splices in.

    band=None writes one fully-specified <circle> per dot -- simple, and what
    the `</>` glyph has always emitted.

    band=N quantises opacity to N levels and hoists fill/fill-opacity onto
    shared <g> wrappers. A tonal portrait needs thousands of dots, and at that
    count repeating two colour attributes on every circle roughly doubles the
    file. Grouping is plain SVG that GitHub's sanitiser passes untouched, and
    at N>=32 the banding is not visible.
    """
    if band is None:
        return (f'<g id="{group_id}" aria-hidden="true">\n  '
                + "\n  ".join(circle(d) for d in dots)
                + "\n</g>\n")

    groups = {}
    for cx, cy, r, opacity, color in dots:
        key = (color, round(round(opacity * band) / band, 3))
        groups.setdefault(key, []).append(f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}"/>')

    lines = []
    for (color, opacity), items in groups.items():
        lines.append(f'<g fill="{color}" fill-opacity="{opacity:g}">'
                     + "".join(items) + '</g>')
    return (f'<g id="{group_id}" aria-hidden="true">\n  '
            + "\n  ".join(lines) + "\n</g>\n")


def write_fragment(dots, group_id, path, band=None):
    text = fragment(dots, group_id, band)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    return len(text)


def standalone_svg(dots, group_id, background=None, band=None):
    """Wrap dots in a self-contained SVG for previewing the art on its own."""
    bg = (f'<rect width="{ART_WIDTH}" height="{ART_HEIGHT}" fill="{background}"/>'
          if background else "")
    return (f'<svg viewBox="0 0 {ART_WIDTH} {ART_HEIGHT}" '
            f'xmlns="http://www.w3.org/2000/svg">{bg}\n'
            + fragment(dots, group_id, band) + "</svg>\n")
