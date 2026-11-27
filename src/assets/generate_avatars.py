"""Procedural character portrait generator for Griductive Solver (Khoa — GUI Assets).

Generates 50 original, deterministic, antialias-rendered 256x256 RGBA PNG
character tokens in ``src/assets/sprites/avatars/1.png`` .. ``50.png`` using
Pillow only. Zero external or third-party artwork is used.

Usage:
    python src/assets/generate_avatars.py
"""

from __future__ import annotations

import math
import random
from pathlib import Path

from PIL import Image, ImageDraw


AVATAR_DIR = Path(__file__).resolve().parent / "sprites" / "avatars"
COUNT = 50
CANVAS = 512
FINAL_SIZE = 256
OUTLINE = (24, 31, 48, 255)
WHITE = (255, 255, 255, 255)

BACKDROPS = [
    ((78, 129, 173), (45, 78, 115)),   # Steel sky
    ((91, 158, 137), (50, 97, 86)),    # Sage teal
    ((186, 128, 92), (124, 75, 52)),   # Warm ochre
    ((150, 114, 179), (92, 65, 120)),  # Dusty lavender
    ((181, 102, 118), (118, 59, 75)),  # Rose berry
    ((102, 145, 168), (58, 91, 112)),  # Harbor slate
    ((172, 148, 86), (112, 93, 47)),   # Antique gold
    ((118, 156, 102), (68, 99, 59)),   # Moss olive
    ((168, 116, 145), (108, 67, 92)),  # Mauve plum
    ((88, 138, 152), (49, 84, 98)),    # Petrol mist
]

# (base, shadow, blush)
SKINS = [
    ((247, 217, 196), (222, 183, 158), (237, 165, 156)),
    ((237, 198, 168), (209, 164, 132), (227, 148, 136)),
    ((219, 173, 136), (189, 139, 104), (204, 126, 110)),
    ((191, 138, 99), (158, 106, 72), (176, 102, 86)),
    ((148, 98, 68), (117, 73, 49), (138, 76, 62)),
    ((108, 69, 49), (82, 50, 34), (105, 56, 46)),
]

# (base, highlight)
HAIRS = [
    ((34, 38, 48), (64, 70, 86)),      # Charcoal black
    ((66, 44, 33), (99, 69, 53)),      # Espresso
    ((105, 65, 42), (140, 92, 62)),    # Chestnut
    ((148, 66, 44), (186, 94, 66)),    # Auburn
    ((194, 108, 52), (224, 140, 82)),  # Copper ginger
    ((214, 175, 102), (238, 206, 138)),  # Warm blonde
    ((188, 194, 206), (222, 226, 236)),  # Silver gray
    ((86, 94, 110), (122, 132, 150)),  # Salt & pepper
    ((46, 56, 86), (78, 92, 132)),     # Midnight indigo
]

OUTFIT_COLORS = [
    ((58, 74, 108), (226, 232, 242), (204, 78, 86)),    # Navy + white + crimson tie
    ((146, 64, 74), (242, 235, 226), (218, 176, 88)),   # Burgundy + cream + gold
    ((56, 106, 92), (234, 240, 236), (224, 152, 74)),   # Forest + off-white + amber
    ((166, 128, 78), (242, 236, 224), (72, 92, 124)),   # Trench tan + cream + slate
    ((88, 72, 118), (236, 232, 244), (82, 190, 168)),   # Plum + lilac + mint
    ((68, 82, 92), (228, 234, 238), (212, 112, 72)),    # Charcoal + mist + rust
    ((154, 92, 66), (244, 234, 220), (62, 128, 138)),   # Terracotta + sand + teal
    ((52, 98, 128), (234, 242, 248), (228, 186, 84)),   # Cobalt + ice + mustard
]

EYE_COLORS = [
    (46, 62, 86),
    (74, 52, 38),
    (52, 102, 82),
    (64, 96, 138),
    (96, 74, 46),
]

HAIRSTYLES = [
    "classic_part",
    "bob",
    "curly_puff",
    "long_wavy",
    "spiky",
    "bun",
    "ponytail",
    "swept_fringe",
    "buzz",
    "twin_buns",
]

OUTFITS = [
    "trench_coat",
    "shirt_tie",
    "bowtie_vest",
    "turtleneck",
    "scarf_coat",
    "vneck_blazer",
    "suspenders",
]

EXPRESSIONS = ["warm_smile", "smirk", "serious", "cheerful", "curious"]
EYEWEAR = ["none", "none", "none", "none", "none", "round", "square", "monocle", "shades"]
HEADWEAR = ["none", "none", "none", "none", "none", "fedora", "beret", "beanie", "cap", "headband"]
FACIAL = ["none", "none", "none", "none", "mustache", "goatee", "freckles", "earrings"]


def _rgba(rgb: tuple[int, int, int], alpha: int = 255) -> tuple[int, int, int, int]:
    return (rgb[0], rgb[1], rgb[2], alpha)


def _darken(rgb: tuple[int, int, int], factor: float = 0.78) -> tuple[int, int, int, int]:
    return (
        max(0, int(rgb[0] * factor)),
        max(0, int(rgb[1] * factor)),
        max(0, int(rgb[2] * factor)),
        255,
    )


def _draw_radial_backdrop(size: int, center_rgb: tuple[int, int, int], edge_rgb: tuple[int, int, int]) -> Image.Image:
    """Create a smooth circular radial-gradient medallion backdrop."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2
    radius = size // 2 - 18
    steps = 36
    for i in range(steps, 0, -1):
        t = i / steps
        r = int(radius * t)
        col = tuple(int(center_rgb[c] * (1.0 - t * 0.85) + edge_rgb[c] * (t * 0.85)) for c in range(3))
        # Slight upward offset for soft key-light glow
        oy = int((1.0 - t) * -36)
        draw.ellipse((cx - r, cy + oy - r, cx + r, cy + oy + r), fill=_rgba(col))
    return img


def _draw_hair_back(draw: ImageDraw.ImageDraw, style: str, hair_rgb: tuple[int, int, int]) -> None:
    fill = _rgba(hair_rgb)
    dark = _darken(hair_rgb, 0.76)
    cx = CANVAS // 2

    if style == "long_wavy":
        draw.rounded_rectangle((cx - 126, 152, cx + 126, 405), radius=62, fill=dark, outline=OUTLINE, width=6)
        draw.ellipse((cx - 134, 275, cx - 58, 395), fill=fill, outline=OUTLINE, width=6)
        draw.ellipse((cx + 58, 275, cx + 134, 395), fill=fill, outline=OUTLINE, width=6)
    elif style == "bob":
        draw.rounded_rectangle((cx - 124, 150, cx + 124, 336), radius=58, fill=dark, outline=OUTLINE, width=6)
    elif style == "curly_puff":
        for angle in range(0, 360, 28):
            rad = math.radians(angle)
            px = cx + int(math.cos(rad) * 102)
            py = 212 + int(math.sin(rad) * 92)
            draw.ellipse((px - 52, py - 52, px + 52, py + 52), fill=fill, outline=OUTLINE, width=6)
    elif style == "bun":
        draw.ellipse((cx - 50, 62, cx + 50, 158), fill=fill, outline=OUTLINE, width=6)
        draw.arc((cx - 32, 82, cx + 32, 134), 200, 340, fill=_rgba((255, 255, 255), 70), width=5)
    elif style == "twin_buns":
        draw.ellipse((cx - 138, 102, cx - 58, 182), fill=fill, outline=OUTLINE, width=6)
        draw.ellipse((cx + 58, 102, cx + 138, 182), fill=fill, outline=OUTLINE, width=6)
    elif style == "ponytail":
        draw.polygon(
            [(cx + 76, 150), (cx + 150, 180), (cx + 166, 304), (cx + 108, 332), (cx + 88, 224)],
            fill=dark,
            outline=OUTLINE,
        )
        draw.line(
            [(cx + 76, 150), (cx + 150, 180), (cx + 166, 304), (cx + 108, 332)],
            fill=OUTLINE,
            width=6,
        )


def _draw_outfit(
    draw: ImageDraw.ImageDraw,
    outfit: str,
    main_rgb: tuple[int, int, int],
    shirt_rgb: tuple[int, int, int],
    accent_rgb: tuple[int, int, int],
) -> None:
    cx = CANVAS // 2
    main = _rgba(main_rgb)
    main_dark = _darken(main_rgb, 0.78)
    shirt = _rgba(shirt_rgb)
    accent = _rgba(accent_rgb)

    # Torso / shoulders base
    draw.pieslice((cx - 178, 346, cx + 178, 620), 180, 360, fill=main, outline=OUTLINE, width=6)
    # Shoulder shading arc
    draw.arc((cx - 166, 358, cx + 166, 595), 205, 335, fill=main_dark, width=10)

    if outfit == "trench_coat":
        draw.polygon([(cx - 46, 348), (cx + 46, 348), (cx, 466)], fill=shirt, outline=OUTLINE)
        draw.polygon([(cx - 54, 348), (cx - 110, 386), (cx - 72, 424), (cx - 90, 444), (cx - 16, 474)], fill=main_dark, outline=OUTLINE)
        draw.polygon([(cx + 54, 348), (cx + 110, 386), (cx + 72, 424), (cx + 90, 444), (cx + 16, 474)], fill=main_dark, outline=OUTLINE)
        draw.line([(cx - 54, 348), (cx - 16, 474)], fill=OUTLINE, width=5)
        draw.line([(cx + 54, 348), (cx + 16, 474)], fill=OUTLINE, width=5)
    elif outfit == "shirt_tie":
        draw.polygon([(cx - 48, 348), (cx + 48, 348), (cx, 480)], fill=shirt, outline=OUTLINE)
        # Necktie
        draw.polygon([(cx - 14, 366), (cx + 14, 366), (cx + 22, 464), (cx, 492), (cx - 22, 464)], fill=accent, outline=OUTLINE)
        draw.polygon([(cx - 18, 356), (cx + 18, 356), (cx + 10, 380), (cx - 10, 380)], fill=accent, outline=OUTLINE)
        # Collars
        draw.polygon([(cx - 52, 344), (cx - 6, 368), (cx - 38, 396)], fill=shirt, outline=OUTLINE)
        draw.polygon([(cx + 52, 344), (cx + 6, 368), (cx + 38, 396)], fill=shirt, outline=OUTLINE)
    elif outfit == "bowtie_vest":
        draw.polygon([(cx - 44, 348), (cx + 44, 348), (cx, 456)], fill=shirt, outline=OUTLINE)
        draw.polygon([(cx - 34, 364), (cx - 4, 378), (cx - 34, 394)], fill=accent, outline=OUTLINE)
        draw.polygon([(cx + 34, 364), (cx + 4, 378), (cx + 34, 394)], fill=accent, outline=OUTLINE)
        draw.ellipse((cx - 10, 368, cx + 10, 388), fill=accent, outline=OUTLINE, width=4)
    elif outfit == "turtleneck":
        draw.rounded_rectangle((cx - 50, 326, cx + 50, 388), radius=18, fill=main_dark, outline=OUTLINE, width=6)
        for rx in range(cx - 32, cx + 36, 16):
            draw.line([(rx, 334), (rx, 380)], fill=main, width=4)
    elif outfit == "scarf_coat":
        draw.rounded_rectangle((cx - 88, 334, cx + 88, 396), radius=28, fill=accent, outline=OUTLINE, width=6)
        draw.rounded_rectangle((cx + 16, 378, cx + 68, 492), radius=16, fill=accent, outline=OUTLINE, width=6)
        draw.line([(cx - 64, 364), (cx + 64, 364)], fill=_darken(accent_rgb, 0.8), width=5)
    elif outfit == "vneck_blazer":
        draw.polygon([(cx - 56, 348), (cx + 56, 348), (cx, 458)], fill=shirt, outline=OUTLINE)
        draw.line([(cx - 56, 348), (cx, 458), (cx + 56, 348)], fill=OUTLINE, width=6)
        draw.ellipse((cx - 8, 466, cx + 8, 482), fill=accent, outline=OUTLINE, width=3)
    elif outfit == "suspenders":
        draw.pieslice((cx - 178, 346, cx + 178, 620), 180, 360, fill=shirt, outline=OUTLINE, width=6)
        draw.rectangle((cx - 78, 356, cx - 50, 504), fill=main, outline=OUTLINE, width=5)
        draw.rectangle((cx + 50, 356, cx + 78, 504), fill=main, outline=OUTLINE, width=5)
        draw.ellipse((cx - 72, 434, cx - 56, 450), fill=accent, outline=OUTLINE, width=3)
        draw.ellipse((cx + 56, 434, cx + 72, 450), fill=accent, outline=OUTLINE, width=3)


def _draw_hair_front(
    draw: ImageDraw.ImageDraw,
    style: str,
    hair_rgb: tuple[int, int, int],
    hi_rgb: tuple[int, int, int],
) -> None:
    fill = _rgba(hair_rgb)
    hi = _rgba(hi_rgb)
    cx = CANVAS // 2

    if style == "classic_part":
        draw.pieslice((cx - 106, 118, cx + 106, 268), 180, 360, fill=fill, outline=OUTLINE, width=6)
        draw.chord((cx - 104, 134, cx + 52, 232), 180, 360, fill=fill)
        draw.polygon([(cx - 102, 198), (cx - 32, 162), (cx + 98, 194), (cx + 102, 224), (cx + 76, 198), (cx - 28, 184), (cx - 84, 222)], fill=fill)
        draw.arc((cx - 72, 136, cx + 60, 200), 205, 325, fill=hi, width=7)
    elif style == "bob":
        draw.pieslice((cx - 110, 118, cx + 110, 276), 180, 360, fill=fill, outline=OUTLINE, width=6)
        draw.rounded_rectangle((cx - 110, 178, cx - 80, 314), radius=16, fill=fill, outline=OUTLINE, width=6)
        draw.rounded_rectangle((cx + 80, 178, cx + 110, 314), radius=16, fill=fill, outline=OUTLINE, width=6)
        draw.arc((cx - 64, 136, cx + 64, 196), 210, 330, fill=hi, width=7)
    elif style == "curly_puff":
        for px, py, r in [
            (cx - 74, 164, 38), (cx - 30, 144, 42), (cx + 22, 142, 42), (cx + 72, 162, 38),
            (cx - 86, 198, 30), (cx + 86, 198, 30),
        ]:
            draw.ellipse((px - r, py - r, px + r, py + r), fill=fill, outline=OUTLINE, width=6)
        draw.arc((cx - 48, 124, cx + 48, 168), 210, 330, fill=hi, width=6)
    elif style == "long_wavy":
        draw.pieslice((cx - 108, 120, cx + 108, 266), 180, 360, fill=fill, outline=OUTLINE, width=6)
        draw.polygon([(cx - 104, 192), (cx - 14, 152), (cx + 14, 152), (cx + 104, 192), (cx + 96, 232), (cx + 68, 196), (cx, 176), (cx - 68, 196), (cx - 96, 232)], fill=fill)
        draw.arc((cx - 66, 138, cx + 66, 196), 210, 330, fill=hi, width=7)
    elif style == "spiky":
        draw.pieslice((cx - 104, 120, cx + 104, 260), 180, 360, fill=fill, outline=OUTLINE, width=6)
        pts = [
            (cx - 100, 198), (cx - 106, 152), (cx - 66, 156), (cx - 46, 114),
            (cx - 12, 142), (cx + 18, 108), (cx + 46, 144), (cx + 82, 126),
            (cx + 86, 162), (cx + 106, 166), (cx + 98, 204), (cx + 72, 184),
            (cx, 178), (cx - 72, 186),
        ]
        draw.polygon(pts, fill=fill, outline=OUTLINE)
        draw.line(pts[:11], fill=OUTLINE, width=6)
    elif style in ("bun", "twin_buns", "ponytail"):
        draw.pieslice((cx - 104, 126, cx + 104, 260), 180, 360, fill=fill, outline=OUTLINE, width=6)
        draw.chord((cx - 96, 148, cx + 96, 224), 190, 350, fill=fill)
        draw.arc((cx - 56, 140, cx + 56, 190), 210, 330, fill=hi, width=6)
    elif style == "swept_fringe":
        draw.pieslice((cx - 108, 120, cx + 108, 268), 180, 360, fill=fill, outline=OUTLINE, width=6)
        draw.polygon([(cx - 104, 194), (cx - 64, 148), (cx + 96, 170), (cx + 100, 226), (cx + 22, 194), (cx - 86, 212)], fill=fill, outline=OUTLINE)
        draw.arc((cx - 58, 138, cx + 70, 196), 200, 320, fill=hi, width=7)
    elif style == "buzz":
        draw.arc((cx - 94, 134, cx + 94, 250), 195, 345, fill=fill, width=22)


def _draw_face(
    draw: ImageDraw.ImageDraw,
    skin_tuple: tuple[tuple[int, int, int], tuple[int, int, int], tuple[int, int, int]],
    eye_rgb: tuple[int, int, int],
    hair_rgb: tuple[int, int, int],
    expression: str,
    facial: str,
) -> None:
    cx = CANVAS // 2
    skin, shadow, blush = (_rgba(c) for c in skin_tuple)

    # Neck
    draw.rounded_rectangle((cx - 34, 304, cx + 34, 376), radius=14, fill=shadow, outline=OUTLINE, width=6)
    # Ears
    draw.ellipse((cx - 114, 232, cx - 78, 282), fill=skin, outline=OUTLINE, width=6)
    draw.ellipse((cx + 78, 232, cx + 114, 282), fill=skin, outline=OUTLINE, width=6)

    if facial == "earrings":
        draw.ellipse((cx - 104, 272, cx - 86, 290), fill=(242, 200, 76, 255), outline=OUTLINE, width=4)
        draw.ellipse((cx + 86, 272, cx + 104, 290), fill=(242, 200, 76, 255), outline=OUTLINE, width=4)

    # Head shape
    draw.rounded_rectangle((cx - 96, 142, cx + 96, 340), radius=86, fill=skin, outline=OUTLINE, width=6)
    # Subtle lower chin shadow
    draw.arc((cx - 82, 224, cx + 82, 332), 25, 155, fill=shadow, width=6)

    # Pre-blended warm cheek blush (opaque RGBA so skin layer never turns semi-transparent)
    blended_blush = (
        int(skin[0] * 0.70 + blush[0] * 0.30),
        int(skin[1] * 0.70 + blush[1] * 0.30),
        int(skin[2] * 0.70 + blush[2] * 0.30),
        255,
    )
    draw.ellipse((cx - 72, 256, cx - 40, 276), fill=blended_blush)
    draw.ellipse((cx + 40, 256, cx + 72, 276), fill=blended_blush)

    if facial == "freckles":
        for fx, fy in [(cx - 56, 260), (cx - 46, 266), (cx - 60, 268), (cx + 56, 260), (cx + 46, 266), (cx + 60, 268)]:
            draw.ellipse((fx - 3, fy - 3, fx + 3, fy + 3), fill=shadow)

    # Eyebrows
    brow = _darken(hair_rgb, 0.82)
    if expression == "curious":
        draw.arc((cx - 62, 202, cx - 18, 224), 195, 345, fill=brow, width=7)
        draw.arc((cx + 18, 192, cx + 62, 218), 195, 345, fill=brow, width=7)
    elif expression == "serious":
        draw.line([(cx - 60, 214), (cx - 18, 218)], fill=brow, width=8)
        draw.line([(cx + 18, 218), (cx + 60, 214)], fill=brow, width=8)
    else:
        draw.arc((cx - 62, 204, cx - 18, 226), 195, 345, fill=brow, width=7)
        draw.arc((cx + 18, 204, cx + 62, 226), 195, 345, fill=brow, width=7)

    # Eyes (sclera + iris + pupil + bright catchlight)
    for ex in (cx - 40, cx + 40):
        draw.ellipse((ex - 17, 228, ex + 17, 258), fill=WHITE, outline=OUTLINE, width=4)
        draw.ellipse((ex - 11, 232, ex + 11, 254), fill=_rgba(eye_rgb))
        draw.ellipse((ex - 6, 237, ex + 6, 249), fill=OUTLINE)
        draw.ellipse((ex - 7, 234, ex - 1, 240), fill=WHITE)

    # Nose
    draw.arc((cx - 10, 252, cx + 10, 276), 20, 160, fill=shadow, width=6)

    # Facial hair (goatee / mustache)
    hair_col = _rgba(hair_rgb)
    if facial == "goatee":
        draw.pieslice((cx - 32, 294, cx + 32, 342), 0, 180, fill=hair_col, outline=OUTLINE, width=4)
    if facial == "mustache":
        draw.chord((cx - 38, 276, cx + 4, 304), 180, 360, fill=hair_col, outline=OUTLINE, width=4)
        draw.chord((cx - 4, 276, cx + 38, 304), 180, 360, fill=hair_col, outline=OUTLINE, width=4)

    # Mouth
    if expression == "warm_smile":
        draw.arc((cx - 28, 276, cx + 28, 312), 15, 165, fill=OUTLINE, width=6)
    elif expression == "smirk":
        draw.arc((cx - 18, 282, cx + 32, 308), 5, 145, fill=OUTLINE, width=6)
    elif expression == "serious":
        draw.line([(cx - 22, 298), (cx + 22, 298)], fill=OUTLINE, width=6)
    elif expression == "cheerful":
        draw.chord((cx - 28, 280, cx + 28, 318), 0, 180, fill=(166, 68, 76, 255), outline=OUTLINE, width=5)
        draw.rectangle((cx - 18, 295, cx + 18, 303), fill=WHITE)
    elif expression == "curious":
        draw.ellipse((cx - 11, 288, cx + 11, 308), fill=(166, 68, 76, 255), outline=OUTLINE, width=5)


def _draw_eyewear(draw: ImageDraw.ImageDraw, eyewear: str) -> None:
    cx = CANVAS // 2
    frame = (36, 44, 62, 255)
    lens = (210, 236, 255, 70)

    if eyewear == "round":
        draw.ellipse((cx - 66, 218, cx - 12, 270), fill=lens, outline=frame, width=6)
        draw.ellipse((cx + 12, 218, cx + 66, 270), fill=lens, outline=frame, width=6)
        draw.line([(cx - 12, 242), (cx + 12, 242)], fill=frame, width=6)
        draw.line([(cx - 94, 236), (cx - 66, 240)], fill=frame, width=5)
        draw.line([(cx + 66, 240), (cx + 94, 236)], fill=frame, width=5)
    elif eyewear == "square":
        draw.rounded_rectangle((cx - 68, 222, cx - 12, 266), radius=10, fill=lens, outline=frame, width=6)
        draw.rounded_rectangle((cx + 12, 222, cx + 68, 266), radius=10, fill=lens, outline=frame, width=6)
        draw.line([(cx - 12, 240), (cx + 12, 240)], fill=frame, width=6)
        draw.line([(cx - 94, 236), (cx - 68, 238)], fill=frame, width=5)
        draw.line([(cx + 68, 238), (cx + 94, 236)], fill=frame, width=5)
    elif eyewear == "monocle":
        gold = (224, 184, 72, 255)
        draw.ellipse((cx + 12, 218, cx + 66, 270), fill=lens, outline=gold, width=6)
        draw.line([(cx + 66, 252), (cx + 80, 344)], fill=gold, width=4)
    elif eyewear == "shades":
        dark_lens = (30, 38, 56, 235)
        draw.rounded_rectangle((cx - 70, 222, cx - 10, 266), radius=12, fill=dark_lens, outline=OUTLINE, width=6)
        draw.rounded_rectangle((cx + 10, 222, cx + 70, 266), radius=12, fill=dark_lens, outline=OUTLINE, width=6)
        draw.line([(cx - 10, 236), (cx + 10, 236)], fill=OUTLINE, width=7)
        draw.line([(cx - 56, 232), (cx - 34, 254)], fill=(255, 255, 255, 95), width=6)
        draw.line([(cx + 24, 232), (cx + 46, 254)], fill=(255, 255, 255, 95), width=6)


def _draw_headwear(
    draw: ImageDraw.ImageDraw,
    headwear: str,
    main_rgb: tuple[int, int, int],
    accent_rgb: tuple[int, int, int],
) -> None:
    cx = CANVAS // 2
    hat = _darken(main_rgb, 0.88)
    band = _rgba(accent_rgb)

    if headwear == "fedora":
        draw.rounded_rectangle((cx - 82, 86, cx + 82, 168), radius=34, fill=hat, outline=OUTLINE, width=6)
        draw.rectangle((cx - 82, 144, cx + 82, 164), fill=band, outline=OUTLINE, width=4)
        draw.ellipse((cx - 128, 150, cx + 128, 190), fill=hat, outline=OUTLINE, width=6)
    elif headwear == "beret":
        draw.ellipse((cx - 104, 102, cx + 98, 184), fill=hat, outline=OUTLINE, width=6)
        draw.line([(cx - 4, 90), (cx + 10, 108)], fill=OUTLINE, width=7)
    elif headwear == "beanie":
        draw.pieslice((cx - 98, 92, cx + 98, 226), 180, 360, fill=hat, outline=OUTLINE, width=6)
        draw.rounded_rectangle((cx - 102, 148, cx + 102, 184), radius=14, fill=band, outline=OUTLINE, width=6)
        draw.ellipse((cx - 22, 74, cx + 22, 112), fill=band, outline=OUTLINE, width=6)
    elif headwear == "cap":
        draw.pieslice((cx - 98, 102, cx + 98, 222), 180, 360, fill=hat, outline=OUTLINE, width=6)
        draw.chord((cx - 40, 146, cx + 132, 198), 180, 360, fill=band, outline=OUTLINE, width=6)
    elif headwear == "headband":
        draw.arc((cx - 98, 134, cx + 98, 250), 192, 348, fill=band, width=16)


def render_avatar(index: int) -> Image.Image:
    """Deterministically render character portrait ``index`` (1..50)."""
    rng = random.Random(202614003 + index * 7919)

    backdrop = BACKDROPS[(index * 3 + rng.randrange(3)) % len(BACKDROPS)]
    skin = SKINS[(index * 5 + rng.randrange(len(SKINS))) % len(SKINS)]
    hair_base, hair_hi = HAIRS[(index * 7 + rng.randrange(len(HAIRS))) % len(HAIRS)]
    outfit_main, outfit_shirt, outfit_accent = OUTFIT_COLORS[(index * 3 + rng.randrange(len(OUTFIT_COLORS))) % len(OUTFIT_COLORS)]
    eye = EYE_COLORS[rng.randrange(len(EYE_COLORS))]

    hairstyle = HAIRSTYLES[(index - 1) % len(HAIRSTYLES)]
    outfit = OUTFITS[(index * 2 + rng.randrange(len(OUTFITS))) % len(OUTFITS)]
    expression = EXPRESSIONS[(index * 2 + rng.randrange(len(EXPRESSIONS))) % len(EXPRESSIONS)]
    eyewear = EYEWEAR[rng.randrange(len(EYEWEAR))]
    headwear = HEADWEAR[rng.randrange(len(HEADWEAR))]
    facial = FACIAL[rng.randrange(len(FACIAL))]

    # Avoid visual clash between tall/voluminous hairstyles and hats
    if hairstyle in ("bun", "twin_buns", "curly_puff", "spiky") and headwear in ("fedora", "beret", "beanie", "cap"):
        headwear = "none" if rng.random() < 0.78 else "headband"
    if hairstyle == "ponytail" and headwear in ("fedora", "beanie"):
        headwear = "none"

    # Base medallion
    bg = _draw_radial_backdrop(CANVAS, backdrop[0], backdrop[1])
    char_layer = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    # Mode "RGBA" enables proper alpha-blending for blush and tinted lenses.
    draw = ImageDraw.Draw(char_layer, "RGBA")

    _draw_hair_back(draw, hairstyle, hair_base)
    _draw_outfit(draw, outfit, outfit_main, outfit_shirt, outfit_accent)
    _draw_face(draw, skin, eye, hair_base, expression, facial)
    _draw_hair_front(draw, hairstyle, hair_base, hair_hi)
    if eyewear != "none":
        glass_layer = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
        _draw_eyewear(ImageDraw.Draw(glass_layer), eyewear)
        char_layer = Image.alpha_composite(char_layer, glass_layer)
        draw = ImageDraw.Draw(char_layer)
    if headwear != "none":
        _draw_headwear(draw, headwear, outfit_main, outfit_accent)

    # Composite character cleanly inside circular medallion mask
    combined = Image.alpha_composite(bg, char_layer)
    mask = Image.new("L", (CANVAS, CANVAS), 0)
    mdraw = ImageDraw.Draw(mask)
    margin = 18
    mdraw.ellipse((margin, margin, CANVAS - margin, CANVAS - margin), fill=255)

    final = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    final.paste(combined, (0, 0), mask)

    # Crisp outer token ring
    fdraw = ImageDraw.Draw(final)
    fdraw.ellipse((margin, margin, CANVAS - margin, CANVAS - margin), outline=(228, 236, 248, 220), width=8)
    fdraw.ellipse((margin + 6, margin + 6, CANVAS - margin - 6, CANVAS - margin - 6), outline=(20, 27, 42, 160), width=4)

    return final.resize((FINAL_SIZE, FINAL_SIZE), Image.Resampling.LANCZOS)


def generate_all(output_dir: Path = AVATAR_DIR, count: int = COUNT) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for idx in range(1, count + 1):
        out_path = output_dir / f"{idx}.png"
        img = render_avatar(idx)
        img.save(out_path, format="PNG", optimize=True)
        written.append(out_path)
    return written


if __name__ == "__main__":
    paths = generate_all()
    print(f"Generated {len(paths)} original avatar PNGs in {AVATAR_DIR}")
