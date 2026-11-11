"""User settings, saved as JSON in %APPDATA%\\HockeyScoreWidget (never in the repo)."""

from __future__ import annotations

import json
import os
from pathlib import Path

DEFAULTS: dict = {
    # OBS WebSocket
    "obs_host": "127.0.0.1",
    "obs_port": 4455,
    "obs_password": "",
    "obs_scene": "",           # empty = current program scene
    "obs_source": "Score Hockey",
    # App
    "server_port": 8765,
    "refresh_seconds": 0.25,  # how often the widget redraws; the NHL API is polled on its own schedule
    # Match choice
    "auto_favourite": True,
    "favourite": "MTL",
    "selected_game": None,
    # Widget look
    "layout": "classic",       # a key of LOOKS
    "preset": "classic",       # last preset picked in the Presets tab (only highlights its button)
    "team_colors": True,       # each side in its team colour; off = "accent" for both
    "name_format": "abbrev",   # "abbrev" or "name"
    "name_overrides": {},      # {"MTL": "Habs"}
    "color_overrides": {},     # {"MTL": "#AF1E2D"}
    "logo_overrides": {},      # {"MTL": "C:/.../logo.png"}
    "show_logos": True,
    "show_names": True,
    "show_sog": False,
    "show_status": True,
    "show_period": True,
    "show_gloss": True,
    "accent": "#2D7F55",       # panel colour when team colours are off
    "background": "#0B0B0C",   # centre block (period and clock)
    "text": "#F1F6F3",
    "delay_seconds": 0,
}

# Widget dimensions in pixels: key -> (label, min, max, default). The app builds its sliders from this.
SIZES: dict[str, tuple[str, int, int, int]] = {
    "bar_height": ("Hauteur", 40, 160, 84),
    "radius": ("Arrondi des coins", 0, 60, 8),
    "border": ("Épaisseur du contour", 0, 8, 3),
    "skew": ("Inclinaison (penché)", 0, 30, 14),
    "team_padding": ("Marge sur les côtés", 0, 60, 20),
    "logo_size": ("Taille du logo", 24, 140, 62),
    "logo_gap": ("Écart logo et nom", 0, 60, 16),
    "name_size": ("Taille du nom", 16, 80, 40),
    "name_spacing": ("Écart entre les lettres", -4, 12, 0),
    "score_size": ("Taille des chiffres", 24, 120, 64),
    "score_width": ("Largeur de la case", 40, 200, 86),
    "score_spacing": ("Écart entre les chiffres", -8, 20, 0),
    "clock_size": ("Taille du temps", 16, 90, 44),
    "clock_spacing": ("Écart entre les chiffres", -6, 20, 0),
    "period_size": ("Taille de la période", 10, 50, 24),
    "center_width": ("Largeur du centre", 60, 260, 128),
}
DEFAULTS.update({key: spec[3] for key, spec in SIZES.items()})

# How each layout draws, read by widget.html and preview.py alike.
#   shape: rounded | slant (whole bar skewed) | pill (rounded, slanted centre) | chamfer (cut corners)
#   frame: silver | gold | team (away colour to home colour) | none
#   fill:  solid | texture (ice) | dark | fade (colour to dark) | none (underline only)
#   stack: name above the score in the team panel (no separate score box)
#   one_line: period and clock on one line;  info: shots on goal strip under the bar
_LOOK = dict(shape="rounded", frame="silver", fill="solid", stack=False, one_line=False, info=False)
LOOKS: dict[str, dict] = {
    "classic": _LOOK,
    "slanted": dict(_LOOK, shape="slant"),
    "modern": dict(_LOOK, shape="pill"),
    "minimal": dict(_LOOK, frame="none", fill="none", one_line=True),
    "textured": dict(_LOOK, fill="texture", stack=True),
    "compact": dict(_LOOK, shape="slant", frame="team", one_line=True),
    "elegant": dict(_LOOK, shape="chamfer", frame="gold", fill="dark", stack=True),
    "wide": dict(_LOOK, fill="fade", stack=True, info=True),
}

_SHOW = dict(team_colors=True, show_logos=True, show_names=True, show_sog=False, show_status=True,
             show_period=True, show_gloss=True, name_format="abbrev")
_BASE = {**_SHOW, **{key: spec[3] for key, spec in SIZES.items()}}
# Presets tab: key -> (button label, settings it sets). Team names, colours and logos are never touched.
PRESETS: dict[str, tuple[str, dict]] = {
    "classic": ("Classique", dict(_BASE, layout="classic")),
    "slanted": ("Penché", dict(_BASE, layout="slanted", show_names=False)),
    "simple": ("Classique simple", dict(_BASE, layout="classic", name_format="name", radius=2, border=3,
                                        show_gloss=False, name_size=36, logo_size=60, score_size=60,
                                        clock_size=40, period_size=30, center_width=118)),
    "modern": ("Logo d'équipe moderne", dict(_BASE, layout="modern", name_format="name", radius=42, border=4,
                                             name_size=36, logo_size=64, score_size=62, clock_size=40,
                                             period_size=30, center_width=118, team_padding=24)),
    "minimal": ("Minimaliste", dict(_BASE, layout="minimal", show_logos=False, show_gloss=False, border=0,
                                    radius=0, bar_height=70, name_size=52, score_size=58, score_width=70,
                                    clock_size=46, period_size=46, center_width=220, team_padding=24)),
    "textured": ("Logos et fond texturé", dict(_BASE, layout="textured", name_format="name", bar_height=118,
                                               radius=4, border=3, show_gloss=False, logo_size=110,
                                               logo_gap=24, name_size=30, score_size=74, clock_size=42,
                                               period_size=34, center_width=130, team_padding=26)),
    "compact": ("Compact (coin)", dict(_BASE, layout="compact", show_names=False, radius=2, border=3,
                                       skew=14, logo_size=70, score_size=60, score_width=90, clock_size=38,
                                       period_size=38, center_width=150, team_padding=30)),
    "elegant": ("Élégant", dict(_BASE, layout="elegant", name_format="name", bar_height=100, radius=22,
                                border=4, show_gloss=False, logo_size=86, logo_gap=22, name_size=24,
                                score_size=58, clock_size=46, period_size=36, center_width=140,
                                team_padding=28)),
    "wide": ("Large avec infos", dict(_BASE, layout="wide", name_format="name", show_sog=True, bar_height=106,
                                      radius=4, border=3, logo_size=120, logo_gap=26, name_size=28,
                                      score_size=70, clock_size=42, period_size=34, center_width=130,
                                      team_padding=18)),
}


def settings_path() -> Path:
    base = os.environ.get("APPDATA") or str(Path.home())
    return Path(base) / "HockeyScoreWidget" / "settings.json"


def load(path: Path | None = None) -> dict:
    path = path or settings_path()
    data = dict(DEFAULTS)
    try:
        saved = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return data
    if isinstance(saved, dict):
        # Unknown keys are dropped, wrong types fall back to the default.
        for key, default in DEFAULTS.items():
            value = saved.get(key, default)
            if default is None or isinstance(value, type(default)):
                data[key] = value
        if data["layout"] not in LOOKS:
            data["layout"] = DEFAULTS["layout"]
        for key, (_label, low, high, _default) in SIZES.items():
            data[key] = min(high, max(low, data[key]))
    return data


def save(data: dict, path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic: a crash mid-write never leaves a broken file
