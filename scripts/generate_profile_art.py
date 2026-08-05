#!/usr/bin/env python3
"""
generate_profile_art.py

Emits the purple dot-matrix artwork that fills the left column of
assets/profile-terminal.svg, as a standalone <g> fragment of SVG <circle>
elements consumed by assemble_hero.py.

Two subjects are available:

    code        the original geometric `</>` glyph (art_code.py)
    portrait    a dot-matrix portrait derived from a real photograph
                (art_portrait.py), in three styles

Why circles instead of a <path> or an embedded raster:
GitHub sanitizes README SVGs and strips a lot of exotic markup, and a raster
<image> tag baked into a profile SVG is both against the design brief and
fragile across renderers. Vector circles are cheap, always render, and give
the "terminal halftone" look we want.

Both subjects are deterministic: the same inputs always produce a byte-
identical file.

Usage:
    python3 generate_profile_art.py                          # portrait (default)
    python3 generate_profile_art.py --subject code           # original </> art
    python3 generate_profile_art.py --subject portrait --style structure
    python3 generate_profile_art.py --preview out.svg        # + standalone SVG

Dependencies:
    code      standard library only
    portrait  Pillow, NumPy

Writes:
    ../assets/profile-art.svg   (overridable with --out)
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import dotmatrix  # noqa: E402

DEFAULT_OUT = os.path.join(dotmatrix.ASSETS_DIR, "profile-art.svg")
# The source photograph. A .png of the same name wins if it exists, so the
# asset can be swapped to a lossless original later without touching the code.
def _default_source():
    for name in ("profile-source.png", "profile-source.jpg"):
        path = os.path.join(dotmatrix.ASSETS_DIR, name)
        if os.path.exists(path):
            return path
    return os.path.join(dotmatrix.ASSETS_DIR, "profile-source.jpg")


DEFAULT_SOURCE = _default_source()


def load_subject(name):
    if name == "code":
        import art_code
        return art_code
    if name == "portrait":
        import art_portrait
        return art_portrait
    raise SystemExit(f"unknown subject: {name}")


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--subject", choices=("code", "portrait"), default="portrait",
                   help="which artwork to generate (default: portrait)")
    p.add_argument("--style", default="hybrid",
                   help="portrait style: halftone | structure | hybrid")
    p.add_argument("--source", default=DEFAULT_SOURCE,
                   help="source photograph for --subject portrait")
    p.add_argument("--out", default=DEFAULT_OUT,
                   help="output path for the <g> fragment")
    p.add_argument("--rows", type=int, default=None,
                   help="portrait grid rows (default: 70)")
    p.add_argument("--band", type=int, default=48,
                   help="opacity quantisation levels for portrait output")
    p.add_argument("--preview", default=None,
                   help="also write a standalone, viewable SVG here")
    p.add_argument("--preview-bg", default="#10151c",
                   help="background colour for --preview (use 'none' for clear)")
    args = p.parse_args()

    module = load_subject(args.subject)

    if args.subject == "portrait":
        if not os.path.exists(args.source):
            raise SystemExit(f"source photograph not found: {args.source}")
        dots = module.build_dots(args.source, style=args.style, rows=args.rows)
        label = f"portrait/{args.style}"
        # Thousands of dots: band the opacities so fill attributes are shared.
        band = args.band
    else:
        dots = module.build_dots()
        label = "code"
        band = None   # keep the historic byte-for-byte output

    size = dotmatrix.write_fragment(dots, module.GROUP_ID, args.out, band)
    print(f"[{label}] {len(dots)} dots -> {args.out} ({size/1024:.1f} KB)")

    if args.preview:
        bg = None if args.preview_bg == "none" else args.preview_bg
        os.makedirs(os.path.dirname(os.path.abspath(args.preview)), exist_ok=True)
        with open(args.preview, "w", encoding="utf-8", newline="\n") as f:
            f.write(dotmatrix.standalone_svg(dots, module.GROUP_ID, bg, band))
        print(f"           preview -> {args.preview}")

    print("Now run assemble_hero.py to rebuild assets/profile-terminal.svg.")


if __name__ == "__main__":
    main()
