import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from hockey_widget import nhl_api, settings
from hockey_widget.server import make_server
from hockey_widget.widget_state import DelayedFeed, build_state

FIXTURE = Path(__file__).parent / "fixtures" / "score.json"


def live_game(**overrides) -> dict:
    raw = {"id": 7, "gameState": "LIVE", "startTimeUTC": "2026-11-10T00:00:00Z",
           "awayTeam": {"abbrev": "TOR", "name": {"default": "Maple Leafs"}, "score": 1, "sog": 12},
           "homeTeam": {"abbrev": "MTL", "name": {"default": "Canadiens", "fr": "Canadiens"}, "score": 2},
           "clock": {"timeRemaining": "12:34", "inIntermission": False},
           "periodDescriptor": {"number": 2, "periodType": "REG"}}
    raw.update(overrides)
    return raw


class NhlApiTest(unittest.TestCase):
    def test_real_response_parses(self) -> None:
        games = nhl_api.parse_games(json.loads(FIXTURE.read_text(encoding="utf-8")))
        self.assertGreater(len(games), 0)
        self.assertTrue(all(g.away.abbrev and g.home.abbrev for g in games))

    def test_status_lines(self) -> None:
        game = nhl_api.parse_games({"games": [live_game()]})[0]
        self.assertEqual(nhl_api.status_text(game), "2e période · 12:34")
        pause = nhl_api.parse_games({"games": [live_game(clock={"timeRemaining": "15:00", "inIntermission": True})]})[0]
        self.assertEqual(nhl_api.status_text(pause), "Entracte · 15:00")
        final_ot = nhl_api.parse_games({"games": [live_game(gameState="FINAL", periodDescriptor={"number": 4, "periodType": "OT"})]})[0]
        self.assertEqual(nhl_api.status_text(final_ot), "Final (prol.)")

    def test_future_game_has_no_score(self) -> None:
        raw = live_game(gameState="FUT")
        del raw["awayTeam"]["score"], raw["homeTeam"]["score"]
        game = nhl_api.parse_games({"games": [raw]})[0]
        self.assertIsNone(game.away.score)
        self.assertEqual(build_state(game, settings.DEFAULTS)["game"]["away"]["score"], "-")

    def test_pick_game_prefers_favourite_then_selection(self) -> None:
        other = live_game(id=1, awayTeam={"abbrev": "BOS"}, homeTeam={"abbrev": "NYR"})
        games = nhl_api.parse_games({"games": [other, live_game()]})
        self.assertEqual(nhl_api.pick_game(games, "MTL", 1).id, 7)
        self.assertEqual(nhl_api.pick_game(games, "", 1).id, 1)
        self.assertIsNone(nhl_api.pick_game([], "MTL", None))


class WidgetStateTest(unittest.TestCase):
    def test_names(self) -> None:
        game = nhl_api.parse_games({"games": [live_game()]})[0]
        look = dict(settings.DEFAULTS, name_format="name", name_overrides={"TOR": "Leafs"})
        state = build_state(game, look)["game"]
        self.assertEqual((state["away"]["label"], state["home"]["label"]), ("Leafs", "Canadiens"))

    def test_delay(self) -> None:
        feed = DelayedFeed()
        style = {"style": {}}
        feed.push({**style, "game": {"score": 0}}, now=100)
        feed.push({**style, "game": {"score": 1}}, now=130)
        self.assertEqual(feed.current(0, now=131)["game"], {"score": 1})
        self.assertEqual(feed.current(20, now=131)["game"], {"score": 0})
        self.assertEqual(feed.current(60, now=131)["game"], {"score": 0})  # nothing that old: the oldest
        feed.push({**style, "game": {"id": 2, "score": 5}}, now=132)  # another game picked: shown at once
        self.assertEqual(feed.current(20, now=133)["game"], {"id": 2, "score": 5})

    def test_clock_counts_down_between_polls(self) -> None:
        feed = DelayedFeed()
        game = {"id": 7, "period": "2e", "clock": "12:34", "running": True, "clock_seconds": 754,
                "clock_at": 100, "fresh_at": 100}

        def push(now: float, **changes) -> None:
            feed.push({"style": {}, "game": {**game, "clock_at": now, "fresh_at": now, **changes}}, now=now)

        push(100)
        self.assertEqual(feed.current(0, now=107)["game"]["clock"], "12:27")
        self.assertEqual(feed.current(5, now=107)["game"]["clock"], "12:32")  # stream delay
        self.assertEqual(feed.current(25, now=107)["game"]["clock"], "12:52")  # delay longer than history
        push(120, clock_seconds=744)  # staler answer (10 s of clock in 20 s): no jump back up
        self.assertEqual(feed.current(0, now=121)["game"]["clock"], "12:13")
        push(140, clock_seconds=710)  # fresher answer: the clock catches up
        self.assertEqual(feed.current(0, now=141)["game"]["clock"], "11:49")
        push(160, clock_seconds=740)  # far later: a whistle was missed, start again from this answer
        self.assertEqual(feed.current(0, now=161)["game"]["clock"], "12:19")
        self.assertEqual(feed.current(0, now=400)["game"]["clock"], "11:20")  # API down: freezes after 60 s
        push(180, clock_seconds=730, running=False)
        self.assertEqual(feed.current(0, now=300)["game"]["clock"], "12:34")  # whistle: the API's own text
        parsed = nhl_api.parse_games({"games": [live_game(clock={"timeRemaining": "05:00", "secondsRemaining": 300,
                                                                  "running": True})]})[0]
        self.assertTrue(build_state(parsed, settings.DEFAULTS)["game"]["running"])


class PenaltyTest(unittest.TestCase):
    SITUATION = {"awayTeam": {"abbrev": "TOR", "strength": 4}, "secondsRemaining": 66,
                 "homeTeam": {"abbrev": "MTL", "strength": 5, "situationDescriptions": ["PP"]}}

    def state(self, conf: dict = settings.DEFAULTS, situation: dict | None = SITUATION, **clock) -> dict:
        raw = live_game(situation=situation,
                        clock={"timeRemaining": "12:34", "secondsRemaining": 754, "running": True, **clock})
        return build_state(nhl_api.parse_games({"games": [raw]}, fetched_at=100)[0], conf)

    def test_power_play(self) -> None:
        self.assertIsNone(self.state(situation=None)["game"]["pp"])
        state = self.state()
        self.assertEqual(state["game"]["pp"], {"text": "4v5", "side": "home", "clock": "1:06", "until": 688})
        feed = DelayedFeed()
        feed.push(state, now=100)
        self.assertEqual(feed.current(0, now=110)["game"]["pp"]["clock"], "0:56")  # runs with the game clock
        feed.push(self.state(situation={**self.SITUATION, "secondsRemaining": 20}), now=101)
        self.assertIsNone(feed.current(0, now=125)["game"]["pp"])  # penalty over before the API says so
        self.assertIsNone(self.state(inIntermission=True)["game"]["pp"])

    def test_preview_draws_the_penalty_box(self) -> None:
        from hockey_widget import preview
        logos = preview.LogoCache()
        for layout, grows in (("classic", "width"), ("minimal", "height")):
            conf = {**settings.DEFAULTS, "layout": layout, "show_logos": False}
            plain = preview.render(self.state(conf, situation=None), conf, logos)
            boxed = preview.render(self.state(conf), conf, logos)
            self.assertGreater(getattr(boxed, grows), getattr(plain, grows), layout)
            if layout == "minimal":  # period and clock side by side: no clock, narrower centre
                no_clock = {**conf, "show_clock": False}
                self.assertLess(preview.render(self.state(no_clock, situation=None), no_clock, logos).width,
                                plain.width)
            hidden = {**conf, "show_pp": False}
            self.assertEqual(preview.render(self.state(hidden), hidden, logos).size, plain.size)


class EspnTest(unittest.TestCase):
    def game(self, **clock) -> nhl_api.Game:
        raw = live_game(clock={"timeRemaining": "12:34", "secondsRemaining": 754, "running": False, **clock})
        return nhl_api.parse_games({"games": [raw]}, fetched_at=100)[0]

    def test_find_event_and_status(self) -> None:
        from hockey_widget import espn
        board = {"events": [{"id": "1", "competitions": [{"competitors": [{"team": {"abbreviation": "NJ"}},
                                                                          {"team": {"abbreviation": "TOR"}}]}]},
                            {"id": "2", "competitions": [{"competitors": [{"team": {"abbreviation": "MTL"}},
                                                                          {"team": {"abbreviation": "TOR"}}]}]}]}
        self.assertEqual(espn.find_event(board, self.game()), "2")
        status = {"clock": 702.0, "period": 2, "type": {"name": "STATUS_IN_PROGRESS"}}
        self.assertEqual(espn.parse_status(status, 7, 110), espn.Clock(7, 2, 702, 110))
        self.assertIsNone(espn.parse_status({**status, "type": {"name": "STATUS_END_PERIOD"}}, 7, 110))

    def test_merge_takes_the_fresher_clock(self) -> None:
        from hockey_widget import espn
        stopped = self.game()
        resumed = espn.merge(stopped, espn.Clock(7, 2, 748, 110))  # NHL still says stopped at 754: play resumed
        self.assertEqual((resumed.clock_seconds, resumed.running, resumed.fetched_at), (748, True, 110))
        self.assertIs(espn.merge(stopped, espn.Clock(7, 2, 754, 110)), stopped)  # nothing new
        running = self.game(running=True)
        self.assertIs(espn.merge(running, espn.Clock(7, 2, 746, 110)), running)  # NHL already counts lower
        self.assertEqual(espn.merge(running, espn.Clock(7, 2, 740, 110)).clock_seconds, 740)
        self.assertIs(espn.merge(running, espn.Clock(7, 3, 700, 110)), running)  # other period
        self.assertIs(espn.merge(running, espn.Clock(8, 2, 700, 110)), running)  # other game
        self.assertIsNone(espn.merge(None, espn.Clock(7, 2, 700, 110)))


class SettingsTest(unittest.TestCase):
    def test_round_trip_and_bad_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            self.assertEqual(settings.load(path), settings.DEFAULTS)
            settings.save(dict(settings.DEFAULTS, obs_port=4444, junk=1), path)
            self.assertEqual(settings.load(path)["obs_port"], 4444)
            path.write_text(json.dumps({"obs_port": "x"}), encoding="utf-8")
            self.assertEqual(settings.load(path)["obs_port"], 4455)
            path.write_text("{broken", encoding="utf-8")
            self.assertEqual(settings.load(path), settings.DEFAULTS)


class ServerTest(unittest.TestCase):
    def test_routes(self) -> None:
        server = make_server(0, lambda: {"game": None, "style": {}})
        import threading
        threading.Thread(target=server.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            self.assertIn(b"/state", urllib.request.urlopen(base + "/widget").read())
            self.assertEqual(json.load(urllib.request.urlopen(base + "/state")), {"game": None, "style": {}})
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()


class TeamsTest(unittest.TestCase):
    def test_all_32_teams_have_colour_and_logo(self) -> None:
        from hockey_widget import teams
        self.assertEqual(len(teams.COLORS), 32)
        self.assertTrue(all(len(c) == 7 and c.startswith("#") for c in teams.COLORS.values()))
        self.assertTrue(teams.logo("MTL").endswith("/MTL_dark.svg"))
        self.assertEqual(teams.logo("XYZ"), "")
        self.assertEqual(teams.color("XYZ"), teams.DEFAULT_COLOR)

    def test_state_has_scoreboard_centre_and_team_colour(self) -> None:
        game = nhl_api.parse_games({"games": [live_game()]})[0]
        state = build_state(game, settings.load(Path("missing.json")))
        self.assertEqual((state["game"]["period"], state["game"]["clock"]), ("2e", "12:34"))
        self.assertEqual(state["game"]["home"]["color"], "#AF1E2D")
        self.assertEqual(state["style"]["layout"], "classic")
        final = nhl_api.parse_games({"games": [live_game(gameState="OFF", periodDescriptor={"number": 5, "periodType": "SO"})]})[0]
        self.assertEqual(nhl_api.status_parts(final), ("T.B.", "Final"))


class CustomLookTest(unittest.TestCase):
    def test_sizes_are_clamped_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "s.json"
            path.write_text(json.dumps({"logo_size": 9999, "skew": -50}), encoding="utf-8")
            data = settings.load(path)
            self.assertEqual(data["logo_size"], settings.SIZES["logo_size"][2])
            self.assertEqual(data["skew"], settings.SIZES["skew"][1])

    def test_team_overrides_and_custom_logo_route(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            logo = Path(tmp) / "habs.png"
            logo.write_bytes(b"\x89PNG fake")
            look = dict(settings.DEFAULTS, color_overrides={"MTL": "#123456", "TOR": "nope"},
                        logo_overrides={"MTL": str(logo), "TOR": str(Path(tmp) / "gone.png")})
            game = nhl_api.parse_games({"games": [live_game()]})[0]
            state = build_state(game, look)
            self.assertEqual(state["game"]["home"]["color"], "#123456")
            self.assertEqual(state["game"]["away"]["color"], "#00205B")  # bad hex ignored
            self.assertTrue(state["game"]["home"]["logo"].startswith("/logo/MTL?v="))
            self.assertFalse(state["game"]["away"]["logo_custom"])
            self.assertEqual(state["style"]["logo_size"], 62)

            from hockey_widget.widget_state import custom_logo
            server = make_server(0, lambda: state, lambda abbrev: custom_logo(abbrev, look))
            import threading
            threading.Thread(target=server.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{server.server_address[1]}"
            try:
                self.assertEqual(urllib.request.urlopen(base + "/logo/MTL").read(), b"\x89PNG fake")
                for missing in ("/logo/TOR", "/logo/..%2Fx"):
                    with self.assertRaises(urllib.error.HTTPError):
                        urllib.request.urlopen(base + missing)
            finally:
                server.shutdown()
                server.server_close()


class PreviewTest(unittest.TestCase):
    def test_render_matches_layout_choices(self) -> None:
        from hockey_widget import preview
        game = nhl_api.parse_games({"games": [live_game()]})[0]
        look = dict(settings.DEFAULTS, show_logos=False, name_format="name")
        logos = preview.LogoCache()
        classic = preview.render(build_state(game, look), look, logos)
        self.assertEqual(classic.height, look["bar_height"] * 2)
        no_names = dict(look, show_names=False)
        self.assertLess(preview.render(build_state(game, no_names), no_names, logos).width, classic.width)
        slanted = dict(no_names, layout="slanted")
        self.assertGreater(preview.render(build_state(game, slanted), slanted, logos).width,
                           preview.render(build_state(game, no_names), no_names, logos).width)
        self.assertIsNone(preview.render(build_state(None, look), look, logos))
        for key, (_label, values) in settings.PRESETS.items():  # every preset draws
            conf = dict(settings.DEFAULTS, **values)
            self.assertIn(conf["layout"], settings.LOOKS, key)
            self.assertGreaterEqual(preview.render(build_state(game, conf), conf, logos).height,
                                    conf["bar_height"] * 2, key)
