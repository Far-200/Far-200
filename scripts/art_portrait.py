#!/usr/bin/env python3
"""
art_portrait.py

Turns a real photograph into a purple dot-matrix portrait that speaks the same
visual language as the `</>` glyph in art_code.py.

Nothing here is generative: no model invents a face, no detail is hallucinated.
Every dot is a measurement of the source photograph -- background removal by
flood fill, tone mapping, gradient magnitude, and grid sampling. The same photo
plus the same parameters always yields the same SVG.

Pipeline
--------
1.  load + background removal      flood fill from the border on a flat backdrop
2.  head detection                 row-width profile -> hair top, head width, neck
3.  composition                    crop to head-and-shoulders, fade the shoulders
4.  tone                           grayscale, subject-local normalise, local contrast
5.  feature maps                   gradient magnitude, dark-line (black-hat), rim
6.  grid sampling                  mean/min blended so thin dark lines survive
7.  style                          halftone | structure | hybrid -> dot list

Why brightness drives dot *weight* rather than dot *presence*: the terminal
background is dark, so "ink where the photo is dark" would turn the hair and
hoodie into one solid purple slab with a hole where the face is. Instead the
subject mask decides that a dot exists at all, and luminance decides how big
and bright it is. The hair stays present as a dim mass, the face reads as the
bright focal point, and the silhouette never collapses into a blob.

Dependencies: Pillow, NumPy.
"""

import os
from collections import deque

import numpy as np
from PIL import Image, ImageFilter

from dotmatrix import (ART_WIDTH, ART_HEIGHT, DOT_COLOR, DOT_COLOR_DIM,
                       clamp, lerp)

GROUP_ID = "portrait-dot-matrix"

STYLES = ("halftone", "structure", "hybrid")

# ---------------------------------------------------------------------------
# Composition: where the portrait sits inside the 540x540 art box
# ---------------------------------------------------------------------------
# Chosen to occupy roughly the optical weight of the `</>` glyph while allowing
# the extra height a head-and-shoulders composition needs. In hero coordinates
# this lands at x 122..462, y 162..582 -- clear of the prompt line (y=100), the
# footer divider (y=672), and the right-hand info column (x=592).

BOX_CX = 270.0
BOX_CY = 250.0
BOX_W = 382.0
BOX_H = 472.0

GRID_ROWS = 70                      # -> pitch ~6.74 art units
JITTER = 0.55                       # organic wobble, matches the glyph's feel
SEED = 20260731

# Fraction of the crop height the head (hair top -> chin) should occupy.
HEAD_FRACTION = 0.70
HEADROOM = 0.045                    # extra crop above the hair, as a fraction

# Shoulders dissolve toward the bottom of the crop instead of ending in a bar.
SHOULDER_FADE_START = 0.72          # fraction of crop height where fade begins
SIDE_FADE = 0.055                   # horizontal dissolve at the crop edges

BG_TOLERANCE = 34.0                 # RGB distance treated as "backdrop"
SAMPLE_PX = 2400                    # working resolution before grid sampling

# --- tone ------------------------------------------------------------------

TONE_FLOOR = 0.12                   # darkest subject areas still get some ink
TONE_GAMMA = 1.70                   # S-curve steepness, not a plain power
LOCAL_CONTRAST = 0.55               # unsharp amount, gives hair internal texture
DARKLINE_STRENGTH = 0.85            # how hard glasses/brows/mouth carve out ink
MIN_BLEND = 0.25                    # min-pooling weight when sampling a cell

# --- dot treatment ---------------------------------------------------------

DOT_R_FRAC = (0.20, 0.52)           # dot radius as a fraction of the cell
DOT_OPACITY = (0.30, 1.00)
RADIUS_CURVE = 0.85                 # <1 lifts midtones, >1 crushes them
OPACITY_CURVE = 0.60                # keeps most ink near-solid, halftone style
RIM_BOOST = 0.26                    # extra weight along the subject silhouette
HYBRID_SHARPEN = 0.50               # grid-level unsharp, keeps features crisp
MIN_WEIGHT = 0.10                   # below this a cell emits no dot at all


# ===========================================================================
# Stage 1-3: photograph -> composed, background-free head-and-shoulders
# ===========================================================================


def _flood_background(bgish):
    """Background = backdrop-coloured pixels *connected to the image border*.

    Connectivity matters: the hoodie reaches the bottom corners, and light
    highlights inside the hair are backdrop-coloured but enclosed. A plain
    colour threshold would punch holes in the subject; a flood fill will not.
    """
    h, w = bgish.shape
    seen = np.zeros((h, w), bool)
    dq = deque()

    def push(y, x):
        if bgish[y, x] and not seen[y, x]:
            seen[y, x] = True
            dq.append((y, x))

    for x in range(w):
        push(0, x)
        push(h - 1, x)
    for y in range(h):
        push(y, 0)
        push(y, w - 1)

    while dq:
        y, x = dq.popleft()
        if y > 0:
            push(y - 1, x)
        if y < h - 1:
            push(y + 1, x)
        if x > 0:
            push(y, x - 1)
        if x < w - 1:
            push(y, x + 1)

    return seen


def _clean_mask(mask, radius=3):
    """Close pinholes then shave single-pixel fringe off the silhouette."""
    img = Image.fromarray((mask * 255).astype(np.uint8))
    img = img.filter(ImageFilter.MaxFilter(radius))   # close
    img = img.filter(ImageFilter.MinFilter(radius))
    img = img.filter(ImageFilter.MinFilter(3))        # shave halo
    img = img.filter(ImageFilter.MaxFilter(3))
    return np.asarray(img) > 127


def extract_subject(path):
    """Return (rgb float array, subject mask) with the flat backdrop removed."""
    im = Image.open(path).convert("RGB")
    rgb = np.asarray(im).astype(np.float32)

    border = np.concatenate([
        rgb[:6].reshape(-1, 3), rgb[-6:].reshape(-1, 3),
        rgb[:, :6].reshape(-1, 3), rgb[:, -6:].reshape(-1, 3),
    ])
    backdrop = np.median(border, axis=0)

    bgish = np.linalg.norm(rgb - backdrop, axis=2) < BG_TOLERANCE
    mask = ~_flood_background(bgish)
    return rgb, _clean_mask(mask)


def measure_head(mask):
    """Locate hair top, head width and neck from the subject's row widths.

    Deterministic and photo-agnostic: no face model, just the shape of the
    silhouette. Works because a head-and-shoulders photo is narrow at the hair,
    widest at the ears, pinched at the neck, and flares at the shoulders.
    """
    h, w = mask.shape
    widths = mask.sum(axis=1)

    rows = np.where(widths >= max(24, w * 0.02))[0]
    if rows.size == 0:
        raise ValueError("no subject found in the source image")
    head_top = int(rows[0])

    # Widest point of the head lives in the upper half of the silhouette.
    upper = widths[head_top:head_top + int(h * 0.5)]
    head_w = int(upper.max())

    # Neck: narrowest row between the ears and the shoulder flare.
    lo = head_top + int(head_w * 0.60)
    hi = min(h, head_top + int(head_w * 1.70))
    neck = int(lo + np.argmin(widths[lo:hi])) if hi > lo + 1 else head_top + head_w

    # Horizontal centre from the head band only, so shoulders cannot pull it.
    band = mask[head_top:neck]
    cols = np.where(band.any(axis=0))[0]
    cx = float((cols[0] + cols[-1]) / 2.0)

    return head_top, neck, head_w, cx


def compose(path):
    """Crop to a centred head-and-shoulders and build a soft alpha channel."""
    rgb, mask = extract_subject(path)
    head_top, neck, head_w, cx = measure_head(mask)

    head_h = neck - head_top
    crop_h = head_h / HEAD_FRACTION
    crop_w = crop_h * (BOX_W / BOX_H)

    top = head_top - crop_h * HEADROOM
    left = cx - crop_w / 2.0

    # Pad rather than clamp, so the composition never shifts off-centre.
    src = np.dstack([rgb, mask.astype(np.float32) * 255.0])
    img = Image.fromarray(src.astype(np.uint8), mode="RGBA")
    img = img.transform(
        (int(round(crop_w)), int(round(crop_h))), Image.AFFINE,
        (1, 0, left, 0, 1, top), resample=Image.BICUBIC, fillcolor=(0, 0, 0, 0))
    img = img.resize((int(SAMPLE_PX * BOX_W / BOX_H), SAMPLE_PX), Image.LANCZOS)

    arr = np.asarray(img).astype(np.float32) / 255.0
    rgb_c, alpha = arr[..., :3], arr[..., 3]

    h, w = alpha.shape
    # Dissolve the shoulders downward so the hoodie suggests a torso instead of
    # ending in a photograph-shaped bar across the bottom of the artwork.
    ys = np.linspace(0.0, 1.0, h)[:, None]
    fade = np.clip((ys - SHOULDER_FADE_START) / (1.0 - SHOULDER_FADE_START), 0, 1)
    alpha = alpha * (1.0 - fade ** 1.4)

    xs = np.linspace(0.0, 1.0, w)[None, :]
    side = np.clip(np.minimum(xs, 1.0 - xs) / SIDE_FADE, 0, 1)
    alpha = alpha * side ** 0.8

    return rgb_c, alpha


# ===========================================================================
# Stage 4-5: tone and feature maps
# ===========================================================================


def _box1d(a, radius, axis):
    """Separable box blur via a summed-area table. O(n) and exact."""
    r = int(max(1, round(radius)))
    a = np.moveaxis(a, axis, -1)
    pad = np.pad(a, [(0, 0)] * (a.ndim - 1) + [(r, r)], mode="edge")
    cs = np.cumsum(pad, axis=-1, dtype=np.float64)
    cs = np.concatenate([np.zeros(cs.shape[:-1] + (1,)), cs], axis=-1)
    n = a.shape[-1]
    out = (cs[..., 2 * r + 1:2 * r + 1 + n] - cs[..., :n]) / (2 * r + 1)
    return np.moveaxis(out.astype(np.float32), -1, axis)


def _blur(a, radius):
    """Three box passes approximate a Gaussian closely enough for tone work,
    and unlike PIL's GaussianBlur they operate on float arrays directly."""
    r = max(radius / 1.75, 0.6)
    for _ in range(3):
        a = _box1d(_box1d(a, r, 0), r, 1)
    return a


def build_maps(rgb, alpha):
    """Return dict of full-resolution float maps used by the styles."""
    luma = (0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2])
    luma = luma.astype(np.float32)

    solid = alpha > 0.55
    if solid.sum() < 100:
        solid = alpha > 0.1

    # Normalise inside the subject only. The backdrop is gone, so global
    # normalisation would key off transparent pixels and wash out the face.
    lo, hi = np.percentile(luma[solid], [1.5, 98.5])
    norm = np.clip((luma - lo) / max(hi - lo, 1e-5), 0.0, 1.0)

    # Local contrast: hair and beard are near-black in the raw photo. Unsharp
    # masking gives them internal structure so they read as texture, not tar.
    base = _blur(norm, SAMPLE_PX * 0.012)
    detail = np.clip(norm + LOCAL_CONTRAST * (norm - base), 0.0, 1.0)

    # Dark-line response (black-hat): positive where a pixel is darker than its
    # surroundings. This is what keeps the thin glasses rims, the brows, the
    # nostrils and the mouth line from being averaged away by the grid.
    fine = _blur(detail, SAMPLE_PX * 0.0045)
    darkline = np.clip(fine - detail, 0.0, 1.0)
    darkline = darkline / max(np.percentile(darkline[solid], 99.0), 1e-5)
    darkline = np.clip(darkline, 0.0, 1.0)

    # Gradient magnitude for the structure-led styles.
    sm = _blur(detail, SAMPLE_PX * 0.0030)
    gy, gx = np.gradient(sm)
    edge = np.hypot(gx, gy)
    edge = edge / max(np.percentile(edge[solid], 99.0), 1e-5)
    edge = np.clip(edge, 0.0, 1.0) * alpha

    # Silhouette rim: gradient of the alpha channel. Draws the hair outline,
    # ear line and shoulder line even where the photo itself is black-on-black.
    ay, ax = np.gradient(_blur(alpha, SAMPLE_PX * 0.0035))
    rim = np.hypot(ax, ay)
    rim = np.clip(rim / max(rim.max(), 1e-5), 0.0, 1.0)

    tone = np.clip(detail - DARKLINE_STRENGTH * darkline, 0.0, 1.0)

    return {"tone": tone, "edge": edge, "rim": rim,
            "darkline": darkline, "alpha": alpha}


# ===========================================================================
# Stage 6: grid sampling
# ===========================================================================


def _sample(mapping, rows, cols, blend_min=0.0):
    """Downsample a map onto the dot grid.

    Straight averaging destroys anything thinner than a cell -- which is
    exactly the glasses. Blending in the cell minimum lets a thin dark line
    still pull its cell down, so the frame survives as negative space.
    """
    h, w = mapping.shape
    ys = (np.linspace(0, h, rows + 1)).astype(int)
    xs = (np.linspace(0, w, cols + 1)).astype(int)
    out = np.zeros((rows, cols), np.float32)
    for r in range(rows):
        for c in range(cols):
            tile = mapping[ys[r]:ys[r + 1], xs[c]:xs[c + 1]]
            if tile.size == 0:
                continue
            m = float(tile.mean())
            out[r, c] = (1.0 - blend_min) * m + blend_min * float(tile.min()) \
                if blend_min else m
    return out


def _sample_max(mapping, rows, cols):
    h, w = mapping.shape
    ys = (np.linspace(0, h, rows + 1)).astype(int)
    xs = (np.linspace(0, w, cols + 1)).astype(int)
    out = np.zeros((rows, cols), np.float32)
    for r in range(rows):
        for c in range(cols):
            tile = mapping[ys[r]:ys[r + 1], xs[c]:xs[c + 1]]
            if tile.size:
                out[r, c] = float(tile.max())
    return out


def _scurve(t, gamma):
    """Symmetric contrast curve: fixes 0, 0.5 and 1, steepens everything
    between. A plain t**gamma would darken the hair correctly but also rob the
    skin of its highlights, leaving the whole face at three-quarter ink."""
    t = np.clip(t, 0.0, 1.0)
    a = t ** gamma
    b = (1.0 - t) ** gamma
    return a / np.maximum(a + b, 1e-6)


def _grid_blur(g):
    """3x3 blur on the dot grid itself, used as the base for grid-level
    unsharp masking."""
    pad = np.pad(g, 1, mode="edge")
    acc = np.zeros_like(g)
    for dy in (0, 1, 2):
        for dx in (0, 1, 2):
            acc += pad[dy:dy + g.shape[0], dx:dx + g.shape[1]]
    return acc / 9.0


def _despeckle(weight, cover, threshold, min_neighbours=2):
    """Drop lone dots with no lit neighbours -- the classic halftone confetti."""
    lit = (weight > threshold) & (cover > 0.25)
    pad = np.pad(lit, 1)
    n = sum(pad[1 + dy:1 + dy + lit.shape[0], 1 + dx:1 + dx + lit.shape[1]]
            for dy in (-1, 0, 1) for dx in (-1, 0, 1)
            if not (dy == 0 and dx == 0)).astype(int)
    return lit & (n >= min_neighbours)


# ===========================================================================
# Stage 7: styles
# ===========================================================================


def _grid_geometry(rows=None):
    pitch = BOX_H / (rows or GRID_ROWS)
    cols = int(round(BOX_W / pitch))
    x0 = BOX_CX - (cols * pitch) / 2.0
    y0 = BOX_CY - BOX_H / 2.0
    return pitch, cols, x0, y0


def _emit(weight, keep, rng, pitch, cols, x0, y0, dot_r, bright_cut=0.62):
    """Turn a weight grid into draw-ordered dots (dim first, bright last)."""
    rows = weight.shape[0]
    dim, bright = [], []
    for r in range(rows):
        for c in range(cols):
            if not keep[r, c]:
                continue
            wgt = float(clamp(weight[r, c]))
            cx = x0 + (c + 0.5) * pitch + rng.uniform(-JITTER, JITTER)
            cy = y0 + (r + 0.5) * pitch + rng.uniform(-JITTER, JITTER)
            radius = lerp(dot_r[0], dot_r[1], wgt ** RADIUS_CURVE)
            opacity = lerp(DOT_OPACITY[0], DOT_OPACITY[1], wgt ** OPACITY_CURVE)
            dot = (cx, cy, radius, opacity,
                   DOT_COLOR if wgt >= bright_cut else DOT_COLOR_DIM)
            (bright if wgt >= bright_cut else dim).append(dot)
    return dim + bright


def build_dots(source, style="hybrid", rows=None, floor=None, gamma=None,
               dot_r=None, minblend=None, **_ignored):
    """Build the portrait dot list for one of the three candidate styles."""
    if style not in STYLES:
        raise ValueError(f"unknown style {style!r}; expected one of {STYLES}")

    import random
    rng = random.Random(SEED)

    rows = rows or GRID_ROWS
    floor = TONE_FLOOR if floor is None else floor
    gamma = TONE_GAMMA if gamma is None else gamma
    minblend = MIN_BLEND if minblend is None else minblend

    rgb, alpha = compose(source)
    maps = build_maps(rgb, alpha)

    pitch, cols, x0, y0 = _grid_geometry(rows)
    # Dot radius scales with the cell so the halftone density stays constant
    # no matter what grid resolution is chosen.
    dot_r = dot_r or (pitch * DOT_R_FRAC[0], pitch * DOT_R_FRAC[1])

    cover = _sample(maps["alpha"], rows, cols)
    tone = _sample(maps["tone"], rows, cols, blend_min=minblend)
    edge = _sample_max(maps["edge"], rows, cols)
    rim = _sample_max(maps["rim"], rows, cols)

    # Tonal base shared by every style: presence from the mask, weight from
    # luminance, with a floor so dark hair never disappears entirely.
    lit = cover > 0.30
    base = np.where(lit, floor + (1.0 - floor) * _scurve(tone, gamma), 0.0)
    base *= np.clip(cover * 1.35, 0.0, 1.0)

    if style == "halftone":
        # Candidate A. Pure tonal halftone: dot size alone carries the image,
        # exactly like a printed newspaper portrait. The silhouette is held by
        # the mask and a whisper of rim, nothing else. Softest and most even.
        weight = base + 0.30 * rim * lit
        cut = 0.34

    elif style == "structure":
        # Candidate B. Feature-led line drawing: the silhouette rim plus the
        # internal edges (glasses, brows, hairline, jaw, lips) do the work, and
        # interior tone is reduced to a faint wash. Openest and most graphic.
        clean_edge = edge * (0.30 + 0.70 * tone)
        structure = np.clip(np.maximum(rim * 1.10, clean_edge * 1.60), 0.0, 1.0)
        weight = np.where(lit, 0.30 * base + 0.95 * structure, 0.0)
        cut = 0.38

    else:  # hybrid
        # Candidate C. Tonal mass plus a sharpening pass applied *at the dot
        # grid's own resolution*, which is what keeps sub-cell features from
        # being averaged into mush: the glasses stay a dark bar across bright
        # skin, the eye sockets stay sunken, the lips keep their line.
        blur = _grid_blur(base)
        sharp = np.clip(base + HYBRID_SHARPEN * (base - blur), 0.0, 1.0)
        weight = np.where(lit, sharp + RIM_BOOST * rim, 0.0)
        cut = 0.34

    weight = np.clip(weight, 0.0, 1.0)
    keep = _despeckle(weight, cover, MIN_WEIGHT,
                      min_neighbours=1 if style == "structure" else 2)

    return _emit(weight, keep, rng, pitch, cols, x0, y0, dot_r)
