"""Draws the scoreboard as an image for the app window, from the same state the OBS widget reads.

It mirrors widget.html (same sizes, colours, layouts) so the app can show a faithful preview
without a browser. The browser widget stays the reference: change both together.
"""

from __future__ import annotations

import io
import math
import threading
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

FONTS = Path(__file__).parent / "fonts"
SILVER = ((0.0, (244, 246, 248, 255)), (0.45, (142, 149, 156, 255)), (0.70, (217, 221, 225, 255)),
          (1.0, (107, 113, 120, 255)))
GLOSS = ((0.0, (255, 255, 255, 56)), (0.48, (255, 255, 255, 10)), (0.52, (0, 0, 0, 26)), (1.0, (0, 0, 0, 71)))
SEPARATOR = (154, 160, 166)
LIVE_DOT = (229, 72, 77)
CENTER_PAD = 14
NHL_LOGO_SCALE = 1.68  # NHL SVGs have wide empty margins, as in widget.html


def _rgb(colour: str) -> tuple[int, int, int]:
    return tuple(int(colour[i:i + 2], 16) for i in (1, 3, 5))


def _font(weight: str, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONTS / f"BarlowCondensed-{weight}.ttf"), max(1, round(size)))


class LogoCache:
    """Logos as images. NHL logos download in the background; until then the side shows no logo."""

    def __init__(self, on_ready=None) -> None:
        self._svg: dict[str, bytes] = {}
        self._images: dict[tuple[str, int], Image.Image] = {}
        self._pending: set[str] = set()
        self._lock = threading.Lock()
        self._on_ready = on_ready

    def get(self, source: str, px: int) -> Image.Image | None:
        if px <= 0 or not source:
            return None
        key = (source, px)
        with self._lock:
            if key in self._images:
                return self._images[key]
            data = self._svg.get(source)
        if source.startswith("http"):
            if data is None:
                self._download(source)
                return None
            image = _raster(data, px, svg=True)
        else:
            try:
                data = Path(source).read_bytes()
            except OSError:
                return None
            image = _raster(data, px, svg=source.lower().endswith(".svg"))
        with self._lock:
            self._images[key] = image
        return image

    def _download(self, url: str) -> None:
        with self._lock:
            if url in self._pending:
                return
            self._pending.add(url)

        def work() -> None:
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "hockey-score-widget"})
                with urllib.request.urlopen(request, timeout=10) as response:
                    data = response.read(2_000_000)
            except OSError:
                data = None  # offline: no logo in the preview, the widget still tries on its own
            with self._lock:
                self._pending.discard(url)
                if data:
                    self._svg[url] = data
            if data and self._on_ready:
                self._on_ready()
        threading.Thread(target=work, daemon=True).start()


def _raster(data: bytes, px: int, svg: bool) -> Image.Image | None:
    try:
        if svg:
            import resvg_py
            data = resvg_py.svg_to_bytes(svg_string=data.decode("utf-8"), width=px)
        image = Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception:  # broken or unsupported file: show no logo rather than crash the app
        return None
    image.thumbnail((px, px), Image.LANCZOS)
    return image


def _gradient(width: int, height: int, stops) -> Image.Image:
    """Vertical RGBA gradient, like CSS linear-gradient(180deg, ...)."""
    column = Image.new("RGBA", (1, height))
    for y in range(height):
        t = y / max(1, height - 1)
        for (t0, c0), (t1, c1) in zip(stops, stops[1:]):
            if t0 <= t <= t1:
                k = (t - t0) / max(1e-6, t1 - t0)
                column.putpixel((0, y), tuple(round(a + (b - a) * k) for a, b in zip(c0, c1)))
                break
    return column.resize((width, height))


def _text_width(text: str, font: ImageFont.FreeTypeFont, spacing: float) -> float:
    if not text:
        return 0.0
    return font.getlength(text) + spacing * len(text)


def _draw_text(draw: ImageDraw.ImageDraw, cx: float, cy: float, text: str, font, spacing: float,
               fill, shadow: bool = True) -> None:
    """Centred text with CSS-like letter spacing and a soft drop shadow."""
    x = cx - _text_width(text, font, spacing) / 2 + spacing / 2
    for char in text:
        if shadow:
            draw.text((x, cy + 2), char, font=font, fill=(0, 0, 0, 110), anchor="lm")
        draw.text((x, cy), char, font=font, fill=fill, anchor="lm")
        x += font.getlength(char) + spacing


def render(state: dict, settings: dict, logos: LogoCache, scale: float = 2.0,
           custom_logo=lambda _abbrev: None) -> Image.Image | None:
    """The scoreboard at `scale` times its OBS size, or None when there is no game to show."""
    game, style = state.get("game"), state.get("style") or {}
    if not game or not style:
        return None
    s = lambda key: style[key] * scale  # noqa: E731 - sizes in output pixels
    height, border = round(s("bar_height")), round(s("border"))
    inner_h = height - 2 * border
    text = _rgb(style["text"]) + (255,)

    name_font = _font("Bold", s("name_size"))
    sog_font = _font("Medium", s("name_size") * .4)
    score_font = _font("ExtraBold", s("score_size"))
    clock_font = _font("Bold", s("clock_size"))
    period_font = _font("Bold", s("period_size"))

    def side_parts(team: dict) -> dict:
        show_sog = style["show_sog"] and team.get("sog") is not None
        name = team["label"].upper() if style["show_names"] else ""
        sog = f"Tirs {team['sog']}" if show_sog else ""
        label_w = max(_text_width(name, name_font, s("name_spacing")), _text_width(sog, sog_font, 0))
        logo = None
        if style["show_logos"] and team.get("logo"):
            path = custom_logo(team["abbrev"])
            if path:
                logo = logos.get(str(path), round(s("logo_size")))
            else:
                logo = logos.get(team["logo"], round(s("logo_size") * NHL_LOGO_SCALE))
        logo_w = s("logo_size") if logo or (style["show_logos"] and team.get("logo")) else 0
        gap = s("logo_gap") if logo_w and label_w else 0
        width = 2 * s("team_padding") + logo_w + gap + label_w
        colour = team["color"] if style["team_colors"] and team.get("color") else style["accent"]
        score = str(team["score"])
        score_w = max(s("score_width"), _text_width(score, score_font, s("score_spacing")) + 8 * scale)
        return dict(name=name, sog=sog, label_w=label_w, logo=logo, logo_w=logo_w, gap=gap, width=width,
                    colour=_rgb(colour), score=score, score_w=score_w)

    away, home = side_parts(game["away"]), side_parts(game["home"])
    period = (game.get("period") or "") if style["show_period"] else ""
    clock = game.get("clock") or ""
    show_center = style["show_status"]
    center_w = 0.0
    if show_center:
        dot = 14 * scale if period and game.get("live") else 0
        center_w = max(s("center_width"), 2 * CENTER_PAD * scale + max(
            _text_width(period, period_font, 0) + dot, _text_width(clock, clock_font, s("clock_spacing"))))
    cells = [("team", away), ("score", away), ("center", None), ("score", home), ("team", home)]
    widths = [away["width"], away["score_w"], center_w + (4 * scale if show_center else 0), home["score_w"], home["width"]]
    inner_w = round(sum(widths))
    width = inner_w + 2 * border

    # Background layer: silver frame, coloured cells, gloss.
    back = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    mask = Image.new("L", (width, height), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=round(s("radius")), fill=255)
    back.paste(_gradient(width, height, SILVER), (0, 0), mask)
    inner = Image.new("RGBA", (inner_w, inner_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(inner)
    x = 0.0
    spans = []
    for (kind, team), w in zip(cells, widths):
        x0, x1 = round(x), round(x + w)
        if kind == "team":
            draw.rectangle((x0, 0, x1, inner_h), fill=team["colour"])
        elif kind == "score":
            dark = tuple(round(c * .72) for c in team["colour"])
            draw.rectangle((x0, 0, x1, inner_h), fill=dark)
        elif w:
            draw.rectangle((x0, 0, x1, inner_h), fill=_rgb(style["background"]))
            draw.rectangle((x0, 0, x0 + round(2 * scale) - 1, inner_h), fill=SEPARATOR)
            draw.rectangle((x1 - round(2 * scale), 0, x1, inner_h), fill=SEPARATOR)
        spans.append((x0, x1))
        x += w
    if style["show_gloss"]:
        inner = Image.alpha_composite(inner, _gradient(inner_w, inner_h, GLOSS))
    inner_mask = Image.new("L", (inner_w, inner_h), 0)
    ImageDraw.Draw(inner_mask).rounded_rectangle((0, 0, inner_w - 1, inner_h - 1),
                                                 radius=max(0, round(s("radius") - s("border"))), fill=255)
    back.paste(inner, (border, border), inner_mask)

    # Content layer: logos and text, never skewed (the widget straightens them too).
    front = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(front)
    mid = height / 2

    def team_content(team: dict, x0: float, x1: float, logo_first: bool) -> None:
        left = border + x0 + s("team_padding")
        blocks = [("logo", team["logo_w"]), ("gap", team["gap"]), ("label", team["label_w"])]
        if not logo_first:
            blocks.reverse()
        for kind, w in blocks:
            if kind == "logo" and team["logo"] is not None:
                img = team["logo"]
                front.alpha_composite(img, (round(left + w / 2 - img.width / 2), round(mid - img.height / 2)))
            elif kind == "label" and w:
                if team["name"] and team["sog"]:
                    name_y = mid - s("name_size") * .2
                    _draw_text(draw, left + w / 2, name_y, team["name"], name_font, s("name_spacing"), text)
                    _draw_text(draw, left + w / 2, name_y + s("name_size") * .7, team["sog"], sog_font, 0,
                               text[:3] + (204,), shadow=False)
                elif team["name"] or team["sog"]:
                    font = name_font if team["name"] else sog_font
                    _draw_text(draw, left + w / 2, mid, team["name"] or team["sog"], font,
                               s("name_spacing") if team["name"] else 0, text)
            left += w

    team_content(away, *spans[0], logo_first=True)
    team_content(home, *spans[4], logo_first=False)
    for team, (x0, x1) in ((away, spans[1]), (home, spans[3])):
        _draw_text(draw, border + (x0 + x1) / 2, mid, team["score"], score_font, s("score_spacing"), text)
    if show_center:
        cx = border + sum(spans[2]) / 2
        p_h = s("period_size") if period else 0
        top = mid - (p_h + (s("clock_size") if clock else 0)) / 2
        if period:
            live = game.get("live")
            dot = 14 * scale if live else 0
            px = cx + dot / 2
            if live:
                left = px - _text_width(period, period_font, 0) / 2 - dot + 2 * scale
                draw.ellipse((left, top + p_h / 2 - 4 * scale, left + 8 * scale, top + p_h / 2 + 4 * scale),
                             fill=LIVE_DOT)
            _draw_text(draw, px, top + p_h / 2, period, period_font, 0, text, shadow=False)
        if clock:
            _draw_text(draw, cx, top + p_h + s("clock_size") / 2, clock, clock_font, s("clock_spacing"), text,
                       shadow=False)

    if style["layout"] != "slanted":
        return Image.alpha_composite(back, front)
    # Slanted: shear the background around its middle line, like CSS skewX on the frame.
    tilt = math.tan(math.radians(style["skew"]))
    margin = math.ceil(tilt * height / 2)
    out = Image.new("RGBA", (width + 2 * margin, height), (0, 0, 0, 0))
    sheared = back.transform(out.size, Image.AFFINE, (1, tilt, -margin - tilt * mid, 0, 1, 0), Image.BICUBIC)
    out.alpha_composite(sheared)
    out.alpha_composite(front, (margin, 0))
    return out
