"""Planisphere Watch for Xiaomi Smart Band 11: a flat vector planisphere face built as a Band 10/11 GMF project."""

import json
import shutil
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent
GMF = ROOT / "build" / "gmf"
DATA = ROOT / "data"

W, H = 212, 520
CENTER = (106, 262)
SS = 4
SAMPLE = {"hour": 10, "minute": 8, "second": 32, "month": 10, "day": 1, "weekday": 4, "battery": 82, "steps": 7645}

# Flat palette sampled from the reference artwork
BLACK = (0, 0, 0)
CHAR = (26, 26, 26)
GOLD = (181, 159, 129)
NAVY = (25, 39, 80)
NAVY_HI = (64, 84, 128)
RAY = (170, 186, 222)  # pale blue-white hairlines inside the crescent
RAY_STEP = 6  # degrees between hairlines
CRESCENT_GROOVE = True  # lighter band along the crescent's outer edge
GRID = (66, 62, 55)
AOD_DIM = 0.9
PANEL = BLACK  # capsule panel colour; CHAR restores the reference charcoal

FONT = "/System/Library/Fonts/Supplemental/Bodoni 72.ttc"
BOOK, BOLD = 0, 2

# Dial geometry (band px from CENTER)
R_OUTER = 104
R_TICKS = 98
R_NUMERALS = 91.5
R_NUM_IN = 85
R_SPARKLE = 78
R_SPARKLE_IN = 71
R_CHART = 68  # star window radius on the normal face
R_STARS = 84  # sky projection radius (equator); the AOD shows the sky out to here
DEC_LIMIT = 0
MAG_LIMIT = 3.8
# d3-celestial rank-1 constellations visible from the north, plus Lyra (Vega) and Ursa Minor (Polaris)
CONSTELLATIONS = {"And", "Aql", "Ari", "Aur", "Boo", "Cas", "Cyg", "Gem", "Leo", "Ori", "Peg", "Per",
                  "Tau", "UMa", "Vir", "Lyr", "UMi"}

# Crescent (rotates once a minute)
CRESCENT_R = 68
HOLE_R = 44
HOLE_SHIFT = 18  # hole sits near the rim (6px wall) ...
HOLE_DIR = 45  # ... under the top-right spade
MAX_HAND_R = 106  # pointer sprites are squares centred on the pivot; keep them within the 212px width


class Pen:
    """Supersampled vector drawing in band-pixel coordinates."""

    def __init__(self, w: int, h: int, bg=(0, 0, 0, 0)):
        self.img = Image.new("RGBA", (w * SS, h * SS), bg)
        self.d = ImageDraw.Draw(self.img)
        self.size = (w, h)

    @staticmethod
    def rgba(color, alpha=1.0):
        return tuple(color[:3]) + (int(255 * alpha),)

    def circle(self, cx, cy, r, color=None, width=0.8, fill=None, alpha=1.0):
        box = [(cx - r) * SS, (cy - r) * SS, (cx + r) * SS, (cy + r) * SS]
        self.d.ellipse(box, fill=self.rgba(fill) if fill else None,
                       outline=self.rgba(color, alpha) if color else None, width=max(1, round(width * SS)))

    def line(self, pts, color, width=0.8, alpha=1.0):
        self.d.line([(x * SS, y * SS) for x, y in pts], fill=self.rgba(color, alpha), width=max(1, round(width * SS)),
                    joint="curve")

    def poly(self, pts, fill=None, outline=None, width=0.8):
        pts = [(x * SS, y * SS) for x, y in pts]
        if fill:
            self.d.polygon(pts, fill=self.rgba(fill))
        if outline:
            self.d.line(pts + [pts[0]], fill=self.rgba(outline), width=max(1, round(width * SS)), joint="curve")

    def paste(self, sprite: Image.Image, x, y):
        big = sprite.resize((sprite.width * SS, sprite.height * SS), Image.LANCZOS)
        self.img.alpha_composite(big, (round(x * SS), round(y * SS)))

    def done(self) -> Image.Image:
        return self.img.resize(self.size, Image.LANCZOS)


def save(img: Image.Image, name: str, aod: bool = False) -> str:
    folder = GMF / ("images_aod" if aod else "images")
    folder.mkdir(parents=True, exist_ok=True)
    img.save(folder / f"{name}.png")
    return name


def font(size: float, weight: int = BOOK) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT, round(size * SS), index=weight)


def text_sprite(text: str, size: float, cell=None, color=GOLD, weight=BOOK, tracking: float = 0) -> Image.Image:
    f = font(size, weight)
    probe = Image.new("L", (round(size * SS * (len(text) + 2)), round(size * SS * 2)))
    draw = ImageDraw.Draw(probe)
    x = 0
    for ch in text:
        draw.text((x, 0), ch, font=f, fill=255)
        x += draw.textlength(ch, font=f) + tracking * SS
    box = probe.getbbox() or (0, 0, 1, 1)
    ref = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), "0", font=f)
    ink = probe.crop((box[0], ref[1], box[2], ref[3]))
    w = cell[0] * SS if cell else ink.width + 2 * SS
    h = cell[1] * SS if cell else ink.height + 2 * SS
    mask = Image.new("L", (w, h))
    mask.paste(ink, ((w - ink.width) // 2, (h - ink.height) // 2))
    mask = mask.resize((w // SS, h // SS), Image.LANCZOS)
    out = Image.new("RGBA", mask.size, color + (0,))
    out.putalpha(mask)
    return out


def sparkle(pen: Pen, cx, cy, r, color, fill=None, width=0.6, inner=0.28):
    """Four-pointed star (the reference's recurring motif)."""
    pts = []
    for i in range(8):
        a = np.radians(i * 45)
        rr = r if i % 2 == 0 else r * inner
        pts.append((cx + rr * np.sin(a), cy - rr * np.cos(a)))
    pen.poly(pts, fill=fill, outline=color, width=width)


def project_sky(ra: float, dec: float, rim_r: float, rim_dec: float = DEC_LIMIT) -> tuple[float, float]:
    """North-polar azimuthal equidistant projection; returns offsets from the centre."""
    r = (90 - dec) / (90 - rim_dec) * rim_r
    t = np.radians(ra)
    return r * np.sin(t), r * np.cos(t)


def star_layer(size: int, clip_r: float, color=GOLD, line_alpha=1.0, star_scale=1.0, line_w=1.1) -> Image.Image:
    """Real stars (d3-celestial, BSD-3) and simplified constellation lines, clipped to clip_r."""
    stars = json.loads((DATA / "stars.6.json").read_text())["features"]
    lines = json.loads((DATA / "constellations.lines.json").read_text())["features"]
    c = size / 2
    visible = np.array([f["geometry"]["coordinates"] for f in stars
                        if f["properties"]["mag"] <= MAG_LIMIT and f["geometry"]["coordinates"][1] >= DEC_LIMIT])

    def is_visible(ra, dec):
        d_ra = (visible[:, 0] - ra + 180) % 360 - 180
        return bool((np.hypot(d_ra * np.cos(np.radians(dec)), visible[:, 1] - dec) < 0.3).any())

    def at(ra, dec):
        x, y = project_sky(ra, dec, R_STARS)
        return c + x, c + y

    pen = Pen(size, size)
    for feature in lines:
        if feature["id"] not in CONSTELLATIONS:
            continue
        for path in feature["geometry"]["coordinates"]:
            # Only segments between drawn stars, so no line ends in empty sky
            for a, b in zip(path, path[1:]):
                if is_visible(*a) and is_visible(*b):
                    pen.line([at(*a), at(*b)], color, line_w, alpha=line_alpha)
    for feature in stars:
        mag = feature["properties"]["mag"]
        ra, dec = feature["geometry"]["coordinates"]
        if mag > MAG_LIMIT or dec < DEC_LIMIT:
            continue
        x, y = at(ra, dec)
        k = np.clip((MAG_LIMIT - mag) / (MAG_LIMIT + 1.5), 0, 1)
        if k > 0.55:
            sparkle(pen, x, y, (2.2 + 2.2 * k) * star_scale, None, fill=color, inner=0.3)
        else:
            pen.circle(x, y, (0.55 + 1.1 * k) * star_scale, fill=color)
    img = pen.done()
    yy, xx = np.mgrid[:size, :size] - c
    a = np.asarray(img).astype(float)
    a[..., 3] *= np.clip((clip_r - np.hypot(xx, yy)) / 1.5, 0, 1)
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def chart_grid(pen: Pen, cx, cy, clip_r, color, alpha):
    """RA spokes every 2h and Dec 30/60 circles, in the star map's projection."""
    for dec in (60, 30):
        r = (90 - dec) / (90 - DEC_LIMIT) * R_STARS
        if r < clip_r:
            pen.circle(cx, cy, r, color, 0.75, alpha=alpha)
    for ra in range(0, 360, 30):
        x, y = project_sky(ra, DEC_LIMIT, clip_r)
        pen.line([(cx, cy), (cx + x, cy + y)], color, 0.75, alpha=alpha)


def numerals(pen: Pen, cx, cy, color, size=9.5):
    """Roman numerals set along the ring, tops facing outward like the reference."""
    for i, num in enumerate(["XII", "I", "II", "III", "IV", "V", "VI", "VII", "VIII", "IX", "X", "XI"]):
        sprite = text_sprite(num, size, color=color, weight=BOLD, tracking=0.3)
        ang = i * 30
        sprite = sprite.rotate(-ang, expand=True, resample=Image.BICUBIC)
        t = np.radians(ang)
        x = cx + R_NUMERALS * np.sin(t) - sprite.width / 2
        y = cy - R_NUMERALS * np.cos(t) - sprite.height / 2
        pen.paste(sprite, x, y)


def dial(pen: Pen, cx, cy, color, aod=False):
    """Static rings, ticks, numerals and sparkle band; the AOD keeps only the numerals."""
    if aod:
        numerals(pen, cx, cy, color)
        return
    pen.circle(cx, cy, R_OUTER, color, 0.9)
    for i in range(60):
        t = np.radians(i * 6)
        inner = R_OUTER - (4.5 if i % 5 == 0 else 2.2)
        pen.line([(cx + inner * np.sin(t), cy - inner * np.cos(t)),
                  (cx + R_OUTER * np.sin(t), cy - R_OUTER * np.cos(t))], color, 0.7 if i % 5 else 0.9)
    pen.circle(cx, cy, R_TICKS, color, 0.5)
    numerals(pen, cx, cy, color)
    pen.circle(cx, cy, R_NUM_IN, color, 0.6)
    for i in range(24):
        t = np.radians(i * 15 + 7.5)
        sparkle(pen, cx + R_SPARKLE * np.sin(t), cy - R_SPARKLE * np.cos(t), 3.2, color, width=0.5)
    pen.circle(cx, cy, R_SPARKLE_IN, color, 0.6)


def background() -> Image.Image:
    pen = Pen(W, H, BLACK + (255,))
    inset, frame = 4, 7
    pen.d.rounded_rectangle([inset * SS, inset * SS, (W - inset) * SS, (H - inset) * SS],
                            radius=(W / 2 - inset) * SS, fill=PANEL + (255,))
    # Faint sector grid around the dial, like the reference backdrop
    cx, cy = CENTER
    grid = Pen(W, H)
    for r in (120, 152, 192, 240, 300):
        grid.circle(cx, cy, r, GRID, 1.1)
    for i in range(24):
        t = np.radians(i * 15)
        grid.line([(cx + 108 * np.sin(t), cy - 108 * np.cos(t)), (cx + 420 * np.sin(t), cy - 420 * np.cos(t))], GRID, 1.1)
    pen.img.alpha_composite(grid.img)
    pen.d.rounded_rectangle([frame * SS, frame * SS, (W - frame) * SS, (H - frame) * SS],
                            radius=(W / 2 - frame) * SS, outline=GOLD + (255,), width=round(0.8 * SS))
    # Dial
    pen.circle(cx, cy, R_OUTER + 1, fill=PANEL)
    pen.circle(cx, cy, R_CHART, fill=tuple(max(0, v - 10) for v in PANEL))
    chart_grid(pen, cx, cy, R_CHART, GOLD, 0.5)
    stars = star_layer(W, R_CHART)
    pen.paste(stars, cx - W / 2, cy - W / 2)
    sparkle(pen, cx, cy, 7, GOLD, fill=GOLD, inner=0.38)
    dial(pen, cx, cy, GOLD)
    # Top info plate, and a star finial under the time
    plate(pen, 106, 56, 164, 56)
    pen.line([(70, 474), (142, 474)], GOLD, 0.6)
    sparkle(pen, 106, 474, 6.5, GOLD, fill=GOLD, inner=0.25)
    return pen.done()


def plate(pen: Pen, cx, cy, w, h, color=GOLD):
    """Elongated hexagon label plate from the reference header."""
    pts = [(cx - w / 2, cy), (cx - w / 2 + h / 2, cy - h / 2), (cx + w / 2 - h / 2, cy - h / 2),
           (cx + w / 2, cy), (cx + w / 2 - h / 2, cy + h / 2), (cx - w / 2 + h / 2, cy + h / 2)]
    pen.poly(pts, fill=BLACK, outline=color, width=0.8)
    pen.line([(cx - 22, cy - 1), (cx + 22, cy - 1)], color, 0.6)  # rule between weekday and date


def spade_masks(size: int, c: float, ang: float) -> tuple[np.ndarray, np.ndarray]:
    """Card-suit spade (tip outward, round lobes, stem sunk into the crescent) as SS-res fill/inlay masks."""
    k = SS
    t = np.radians(ang)
    u = np.array([np.sin(t), -np.cos(t)])
    v = np.array([np.cos(t), np.sin(t)])
    root = np.array([c, c]) + u * (CRESCENT_R - 4)
    P = lambda a_, b_: tuple((root + u * a_ + v * b_) * k)
    fill = Image.new("L", (size * k, size * k))
    d = ImageDraw.Draw(fill)
    lobe_u, lobe_v, lobe_r = 13, 5.6, 5.8
    for side in (-1, 1):
        x, y = P(lobe_u, side * lobe_v)
        d.ellipse([x - lobe_r * k, y - lobe_r * k, x + lobe_r * k, y + lobe_r * k], fill=255)
    d.polygon([P(lobe_u + 1.2, -11.2), P(30, 0), P(lobe_u + 1.2, 11.2)], fill=255)
    d.polygon([P(0, -4.5), P(0, 4.5), P(10, 1.4), P(10, -1.4)], fill=255)
    inlay = Image.new("L", fill.size)
    ImageDraw.Draw(inlay).polygon([P(12, 0), P(16.5, -2.6), P(22, 0), P(16.5, 2.6)], fill=255)
    return np.asarray(fill).astype(float) / 255, np.asarray(inlay).astype(float) / 255


def crescent_sprite() -> Image.Image:
    """Eccentric navy crescent with hairline rays, an inner groove, rim diamonds and four card spades."""
    size, c = MAX_HAND_R * 2, MAX_HAND_R
    ht = np.radians(HOLE_DIR)
    hx, hy = c + HOLE_SHIFT * np.sin(ht), c - HOLE_SHIFT * np.cos(ht)
    body = Pen(size, size)
    body.circle(c, c, CRESCENT_R, fill=NAVY)
    # Groove and rays live inside the crescent only
    deco = Pen(size, size)
    if CRESCENT_GROOVE:
        deco.circle(c, c, CRESCENT_R - 6, NAVY_HI, 2.2)
    for i in range(360 // RAY_STEP):
        t = np.radians(i * RAY_STEP)
        deco.line([(c + (HOLE_R - 20) * np.sin(t), c - (HOLE_R - 20) * np.cos(t)),
                   (c + (CRESCENT_R - 9) * np.sin(t), c - (CRESCENT_R - 9) * np.cos(t))], RAY, 0.6, alpha=0.6)
    hole = Image.new("L", body.img.size)
    ImageDraw.Draw(hole).ellipse([(hx - HOLE_R) * SS, (hy - HOLE_R) * SS, (hx + HOLE_R) * SS, (hy + HOLE_R) * SS], fill=255)
    # Keep the groove clear of the thin side of the crescent
    groove_keep = Image.new("L", body.img.size)
    gk = ImageDraw.Draw(groove_keep)
    gk.ellipse([(c - CRESCENT_R + 2) * SS, (c - CRESCENT_R + 2) * SS, (c + CRESCENT_R - 2) * SS, (c + CRESCENT_R - 2) * SS], fill=255)
    gk.ellipse([(hx - HOLE_R - 4) * SS, (hy - HOLE_R - 4) * SS, (hx + HOLE_R + 4) * SS, (hy + HOLE_R + 4) * SS], fill=0)
    deco_a = np.asarray(deco.img).astype(float)
    deco_a[..., 3] *= np.asarray(groove_keep).astype(float) / 255
    body.img.alpha_composite(Image.fromarray(deco_a.astype(np.uint8), "RGBA"))
    a = np.asarray(body.img).astype(float)
    a[..., 3] *= 1 - np.asarray(hole).astype(float) / 255
    body.img = Image.fromarray(a.astype(np.uint8), "RGBA")
    body.d = ImageDraw.Draw(body.img)
    body.circle(c, c, CRESCENT_R, GOLD, 0.9)
    body.circle(hx, hy, HOLE_R, GOLD, 0.9)
    # Small diamonds on the rim at the quarters
    for ang in (0, 90, 180, 270):
        t = np.radians(ang)
        x, y = c + CRESCENT_R * np.sin(t), c - CRESCENT_R * np.cos(t)
        body.poly([(x, y - 3), (x + 2.2, y), (x, y + 3), (x - 2.2, y)], fill=NAVY, outline=GOLD, width=0.6)

    # Spades on the diagonals: gold rim only outside the crescent, navy fill flowing into it
    yy, xx = np.mgrid[: size * SS, : size * SS] / SS - c
    outside = np.clip(np.hypot(xx, yy) - CRESCENT_R + 0.5, 0, 1)
    out = np.asarray(body.img).astype(float)
    for ang in (45, 135, 225, 315):
        fill, inlay = spade_masks(size, c, ang)
        rim = np.asarray(Image.fromarray((fill * 255).astype(np.uint8)).filter(
            ImageFilter.MaxFilter(round(0.9 * SS) * 2 + 1))).astype(float) / 255
        for color, alpha in ((GOLD, np.clip(rim - fill, 0, 1) * outside), (NAVY, fill), (GOLD, inlay)):
            a_ = alpha[..., None]
            out[..., :3] = out[..., :3] * (1 - a_) + np.array(color, float) * a_
            out[..., 3:] = np.maximum(out[..., 3:], a_ * 255)
    body.img = Image.fromarray(out.astype(np.uint8), "RGBA")
    return body.done()


HAND_SCALE = 0.42  # traced source px to band px; puts the minute tip on the tick ring


def drawn_hand(name: str, gold=GOLD, inlay=NAVY) -> Image.Image:
    """Hand from the vector trace in data/hands.json: solid gold with navy cut-outs, pivot at the sprite centre."""
    spec = json.loads((DATA / "hands.json").read_text())[name]
    pts = np.array(spec["body"]) * HAND_SCALE
    r = int(np.ceil(np.hypot(*pts.T).max())) + 2
    pen = Pen(2 * r, 2 * r)
    P = lambda poly: [(r + x * HAND_SCALE, r + y * HAND_SCALE) for x, y in poly]
    pen.poly(P(spec["body"]), fill=gold)
    # Slight fall-off toward the tip gives the flat gold some depth
    a = np.asarray(pen.img).astype(float)
    ys = np.arange(2 * r * SS)[:, None] / SS
    a[..., :3] *= np.clip(1.06 - (r - ys) / 600, 0.86, 1.06)[..., None]
    pen.img = Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGBA")
    pen.d = ImageDraw.Draw(pen.img)
    for hole in (False, True):  # cut-outs first, then the light holes inside them
        for item in spec["inlays"]:
            if item["hole"] == hole:
                pen.poly(P(item["points"]), fill=gold if hole else inlay)
    return pen.done()


def pointer(name, sprite, source, style, max_value, end_angle, aod=False) -> dict:
    pivot = sprite.width // 2
    element = {
        "type": "widge_pointer",
        "x": CENTER[0] - pivot,
        "y": CENTER[1] - pivot,
        "dataSrc": source,
        "image": save(sprite, name, aod),
        "pointerStyle": style,
        "pivotX": pivot,
        "pivotY": pivot,
        "maxValue": max_value,
        "startAngle": 0,
        "endAngle": end_angle,
    }
    if style == "rotate":
        element["imageList"] = [save(Image.new("RGBA", sprite.size), f"{name}-blank", aod)]
    return element


def digits(prefix, size, cell, color=GOLD, weight=BOOK, aod=False) -> list[str]:
    names = [save(text_sprite(str(n), size, cell, color, weight), f"{prefix}-{n}", aod) for n in range(10)]
    return names + [save(Image.new("RGBA", cell), f"{prefix}-minus", aod)]


def number(x, y, source, digit_names, count, align, zero=True, unit=None) -> dict:
    element = {
        "type": "widge_dignum", "x": x, "y": y, "showCount": count,
        "align": {"right": 0, "left": 1, "center": 2}[align], "spacing": 0, "showZero": zero,
        "dataSrc": source, "imageList": digit_names,
    }
    if unit:
        element["image"] = unit
    return element


def image(x, y, name) -> dict:
    return {"type": "element", "x": x, "y": y, "image": name}


def icon(size, draw_fn, color=GOLD) -> Image.Image:
    pen = Pen(*size)
    draw_fn(pen, color)
    return pen.done()


def aod_background() -> Image.Image:
    dim = tuple(int(v * AOD_DIM) for v in GOLD)
    pen = Pen(W, H, BLACK + (255,))
    cx, cy = CENTER
    pen.paste(star_layer(W, R_NUM_IN - 2, GOLD, line_alpha=0.6, star_scale=1.6, line_w=0.6), cx - W / 2, cy - W / 2)
    dial(pen, cx, cy, dim, aod=True)
    return pen.done()


def build() -> None:
    shutil.rmtree(GMF, ignore_errors=True)
    dim = tuple(int(v * AOD_DIM) for v in GOLD)
    save(background(), "bg")

    weekdays = [save(text_sprite(d, 17, (54, 20), weight=BOLD, tracking=2.2), f"wd-{d.lower()}")
                for d in ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]]
    date_digits = digits("d", 25, (15, 26))
    slash = save(text_sprite("/", 25, (10, 26)), "d-slash")
    small = digits("s", 18, (11, 20), weight=BOLD)
    pct = save(text_sprite("%", 14, (14, 20), weight=BOLD), "s-pct")
    time_digits = digits("t", 40, (22, 32))
    colon = save(text_sprite(":", 40, (10, 32)), "t-colon")

    def battery(pen, color):
        pen.d.rounded_rectangle([1 * SS, 2 * SS, 17 * SS, 10 * SS], radius=2 * SS, outline=color + (255,), width=SS)
        pen.d.rectangle([18 * SS, 4.5 * SS, 19.2 * SS, 7.5 * SS], fill=color + (255,))
        pen.d.rectangle([3 * SS, 4 * SS, 12 * SS, 8 * SS], fill=color + (255,))

    def steps(pen, color):
        sparkle(pen, 6, 6, 5.5, color, width=0.8)

    bat_icon = save(icon((21, 12), battery).resize((25, 14), Image.LANCZOS), "i-battery")
    step_icon = save(icon((12, 12), steps).resize((15, 15), Image.LANCZOS), "i-steps")

    def clock(digit_names, colon_name):
        return [number(101, 388, "0811", digit_names, 2, "right"), image(101, 388, colon_name),
                number(111, 388, "1011", digit_names, 2, "left")]

    normal = [
        image(0, 0, "bg"),
        # Two-row plate centred on x=106: weekday (54px) above "10/01" (70px)
        {"type": "widge_imagelist", "x": 79, "y": 33, "dataSrc": "2012", "imageList": weekdays,
         "imageIndexList": list(range(7))},
        number(71, 57, "1012", date_digits, 2, "left"),
        image(101, 57, slash),
        number(111, 57, "1812", date_digits, 2, "left"),
        image(24, 99, bat_icon),
        number(53, 96, "0841", small, 3, "left", zero=False, unit=pct),
        image(117, 98, step_icon),
        number(188, 96, "0821", small, 5, "right", zero=False),
        *clock(time_digits, colon),
        pointer("crescent", crescent_sprite(), "1811", "simple", 60, 3600),
        pointer("hour", drawn_hand("hour"), "0811", "rotate", 24, 7200),
        pointer("minute", drawn_hand("minute"), "1011", "rotate", 60, 3600),
    ]

    save(aod_background(), "aod-bg", aod=True)
    aod_digits = digits("ad", 25, (15, 26), dim, aod=True)
    aod_slash = save(text_sprite("/", 25, (10, 26), dim), "ad-slash", aod=True)
    # Stars and the digital time run at full brightness on the AOD; everything else at AOD_DIM
    aod_time = digits("at", 40, (22, 32), GOLD, aod=True)
    aod_colon = save(text_sprite(":", 40, (10, 32), GOLD), "at-colon", aod=True)
    aod = [
        image(0, 0, "aod-bg"),
        # "10/01" is 70px wide, centred on x=106
        number(71, 45, "1012", aod_digits, 2, "left"),
        image(101, 45, aod_slash),
        number(111, 45, "1812", aod_digits, 2, "left"),
        *clock(aod_time, aod_colon),
        pointer("aod-hour", drawn_hand("hour", dim, BLACK), "0811", "rotate", 24, 7200, aod=True),
        pointer("aod-minute", drawn_hand("minute", dim, BLACK), "1011", "rotate", 60, 3600, aod=True),
    ]

    normal_preview = render(normal, "images")
    normal_preview.convert("RGB").save(GMF / "images" / "preview.png")
    definition = {
        "name": "Planisphere Watch",
        "id": "531900110",
        "previewImg": "preview",
        "elementsNormal": normal,
        "elementsAod": aod,
    }
    (GMF / "wfDef.json").write_text(json.dumps(definition, indent=2) + "\n")

    sheet = Image.new("RGBA", (W * 2 + 20, H), (40, 40, 40, 255))
    sheet.paste(pill(normal_preview), (0, 0))
    sheet.paste(pill(render(aod, "images_aod")), (W + 20, 0))
    sheet.save(ROOT / "build" / "preview-normal-aod.png")
    print(f"GMF written to {GMF}")


def render(elements: list[dict], folder: str) -> Image.Image:
    canvas = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    load = lambda name: Image.open(GMF / folder / f"{name}.png").convert("RGBA")
    sources = {"0811": "hour", "1011": "minute", "1811": "second", "1012": "month", "1812": "day",
               "2012": "weekday", "0841": "battery", "0821": "steps"}
    for el in elements:
        if el["type"] == "element":
            canvas.alpha_composite(load(el["image"]), (el["x"], el["y"]))
        elif el["type"] == "widge_imagelist":
            value = SAMPLE[sources[el["dataSrc"]]]
            canvas.alpha_composite(load(el["imageList"][el["imageIndexList"].index(value)]), (el["x"], el["y"]))
        elif el["type"] == "widge_dignum":
            value = SAMPLE[sources[el["dataSrc"]]]
            text = str(value).zfill(el["showCount"]) if el["showZero"] else str(value)
            glyphs = [load(el["imageList"][int(c)]) for c in text] + ([load(el["image"])] if "image" in el else [])
            total = sum(g.width for g in glyphs)
            x = {1: el["x"], 2: el["x"] - total // 2, 0: el["x"] - total}[el["align"]]
            for g in glyphs:
                canvas.alpha_composite(g, (x, el["y"]))
                x += g.width
        elif el["type"] == "widge_pointer":
            value = SAMPLE[sources[el["dataSrc"]]]
            if el["dataSrc"] == "0811":
                value += SAMPLE["minute"] / 60  # firmware moves the hour hand smoothly (verified on device)
            angle = el["startAngle"] + (el["endAngle"] - el["startAngle"]) * value / el["maxValue"]
            layer = Image.new("RGBA", (W, H))
            layer.alpha_composite(load(el["image"]), (el["x"], el["y"]))
            pivot = (el["x"] + el["pivotX"], el["y"] + el["pivotY"])
            canvas.alpha_composite(layer.rotate(-angle / 10, center=pivot, resample=Image.BICUBIC))
    return canvas


def pill(img: Image.Image) -> Image.Image:
    mask = Image.new("L", (W, H))
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, W - 1, H - 1), radius=W // 2, fill=255)
    out = Image.new("RGBA", (W, H), (40, 40, 40, 255))
    out.paste(img, (0, 0), mask)
    return out


if __name__ == "__main__":
    build()
