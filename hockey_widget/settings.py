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
    "poll_seconds": 10,
    # Match choice
    "auto_favourite": True,
    "favourite": "MTL",
    "selected_game": None,
    # Widget look
    "layout": "classic",       # "classic" (logo + name) or "slanted" (slanted ends)
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
    "bar_height": ("Hauteur", 50, 160, 84),
    "radius": ("Arrondi des coins", 0, 30, 8),
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
        for key, (_label, low, high, _default) in SIZES.items():
            data[key] = min(high, max(low, data[key]))
    return data


def save(data: dict, path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)  # atomic: a crash mid-write never leaves a broken file
