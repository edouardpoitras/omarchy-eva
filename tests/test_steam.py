"""Unit tests for Steam Game Discovery, Indexing, and Launching in Eva."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from core.app_indexer import AppIndexer
from core.capabilities import capabilities_registry
from core.dispatcher import CommandDispatcher, split_compound_commands
from core.steam_indexer import SteamIndexer


SAMPLE_ACF = """
"AppState"
{
	"appid"		"252950"
	"name"		"Rocket League"
	"StateFlags"		"4"
	"installdir"		"rocketleague"
	"LastPlayed"		"1790531439"
	"SizeOnDisk"		"43669064093"
}
"""

SAMPLE_TOOL_ACF = """
"AppState"
{
	"appid"		"1493710"
	"name"		"Proton Experimental"
	"StateFlags"		"4"
	"installdir"		"Proton - Experimental"
}
"""

SAMPLE_VDF = """
"libraryfolders"
{
	"0"
	{
		"path"		"{ROOT_DIR}"
		"apps"
		{
			"252950"		"0"
		}
	}
}
"""


class TestSteamIndexer(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.steam_root = self.tmp_dir.name

        # Create mock steamapps directory
        self.steamapps = os.path.join(self.steam_root, "steamapps")
        os.makedirs(self.steamapps, exist_ok=True)

        # Write sample ACF files
        with open(os.path.join(self.steamapps, "appmanifest_252950.acf"), "w") as f:
            f.write(SAMPLE_ACF)

        with open(os.path.join(self.steamapps, "appmanifest_1493710.acf"), "w") as f:
            f.write(SAMPLE_TOOL_ACF)

        # Write libraryfolders.vdf
        with open(os.path.join(self.steamapps, "libraryfolders.vdf"), "w") as f:
            f.write(SAMPLE_VDF.replace("{ROOT_DIR}", self.steam_root))

        self.steam = SteamIndexer(steam_roots=[self.steam_root])

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_library_and_game_discovery(self):
        """Verify libraries and games are discovered and indexed."""
        self.assertIn(self.steam_root, self.steam._libraries)
        games = self.steam.list_games()
        self.assertEqual(len(games), 1)
        self.assertEqual(games[0]["appid"], "252950")
        self.assertEqual(games[0]["name"], "Rocket League")
        self.assertEqual(games[0]["installdir"], "rocketleague")

        # Verify Proton tool is filtered from games list, but included when requested
        all_software = self.steam.list_games(include_tools=True)
        self.assertEqual(len(all_software), 2)

    def test_game_matching_variants(self):
        """Test exact, lowercase, and normalized query lookups."""
        # Exact title
        self.assertEqual(self.steam.find_game("Rocket League")["appid"], "252950")
        # Lowercase
        self.assertEqual(self.steam.find_game("rocket league")["appid"], "252950")
        # Concatenated / unspaced
        self.assertEqual(self.steam.find_game("RocketLeague")["appid"], "252950")
        self.assertEqual(self.steam.find_game("rocketleague")["appid"], "252950")
        # App ID
        self.assertEqual(self.steam.find_game("252950")["name"], "Rocket League")
        # Installdir
        self.assertEqual(self.steam.find_game("rocketleague")["name"], "Rocket League")
        # Non-existent
        self.assertIsNone(self.steam.find_game("Super Mario 64"))

    @patch("subprocess.Popen")
    def test_launch_game(self, mock_popen):
        """Test game launch command generation."""
        res = self.steam.launch_game("RocketLeague")
        self.assertTrue(res["success"])
        self.assertEqual(res["appid"], "252950")
        self.assertEqual(res["exec"], "steam steam://rungameid/252950")
        mock_popen.assert_called_once()


class TestSteamIntegration(unittest.TestCase):
    def setUp(self):
        self.mock_hypr = MagicMock()
        self.mock_media = MagicMock()
        self.mock_system = MagicMock()
        self.mock_system2 = MagicMock()

        # Build real SteamIndexer pointing to mock data
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.steamapps = os.path.join(self.tmp_dir.name, "steamapps")
        os.makedirs(self.steamapps, exist_ok=True)
        with open(os.path.join(self.steamapps, "appmanifest_252950.acf"), "w") as f:
            f.write(SAMPLE_ACF)

        self.steam = SteamIndexer(steam_roots=[self.tmp_dir.name])
        self.apps = AppIndexer(search_paths=[], steam=self.steam)

        self.dispatcher = CommandDispatcher(
            hypr=self.mock_hypr,
            media=self.mock_media,
            system=self.mock_system,
            system2=self.mock_system2,
            apps=self.apps,
            steam=self.steam,
        )

    def tearDown(self):
        self.tmp_dir.cleanup()

    def test_app_indexer_resolves_steam_game(self):
        """AppIndexer discovers Steam game and resolves aliases."""
        app = self.apps.find_app("RocketLeague")
        self.assertIsNotNone(app)
        self.assertEqual(app["name"], "Rocket League")
        self.assertIn("252950", app["exec"])

        app_spaced = self.apps.find_app("rocket league")
        self.assertIsNotNone(app_spaced)
        self.assertEqual(app_spaced["name"], "Rocket League")

    def test_direct_game_launch_dispatch(self):
        """Dispatcher matches direct game launch voice commands."""
        for phrase in [
            "launch RocketLeague",
            "launch Rocket League",
            "launch game Rocket League in steam",
            "play RocketLeague",
            "play Rocket League",
            "start Rocket League",
        ]:
            res = self.dispatcher.dispatch_text(phrase, execute=False)
            self.assertTrue(res.get("matched"), f"Failed to match: {phrase}")
            self.assertEqual(res.get("intent"), "STEAM_LAUNCH")
            self.assertEqual(res.get("action"), "steam_launch Rocket League")

    def test_compound_switch_to_steam_and_launch_game(self):
        """'switch to steam and launch RocketLeague' executes compound sequence."""
        # 1. Compound splitting
        parts = split_compound_commands("switch to steam and launch RocketLeague")
        self.assertEqual(parts, ["switch to steam", "launch RocketLeague"])

        # 2. Dry run
        dry = self.dispatcher.dispatch_text("switch to steam and launch RocketLeague", execute=False)
        self.assertTrue(dry.get("matched"))
        self.assertEqual(dry.get("intent"), "COMPOUND_REFLEX")
        self.assertEqual(dry.get("action"), "focus steam -> steam_launch Rocket League")

        # 3. Execution (Steam open window exists)
        self.mock_hypr.focus_window_by_query.return_value = True
        self.mock_hypr.find_open_window.return_value = {
            "initialClass": "steam",
            "workspace": {"id": 1, "name": "1"},
        }

        with patch("subprocess.Popen") as mock_popen:
            res = self.dispatcher.dispatch_text("switch to steam and launch RocketLeague", execute=True)
            self.assertTrue(res.get("matched"))
            self.assertTrue(res.get("success"))
            self.assertEqual(res.get("intent"), "COMPOUND_REFLEX")
            self.assertEqual(res.get("action"), "focus steam -> steam_launch Rocket League")
            # Verify Steam window focus was invoked
            self.mock_hypr.focus_window_by_query.assert_called_with("steam")
            # Verify game launch was invoked
            mock_popen.assert_called_once()

    def test_capabilities_registry_has_games(self):
        """Capabilities registry includes games domain and documentation."""
        domain = capabilities_registry.get_domain("games")
        self.assertIsNotNone(domain)
        self.assertEqual(domain["title"], "Steam Game Discovery & Execution")
        self.assertIn("STEAM_LAUNCH", domain["schema_intents"])
        self.assertIn("switch to steam and launch RocketLeague", domain["examples"])


if __name__ == "__main__":
    unittest.main()
