#!/usr/bin/env python3
"""
assemble_hero.py

Combines the dot-matrix portrait fragment (assets/profile-art.svg, produced
by generate_profile_art.py) with the terminal chrome, neofetch-style info
column, and bottom prompt line into the final, committed hero image:

    assets/profile-terminal.svg

Run generate_profile_art.py first if profile-source.png changes.
"""

import os

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ART_PATH = os.path.join(SCRIPT_DIR, "..", "assets", "profile-art.svg")
OUTPUT_PATH = os.path.join(SCRIPT_DIR, "..", "assets", "profile-terminal.svg")

with open(ART_PATH) as f:
    ART_FRAGMENT = f.read().strip()

# Palette
BG = "#0d1117"
PANEL = "#10151c"
BORDER = "#30363d"
TEXT_PRIMARY = "#f0f6fc"
TEXT_SECONDARY = "#8b949e"
PURPLE = "#a855f7"
PURPLE_LIGHT = "#c084fc"
GREEN = "#3fb950"
BLUE = "#58a6ff"

FONT = ('ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, '
        '"Liberation Mono", monospace')

info_rows = [
    ("Role", "CSE Student · Full-Stack Builder"),
    ("University", "REVA University · Bengaluru"),
    ("Focus", "Backend Systems · AI Tools · Practical Software"),
    ("Stack", "React · Python · FastAPI · Java · C++"),
    ("Building", "Think Before Code · FlowTrace"),
    ("Learning", "DSA · System Design · Secure Backend Dev"),
    ("Mode", "Building · Breaking · Fixing · Shipping"),
]

RIGHT_COL_X = 592
ROW_HEIGHT = 34
ROWS_START_Y = 260
LABEL_COL_WIDTH = 118  # label sits in this width before the value starts

row_svg = []
for i, (label, value) in enumerate(info_rows):
    y = ROWS_START_Y + i * ROW_HEIGHT
    row_svg.append(
        f'<text x="{RIGHT_COL_X}" y="{y}" font-family=\'{FONT}\' '
        f'font-size="15" font-weight="600" fill="{PURPLE}">{label}</text>'
    )
    row_svg.append(
        f'<text x="{RIGHT_COL_X + LABEL_COL_WIDTH}" y="{y}" '
        f'font-family=\'{FONT}\' font-size="15" fill="{TEXT_PRIMARY}">'
        f'{value}</text>'
    )

info_rows_svg = "\n  ".join(row_svg)

svg = f'''<svg viewBox="0 0 1400 760" xmlns="http://www.w3.org/2000/svg" role="img" aria-labelledby="hero-title hero-desc">
  <title id="hero-title">Farhaan Khan developer profile terminal</title>
  <desc id="hero-desc">A neofetch-style terminal window showing Farhaan Khan's role, university, focus areas, tech stack, current projects, and a dot-matrix portrait of Quackrates, the Think Before Code mascot.</desc>

  <rect width="1400" height="760" fill="{BG}"/>

  <!-- terminal card -->
  <rect x="24" y="24" width="1352" height="712" rx="14" fill="{PANEL}" stroke="{BORDER}" stroke-width="1.5"/>

  <!-- chrome bar -->
  <line x1="24" y1="66" x2="1376" y2="66" stroke="{BORDER}" stroke-width="1"/>
  <circle cx="54" cy="45" r="6" fill="#f85149" fill-opacity="0.75"/>
  <circle cx="76" cy="45" r="6" fill="#d29922" fill-opacity="0.75"/>
  <circle cx="98" cy="45" r="6" fill="{GREEN}" fill-opacity="0.75"/>
  <text x="700" y="50" text-anchor="middle" font-family='{FONT}' font-size="14" fill="{TEXT_SECONDARY}">Far-200 — profile</text>
  <circle cx="1330" cy="45" r="4" fill="{GREEN}"/>
  <text x="1344" y="50" text-anchor="end" font-family='{FONT}' font-size="13" font-weight="600" fill="{GREEN}">BUILDING</text>

  <!-- prompt line -->
  <text x="52" y="100" font-family='{FONT}' font-size="17">
    <tspan fill="{GREEN}">farhaan</tspan><tspan fill="{TEXT_SECONDARY}">@github</tspan><tspan fill="{TEXT_SECONDARY}">:~$ </tspan><tspan fill="{PURPLE_LIGHT}">neofetch --profile</tspan>
  </text>

  <!-- left column: dot-matrix portrait -->
  <g transform="translate(52,150) scale(0.889)">
    {ART_FRAGMENT}
  </g>

  <!-- right column: neofetch-style info -->
  <text x="{RIGHT_COL_X}" y="200" font-family='{FONT}' font-size="28" font-weight="700" fill="{TEXT_PRIMARY}">farhaan khan</text>
  {info_rows_svg}

  <text x="{RIGHT_COL_X}" y="{ROWS_START_Y + len(info_rows) * ROW_HEIGHT + 40}" font-family='{FONT}' font-size="14" font-style="italic" fill="{TEXT_SECONDARY}">Still debugging code, career plans, and occasionally life.</text>

  <!-- footer -->
  <line x1="52" y1="672" x2="1348" y2="672" stroke="{BORDER}" stroke-width="1"/>
  <text x="52" y="706" font-family='{FONT}' font-size="16">
    <tspan fill="{GREEN}">farhaan</tspan><tspan fill="{TEXT_SECONDARY}">@github</tspan><tspan fill="{TEXT_SECONDARY}">:~$ </tspan><tspan fill="{TEXT_PRIMARY}">think-before-code</tspan><tspan fill="{PURPLE_LIGHT}">▌</tspan>
  </text>
  <text x="1348" y="706" text-anchor="end" font-family='{FONT}' font-size="13" fill="{TEXT_SECONDARY}">open to internships · backend / AI-assisted roles</text>
</svg>
'''

with open(OUTPUT_PATH, "w") as f:
    f.write(svg)

print(f"Wrote {len(svg)} bytes to {OUTPUT_PATH}")
