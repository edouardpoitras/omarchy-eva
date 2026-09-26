"""Virtual input controller with subtle human-like delays for Omarchy Eva.

Implements fluid, natural mouse movement via cubic ease-out interpolation on Hyprland IPC
and cadence-delayed keyboard typing via wtype.
"""

import math
import os
import random
import re
import subprocess
import time
from typing import List, Optional, Tuple


class InputController:
    """Simulates natural user inputs (mouse motion, clicks, and keystrokes)."""

    def __init__(self):
        self.wtype_bin = "/usr/bin/wtype"

    def get_cursor_pos(self) -> Tuple[int, int]:
        """Retrieve current global cursor coordinates."""
        try:
            res = subprocess.run(
                ["hyprctl", "cursorpos"],
                capture_output=True,
                text=True,
                timeout=1.0,
            )
            if res.returncode == 0 and res.stdout.strip():
                parts = res.stdout.strip().split(",")
                if len(parts) == 2:
                    return int(parts[0].strip()), int(parts[1].strip())
        except Exception:
            pass
        return 0, 0

    def move_cursor_to(
        self,
        target_x: int,
        target_y: int,
        smooth: bool = True,
        duration_ms: float = 240.0,
        steps: int = 16,
    ) -> bool:
        """Move pointer to target coordinates with subtle human-like easing.
        
        Args:
            target_x: Target X coordinate in pixels.
            target_y: Target Y coordinate in pixels.
            smooth: If True, interpolates along a smooth cubic ease-out curve.
            duration_ms: Total duration of movement in milliseconds.
            steps: Number of intermediate interpolation steps.
        """
        if not smooth:
            return self._set_cursor_pos(target_x, target_y)

        x0, y0 = self.get_cursor_pos()
        if x0 == target_x and y0 == target_y:
            return True

        step_delay = (duration_ms / 1000.0) / max(steps, 1)

        # Generate trajectory points using cubic ease-out: f(t) = 1 - (1 - t)^3
        for i in range(1, steps + 1):
            t = i / steps
            # Smooth cubic ease-out curve with subtle micro-jitter
            factor = 1.0 - math.pow(1.0 - t, 3)
            
            # Subtle human perceptual noise (max 1px) on intermediate frames
            jitter_x = random.randint(-1, 1) if i < steps else 0
            jitter_y = random.randint(-1, 1) if i < steps else 0

            cur_x = int(round(x0 + (target_x - x0) * factor)) + jitter_x
            cur_y = int(round(y0 + (target_y - y0) * factor)) + jitter_y

            self._set_cursor_pos(cur_x, cur_y)
            time.sleep(step_delay)

        # Guarantee exact target coordinates at end
        self._set_cursor_pos(target_x, target_y)
        return True

    def _set_cursor_pos(self, x: int, y: int) -> bool:
        """Issue direct Hyprland IPC cursor move command."""
        lua_code = f"hl.dispatch(hl.dsp.cursor.move({{ x = {x}, y = {y} }}))"
        try:
            res = subprocess.run(
                ["hyprctl", "eval", lua_code],
                capture_output=True,
                timeout=0.5,
            )
            return res.returncode == 0
        except Exception:
            return False

    def click(
        self,
        button: str = "left",
        double: bool = False,
        target_pos: Optional[Tuple[int, int]] = None,
    ) -> bool:
        """Execute a natural mouse click with subtle press-release latency.
        
        Args:
            button: 'left', 'right', or 'middle'.
            double: If True, executes a double click.
            target_pos: Optional (x, y) coordinates to move to before clicking.
        """
        if target_pos:
            self.move_cursor_to(target_pos[0], target_pos[1], smooth=True)
            # Brief human hesitation before click (30ms)
            time.sleep(0.03)

        btn_map = {
            "left": "mouse:272",
            "right": "mouse:273",
            "middle": "mouse:274",
        }
        key = btn_map.get(button.lower(), "mouse:272")
        lua_code = f"hl.dispatch(hl.dsp.send_shortcut({{ mods = 0, key = '{key}' }}))"

        try:
            res = subprocess.run(["hyprctl", "eval", lua_code], capture_output=True, timeout=0.5)
            ok = res.returncode == 0

            if double and ok:
                time.sleep(0.08)  # 80ms double-click interval
                res2 = subprocess.run(["hyprctl", "eval", lua_code], capture_output=True, timeout=0.5)
                ok = res2.returncode == 0

            return ok
        except Exception:
            return False

    def type_text(self, text: str, delay_ms: int = 25) -> bool:
        """Type arbitrary text with natural human keystroke cadence.
        
        Args:
            text: String to type.
            delay_ms: Milliseconds of delay between successive keystrokes (default: 25ms).
        """
        if not text:
            return True

        if not os.path.exists(self.wtype_bin):
            print(f"Error: wtype binary not found at {self.wtype_bin}")
            return False

        # Apply slight random variation around target delay (e.g. 20-30ms for 25ms target)
        actual_delay = max(5, int(delay_ms + random.randint(-3, 3)))
        cmd = [self.wtype_bin, "-d", str(actual_delay), "--", text]

        try:
            res = subprocess.run(cmd, capture_output=True, timeout=10.0)
            return res.returncode == 0
        except Exception as e:
            print(f"Error typing with wtype: {e}")
            return False

    def press_key(self, key: str, mods: Optional[List[str]] = None) -> bool:
        """Press and release a named key with optional modifiers."""
        if not os.path.exists(self.wtype_bin):
            return False

        cmd = [self.wtype_bin]
        mods = mods or []
        for m in mods:
            cmd.extend(["-M", m.lower()])

        cmd.extend(["-k", key])

        for m in reversed(mods):
            cmd.extend(["-m", m.lower()])

        try:
            res = subprocess.run(cmd, capture_output=True, timeout=2.0)
            return res.returncode == 0
        except Exception:
            return False

    def hotkey(self, chord: str) -> bool:
        """Execute a keyboard chord (e.g. 'ctrl+c', 'ctrl+shift+t', 'super+space')."""
        parts = [p.strip() for p in chord.split("+")]
        if not parts:
            return False

        key = parts[-1]
        mods = parts[:-1]
        mod_map = {
            "ctrl": "ctrl",
            "control": "ctrl",
            "shift": "shift",
            "alt": "alt",
            "super": "logo",
            "win": "logo",
            "meta": "logo",
        }
        resolved_mods = [mod_map.get(m.lower(), m.lower()) for m in mods]
        return self.press_key(key, resolved_mods)
