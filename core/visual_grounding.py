"""Two-Tier Visual Grounding and Auto-Click Engine for Omarchy Jarvis.

Locates desktop UI elements via:
1. High-speed Tesseract TSV OCR bounding boxes (~300ms, zero tokens) for textual targets.
2. Multimodal Gemini CLI vision grounding for visual attributes (colors, icons, shapes).
3. Smooth organic cursor gliding (cubic ease-out) and natural click execution.
"""

import json
import os
import re
import shlex
import subprocess
import time
from typing import Any, Dict, List, Optional, Tuple

from core.input_controller import InputController
from core.soundscape import Soundscape
from core.vision_capture import VisionCapture, WORKSPACE_SCREENSHOT_PATH


class VisualGrounding:
    """Combines screen perception, OCR/vision grounding, and natural virtual click execution."""

    VISUAL_INDICATORS = {
        "red", "blue", "green", "yellow", "orange", "purple", "pink", "black", "white",
        "grey", "gray", "dark", "light", "icon", "logo", "symbol", "avatar", "picture",
        "image", "circle", "square", "triangle", "arrow", "checkbox", "radio", "toggle",
        "slider", "dock", "bar",
    }

    def __init__(
        self,
        vision: Optional[VisionCapture] = None,
        input_ctrl: Optional[InputController] = None,
        sound: Optional[Soundscape] = None,
    ):
        self.vision = vision or VisionCapture()
        self.input = input_ctrl or InputController()
        self.sound = sound or Soundscape()

    def locate_text_ocr(self, image_path: str, target: str) -> Optional[Tuple[int, int]]:
        """Locate exact word or phrase coordinates via Tesseract TSV bounding boxes."""
        t_clean = target.strip().lower()
        # Remove surrounding punctuation/quotes
        t_clean = re.sub(r"^[\"']|[\"']$", "", t_clean).strip()
        if not t_clean:
            return None

        # Clean target into search tokens
        target_tokens = [w for w in re.split(r"\s+", t_clean) if w]
        if not target_tokens:
            return None

        try:
            res = subprocess.run(
                ["tesseract", image_path, "stdout", "tsv"],
                capture_output=True,
                text=True,
                check=False,
                timeout=4.0,
            )
            if res.returncode != 0:
                return None

            lines = res.stdout.splitlines()
            entries: List[Dict[str, Any]] = []

            for line in lines[1:]:
                parts = line.split("\t")
                if len(parts) >= 12:
                    text_val = parts[11].strip()
                    if text_val:
                        try:
                            conf = float(parts[10])
                            if conf > 30:  # reasonable OCR confidence threshold
                                entries.append({
                                    "left": int(parts[6]),
                                    "top": int(parts[7]),
                                    "width": int(parts[8]),
                                    "height": int(parts[9]),
                                    "conf": conf,
                                    "text": text_val.lower(),
                                    "raw_text": text_val,
                                    "line_num": int(parts[4]),
                                    "par_num": int(parts[3]),
                                    "block_num": int(parts[2]),
                                })
                        except (ValueError, IndexError):
                            continue

            # 1. Single word exact or fuzzy match
            if len(target_tokens) == 1:
                token = target_tokens[0]
                candidates = []
                for e in entries:
                    clean_e = re.sub(r"[^\w]", "", e["text"])
                    clean_t = re.sub(r"[^\w]", "", token)
                    if clean_t and clean_t == clean_e:
                        candidates.append((100, e))
                    elif clean_t and (clean_t in clean_e or clean_e in clean_t) and len(clean_e) >= 3:
                        candidates.append((70, e))

                if candidates:
                    candidates.sort(key=lambda x: (x[0], x[1]["conf"]), reverse=True)
                    best = candidates[0][1]
                    center_x = best["left"] + best["width"] // 2
                    center_y = best["top"] + best["height"] // 2
                    return center_x, center_y

            # 2. Multi-word contiguous phrase matching
            n_tokens = len(target_tokens)
            for i in range(len(entries) - n_tokens + 1):
                window = entries[i : i + n_tokens]
                # Ensure tokens are on the same line
                if any(w["line_num"] != window[0]["line_num"] for w in window):
                    continue

                matched = True
                for j, tok in enumerate(target_tokens):
                    tok_clean = re.sub(r"[^\w]", "", tok)
                    word_clean = re.sub(r"[^\w]", "", window[j]["text"])
                    if not (tok_clean == word_clean or (tok_clean in word_clean and len(word_clean) >= 3)):
                        matched = False
                        break

                if matched:
                    # Calculate bounding box encompassing the whole phrase
                    left = window[0]["left"]
                    right = window[-1]["left"] + window[-1]["width"]
                    top = min(w["top"] for w in window)
                    bottom = max(w["top"] + w["height"] for w in window)
                    center_x = (left + right) // 2
                    center_y = (top + bottom) // 2
                    return center_x, center_y

        except Exception:
            pass

        return None

    def locate_element_agent(self, image_path: str, target: str) -> Optional[Tuple[int, int]]:
        """Locate element coordinates using multimodal Gemini CLI spatial grounding."""
        prompt = (
            f"You are an operating system UI element locator.\n"
            f"Attached Screen Capture: @{image_path}\n"
            f"Locate the UI element: '{target}' in the attached desktop screenshot.\n"
            "Respond ONLY with a single JSON object in this exact schema, with no preamble or explanation:\n"
            '{"found": true, "x": <integer_pixel_x>, "y": <integer_pixel_y>, "description": "<brief description>"}\n'
            'or if not visible: {"found": false, "reason": "<explanation>"}'
        )

        try:
            cmd = ["gemini", "-p", prompt, "--yolo"]
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=18.0,
                check=False,
            )
            out = proc.stdout or proc.stderr or ""
            # Search for JSON object in agent response
            match = re.search(r"\{[^{}]*\"found\"[^{}]*\}", out, re.DOTALL)
            if match:
                data = json.loads(match.group(0))
                if data.get("found"):
                    x = int(data.get("x", 0))
                    y = int(data.get("y", 0))
                    if x > 0 and y > 0:
                        return x, y
        except Exception:
            pass

        return None

    def locate_element(self, target: str, mode: str = "fullscreen") -> Dict[str, Any]:
        """Resolve screen coordinates for target element using Two-Tier strategy."""
        t_start = time.perf_counter()
        img_path, lat = self.vision.capture_screen(mode=mode)
        if not img_path or not os.path.exists(img_path):
            return {"found": False, "target": target, "error": "Screen capture failed."}

        # Prefer the workspace capture path for agent tools
        workspace_img = WORKSPACE_SCREENSHOT_PATH if os.path.exists(WORKSPACE_SCREENSHOT_PATH) else img_path

        t_clean = target.strip()
        # Clean leading words like "the", "on", "button"
        core_target = re.sub(r"^(?:the\s+|on\s+)+", "", t_clean, flags=re.IGNORECASE).strip()
        # Strip trailing "button", "icon", "menu"
        text_query = re.sub(r"\s+(?:button|icon|menu|item|link)$", "", core_target, flags=re.IGNORECASE).strip()

        is_visual = any(w in core_target.lower().split() for w in self.VISUAL_INDICATORS)

        # Tier 1: Try Fast OCR if target appears textual
        if not is_visual and text_query:
            coord = self.locate_text_ocr(img_path, text_query)
            if coord:
                latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
                return {
                    "found": True,
                    "target": target,
                    "query": text_query,
                    "x": coord[0],
                    "y": coord[1],
                    "method": "tesseract_ocr",
                    "latency_ms": latency_ms,
                }

        # Tier 2: Multimodal Vision Grounding via Gemini CLI
        agent_coord = self.locate_element_agent(workspace_img, target)
        if agent_coord:
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            return {
                "found": True,
                "target": target,
                "x": agent_coord[0],
                "y": agent_coord[1],
                "method": "gemini_vision",
                "latency_ms": latency_ms,
            }

        # Fallback: If visual check failed, try OCR with full phrase as last resort
        fallback_coord = self.locate_text_ocr(img_path, core_target)
        if fallback_coord:
            latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
            return {
                "found": True,
                "target": target,
                "query": core_target,
                "x": fallback_coord[0],
                "y": fallback_coord[1],
                "method": "tesseract_ocr_fallback",
                "latency_ms": latency_ms,
            }

        latency_ms = round((time.perf_counter() - t_start) * 1000, 2)
        return {
            "found": False,
            "target": target,
            "latency_ms": latency_ms,
            "error": f"Could not visually locate '{target}' on the screen.",
        }

    def locate_and_click(
        self,
        target: str,
        button: str = "left",
        double: bool = False,
        mode: str = "fullscreen",
        smooth: bool = True,
    ) -> Dict[str, Any]:
        """Locate UI element on screen, smoothly move pointer, click, and play soundscape earcon."""
        loc = self.locate_element(target, mode=mode)
        if not loc.get("found"):
            self.sound.error()
            return {
                "success": False,
                "target": target,
                "error": loc.get("error", "Element not found."),
                "latency_ms": loc.get("latency_ms", 0.0),
            }

        x = loc["x"]
        y = loc["y"]

        # Smooth cubic ease-out movement to target
        self.input.move_cursor_to(x, y, smooth=smooth, duration_ms=220)

        # Natural cadence click
        ok = self.input.click(button=button, double=double)

        if ok:
            self.sound.success()
            click_type = "Double clicked" if double else ("Right clicked" if button == "right" else "Clicked")
            speech = f"{click_type} on {target}."
            return {
                "success": True,
                "target": target,
                "x": x,
                "y": y,
                "button": button,
                "double": double,
                "method": loc.get("method"),
                "latency_ms": loc.get("latency_ms"),
                "speech": speech,
            }
        else:
            self.sound.error()
            return {
                "success": False,
                "target": target,
                "x": x,
                "y": y,
                "error": "Failed to dispatch virtual mouse click.",
            }
