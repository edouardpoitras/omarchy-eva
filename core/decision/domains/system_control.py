"""Specialized System Telemetry, Health, and Power Decision Model."""

from typing import Any, Dict, Optional

from core.decision.base import BaseDecisionEngine, DecisionQuestion
from core.decision.token_extractor import TokenExtractor
from core.system_control import SystemControl


class SystemControlDomainModel:
    """Specialized System 1 model for hardware controls and telemetry."""

    def __init__(self, engine: BaseDecisionEngine, system: Optional[SystemControl] = None):
        self.engine = engine
        self.system = system or SystemControl()

    def get_question_schema(self) -> Dict[str, DecisionQuestion]:
        """Return the Clef decision question schema for system control."""
        return {
            "system_action": DecisionQuestion(
                question_id="system_action",
                question_type="choice",
                instructions="Determine the hardware, telemetry, or power action requested.",
                criteria={
                    "battery": "Check battery percentage, charging state, or health",
                    "ram": "Check memory / RAM utilization",
                    "cpu": "Check processor load or top CPU processes",
                    "disk": "Check storage and disk space utilization",
                    "ip": "Check local or external IP address",
                    "time": "Check current time or date",
                    "wifi": "Scan, connect, or check Wi-Fi network status",
                    "bluetooth": "Scan, connect, or manage Bluetooth devices",
                    "brightness": "Query or adjust display screen brightness",
                    "power_lock": "Lock the active desktop session",
                    "power_suspend": "Put the system into sleep / suspend mode",
                    "power_reboot": "Reboot the computer",
                    "power_shutdown": "Shut down and power off the machine",
                },
            )
        }

    def execute(self, text: str, context: Optional[Dict[str, Any]] = None, dry_run: bool = False) -> Dict[str, Any]:
        """Decide and execute the system action."""
        schema = self.get_question_schema()
        decisions = self.engine.predict(state=text, questions=schema, context=context)
        action_res = decisions.get("system_action")
        action = action_res.selected_option if action_res else "battery"
        confidence = action_res.confidence if action_res else 0.8

        tokens = TokenExtractor.extract_system_tokens(text)

        if dry_run:
            return {
                "domain": "system_control",
                "action": action,
                "confidence": confidence,
                "tokens": tokens,
                "success": True,
            }

        success = False
        speech = None

        if action == "battery":
            res = self.system.get_battery_status()
            speech = res.get("speech") or f"Battery is at {res.get('percentage')}%."
            success = res.get("success", True)
        elif action == "ram":
            res = self.system.get_ram_status()
            speech = res.get("speech") or f"RAM usage is {res.get('used_gb')} of {res.get('total_gb')} GB."
            success = res.get("success", True)
        elif action == "cpu":
            res = self.system.get_top_processes(by="cpu", count=3)
            speech = res.get("speech") or "Fetched top CPU processes."
            success = res.get("success", True)
        elif action == "disk":
            res = self.system.get_disk_space()
            speech = res.get("speech") or f"Disk has {res.get('avail_gb')} GB available."
            success = res.get("success", True)
        elif action == "ip":
            res = self.system.get_local_ip()
            speech = res.get("speech") or f"Your IP address is {res.get('ip')}."
            success = res.get("success", True)
        elif action == "time":
            res = self.system.get_time_date()
            speech = res.get("speech") or res.get("time", "")
            success = res.get("success", True)
        elif action == "wifi":
            net = tokens.get("network")
            if net:
                res = self.system.connect_wifi(net)
                speech = res.get("speech")
                success = res.get("success", False)
            else:
                res = self.system.get_wifi_status()
                speech = res.get("speech") or "Checked Wi-Fi status."
                success = res.get("success", True)
        elif action == "bluetooth":
            res = self.system.list_bluetooth_devices()
            speech = res.get("speech") or "Listed Bluetooth devices."
            success = res.get("success", True)
        elif action == "brightness":
            lvl = tokens.get("level")
            if lvl is not None:
                res = self.system.set_brightness(lvl)
                speech = f"Set brightness to {lvl} percent."
                success = res.get("success", True)
            else:
                res = self.system.get_brightness()
                speech = f"Current brightness is {res.get('level')}%."
                success = res.get("success", True)
        elif action == "power_lock":
            res = self.system.power_action("lock")
            speech = "Locking screen."
            success = res.get("success", True)
        elif action == "power_suspend":
            res = self.system.power_action("suspend")
            speech = "Suspending system."
            success = res.get("success", True)
        elif action == "power_reboot":
            res = self.system.power_action("reboot")
            speech = "Rebooting system."
            success = res.get("success", True)
        elif action == "power_shutdown":
            res = self.system.power_action("shutdown")
            speech = "Shutting down system."
            success = res.get("success", True)

        return {
            "domain": "system_control",
            "action": action,
            "confidence": confidence,
            "tokens": tokens,
            "success": success,
            "speech": speech,
            "latency_ms": action_res.latency_ms if action_res else 0.0,
        }
