"""Unit tests for System 1 hardware & device controls.

Tests audio output/mic device routing, WiFi, Bluetooth, brightness,
displays, and dispatcher integration.
"""

import unittest
from unittest.mock import MagicMock, patch

from core.dispatcher import CommandDispatcher
from core.system_control import SystemControl

MOCK_WPCTL_STATUS = """
PipeWire 'pipewire-0' [1.6.8, eddie@eddie-desktop, cookie:4241650017]
 └─ Clients:
        32. WirePlumber                         [1.6.8, eddie@eddie-desktop, pid:1727]
        33. pipewire                            [1.6.8, eddie@eddie-desktop, pid:1728]

Audio
 ├─ Devices:
 │      48. AD102 High Definition Audio Controller [alsa]
 │      63. Webcam Vitade AF                    [alsa]
 │      64. Razer Kraken X USB                  [alsa]
 │      65. USB Audio                           [alsa]
 │  
 ├─ Sinks:
 │  *   66. Razer Kraken X USB Analog Stereo    [vol: 0.50]
 │      69. USB Audio S/PDIF Output             [vol: 0.50]
 │      70. USB Audio Speakers                  [vol: 0.50]
 │      71. USB Audio Front Headphones          [vol: 1.00]
 │     113. AD102 High Definition Audio Controller Digital Stereo (HDMI) [Q27G2G4] [vol: 0.40]
 │  
 ├─ Sources:
 │  *   67. Razer Kraken X USB Analog Stereo    [vol: 1.00]
 │      68. Webcam Vitade AF Mono               [vol: 1.00]
 │      72. USB Audio Line Input                [vol: 1.00]
 │      73. USB Audio Microphone                [vol: 1.00]
 │  
 ├─ Filters:
 │  
 └─ Streams:

Video
 ├─ Devices:
 │      53. USB 2.0 Camera                      [v4l2]
 │  
 ├─ Sinks:
 │  
 ├─ Sources:
 │  *   44. USB 2.0 Camera (V4L2)              
 │  
 ├─ Filters:
 │  
 └─ Streams:

Settings
 └─ Default Configured Devices:
         0. Audio/Sink    alsa_output.usb-Razer_Razer_Kraken_X_USB_00000000-00.analog-stereo
"""

MOCK_HYPR_MONITORS = """[
  {
    "id": 0,
    "name": "DP-2",
    "description": "AOC Q27G2G4",
    "width": 2560,
    "height": 1440,
    "scale": 1.0,
    "focused": false,
    "activeWorkspace": {"id": 2, "name": "2"}
  },
  {
    "id": 1,
    "name": "DP-3",
    "description": "AOC Q27G2G4",
    "width": 2560,
    "height": 1440,
    "scale": 1.0,
    "focused": true,
    "activeWorkspace": {"id": 3, "name": "3"}
  }
]"""


class TestDeviceHardwareControls(unittest.TestCase):
    """Test suite for SystemControl device features and CommandDispatcher integration."""

    def setUp(self):
        self.sc = SystemControl()
        self.dispatcher = CommandDispatcher()

    # ------------------------------------------------------------- Audio Routing
    @patch("subprocess.run")
    def test_get_audio_devices_parsing(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = MOCK_WPCTL_STATUS
        mock_run.return_value = mock_proc

        res = self.sc.get_audio_devices()
        self.assertTrue(res["success"])
        sinks = res["sinks"]
        sources = res["sources"]

        self.assertEqual(len(sinks), 5)
        self.assertEqual(len(sources), 4)

        # Check default sink
        def_sink = next(s for s in sinks if s["is_default"])
        self.assertEqual(def_sink["id"], 66)
        self.assertEqual(def_sink["name"], "Razer Kraken X USB Analog Stereo")
        self.assertEqual(def_sink["volume"], 0.50)

        # Check default source
        def_src = next(s for s in sources if s["is_default"])
        self.assertEqual(def_src["id"], 67)
        self.assertEqual(def_src["name"], "Razer Kraken X USB Analog Stereo")

    def test_match_audio_device_fuzzy(self):
        devices = [
            {"id": 66, "name": "Razer Kraken X USB Analog Stereo", "is_default": True},
            {"id": 69, "name": "USB Audio S/PDIF Output", "is_default": False},
            {"id": 70, "name": "USB Audio Speakers", "is_default": False},
            {"id": 71, "name": "USB Audio Front Headphones", "is_default": False},
            {"id": 113, "name": "AD102 High Definition Audio Controller Digital Stereo (HDMI)", "is_default": False},
        ]

        # Alias: headset -> Razer Kraken
        dev = self.sc._match_audio_device("headset", devices)
        self.assertIsNotNone(dev)
        self.assertEqual(dev["id"], 66)

        # Alias: speakers -> USB Audio Speakers
        dev = self.sc._match_audio_device("speakers", devices)
        self.assertIsNotNone(dev)
        self.assertEqual(dev["id"], 70)

        # Alias: headphones -> USB Audio Front Headphones
        dev = self.sc._match_audio_device("front headphones", devices)
        self.assertIsNotNone(dev)
        self.assertEqual(dev["id"], 71)

        # Alias: hdmi -> HDMI Digital Stereo
        dev = self.sc._match_audio_device("hdmi", devices)
        self.assertIsNotNone(dev)
        self.assertEqual(dev["id"], 113)

        # Exact ID match
        dev = self.sc._match_audio_device("69", devices)
        self.assertIsNotNone(dev)
        self.assertEqual(dev["id"], 69)

    @patch("subprocess.run")
    def test_switch_audio_output_success(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = MOCK_WPCTL_STATUS
        mock_run.return_value = mock_proc

        res = self.sc.switch_audio_output("speakers")
        self.assertTrue(res["success"])
        self.assertEqual(res["device_id"], 70)
        self.assertIn("Speakers", res["device_name"])
        self.assertIn("switched to", res["speech"].lower())

    @patch("subprocess.run")
    def test_switch_audio_input_success(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = MOCK_WPCTL_STATUS
        mock_run.return_value = mock_proc

        res = self.sc.switch_audio_input("webcam")
        self.assertTrue(res["success"])
        self.assertEqual(res["device_id"], 68)
        self.assertIn("Vitade", res["device_name"])
        self.assertIn("switched to", res["speech"].lower())

    # ------------------------------------------------------------- WiFi
    @patch("subprocess.run")
    def test_list_wifi_networks(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "20083:34:WPA3\nBaxter:32:WPA2\n:30:\n20083:27:WPA3\nBaxter:24:WPA2\n"
        mock_run.return_value = mock_proc

        res = self.sc.list_wifi_networks()
        self.assertTrue(res["success"])
        ssids = [n["ssid"] for n in res["networks"]]
        self.assertIn("20083", ssids)
        self.assertIn("Baxter", ssids)
        self.assertEqual(len(ssids), 2)  # Deduplicated

    @patch("subprocess.run")
    def test_connect_wifi(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "Device 'wlp7s0' successfully activated with 'Baxter'."
        mock_run.return_value = mock_proc

        res = self.sc.connect_wifi("Baxter")
        self.assertTrue(res["success"])
        self.assertIn("Baxter", res["speech"])

    # ------------------------------------------------------------- Bluetooth
    @patch("subprocess.run")
    def test_list_bluetooth_devices(self, mock_run):
        def _side_effect(cmd, **kwargs):
            m = MagicMock()
            m.returncode = 0
            if "Connected" in cmd:
                m.stdout = "Device 3C:64:CF:CB:9A:11 Sony WH-1000XM4\n"
            else:
                m.stdout = "Device 3C:64:CF:CB:9A:11 Sony WH-1000XM4\nDevice 12:34:56:78:90:AB MX Master 3\n"
            return m

        mock_run.side_effect = _side_effect

        res = self.sc.list_bluetooth_devices()
        self.assertTrue(res["success"])
        devices = res["devices"]
        self.assertEqual(len(devices), 2)
        self.assertTrue(devices[0]["connected"])
        self.assertFalse(devices[1]["connected"])

    # ------------------------------------------------------------- Brightness & Displays
    @patch("subprocess.run")
    def test_list_displays(self, mock_run):
        mock_proc = MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = MOCK_HYPR_MONITORS
        mock_run.return_value = mock_proc

        res = self.sc.list_displays()
        self.assertTrue(res["success"])
        self.assertEqual(len(res["monitors"]), 2)
        self.assertIn("DP-2", res["speech"])
        self.assertIn("DP-3", res["speech"])

    # ------------------------------------------------------------- Dispatcher Integration
    def test_dispatcher_audio_output_switch(self):
        cmd = "switch audio output device to headset"
        res = self.dispatcher.dispatch_text(cmd, execute=False)
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "AUDIO_CONTROL")
        self.assertEqual(res["action"], "switch_audio_output headset")

    def test_dispatcher_audio_output_speakers(self):
        cmd = "switch audio output to speakers"
        res = self.dispatcher.dispatch_text(cmd, execute=False)
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "AUDIO_CONTROL")
        self.assertEqual(res["action"], "switch_audio_output speakers")

    def test_dispatcher_mic_switch(self):
        cmd = "switch microphone to headset"
        res = self.dispatcher.dispatch_text(cmd, execute=False)
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "AUDIO_CONTROL")
        self.assertEqual(res["action"], "switch_audio_input headset")

    def test_dispatcher_wifi_connect(self):
        cmd = "connect to wifi Baxter"
        res = self.dispatcher.dispatch_text(cmd, execute=False)
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "DEVICE_CONTROL")
        self.assertEqual(res["action"], "wifi_connect Baxter")

    def test_dispatcher_wifi_list(self):
        cmd = "list wifi networks"
        res = self.dispatcher.dispatch_text(cmd, execute=False)
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "DEVICE_CONTROL")
        self.assertEqual(res["action"], "wifi_list")

    def test_dispatcher_bluetooth_connect(self):
        cmd = "connect bluetooth headset"
        res = self.dispatcher.dispatch_text(cmd, execute=False)
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "DEVICE_CONTROL")
        self.assertEqual(res["action"], "bluetooth_connect headset")

    def test_dispatcher_brightness(self):
        cmd = "set brightness to 70%"
        res = self.dispatcher.dispatch_text(cmd, execute=False)
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "DEVICE_CONTROL")
        self.assertEqual(res["action"], "brightness_set 70%")

        cmd_dim = "dim screen"
        res_dim = self.dispatcher.dispatch_text(cmd_dim, execute=False)
        self.assertTrue(res_dim["matched"])
        self.assertEqual(res_dim["intent"], "DEVICE_CONTROL")
        self.assertEqual(res_dim["action"], "brightness_down")

    def test_dispatcher_list_displays(self):
        cmd = "list displays"
        res = self.dispatcher.dispatch_text(cmd, execute=False)
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "DEVICE_CONTROL")
        self.assertEqual(res["action"], "list_displays")

    def test_compound_device_control(self):
        # Multi-action chaining combining audio device switch and brightness
        cmd = "switch audio output to headset and dim screen"
        res = self.dispatcher.dispatch_text(cmd, execute=False)
        self.assertTrue(res["matched"])
        self.assertEqual(res["intent"], "COMPOUND_REFLEX")
        self.assertIn("switch_audio_output headset", res["action"])
        self.assertIn("brightness_down", res["action"])


if __name__ == "__main__":
    unittest.main()
