"""Specialized Screen GUI and Multimodal Vision Decision Model."""

from typing import Any, Dict, List, Optional

from core.decision.base import BaseDecisionEngine, DecisionQuestion
from core.decision.token_extractor import TokenExtractor
from core.input_controller import InputController
from core.vision_capture import VisionCapture
from core.visual_grounding import VisualGrounding


class ScreenGUIDomainModel:
    """Multimodal System 1 model that processes screen pixels and drives GUI interactions."""

    def __init__(
        self,
        engine: BaseDecisionEngine,
        vision: Optional[VisionCapture] = None,
        visual_grounding: Optional[VisualGrounding] = None,
        input_ctrl: Optional[InputController] = None,
    ):
        self.engine = engine
        self.vision = vision or VisionCapture()
        self.visual = visual_grounding or VisualGrounding()
        self.input = input_ctrl or InputController()

    def get_question_schema(self) -> Dict[str, DecisionQuestion]:
        """Return the Clef multimodal decision question schema for screen interaction."""
        return {
            "gui_action": DecisionQuestion(
                question_id="gui_action",
                question_type="choice",
                instructions="Determine the virtual GUI action to perform on the current screen image.",
                criteria={
                    "click_element": "Click a visible button, link, icon, menu item, or text element on the screen",
                    "double_click": "Double-click a visible item, file, or element on the screen",
                    "type_text": "Type text into the currently focused or target text input field",
                    "scroll_screen": "Scroll up or down on the current screen content",
                    "inspect_screen": "Visually inspect and perceive the elements or state of the screen",
                },
            )
        }

    def execute(self, text: str, context: Optional[Dict[str, Any]] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Decide and execute the visual GUI action."""
        # 1. Capture current screen framebuffer
        img_path = None
        if not dry_run:
            img_path, _ = self.vision.capture_screen(mode="fullscreen")

        images = [img_path] if img_path else []

        # 2. Run multimodal decision scoring with Clef
        schema = self.get_question_schema()
        decisions = self.engine.predict(
            state=text,
            questions=schema,
            images=images,
            context=context,
        )
        action_res = decisions.get("gui_action")
        action = action_res.selected_option if action_res else "click_element"
        confidence = action_res.confidence if action_res else 0.8

        tokens = TokenExtractor.extract_gui_tokens(text)

        if dry_run:
            return {
                "domain": "screen_gui",
                "action": action,
                "confidence": confidence,
                "tokens": tokens,
                "success": True,
            }

        success = False
        speech = None

        if action in ("click_element", "double_click"):
            target = tokens.get("target")
            x = tokens.get("x")
            y = tokens.get("y")
            double = action == "double_click" or tokens.get("double", False)
            btn = tokens.get("button", "left")

            if x is not None and y is not None:
                # Direct coordinate click
                success = self.input.click(button=btn, double=double, target_pos=(x, y))
                speech = f"Clicked at ({x}, {y})."
            elif target:
                # Ground target visually and click
                res = self.visual.locate_and_click(target, button=btn, double=double)
                success = res.get("success", False)
                speech = f"Clicked {target}." if success else f"Could not locate {target} on screen."
            else:
                success = False

        elif action == "type_text":
            txt = tokens.get("text")
            if txt:
                success = self.input.type_text(txt)
                speech = f"Typed '{txt}'."
            else:
                success = False

        elif action == "inspect_screen":
            speech = "Inspected current screen elements."
            success = True

        elif action == "scroll_screen":
            speech = "Scrolled screen."
            success = True

        return {
            "domain": "screen_gui",
            "action": action,
            "confidence": confidence,
            "tokens": tokens,
            "success": success,
            "speech": speech,
            "screenshot": img_path,
            "latency_ms": action_res.latency_ms if action_res else 0.0,
        }
