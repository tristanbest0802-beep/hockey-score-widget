import tempfile
import unittest
from pathlib import Path

from hockey_widget.app import TAB_NAMES, App
from hockey_widget.nhl_api import Game, Team


class AppWindowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.app = App(settings_file=Path(self.tmp.name) / "settings.json", start_services=False)

    def tearDown(self) -> None:
        self.app.close()
        self.tmp.cleanup()

    def test_sidebar_pages(self) -> None:
        self.assertEqual(tuple(self.app.pages), TAB_NAMES)
        self.assertEqual(self.app.current_page, TAB_NAMES[0])
        for name in TAB_NAMES:
            self.app.show_page(name)
            self.app.update_idletasks()
            self.assertEqual(self.app.current_page, name)

    def test_games_and_name_override_reach_the_widget(self) -> None:
        mtl = Team("MTL", "Canadiens", 2, 20, "")
        tor = Team("TOR", "Maple Leafs", 1, 18, "")
        self.app._on_games([Game(1, "LIVE", "", tor, mtl, 2, "REG", "05:00", False)])
        _code, entry, _reset = self.app.name_rows[1]
        entry.insert(0, "Habs")
        self.app._on_names_change()
        game = self.app.feed.current(0)["game"]
        self.assertEqual(game["home"]["label"], "Habs")
        self.assertEqual(game["away"]["label"], "TOR")
        self.assertTrue(Path(self.tmp.name, "settings.json").exists())

    def test_invalid_port_is_refused(self) -> None:
        self.app.fields["obs_port"].delete(0, "end")
        self.app.fields["obs_port"].insert(0, "abc")
        self.assertIsNotNone(self.app._read_settings_page())


class CustomisePageTest(unittest.TestCase):
    def test_size_slider_and_reset_reach_the_widget(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            app = App(settings_file=Path(tmp) / "settings.json", start_services=False)
            try:
                app._on_size("clock_size", 70)
                self.assertEqual(app.feed.current(0)["style"]["clock_size"], 70)
                app._reset_sizes(("clock_size",))
                self.assertEqual(app.feed.current(0)["style"]["clock_size"], 44)
                app.layout_var.set("Penché")
                app._on_layout_change()
                self.assertEqual(app.settings["layout"], "slanted")
                self.assertFalse(app.settings["show_names"])
            finally:
                app.close()


if __name__ == "__main__":
    unittest.main()
