"""Unit tests for Phase 4 (Vision Capture & Natural Virtual Input)."""

import os
import unittest
from unittest.mock import MagicMock, patch

from core.input_controller import InputController
from core.system2_agent import System2Agent
from core.vision_capture import VisionCapture


class TestVisionCapture(unittest.TestCase):
    """Test suite for VisionCapture engine."""

    def setUp(self):
        self.vc = VisionCapture(output_path="/tmp/jarvis_test_screen.jpg")

    def tearDown(self):
        if os.path.exists("/tmp/jarvis_test_screen.jpg"):
            try:
                os.remove("/tmp/jarvis_test_screen.jpg")
            except OSError:
                pass

    def test_active_window_geometry_parsing(self):
        mock_output = '{"at": [100, 200], "size": [1920, 1080]}'
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=mock_output)
            geom = self.vc.get_active_window_geometry()
            self.assertEqual(geom, "100,200 1920x1080")

    def test_capture_screen_fullscreen(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
            path, latency = self.vc.capture_screen(mode="fullscreen", quality=70)
            self.assertEqual(path, "/tmp/jarvis_test_screen.jpg")
            self.assertGreaterEqual(latency, 0.0)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            self.assertIn("grim", args)
            self.assertIn("-t", args)
            self.assertIn("jpeg", args)
            self.assertIn("-q", args)
            self.assertIn("70", args)

    def test_capture_screen_active_window(self):
        with patch.object(self.vc, "get_active_window_geometry", return_value="50,50 800x600"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout=b"", stderr=b"")
                path, latency = self.vc.capture_screen(mode="active_window")
                self.assertEqual(path, "/tmp/jarvis_test_screen.jpg")
                args = mock_run.call_args[0][0]
                self.assertIn("-g", args)
                self.assertIn("50,50 800x600", args)


class TestInputController(unittest.TestCase):
    """Test suite for InputController with natural human delays."""

    def setUp(self):
        self.inp = InputController()

    def test_get_cursor_pos(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0, stdout="850, 420\n")
            x, y = self.inp.get_cursor_pos()
            self.assertEqual(x, 850)
            self.assertEqual(y, 420)

    def test_move_cursor_smooth_trajectory(self):
        with patch.object(self.inp, "get_cursor_pos", return_value=(100, 100)):
            with patch.object(self.inp, "_set_cursor_pos", return_value=True) as mock_set:
                with patch("time.sleep"):  # Fast execution in tests
                    ok = self.inp.move_cursor_to(500, 500, smooth=True, steps=10)
                    self.assertTrue(ok)
                    # Verified that multiple intermediate interpolation steps were dispatched
                    self.assertGreaterEqual(mock_set.call_count, 10)
                    # Final call must be target coordinates
                    last_call = mock_set.call_args_list[-1]
                    self.assertEqual(last_call[0], (500, 500))

    def test_click_dispatch(self):
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            ok = self.inp.click(button="left")
            self.assertTrue(ok)
            mock_run.assert_called_once()
            args = mock_run.call_args[0][0]
            self.assertIn("eval", args)
            self.assertIn("mouse:272", args[2])

    def test_type_text_cadence(self):
        with patch("os.path.exists", return_value=True):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                ok = self.inp.type_text("Hello Jarvis", delay_ms=25)
                self.assertTrue(ok)
                mock_run.assert_called_once()
                args = mock_run.call_args[0][0]
                self.assertIn("/usr/bin/wtype", args)
                self.assertIn("-d", args)
                self.assertIn("Hello Jarvis", args)

    def test_hotkey_parsing(self):
        with patch.object(self.inp, "press_key", return_value=True) as mock_press:
            self.inp.hotkey("ctrl+shift+c")
            mock_press.assert_called_once_with("c", ["ctrl", "shift"])


class TestSystem2VisionQuery(unittest.TestCase):
    """Test suite for Multimodal vision querying in System 2."""

    def setUp(self):
        self.agent = System2Agent(enable_tts=False)

    def test_query_vision_prompt_assembly(self):
        with patch.object(self.agent.vision, "capture_screen", return_value=("/tmp/mock_screen.jpg", 25.0)):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0, stdout="I see an open code editor and a terminal window.")
                res = self.agent.query_vision("Describe my screen", speak=False)
                self.assertEqual(res["status"], "ok")
                self.assertEqual(res["image_path"], "/tmp/mock_screen.jpg")
                self.assertEqual(res["vision_latency_ms"], 25.0)
                self.assertIn("open code editor", res["response"])
                # Verify that prompt had image path attached
                prompt_arg = mock_run.call_args[0][0][2]
                self.assertIn("@/tmp/mock_screen.jpg", prompt_arg)

    def test_query_auto_routes_visual_phrases(self):
        with patch.object(self.agent, "query_vision") as mock_vision:
            mock_vision.return_value = {"status": "ok", "response": "Screen visual response"}
            res = self.agent.query("Jarvis, what's on my screen right now?", speak=False)
            mock_vision.assert_called_once()


if __name__ == "__main__":
    unittest.main()
