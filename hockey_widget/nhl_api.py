"""NHL scores from the public (unofficial) api-web.nhle.com endpoint.

All parsing of the API's JSON lives here: if the NHL changes its format,
this is the only file to fix.
"""

from __future__ import annotations

import json
import time
import urllib.request
from dataclasses import dataclass
from datetime import datetime

SCORE_URL = "https://api-web.nhle.com/v1/score/now"
LIVE_STATES = {"LIVE", "CRIT"}
DONE_STATES = {"OFF", "FINAL"}


@dataclass(frozen=True)
class Team:
    abbrev: str
    name: str
    score: int | None
    sog: int | None
    logo: str


@dataclass(frozen=True)
class Game:
    id: int
    state: str
    start_utc: str
    away: Team
    home: Team
    period: int
    period_type: str
    clock: str
    intermission: bool
    clock_seconds: int | None = None
    running: bool = False
    fetched_at: float = 0.0
    # Skaters on the ice while a penalty runs (5 and 4 on a power play), and the penalty time left.
    away_strength: int | None = None
    home_strength: int | None = None
    penalty_seconds: int | None = None

    @property
    def is_live(self) -> bool:
        return self.state in LIVE_STATES

    @property
    def is_done(self) -> bool:
        return self.state in DONE_STATES

    def has_team(self, abbrev: str) -> bool:
        return abbrev in (self.away.abbrev, self.home.abbrev)


def _team(raw: dict) -> Team:
    names = raw.get("name") or {}
    return Team(
        abbrev=raw.get("abbrev", "?"),
        name=names.get("fr") or names.get("default") or raw.get("abbrev", "?"),
        score=raw.get("score"),
        sog=raw.get("sog"),
        logo=raw.get("logo", ""),
    )


def parse_games(data: dict, fetched_at: float | None = None) -> list[Game]:
    fetched_at = time.time() if fetched_at is None else fetched_at
    games = []
    for raw in data.get("games", []):
        clock = raw.get("clock") or {}
        period = raw.get("periodDescriptor") or {}
        situation = raw.get("situation") or {}
        games.append(Game(
            id=int(raw["id"]),
            state=raw.get("gameState", "FUT"),
            start_utc=raw.get("startTimeUTC", ""),
            away=_team(raw.get("awayTeam", {})),
            home=_team(raw.get("homeTeam", {})),
            period=int(period.get("number") or raw.get("period") or 0),
            period_type=period.get("periodType", "REG"),
            clock=clock.get("timeRemaining", ""),
            intermission=bool(clock.get("inIntermission")),
            clock_seconds=clock.get("secondsRemaining"),
            running=bool(clock.get("running")),
            fetched_at=fetched_at,
            away_strength=(situation.get("awayTeam") or {}).get("strength"),
            home_strength=(situation.get("homeTeam") or {}).get("strength"),
            penalty_seconds=situation.get("secondsRemaining"),
        ))
    return games


def fetch_games(timeout: float = 10.0) -> list[Game]:
    request = urllib.request.Request(SCORE_URL, headers={"User-Agent": "hockey-score-widget"})
    with urllib.request.urlopen(request, timeout=timeout) as response:  # follows the 307 to today's date
        # The CDN serves answers up to ~19 s old: date the clock from when the answer was made, not received.
        try:
            age = max(0.0, float(response.headers.get("Age") or 0))
        except ValueError:
            age = 0.0
        return parse_games(json.load(response), fetched_at=time.time() - age)


def local_start(game: Game) -> str:
    try:
        start = datetime.fromisoformat(game.start_utc.replace("Z", "+00:00"))
    except ValueError:
        return ""
    return start.astimezone().strftime("%H:%M")


def period_label(game: Game) -> str:
    if game.period_type == "SO":
        return "Tirs de barrage"
    if game.period_type == "OT":
        return "Prolongation"
    return {1: "1re période", 2: "2e période", 3: "3e période"}.get(game.period, f"{game.period}e période")


def status_text(game: Game) -> str:
    """Short French status line, e.g. '2e période · 12:34'."""
    if game.is_done:
        suffix = {"OT": " (prol.)", "SO": " (t.b.)"}.get(game.period_type, "")
        return "Final" + suffix
    if game.is_live:
        if game.intermission:
            return f"Entracte · {game.clock}" if game.clock else "Entracte"
        return f"{period_label(game)} · {game.clock}" if game.clock else period_label(game)
    return f"Aujourd'hui {local_start(game)}".strip()


def status_parts(game: Game) -> tuple[str, str]:
    """Centre block of the scoreboard: (small top line, big line), e.g. ('2e', '14:37')."""
    if game.is_done:
        return {"OT": "Prol.", "SO": "T.B."}.get(game.period_type, ""), "Final"
    if game.is_live:
        if game.intermission:
            return "Entracte", game.clock
        top = {"OT": "Prol.", "SO": "T.B."}.get(game.period_type) or (
            "1re" if game.period == 1 else f"{game.period}e")
        return top, game.clock
    return "Aujourd'hui", local_start(game)


def pick_game(games: list[Game], favourite: str, selected_id: int | None) -> Game | None:
    """Auto mode: the favourite team's game. Otherwise the selected game, then a live one."""
    by_id = {g.id: g for g in games}
    if favourite:
        for game in games:
            if game.has_team(favourite):
                return game
    if selected_id in by_id:
        return by_id[selected_id]
    live = [g for g in games if g.is_live]
    return (live or games or [None])[0]
