"""What the widget shows: built from a Game plus the look settings, delayed on demand."""

from __future__ import annotations

import re
import threading
import time
from collections import deque
from pathlib import Path

from hockey_widget import teams
from hockey_widget.settings import LOOKS, SIZES
from hockey_widget.nhl_api import Game, Team, status_parts, status_text

STYLE_KEYS = ("layout", "team_colors", "show_logos", "show_names", "show_sog", "show_status", "show_period",
              "show_gloss", "accent", "background", "text", *SIZES)
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
LOGO_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".svg": "image/svg+xml",
              ".webp": "image/webp", ".gif": "image/gif"}


def custom_logo(abbrev: str, settings: dict) -> Path | None:
    """The user's own logo file for this team, if it is still there and is an image."""
    raw = settings.get("logo_overrides", {}).get(abbrev)
    if not isinstance(raw, str) or not raw:
        return None
    path = Path(raw)
    return path if path.suffix.lower() in LOGO_TYPES and path.is_file() else None


def team_color(abbrev: str, settings: dict) -> str:
    override = settings.get("color_overrides", {}).get(abbrev, "")
    return override if isinstance(override, str) and HEX.match(override) else teams.color(abbrev)


def team_label(team: Team, settings: dict) -> str:
    override = settings.get("name_overrides", {}).get(team.abbrev, "").strip()
    if override:
        return override
    return team.name if settings.get("name_format") == "name" else team.abbrev


def build_state(game: Game | None, settings: dict) -> dict:
    style = {key: settings[key] for key in STYLE_KEYS}
    style["look"] = LOOKS.get(settings["layout"], LOOKS["classic"])
    if game is None:
        return {"game": None, "style": style}

    def side(team: Team) -> dict:
        custom = custom_logo(team.abbrev, settings)
        # mtime in the address: a new file with the same name still reloads in OBS.
        logo = (f"/logo/{team.abbrev}?v={int(custom.stat().st_mtime)}" if custom
                else teams.logo(team.abbrev) or team.logo)
        return {"label": team_label(team, settings), "abbrev": team.abbrev,
                "score": team.score if team.score is not None else "-",
                "sog": team.sog, "logo": logo, "logo_custom": custom is not None,
                "color": team_color(team.abbrev, settings)}

    top, big = status_parts(game)
    return {"game": {"id": game.id, "away": side(game.away), "home": side(game.home),
                     "status": status_text(game), "period": top, "clock": big, "live": game.is_live,
                     "running": game.is_live and game.running and game.clock_seconds is not None,
                     "clock_seconds": game.clock_seconds, "clock_at": game.fetched_at},
            "style": style}


# shortcut: if the API stays down, the clock freezes after this many seconds instead of running to 0:00.
MAX_TICK_SECONDS = 30


def tick_clock(game: dict | None, now: float) -> dict | None:
    """The API clock is only as fresh as the last poll: count it down locally between polls."""
    if not game or not game.get("running"):
        return game
    elapsed = min(MAX_TICK_SECONDS, max(0, int(now - game["clock_at"])))
    seconds = max(0, game["clock_seconds"] - elapsed)
    return {**game, "clock": f"{seconds // 60:02d}:{seconds % 60:02d}"}


class DelayedFeed:
    """Keeps recent scores so the widget can lag behind the API like the video stream does.

    Only the score part is delayed: look changes (names, colours) show at once.
    """

    def __init__(self, keep_seconds: int = 600) -> None:
        self._history: deque[tuple[float, dict]] = deque()
        self._keep = keep_seconds
        self._style: dict = {}
        self._lock = threading.Lock()

    def push(self, state: dict, now: float | None = None) -> None:
        now = time.time() if now is None else now
        with self._lock:
            self._style = state["style"]
            self._history.append((now, state["game"]))
            while self._history and self._history[0][0] < now - self._keep:
                self._history.popleft()

    def current(self, delay: float, now: float | None = None) -> dict:
        now = time.time() if now is None else now
        with self._lock:
            game = None
            for stamp, snapshot in self._history:
                if stamp <= now - delay:
                    game = snapshot
                else:
                    break
            if game is None and delay <= 0 and self._history:
                game = self._history[-1][1]
            return {"game": tick_clock(game, now - max(0, delay)), "style": self._style}
