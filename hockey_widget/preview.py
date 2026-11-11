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

from hockey_widget.settings import LOOKS

FONTS = Path(__file__).parent / "fonts"
SILVER = ((0.0, (244, 246, 248, 255)), (0.45, (142, 149, 156, 255)), (0.70, (217, 221, 225, 255)),
          (1.0, (107, 113, 120, 255)))
GLOSS = ((0.0, (255, 255, 255, 56)), (0.48, (255, 255, 255, 10)), (0.52, (0, 0, 0, 26)), (1.0, (0, 0, 0, 71)))
SEPARATOR = (154, 160, 166)
GOLD = ((0.0, (255, 241, 176, 255)), (0.40, (201, 154, 58, 255)), (0.65, (243, 210, 122, 255)),
        (1.0, (138, 100, 32, 255)))
GOLD_LINE = (201, 160, 74)
GOLD_INK = (232, 196, 104, 255)
MINIMAL_LINE = (232, 232, 232)
DARK = ((0.0, (28, 31, 36, 255)), (1.0, (10, 11, 13, 255)))
TEXTURE_INK = (22, 25, 28, 255)
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


def _hgradient(width: int, height: int, stops) -> Image.Image:
    """Horizontal RGBA gradient, left to right."""
    return _gradient(height, width, stops).rotate(90, expand=True)


_NOISE: dict[tuple[int, int], Image.Image] = {}


def _ice(width: int, height: int) -> Image.Image:
    """Light ice with specks, like the --ice texture in widget.html. Cached: the preview redraws every second."""
    key = (width, height)
    if key not in _NOISE:
        base = _gradient(width, height, ((0.0, (242, 244, 246, 255)), (1.0, (201, 208, 214, 255))))
        specks = Image.effect_noise(key, 70).point(lambda v: max(0, min(110, (v - 140) * 3)))
        tint = Image.new("RGBA", key, (140, 153, 168, 0))
        tint.putalpha(specks)
        _NOISE[key] = Image.alpha_composite(base, tint)
    return _NOISE[key]


def _octagon(x0: float, y0: float, x1: float, y1: float, c: float) -> list[tuple[float, float]]:
    return [(x0 + c, y0), (x1 - c, y0), (x1, y0 + c), (x1, y1 - c), (x1 - c, y1), (x0 + c, y1), (x0, y1 - c),
            (x0, y0 + c)]


def render(state: dict, settings: dict, logos: LogoCache, scale: float = 2.0,
           custom_logo=lambda _abbrev: None) -> Image.Image | None:
    """The scoreboard at `scale` times its OBS size, or None when there is no game to show."""
    game, style = state.get("game"), state.get("style") or {}
    if not game or not style:
        return None
    look = style.get("look") or LOOKS["classic"]
    stack, shape, fill, frame = look["stack"], look["shape"], look["fill"], look["frame"]
    s = lambda key: style[key] * scale  # noqa: E731 - sizes in output pixels
    height = round(s("bar_height"))
    border = 0 if frame == "none" else round(s("border"))
    inner_h = height - 2 * border
    text = _rgb(style["text"]) + (255,)
    team_text = TEXTURE_INK if fill == "texture" else text
    center_text = GOLD_INK if frame == "gold" else text

    name_font = _font("Bold", s("name_size"))
    sog_font = _font("Medium", s("name_size") * .4)
    score_font = _font("ExtraBold", s("score_size"))
    clock_font = _font("Bold", s("clock_size"))
    period_font = _font("Bold", s("period_size"))

    def side_parts(team: dict) -> dict:
        show_sog = style["show_sog"] and team.get("sog") is not None and not look["info"]
        name = team["label"].upper() if style["show_names"] else ""
        sog = f"Tirs {team['sog']}" if show_sog else ""
        score = str(team["score"])
        label_w = max(_text_width(name, name_font, s("name_spacing")), _text_width(sog, sog_font, 0),
                      _text_width(score, score_font, s("score_spacing")) if stack else 0)
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
        score_w = 0 if stack else max(s("score_width"), _text_width(score, score_font, s("score_spacing")) + 8 * scale)
        return dict(name=name, sog=sog, label_w=label_w, logo=logo, logo_w=logo_w, gap=gap, width=width,
                    colour=_rgb(colour), score=score, score_w=score_w)

    away, home = side_parts(game["away"]), side_parts(game["home"])
    period = (game.get("period") or "") if style["show_period"] else ""
    clock = "" if not style.get("show_clock", True) and game.get("live") else game.get("clock") or ""
    live = bool(period and game.get("live"))
    dot = 14 * scale if live else 0
    one_gap = s("clock_size") * .3 if look["one_line"] and period and clock else 0
    period_w = _text_width(period, period_font, 0) + dot
    clock_w = _text_width(clock, clock_font, s("clock_spacing"))
    show_center = style["show_status"]
    center_w = 0.0
    if show_center:
        content = period_w + one_gap + clock_w if look["one_line"] else max(period_w, clock_w)
        center_w = max(s("center_width"), 2 * CENTER_PAD * scale + content)
    separators = show_center and shape != "pill"
    if stack:
        cells = [("team", away), ("center", None), ("team", home)]
    else:
        cells = [("team", away), ("score", away), ("center", None), ("score", home), ("team", home)]
    widths = [away["width"] if kind == "team" and team is away else home["width"] if kind == "team"
              else team["score_w"] if kind == "score" else center_w + (4 * scale if separators else 0)
              for kind, team in cells]
    inner_w = round(sum(widths))
    width = inner_w + 2 * border

    # Background layer: frame, coloured cells, gloss.
    back = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    radius = round(s("radius"))
    if frame != "none":
        mask = Image.new("L", (width, height), 0)
        if shape == "chamfer":
            ImageDraw.Draw(mask).polygon(_octagon(0, 0, width, height, radius), fill=255)
        else:
            ImageDraw.Draw(mask).rounded_rectangle((0, 0, width - 1, height - 1), radius=radius, fill=255)
        if frame == "team":
            paint = _hgradient(width, height, ((0.0, away["colour"] + (255,)), (1.0, home["colour"] + (255,))))
        else:
            paint = _gradient(width, height, GOLD if frame == "gold" else SILVER)
        back.paste(paint, (0, 0), mask)
    inner = Image.new("RGBA", (inner_w, inner_h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(inner)
    sep_colour = GOLD_LINE if frame == "gold" else MINIMAL_LINE if fill == "none" else SEPARATOR
    x = 0.0
    spans = []
    for (kind, team), w in zip(cells, widths):
        x0, x1 = round(x), round(x + w)
        spans.append((x0, x1))
        x += w
        if kind == "center" or x1 <= x0:
            continue
        box = (x1 - x0, inner_h)
        if fill == "none":
            continue
        if fill == "dark":
            inner.paste(_gradient(*box, DARK), (x0, 0))
        elif kind == "score":
            draw.rectangle((x0, 0, x1, inner_h), fill=tuple(round(c * .72) for c in team["colour"]))
        elif fill == "texture":
            outer = (0.0, team["colour"] + (255,)), (0.62, team["colour"] + (0,)), (1.0, team["colour"] + (0,))
            tint = _hgradient(*box, outer)
            if team is home:
                tint = tint.transpose(Image.FLIP_LEFT_RIGHT)
            inner.paste(Image.alpha_composite(_ice(*box), tint), (x0, 0))
        else:
            draw.rectangle((x0, 0, x1, inner_h), fill=team["colour"])
            if fill == "fade":
                shade = _hgradient(*box, ((0.0, (0, 0, 0, 0)), (0.3, (0, 0, 0, 0)), (1.0, (0, 0, 0, 128))))
                if team is home:
                    shade = shade.transpose(Image.FLIP_LEFT_RIGHT)
                inner.alpha_composite(shade, (x0, 0))
    if show_center:
        x0, x1 = spans[len(cells) // 2]
        if shape == "pill":
            k = s("bar_height") * .17
            draw.polygon([(x0, 0), (x1 + k, 0), (x1, inner_h), (x0 - k, inner_h)], fill=_rgb(style["background"]))
        else:
            if frame != "none":
                draw.rectangle((x0, 0, x1, inner_h), fill=_rgb(style["background"]))
            line = round(2 * scale)
            draw.rectangle((x0, 0, x0 + line - 1, inner_h), fill=sep_colour)
            draw.rectangle((x1 - line, 0, x1, inner_h), fill=sep_colour)
            if frame == "gold":
                draw.rectangle((x0, 0, x1 - 1, inner_h - 1), outline=sep_colour, width=line)
    if fill == "none":  # minimal: a team-coloured line under name and score
        line = round(6 * scale)
        for team, cols in ((away, (0, 1)), (home, (3, 4))):
            draw.rectangle((spans[cols[0]][0], inner_h - line, spans[cols[1]][1], inner_h), fill=team["colour"])
    if style["show_gloss"] and fill != "none":
        inner = Image.alpha_composite(inner, _gradient(inner_w, inner_h, GLOSS))
    inner_mask = Image.new("L", (inner_w, inner_h), 0)
    if shape == "chamfer":
        cut = max(0, radius - border * .586)
        ImageDraw.Draw(inner_mask).polygon(_octagon(0, 0, inner_w, inner_h, cut), fill=255)
    else:
        ImageDraw.Draw(inner_mask).rounded_rectangle((0, 0, inner_w - 1, inner_h - 1),
                                                     radius=max(0, round(s("radius") - border)), fill=255)
    back.paste(inner, (border, border), inner_mask)

    # Content layer: logos and text, never skewed (the widget straightens them too).
    front = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(front)
    mid = height / 2

    def label(team: dict, cx: float) -> None:
        name_h = s("name_size") if team["name"] else 0
        score_h = s("score_size") * .9 if stack else 0
        sog_h = s("name_size") * .5 if team["sog"] else 0
        y = mid - (name_h + score_h + sog_h) / 2
        if name_h:
            _draw_text(draw, cx, y + name_h / 2, team["name"], name_font, s("name_spacing"), team_text,
                       shadow=fill != "texture")
        if score_h:
            _draw_text(draw, cx, y + name_h + score_h / 2, team["score"], score_font, s("score_spacing"), team_text,
                       shadow=fill != "texture")
        if sog_h:
            _draw_text(draw, cx, y + name_h + score_h + sog_h / 2, team["sog"], sog_font, 0,
                       team_text[:3] + (204,), shadow=False)

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
                label(team, left + w / 2)
            left += w

    team_content(away, *spans[0], logo_first=True)
    team_content(home, *spans[-1], logo_first=False)
    if not stack:
        for team, (x0, x1) in ((away, spans[1]), (home, spans[3])):
            _draw_text(draw, border + (x0 + x1) / 2, mid, team["score"], score_font, s("score_spacing"), text)
    if show_center:
        cx = border + sum(spans[len(cells) // 2]) / 2
        if look["one_line"]:
            left = cx - (period_w + one_gap + clock_w) / 2
            period_c, period_y = left + period_w / 2, mid
            clock_c, clock_y = left + period_w + one_gap + clock_w / 2, mid
        else:
            p_h = s("period_size") if period else 0
            top = mid - (p_h + (s("clock_size") if clock else 0)) / 2
            period_c, period_y = cx, top + p_h / 2
            clock_c, clock_y = cx, top + p_h + s("clock_size") / 2
        if period:
            px = period_c + dot / 2
            if live:
                left = px - _text_width(period, period_font, 0) / 2 - dot + 2 * scale
                draw.ellipse((left, period_y - 4 * scale, left + 8 * scale, period_y + 4 * scale), fill=LIVE_DOT)
            _draw_text(draw, px, period_y, period, period_font, 0, center_text, shadow=fill == "none")
        if clock:
            _draw_text(draw, clock_c, clock_y, clock, clock_font, s("clock_spacing"), center_text,
                       shadow=fill == "none")

    if shape == "slant":
        # Shear the background around its middle line, like CSS skewX on the frame.
        tilt = math.tan(math.radians(style["skew"]))
        margin = math.ceil(tilt * height / 2)
        bar = Image.new("RGBA", (width + 2 * margin, height), (0, 0, 0, 0))
        sheared = back.transform(bar.size, Image.AFFINE, (1, tilt, -margin - tilt * mid, 0, 1, 0), Image.BICUBIC)
        bar.alpha_composite(sheared)
        bar.alpha_composite(front, (margin, 0))
    else:
        bar = Image.alpha_composite(back, front)

    def with_penalty(board: Image.Image) -> Image.Image:
        """Adds the penalty box (5v4 and time left) right of the board or below it, as in widget.html."""
        pp = game.get("pp") if style.get("show_pp", True) else None
        if not pp:
            return board
        # shortcut: a plain rounded box, not the bar's exact frame and shape; only widget.html draws those.
        below = look.get("pp") == "below"
        fonts = (_font("Bold", height * .42),) * 2 if below else (period_font, clock_font)
        texts = [(t, f) for t, f in zip((pp["text"], pp["clock"]), fonts) if t]
        widths = [_text_width(t, f, 0) for t, f in texts]
        gap, pad = (4 if below else 8) * scale, 16 * scale
        if below:
            box_w, box_h = sum(widths) + height * .12 * (len(texts) - 1) + 2 * pad, height * .6
        else:
            box_w, box_h = max(s("center_width") * .7, max(widths) + 2 * pad), height
        box_w, box_h = math.ceil(box_w), math.ceil(box_h)
        if below:
            out = Image.new("RGBA", (max(board.width, box_w), board.height + round(gap) + box_h), (0, 0, 0, 0))
            x0 = {"away": 0, "home": out.width - box_w}.get(pp["side"], (out.width - box_w) // 2)
            y0 = board.height + round(gap)
        else:
            out = Image.new("RGBA", (board.width + round(gap) + box_w, board.height), (0, 0, 0, 0))
            x0, y0 = board.width + round(gap), 0
        out.alpha_composite(board)
        pen = ImageDraw.Draw(out)
        colour = {"away": away["colour"], "home": home["colour"]}.get(pp["side"], _rgb(style["background"]))
        if fill == "none":
            pen.rectangle((x0, y0 + box_h - round(6 * scale), x0 + box_w - 1, y0 + box_h - 1), fill=colour)
        else:
            pen.rounded_rectangle((x0, y0, x0 + box_w - 1, y0 + box_h - 1), radius=min(radius, box_h // 2),
                                  fill=colour, outline=sep_colour if border else None, width=border)
        if below:
            left = x0 + pad
            for (t, f), w in zip(texts, widths):
                _draw_text(pen, left + w / 2, y0 + box_h / 2, t, f, 0, text)
                left += w + height * .12
        else:
            sizes = [s("period_size"), s("clock_size")][:len(texts)]
            top = y0 + (box_h - sum(sizes)) / 2
            for (t, f), size in zip(texts, sizes):
                _draw_text(pen, x0 + box_w / 2, top + size / 2, t, f, 0, text)
                top += size
        return out

    away_sog, home_sog = game["away"].get("sog"), game["home"].get("sog")
    if not (look["info"] and style["show_sog"] and away_sog is not None and home_sog is not None):
        return with_penalty(bar)
    # Info tab under the bar: shots on goal, as in widget.html.
    info = f"TIRS AU BUT : {game['away']['abbrev']} {away_sog} • {game['home']['abbrev']} {home_sog}"
    info_font = _font("Bold", s("name_size") * .72)
    tab_w = _text_width(info, info_font, 0) + 72 * scale
    tab_h = s("name_size") * .72 + 12 * scale
    out = Image.new("RGBA", (max(bar.width, math.ceil(tab_w)), height + math.ceil(tab_h)), (0, 0, 0, 0))
    out.alpha_composite(bar, ((out.width - bar.width) // 2, 0))
    draw = ImageDraw.Draw(out)
    x0, x1, slope, line = (out.width - tab_w) / 2, (out.width + tab_w) / 2, 20 * scale, 2 * scale
    draw.polygon([(x0, height), (x1, height), (x1 - slope, height + tab_h), (x0 + slope, height + tab_h)],
                 fill=SILVER[1][1])
    draw.polygon([(x0 + line, height), (x1 - line, height), (x1 - slope - line, height + tab_h - line),
                  (x0 + slope + line, height + tab_h - line)], fill=(14, 16, 19, 255))
    _draw_text(draw, out.width / 2, height + (tab_h - line) / 2, info, info_font, 0, text, shadow=False)
    return with_penalty(out)
