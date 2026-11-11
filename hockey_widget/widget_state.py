"""What the widget shows: built from a Game plus the look settings, delayed on demand."""

from __future__ import annotations

import math
import re
import threading
import time
from collections import deque
from pathlib import Path

from hockey_widget import teams
from hockey_widget.settings import LOOKS, SIZES
from hockey_widget.nhl_api import Game, Team, status_parts, status_text

STYLE_KEYS = ("layout", "team_colors", "show_logos", "show_names", "show_sog", "show_status", "show_period", "show_clock",
              "show_gloss", "show_pp", "accent", "background", "text", *SIZES)
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
    pp = None
    away_n, home_n, left = game.away_strength, game.home_strength, game.penalty_seconds
    if (game.is_live and not game.intermission and isinstance(away_n, int) and isinstance(home_n, int)
            and (away_n, home_n) != (5, 5)):
        timed = isinstance(left, int) and game.clock_seconds is not None
        pp = {"text": f"{away_n}v{home_n}",  # same order as the bar: away on the left
              "side": "away" if away_n > home_n else "home" if home_n > away_n else "even",
              "clock": _minutes(left) if isinstance(left, int) else "",
              "until": game.clock_seconds - left if timed else None}  # game clock when the penalty ends
    return {"game": {"id": game.id, "away": side(game.away), "home": side(game.home),
                     "status": status_text(game), "period": top, "clock": big, "live": game.is_live,
                     "running": game.is_live and game.running and game.clock_seconds is not None,
                     "clock_seconds": game.clock_seconds, "clock_at": game.fetched_at, "fresh_at": game.fetched_at, "pp": pp},
            "style": style}


# shortcut: if the API stays down, the clock freezes this long after its last answer instead of running to 0:00.
MAX_TICK_SECONDS = 60
# The API's clock is the time of the last play it knows, 0 to ~25 s late, and a new answer only every ~20 s.
# A later answer that implies a later period end is just staler, unless it is this much later: then a
# whistle went unseen between two answers.
MISSED_STOP_SECONDS = 30
PERIOD_SECONDS = 1200


def _minutes(seconds: int) -> str:
    return f"{seconds // 60}:{seconds % 60:02d}"


def tick_clock(game: dict | None, now: float) -> dict | None:
    """The API clock is only as fresh as the last poll: count it down locally between polls."""
    if not game or not game.get("running"):
        return game
    # Negative immediately after a game switch with a stream delay: the clock is wound back by the delay.
    elapsed = math.floor(min(now, game["fresh_at"] + MAX_TICK_SECONDS) - game["clock_at"])
    seconds = min(PERIOD_SECONDS, max(0, game["clock_seconds"] - elapsed))
    pp = game.get("pp")
    if pp and pp["until"] is not None:  # the penalty runs with the game clock
        left = seconds - pp["until"]
        pp = {**pp, "clock": _minutes(left)} if left > 0 else None
    return {**game, "clock": f"{seconds // 60:02d}:{seconds % 60:02d}", "pp": pp}


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
        game = state["game"]
        with self._lock:
            self._style = state["style"]
            last = self._history[-1][1] if self._history else None
            if (game or {}).get("id") != (last or {}).get("id"):
                self._history.clear()  # another game picked: show it now, not once the stream delay has passed
                last = None
            if (game and last and game.get("running") and last.get("running")
                    and (game["id"], game["period"]) == (last["id"], last["period"])):
                # Play never stopped: keep whichever answer puts the clock lowest, it is the least stale one.
                late = game["clock_at"] + game["clock_seconds"] - last["clock_at"] - last["clock_seconds"]
                if 0 <= late <= MISSED_STOP_SECONDS:
                    game = {**game, "clock_at": last["clock_at"], "clock_seconds": last["clock_seconds"]}
            self._history.append((now, game))
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
            if game is None and self._history:
                game = self._history[0][1]  # nothing old enough yet (start, game switch): the oldest we have
            return {"game": tick_clock(game, now - max(0, delay)), "style": self._style}
