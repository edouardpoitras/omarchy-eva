"""Unit tests for Two-Tier Visual Grounding and Auto-Click."""

import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from core.visual_grounding import VisualGrounding


class TestVisualGrounding(unittest.TestCase):
    """Test suite for Tesseract TSV OCR bounding boxes and visual click execution."""

    def setUp(self):
        self.temp_img = tempfile.NamedTemporaryFile(suffix=".jpg")
        self.addCleanup(self.temp_img.close)

        self.mock_vision = MagicMock()
        self.mock_vision.capture_screen.return_value = (self.temp_img.name, 12.5)

        self.mock_input = MagicMock()
        self.mock_input.move_cursor_to.return_value = True
        self.mock_input.click.return_value = True

        self.mock_sound = MagicMock()

        self.vg = VisualGrounding(
            vision=self.mock_vision,
            input_ctrl=self.mock_input,
            sound=self.mock_sound,
        )

    @patch("subprocess.run")
    def test_locate_text_ocr_single_word(self, mock_run):
        """Test single-word exact match coordinate calculation."""
        tsv_mock = """level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext
5\t1\t1\t1\t1\t1\t100\t200\t50\t20\t95\tAbout
5\t1\t1\t1\t1\t2\t160\t200\t40\t20\t90\tFile
"""
        mock_run.return_value = MagicMock(returncode=0, stdout=tsv_mock)

        coord = self.vg.locate_text_ocr("/tmp/screen.jpg", "About")
        self.assertIsNotNone(coord)
        # Center = left + width // 2, top + height // 2
        # (100 + 25, 200 + 10) = (125, 210)
        self.assertEqual(coord, (125, 210))

    @patch("subprocess.run")
    def test_locate_text_ocr_multiword_phrase(self, mock_run):
        """Test multi-word phrase bounding box spanning multiple tokens on same line."""
        tsv_mock = """level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext
5\t1\t1\t1\t1\t1\t100\t150\t60\t24\t92\tVoice
5\t1\t1\t1\t1\t2\t170\t150\t70\t24\t94\tControl
"""
        mock_run.return_value = MagicMock(returncode=0, stdout=tsv_mock)

        coord = self.vg.locate_text_ocr("/tmp/screen.jpg", "voice control")
        self.assertIsNotNone(coord)
        # left = 100, right = 170 + 70 = 240 -> center_x = 170
        # top = 150, bottom = 150 + 24 = 174 -> center_y = 162
        self.assertEqual(coord, (170, 162))

    @patch.object(VisualGrounding, "locate_text_ocr")
    def test_locate_and_click_success(self, mock_ocr):
        """Test complete flow of locate_and_click with smooth glide and sound."""
        mock_ocr.return_value = (500, 300)

        res = self.vg.locate_and_click("Settings", button="left", double=False)
        self.assertTrue(res["success"])
        self.assertEqual(res["x"], 500)
        self.assertEqual(res["y"], 300)
        self.assertEqual(res["method"], "tesseract_ocr")

        self.mock_input.move_cursor_to.assert_called_once_with(500, 300, smooth=True, duration_ms=220)
        self.mock_input.click.assert_called_once_with(button="left", double=False)
        self.mock_sound.success.assert_called_once()

    @patch.object(VisualGrounding, "locate_element")
    def test_locate_and_click_not_found(self, mock_loc):
        """Test locate_and_click gracefully fails and plays error sound if element missing."""
        mock_loc.return_value = {"found": False, "error": "Element not found on screen."}

        res = self.vg.locate_and_click("RareButton")
        self.assertFalse(res["success"])
        self.mock_sound.error.assert_called_once()
        self.mock_input.click.assert_not_called()


if __name__ == "__main__":
    unittest.main()
