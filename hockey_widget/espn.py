"""Second clock source: ESPN's public (unofficial) API, refreshed every ~2 s where the NHL's takes ~20 s.

Only the clock is taken from it, to catch up sooner when play resumes or runs on past the NHL's answer.
Scores, penalties and everything else still come from the NHL (nhl_api.py).
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass, replace

from hockey_widget.nhl_api import Game

SCOREBOARD_URL = "https://site.api.espn.com/apis/site/v2/sports/hockey/nhl/scoreboard"
STATUS_URL = ("https://sports.core.api.espn.com/v2/sports/hockey/leagues/nhl/events/{id}"
              "/competitions/{id}/status")
# NHL abbreviation -> ESPN's, where they differ.
ESPN_ABBREV = {"NJD": "NJ", "TBL": "TB", "LAK": "LA", "SJS": "SJ", "UTA": "UTAH"}


@dataclass(frozen=True)
class Clock:
    game_id: int     # the NHL game it belongs to
    period: int
    seconds: int     # time left in the period
    seen_at: float   # when ESPN's answer was made (Age header taken off)


def _get(url: str, timeout: float) -> tuple[dict, float]:
    request = urllib.request.Request(url, headers={"User-Agent": "hockey-score-widget"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        try:
            age = max(0.0, float(response.headers.get("Age") or 0))
        except ValueError:
            age = 0.0
        return json.load(response), time.time() - age


def find_event(scoreboard: dict, game: Game) -> str | None:
    """ESPN's id for this NHL game, matched on the two teams."""
    want = {ESPN_ABBREV.get(game.away.abbrev, game.away.abbrev), ESPN_ABBREV.get(game.home.abbrev, game.home.abbrev)}
    for event in scoreboard.get("events", []):
        competitors = (event.get("competitions") or [{}])[0].get("competitors", [])
        if {c.get("team", {}).get("abbreviation") for c in competitors} == want:
            return event.get("id")
    return None


def parse_status(status: dict, game_id: int, seen_at: float) -> Clock | None:
    """The clock while the period is being played, None otherwise (intermission, end of period, final)."""
    kind = status.get("type") or {}
    if kind.get("name") != "STATUS_IN_PROGRESS":
        return None
    try:
        return Clock(game_id, int(status["period"]), int(status["clock"]), seen_at)
    except (KeyError, TypeError, ValueError):
        return None


def fetch_event_id(game: Game, timeout: float = 10.0) -> str | None:
    return find_event(_get(SCOREBOARD_URL, timeout)[0], game)


def fetch_clock(event_id: str, game_id: int, timeout: float = 5.0) -> Clock | None:
    status, seen_at = _get(STATUS_URL.format(id=event_id), timeout)
    return parse_status(status, game_id, seen_at)


def merge(game: Game | None, clock: Clock | None) -> Game | None:
    """The NHL game, with ESPN's clock when ESPN shows the clock further down: its answer is the fresher one.

    A clock further down than the NHL knows means play went on since the NHL's answer, so it is running.
    """
    if (game is None or clock is None or clock.game_id != game.id or not game.is_live or game.intermission
            or game.period_type == "SO" or game.clock_seconds is None or clock.period != game.period):
        return game
    # Where the NHL's answer puts the clock at the moment ESPN made its own.
    nhl_then = game.clock_seconds - ((clock.seen_at - game.fetched_at) if game.running else 0)
    if clock.seconds >= nhl_then:
        return game
    return replace(game, clock_seconds=clock.seconds, running=True, fetched_at=clock.seen_at,
                   clock=f"{clock.seconds // 60:02d}:{clock.seconds % 60:02d}")
