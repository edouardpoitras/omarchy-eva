"""High-speed screen perception engine for Omarchy Jarvis.

Captures display framebuffers using grim into local memory in ~30ms,
supporting fullscreen and active-window bounded geometries.
"""

import json
import os
import shutil
import subprocess
import time
from typing import Optional, Tuple

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(REPO_ROOT, ".cache", "jarvis")
os.makedirs(CACHE_DIR, exist_ok=True)
CAPTURES_DIR = os.path.join(REPO_ROOT, "assets", "captures")
os.makedirs(CAPTURES_DIR, exist_ok=True)

DEFAULT_SCREENSHOT_PATH = os.path.join(CACHE_DIR, "screen.jpg")
WORKSPACE_SCREENSHOT_PATH = os.path.join(CAPTURES_DIR, "screen.jpg")
SHM_SCREENSHOT_PATH = "/dev/shm/jarvis_screen.jpg"


class VisionCapture:
    """Wayland framebuffer capture controller via grim."""

    def __init__(self, output_path: str = DEFAULT_SCREENSHOT_PATH):
        self.output_path = output_path
        os.makedirs(os.path.dirname(self.output_path), exist_ok=True)

    def get_active_window_geometry(self) -> Optional[str]:
        """Query active Hyprland window position and dimensions.
        
        Returns:
            Geometry string formatted as "X,Y WxH" for grim -g, or None.
        """
        try:
            res = subprocess.run(
                ["hyprctl", "activewindow", "-j"],
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            if res.returncode == 0 and res.stdout.strip():
                data = json.loads(res.stdout)
                at = data.get("at", [0, 0])
                size = data.get("size", [0, 0])
                if size[0] > 0 and size[1] > 0:
                    return f"{at[0]},{at[1]} {size[0]}x{size[1]}"
        except Exception:
            pass
        return None

    def capture_screen(
        self,
        mode: str = "fullscreen",
        quality: int = 70,
        dest_path: Optional[str] = None,
    ) -> Tuple[Optional[str], float]:
        """Capture screen framebuffer to disk in ~30ms.
        
        Args:
            mode: "fullscreen" for full virtual display, or "active_window" for focused app.
            quality: JPEG quality (0-100, default: 70 for optimal speed/size trade-off).
            dest_path: Optional custom destination file.
            
        Returns:
            Tuple of (file_path, latency_ms).
        """
        target = dest_path or self.output_path
        t_start = time.perf_counter()

        cmd = ["grim", "-t", "jpeg", "-q", str(quality)]

        if mode == "active_window":
            geom = self.get_active_window_geometry()
            if geom:
                cmd.extend(["-g", geom])

        cmd.append(target)

        try:
            res = subprocess.run(cmd, capture_output=True, timeout=2.0)
            if res.returncode != 0:
                print(f"VisionCapture error: {res.stderr.decode()}")
                return None, 0.0

            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)

            # Ensure shared memory and workspace mirrors are also available
            try:
                shutil.copyfile(target, SHM_SCREENSHOT_PATH)
                shutil.copyfile(target, WORKSPACE_SCREENSHOT_PATH)
            except Exception:
                pass

            return target, latency_ms
        except Exception as e:
            print(f"Error capturing screen with grim: {e}")
            return None, 0.0
