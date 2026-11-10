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
        self.assertIsNone(feed.current(60, now=131)["game"])


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
