"""Builds the logo and every image made from it: assets/logo.svg, logo.png, icon.ico, installer bitmaps.

Run from the repo root:  python assets/make_logo.py
The speed trails are computed (tapered strokes along curves), so tweak the numbers here, not the SVG.
"""

from __future__ import annotations

import io
import math
import random
from pathlib import Path

import resvg_py
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
GREEN, GREEN_LIGHT, WHITE = "#2D7F55", "#6FCF9A", "#FFFFFF"


def bezier(p0, p1, p2, p3, t):
    u = 1 - t
    return tuple(u**3 * a + 3 * u * u * t * b + 3 * u * t * t * c + t**3 * d for a, b, c, d in zip(p0, p1, p2, p3))


def trail(points, width, power=1.6, steps=48) -> str:
    """Closed path of a stroke along a cubic curve: a sharp point at the tail, `width` at the head."""
    left, right = [], []
    for i in range(steps + 1):
        t = i / steps
        x, y = bezier(*points, t)
        x2, y2 = bezier(*points, min(1, t + 1e-3))
        x1, y1 = bezier(*points, max(0, t - 1e-3))
        dx, dy = x2 - x1, y2 - y1
        n = math.hypot(dx, dy) or 1
        nx, ny = -dy / n, dx / n
        # Thin tail, full width near the puck, back to a point under it.
        w = width * (t ** power) * (1 - max(0, t - .85) / .15) / 2
        left.append((x + nx * w, y + ny * w))
        right.append((x - nx * w, y - ny * w))
    pts = left + right[::-1]
    return "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in pts) + " Z"


def build_svg() -> str:
    # Trails: (curve points, width, colour, opacity, gradient id). Tails start bottom-left, heads end behind the puck.
    trails = [
        (((-20, 420), (80, 396), (170, 300), (320, 262)), 62, "w", "tw1"),
        (((0, 300), (90, 294), (180, 236), (330, 222)), 32, "w", "tw2"),
        (((10, 490), (120, 466), (210, 370), (340, 318)), 44, "g", "tg1"),
        (((-10, 196), (80, 214), (180, 214), (330, 214)), 18, "w", "tw3"),
        (((80, 520), (180, 496), (260, 420), (350, 352)), 18, "gl", "tg2"),
        (((-6, 356), (70, 346), (150, 318), (300, 290)), 12, "w", "tw4"),
    ]
    colours = {"w": WHITE, "g": GREEN, "gl": GREEN_LIGHT}
    grads, paths = [], []
    for pts, width, colour, gid in trails:
        (x0, y0), *_, (x1, y1) = pts
        grads.append(f'<linearGradient id="{gid}" gradientUnits="userSpaceOnUse" x1="{x0}" y1="{y0}" x2="{x1}" y2="{y1}">'
                     f'<stop offset="0" stop-color="{colours[colour]}" stop-opacity="0"/>'
                     f'<stop offset=".55" stop-color="{colours[colour]}" stop-opacity=".75"/>'
                     f'<stop offset="1" stop-color="{colours[colour]}"/></linearGradient>')
        paths.append(f'<path d="{trail(pts, width)}" fill="url(#{gid})"/>')

    # Ice spray: small flecks near the trail heads, fixed seed so the logo never changes by itself.
    rng = random.Random(7)
    flecks = []
    for _ in range(26):
        t = rng.random()
        x = 90 + t * 120 + rng.uniform(-24, 24)
        y = 340 - t * 110 + rng.uniform(-70, 70)
        r = rng.uniform(1.2, 4.2)
        flecks.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="#FFFFFF" opacity="{rng.uniform(.35, .95):.2f}"/>')

    # Knurled grip on the puck side: short vertical lines, clipped to the side band.
    grip = "".join(f'<line x1="{x}" y1="-2" x2="{x}" y2="60" />' for x in range(-140, 141, 9))

    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">
  <title>Hockey Score Widget</title>
  <defs>
    <radialGradient id="bg" cx=".62" cy=".42" r=".8">
      <stop offset="0" stop-color="#17241E"/><stop offset=".55" stop-color="#0D1210"/><stop offset="1" stop-color="#070908"/>
    </radialGradient>
    <radialGradient id="glow" cx=".5" cy=".5" r=".5">
      <stop offset="0" stop-color="{GREEN_LIGHT}" stop-opacity=".55"/><stop offset="1" stop-color="{GREEN_LIGHT}" stop-opacity="0"/>
    </radialGradient>
    <linearGradient id="side" x1="0" x2="1">
      <stop offset="0" stop-color="#050607"/><stop offset=".38" stop-color="#2A2F35"/>
      <stop offset=".55" stop-color="#121417"/><stop offset="1" stop-color="#030404"/>
    </linearGradient>
    <radialGradient id="top" cx=".36" cy=".3" r=".85">
      <stop offset="0" stop-color="#5C636C"/><stop offset=".45" stop-color="#2A2F35"/><stop offset="1" stop-color="#0C0E10"/>
    </radialGradient>
    <linearGradient id="rim" x1="0" x2="1" y1="0" y2="0">
      <stop offset="0" stop-color="#FFFFFF" stop-opacity="0"/><stop offset=".35" stop-color="#FFFFFF" stop-opacity=".85"/>
      <stop offset=".7" stop-color="{GREEN_LIGHT}" stop-opacity=".9"/><stop offset="1" stop-color="{GREEN_LIGHT}" stop-opacity="0"/>
    </linearGradient>
    <clipPath id="tile"><rect width="512" height="512" rx="112"/></clipPath>
    <clipPath id="band"><path d="M-150 0 v58 a150 52 0 0 0 300 0 v-58 z"/></clipPath>
    <filter id="soft" x="-20%" y="-20%" width="140%" height="140%"><feGaussianBlur stdDeviation="6"/></filter>
    <filter id="shadow" x="-30%" y="-30%" width="160%" height="160%"><feGaussianBlur stdDeviation="14"/></filter>
    {"".join(grads)}
  </defs>
  <g clip-path="url(#tile)">
    <rect width="512" height="512" fill="url(#bg)"/>
    <!-- Ice: a long faint curve under everything, like a skate mark. -->
    <path d="M-20 468 C140 400 330 420 540 360" fill="none" stroke="{GREEN_LIGHT}" stroke-opacity=".18" stroke-width="10"/>
    <path d="M-20 494 C170 440 350 456 540 404" fill="none" stroke="#FFFFFF" stroke-opacity=".08" stroke-width="6"/>
    <ellipse cx="290" cy="250" rx="230" ry="160" fill="url(#glow)"/>
    <g filter="url(#soft)" opacity=".55">{"".join(paths[:3])}</g>
    {"".join(paths)}
    {"".join(flecks)}
    <!-- Puck, tilted as if flying. -->
    <g transform="translate(322 246) rotate(-17) scale(1.1)">
      <ellipse cx="6" cy="86" rx="150" ry="40" fill="#000000" opacity=".55" filter="url(#shadow)"/>
      <path d="M-150 0 v58 a150 52 0 0 0 300 0 v-58 z" fill="url(#side)"/>
      <g clip-path="url(#band)" stroke="#FFFFFF" stroke-opacity=".07" stroke-width="3">{grip}</g>
      <path d="M-150 58 a150 52 0 0 0 300 0" fill="none" stroke="#FFFFFF" stroke-opacity=".12" stroke-width="3"/>
      <ellipse cx="0" cy="0" rx="150" ry="52" fill="url(#top)"/>
      <ellipse cx="0" cy="0" rx="146" ry="49" fill="none" stroke="url(#rim)" stroke-width="6"/>
      <ellipse cx="-46" cy="-14" rx="70" ry="14" fill="#FFFFFF" opacity=".10" filter="url(#soft)"/>
    </g>
  </g>
</svg>
'''


def render(svg: str, px: int) -> Image.Image:
    return Image.open(io.BytesIO(resvg_py.svg_to_bytes(svg_string=svg, width=px))).convert("RGBA")


def installer_images(logo: Image.Image) -> None:
    font_dir = ROOT / "hockey_widget" / "fonts"
    bg, green = (17, 18, 20), (45, 127, 85)
    for scale, suffix in ((1, "100"), (2, "200")):
        w, h = 164 * scale, 314 * scale
        im = Image.new("RGBA", (w, h), bg + (255,))
        s = int(w * .8)
        im.alpha_composite(logo.resize((s, s), Image.LANCZOS), ((w - s) // 2, int(h * .17)))
        d = ImageDraw.Draw(im)
        big = ImageFont.truetype(str(font_dir / "BarlowCondensed-ExtraBold.ttf"), 26 * scale)
        small = ImageFont.truetype(str(font_dir / "BarlowCondensed-Medium.ttf"), 15 * scale)
        y = int(h * .17) + s + 8 * scale
        d.text((w / 2, y), "HOCKEY", font=big, fill=(236, 237, 239), anchor="mt")
        d.text((w / 2, y + 28 * scale), "SCORE WIDGET", font=small, fill=(111, 207, 154), anchor="mt")
        d.rectangle((0, h - 4 * scale, w, h), fill=green)
        im.convert("RGB").save(ROOT / "installer" / f"wizard-{suffix}.bmp")
        side = 55 * scale
        tile = Image.new("RGBA", (side, side), bg + (255,))
        t = int(side * .92)
        tile.alpha_composite(logo.resize((t, t), Image.LANCZOS), ((side - t) // 2, (side - t) // 2))
        tile.convert("RGB").save(ROOT / "installer" / f"petit-{suffix}.bmp")


# Lucide icons (ISC licence), from https://icones.js.org.
ICONS = {
    "monitor-down": '<path d="M12 13V7m3 3l-3 3l-3-3"/><rect width="20" height="14" x="2" y="3" rx="2"/><path d="M12 17v4m-4 0h8"/>',
    "download": '<path d="M12 15V3m9 12v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><path d="m7 10l5 5l5-5"/>',
}


def button(text: str, icon: str, primary: bool, name: str, scale: int = 2) -> None:
    """README button as a PNG at 2x (GitHub shows it at half size, so it stays sharp)."""
    font = ImageFont.truetype(str(ROOT / "hockey_widget" / "fonts" / "BarlowCondensed-Bold.ttf"), 23 * scale)
    ink = "#FFFFFF" if primary else "#ECEDEF"
    icon_px, pad, gap, h = 22 * scale, 22 * scale, 10 * scale, 52 * scale
    w = round(pad * 2 + icon_px + gap + font.getlength(text))
    im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    if primary:
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=10 * scale, fill="#2D7F55")
    else:
        d.rounded_rectangle((0, 0, w - 1, h - 1), radius=10 * scale, fill="#18191C", outline="#2D7F55", width=2 * scale)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24"><g fill="none" stroke="{ink}" '
           f'stroke-linecap="round" stroke-linejoin="round" stroke-width="2">{ICONS[icon]}</g></svg>')
    im.alpha_composite(render(svg, icon_px), (pad, (h - icon_px) // 2))
    d.text((pad + icon_px + gap, h / 2), text, font=font, fill=ink, anchor="lm")
    im.save(ROOT / "assets" / name)


def main() -> None:
    svg = build_svg()
    (ROOT / "assets" / "logo.svg").write_text(svg, encoding="utf-8")
    big = render(svg, 1024)
    big.resize((512, 512), Image.LANCZOS).save(ROOT / "assets" / "logo.png")
    big.save(ROOT / "assets" / "icon.ico", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
    installer_images(big)
    button("Installer pour Windows", "monitor-down", True, "bouton-installer.png")
    button("Télécharger l'exe seul", "download", False, "bouton-telecharger.png")


if __name__ == "__main__":
    main()
