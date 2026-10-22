"""Tests for Token and Slot Extraction Engine."""

import unittest

from core.decision.token_extractor import TokenExtractor


class TestTokenExtractor(unittest.TestCase):
    """Verify accurate entity and token extraction across domains."""

    def test_spotify_track_and_artist(self):
        res = TokenExtractor.extract_spotify_tokens("play bohemian rhapsody by queen")
        self.assertEqual(res["track"].lower(), "bohemian rhapsody")
        self.assertEqual(res["artist"].lower(), "queen")

    def test_spotify_song_with_prefix(self):
        res = TokenExtractor.extract_spotify_tokens("play the song hotel california by eagles")
        self.assertEqual(res["track"].lower(), "hotel california")
        self.assertEqual(res["artist"].lower(), "eagles")

    def test_spotify_album(self):
        res = TokenExtractor.extract_spotify_tokens("play album abbey road by the beatles")
        self.assertEqual(res["album"].lower(), "abbey road")
        self.assertEqual(res["artist"].lower(), "the beatles")

    def test_spotify_playlist(self):
        res = TokenExtractor.extract_spotify_tokens("play playlist lo-fi beats on spotify")
        self.assertEqual(res["playlist"].lower(), "lo-fi beats")

    def test_spotify_artist_only(self):
        res = TokenExtractor.extract_spotify_tokens("play songs by daft punk")
        self.assertEqual(res["artist"].lower(), "daft punk")

    def test_workspace_number(self):
        res = TokenExtractor.extract_workspace_tokens("switch to workspace 3")
        self.assertEqual(res["workspace"], "3")

    def test_workspace_move_app(self):
        res = TokenExtractor.extract_workspace_tokens("move spotify to workspace 4")
        self.assertEqual(res["app"], "spotify")
        self.assertEqual(res["workspace"], "4")

    def test_workspace_direction(self):
        res = TokenExtractor.extract_workspace_tokens("focus left")
        self.assertEqual(res["direction"], "left")

    def test_terminal_command(self):
        res = TokenExtractor.extract_terminal_tokens("run ls -la in terminal")
        self.assertEqual(res["command"], "ls -la")

    def test_browser_url(self):
        res = TokenExtractor.extract_browser_tokens("open https://news.ycombinator.com")
        self.assertEqual(res["url"], "https://news.ycombinator.com")

    def test_browser_search(self):
        res = TokenExtractor.extract_browser_tokens("search google for hyprland keybindings")
        self.assertEqual(res["query"], "hyprland keybindings")

    def test_gui_click_target(self):
        res = TokenExtractor.extract_gui_tokens("click on the submit button")
        self.assertEqual(res["target"], "submit button")
        self.assertEqual(res["button"], "left")
        self.assertFalse(res["double"])

    def test_gui_double_click(self):
        res = TokenExtractor.extract_gui_tokens("double click document.pdf")
        self.assertTrue(res["double"])
        self.assertEqual(res["target"], "document.pdf")

    def test_gui_coordinates(self):
        res = TokenExtractor.extract_gui_tokens("click 450 320")
        self.assertEqual(res["x"], 450)
        self.assertEqual(res["y"], 320)

    def test_system_volume_level(self):
        res = TokenExtractor.extract_system_tokens("set volume to 80%")
        self.assertEqual(res["level"], 80)

    def test_system_wifi_network(self):
        res = TokenExtractor.extract_system_tokens("connect to wifi HomeNet")
        self.assertEqual(res["network"], "HomeNet")


if __name__ == "__main__":
    unittest.main()
