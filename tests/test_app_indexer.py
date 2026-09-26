"""Unit tests for the Universal App Indexer and Launcher."""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from core.app_indexer import AppIndexer


class TestAppIndexer(unittest.TestCase):
    """Test suite for desktop app parsing, alias resolution, and launching."""

    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)

        # Create mock .desktop files
        self.firefox_file = os.path.join(self.temp_dir.name, "firefox.desktop")
        with open(self.firefox_file, "w", encoding="utf-8") as f:
            f.write("""[Desktop Entry]
Version=1.0
Name=Firefox Web Browser
GenericName=Web Browser
Comment=Browse the World Wide Web
Exec=firefox %u
Icon=firefox
Terminal=false
Type=Application
Keywords=Internet;WWW;Browser;Web;
""")

        self.ghostty_file = os.path.join(self.temp_dir.name, "com.mitchellh.ghostty.desktop")
        with open(self.ghostty_file, "w", encoding="utf-8") as f:
            f.write("""[Desktop Entry]
Type=Application
Name=Ghostty
GenericName=Terminal Emulator
Comment=Fast, feature-rich terminal emulator
Exec=ghostty
Icon=com.mitchellh.ghostty
Terminal=false
Categories=System;TerminalEmulator;
Keywords=terminal;shell;prompt;command;
""")

        self.hidden_file = os.path.join(self.temp_dir.name, "hidden.desktop")
        with open(self.hidden_file, "w", encoding="utf-8") as f:
            f.write("""[Desktop Entry]
Type=Application
Name=Hidden Internal App
Exec=hidden-tool
NoDisplay=true
""")

        self.indexer = AppIndexer(search_paths=[self.temp_dir.name])

    def test_indexing_and_cleaning(self):
        """Test desktop file parsing, XDG exec code cleaning, and NoDisplay filtering."""
        apps = self.indexer.list_apps()
        app_names = [a["name"] for a in apps]

        self.assertIn("Firefox Web Browser", app_names)
        self.assertIn("Ghostty", app_names)
        self.assertNotIn("Hidden Internal App", app_names)

        ff = self.indexer.find_app("firefox")
        self.assertIsNotNone(ff)
        self.assertEqual(ff["clean_exec"], "firefox")
        self.assertEqual(ff["name"], "Firefox Web Browser")

    def test_category_and_generic_aliases(self):
        """Test resolving generic categories to preferred applications."""
        # 'browser' should match firefox
        app = self.indexer.find_app("browser")
        self.assertIsNotNone(app)
        self.assertEqual(app["name"], "Firefox Web Browser")

        # 'terminal' should match ghostty
        term = self.indexer.find_app("terminal")
        self.assertIsNotNone(term)
        self.assertEqual(term["name"], "Ghostty")

        # 'shell' keyword should match ghostty
        shell_app = self.indexer.find_app("shell")
        self.assertIsNotNone(shell_app)
        self.assertEqual(shell_app["name"], "Ghostty")

    def test_fuzzy_and_id_matching(self):
        """Test partial ID and name lookups."""
        app = self.indexer.find_app("ghostty")
        self.assertIsNotNone(app)
        self.assertEqual(app["id"], "com.mitchellh.ghostty")

        app_partial = self.indexer.find_app("web browser")
        self.assertIsNotNone(app_partial)
        self.assertEqual(app_partial["name"], "Firefox Web Browser")

    @patch("subprocess.Popen")
    def test_launch(self, mock_popen):
        """Test application launch process dispatch."""
        res = self.indexer.launch("firefox")
        self.assertTrue(res["success"])
        self.assertEqual(res["app"], "Firefox Web Browser")
        mock_popen.assert_called_once()

    def test_nonexistent_app(self):
        """Test looking up an application that does not exist."""
        app = self.indexer.find_app("nonexistent_super_rare_tool")
        self.assertIsNone(app)
        res = self.indexer.launch("nonexistent_super_rare_tool")
        self.assertFalse(res["success"])


if __name__ == "__main__":
    unittest.main()
