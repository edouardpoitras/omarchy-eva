"""Proactive Eva System Awareness & Watchdog Engine.

Continuously monitors system telemetry, hardware limits, network connectivity,
systemd journal anomalies, and ambient weather alerts. Proactively initiates
spoken announcements, HUD warnings, and desktop notifications when issues arise.
"""

import json
import logging
import os
import re
import socket
import subprocess
import threading
import time
import urllib.request
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger("eva.awareness")


class AwarenessEngine:
    """Autonomous background sentinel monitoring system vitals and anomalous events."""

    def __init__(
        self,
        alert_callback: Optional[Callable[..., Any]] = None,
        query_agent_callback: Optional[Callable[[str], Any]] = None,
        cpu_threshold: float = 85.0,
        ram_min_gb: float = 3.0,
        disk_min_gb: float = 15.0,
        battery_min_pct: int = 15,
        enabled: bool = True,
    ):
        self.alert_callback = alert_callback
        self.query_agent_callback = query_agent_callback

        self.cpu_threshold = cpu_threshold
        self.ram_min_gb = ram_min_gb
        self.disk_min_gb = disk_min_gb
        self.battery_min_pct = battery_min_pct
        self.enabled = enabled

        self.running = False
        self._thread: Optional[threading.Thread] = None

        # State tracking
        self._last_alerts: Dict[str, float] = {}
        self._is_online: Optional[bool] = None
        self._last_weather: Dict[str, Any] = {}
        self._last_check_times: Dict[str, float] = {}
        self._current_stats: Dict[str, Any] = {}
        self._seen_journal_entries: set = set()

        # Cooldown intervals in seconds to prevent alarm fatigue
        self.cooldowns = {
            "cpu": 600.0,       # 10 minutes
            "ram": 900.0,       # 15 minutes
            "disk": 3600.0,     # 1 hour
            "battery": 1200.0,  # 20 minutes
            "network": 60.0,    # State-change driven
            "journal": 600.0,   # 10 minutes
            "weather": 3600.0,  # 1 hour
        }

    def start(self):
        """Start awareness monitoring loop in background thread."""
        if self.running:
            return
        self.running = True
        self._thread = threading.Thread(target=self._run_loop, name="EvaAwareness", daemon=True)
        self._thread.start()

    def stop(self):
        """Stop awareness monitoring loop."""
        self.running = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)

    def _can_alert(self, category: str) -> bool:
        """Check if cooldown has expired for an alert category."""
        last = self._last_alerts.get(category, 0.0)
        cooldown = self.cooldowns.get(category, 300.0)
        return (time.time() - last) >= cooldown

    def _record_alert(self, category: str):
        """Mark alert category timestamp to enforce cooldown."""
        self._last_alerts[category] = time.time()

    def trigger_alert(
        self,
        category: str,
        title: str,
        message: str,
        speech: Optional[str] = None,
        alert_type: str = "warning",
        requires_clarification: bool = False,
        force: bool = False,
    ):
        """Emit alert through daemon callback if cooldown permits."""
        if not self.enabled:
            return
        if not force and not self._can_alert(category):
            return

        self._record_alert(category)
        if self.alert_callback:
            try:
                self.alert_callback(
                    title=title,
                    message=message,
                    speech=speech or message,
                    alert_type=alert_type,
                    requires_clarification=requires_clarification,
                )
            except Exception as e:
                logger.error("Failed to emit alert: %s", e)

    # ------------------------------------------------------------- Check Routines
    def check_cpu_usage(self) -> float:
        """Calculate total CPU usage percentage over a brief sample."""
        try:
            with open("/proc/stat", "r") as f:
                fields1 = [float(x) for x in f.readline().split()[1:]]
            idle1, total1 = fields1[3], sum(fields1)

            time.sleep(0.2)

            with open("/proc/stat", "r") as f:
                fields2 = [float(x) for x in f.readline().split()[1:]]
            idle2, total2 = fields2[3], sum(fields2)

            diff_total = total2 - total1
            diff_idle = idle2 - idle1
            if diff_total <= 0:
                return 0.0
            usage = 100.0 * (1.0 - (diff_idle / diff_total))
            return round(usage, 1)
        except Exception:
            return 0.0

    def check_ram_available_gb(self) -> float:
        """Read available RAM in gigabytes from /proc/meminfo."""
        try:
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemAvailable:"):
                        kb = int(line.split()[1])
                        return round(kb / (1024 * 1024), 2)
            return 999.0
        except Exception:
            return 999.0

    def check_disk_free_gb(self) -> float:
        """Read free storage space in gigabytes on root filesystem."""
        try:
            st = os.statvfs("/")
            return round((st.f_bavail * st.f_frsize) / (1024**3), 2)
        except Exception:
            return 999.0

    def check_battery(self) -> Optional[Dict[str, Any]]:
        """Read battery capacity and charging status if available."""
        bat_dir = "/sys/class/power_supply"
        if not os.path.exists(bat_dir):
            return None

        for node in os.listdir(bat_dir):
            if node.startswith("BAT"):
                node_path = os.path.join(bat_dir, node)
                try:
                    with open(os.path.join(node_path, "capacity"), "r") as f:
                        cap = int(f.read().strip())
                    status = "discharging"
                    status_file = os.path.join(node_path, "status")
                    if os.path.exists(status_file):
                        with open(status_file, "r") as f:
                            status = f.read().strip().lower()
                    return {"capacity": cap, "status": status}
                except Exception:
                    pass
        return None

    def check_network_connectivity(self) -> bool:
        """Test internet connectivity via quick socket probe (sub-15ms)."""
        for host in ("1.1.1.1", "8.8.8.8"):
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(1.5)
                s.connect((host, 53))
                s.close()
                return True
            except Exception:
                continue
        return False

    def check_recent_journal_errors(self, since: str = "90 seconds ago") -> List[str]:
        """Query systemd journal for recent priority 3 (error/critical) log messages."""
        try:
            cmd = ["journalctl", "-p", "3", "-xb", "--since", since, "--no-pager", "-o", "short-monotonic"]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=2.5, check=False)
            if proc.returncode != 0:
                return []

            lines = proc.stdout.splitlines()
            anomalies = []
            ignored_patterns = ["-- No entries --", "pulseaudio", "xdg-desktop-portal", "gnome-keyring"]

            for line in lines:
                l_strip = line.strip()
                if not l_strip or any(ign in l_strip for ign in ignored_patterns):
                    continue
                # Hash or simplify line to avoid repetitive reporting
                line_key = re.sub(r"\[\s*\d+\.\d+\]", "", l_strip).strip()
                if line_key not in self._seen_journal_entries:
                    self._seen_journal_entries.add(line_key)
                    # Limit cache size
                    if len(self._seen_journal_entries) > 200:
                        self._seen_journal_entries.clear()
                    anomalies.append(l_strip)

            return anomalies
        except Exception:
            return []

    def check_weather_advisory(self) -> Optional[Dict[str, Any]]:
        """Query ambient weather for extreme conditions or alerts."""
        try:
            req = urllib.request.Request("https://wttr.in/?format=j1", headers={"User-Agent": "curl/8.0"})
            with urllib.request.urlopen(req, timeout=3.5) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                cur = data.get("current_condition", [{}])[0]
                desc = cur.get("weatherDesc", [{}])[0].get("value", "")
                temp_c = cur.get("temp_C", "")
                return {"description": desc, "temp_c": temp_c}
        except Exception:
            return None

    # ------------------------------------------------------------- Main Watchdog Loop
    def _run_loop(self):
        """Continuous background loop evaluating periodic monitors."""
        # Initial wait to let daemon and desktop settle
        time.sleep(3.0)

        # Baseline network state
        self._is_online = self.check_network_connectivity()

        res_timer = 0.0
        net_timer = 0.0
        journal_timer = 0.0
        weather_timer = 0.0

        while self.running:
            now = time.time()

            # 1. System Resources Watchdog (every 10s)
            if (now - res_timer) >= 10.0:
                res_timer = now
                self._evaluate_resources()

            # 2. Network Connectivity Watchdog (every 15s)
            if (now - net_timer) >= 15.0:
                net_timer = now
                self._evaluate_network()

            # 3. Systemd Journal Anomaly Watchdog (every 60s)
            if (now - journal_timer) >= 60.0:
                journal_timer = now
                self._evaluate_journal()

            # 4. Ambient Weather Watchdog (every 30m)
            if (now - weather_timer) >= 1800.0:
                weather_timer = now
                self._evaluate_weather()

            time.sleep(1.0)

    def _evaluate_resources(self):
        """Inspect CPU, RAM, Disk, and Battery against critical thresholds."""
        # CPU
        cpu_usage = self.check_cpu_usage()
        self._current_stats["cpu"] = cpu_usage
        if cpu_usage >= self.cpu_threshold and self._can_alert("cpu"):
            # Identify top culprit
            culprit = "a background process"
            try:
                proc = subprocess.run(
                    ["ps", "-eo", "comm,%cpu", "--sort=-%cpu"],
                    capture_output=True,
                    text=True,
                    timeout=1.0,
                    check=False,
                )
                lines = proc.stdout.splitlines()
                if len(lines) > 1:
                    culprit = lines[1].split()[0]
            except Exception:
                pass

            title = "High CPU Load"
            msg = f"CPU utilization is at {cpu_usage}% (lead: {culprit})."
            speech = f"Sir, system CPU load has reached {int(cpu_usage)} percent, primarily driven by {culprit}."
            self.trigger_alert("cpu", title, msg, speech=speech, alert_type="warning")

        # RAM
        ram_free = self.check_ram_available_gb()
        self._current_stats["ram_free_gb"] = ram_free
        if ram_free < self.ram_min_gb and self._can_alert("ram"):
            title = "Low Available Memory"
            msg = f"Available RAM has dropped to {ram_free} GB."
            speech = f"Sir, available system memory has dropped to {ram_free} gigabytes. Memory pressure is elevated."
            self.trigger_alert("ram", title, msg, speech=speech, alert_type="warning")

        # Disk
        disk_free = self.check_disk_free_gb()
        self._current_stats["disk_free_gb"] = disk_free
        if disk_free < self.disk_min_gb and self._can_alert("disk"):
            title = "Low Disk Space"
            msg = f"Root drive has {disk_free} GB remaining."
            speech = f"Sir, your primary storage drive has only {int(disk_free)} gigabytes of free space remaining."
            self.trigger_alert("disk", title, msg, speech=speech, alert_type="warning")

        # Battery
        bat = self.check_battery()
        if bat:
            self._current_stats["battery"] = bat
            cap = bat.get("capacity", 100)
            status = bat.get("status", "discharging")
            if status == "discharging" and cap <= self.battery_min_pct and self._can_alert("battery"):
                title = "Low Battery"
                msg = f"Battery at {cap}% ({status})."
                speech = f"Sir, battery level is down to {cap} percent. Please connect your power adapter."
                self.trigger_alert("battery", title, msg, speech=speech, alert_type="critical")

    def _evaluate_network(self):
        """Detect transition between online and offline states."""
        online = self.check_network_connectivity()
        self._current_stats["online"] = online

        if self._is_online is not None:
            if self._is_online and not online:
                # Connection lost
                self.trigger_alert(
                    "network",
                    "Network Disconnected",
                    "Internet link is offline.",
                    speech="Sir, internet connectivity has been lost.",
                    alert_type="warning",
                    force=True,
                )
            elif not self._is_online and online:
                # Connection restored
                self.trigger_alert(
                    "network",
                    "Network Restored",
                    "Internet link is online.",
                    speech="Sir, internet connectivity has been restored.",
                    alert_type="info",
                    force=True,
                )

        self._is_online = online

    def _evaluate_journal(self):
        """Inspect journalctl for fatal crashes or hardware faults."""
        anomalies = self.check_recent_journal_errors(since="90 seconds ago")
        if anomalies and self._can_alert("journal"):
            raw_sample = anomalies[0][:160]

            # If System 2 agent is available, use it to synthesize a concise diagnosis
            speech = None
            if self.query_agent_callback:
                try:
                    prompt = (
                        f"The Linux systemd journal logged this critical event:\n\"{raw_sample}\"\n"
                        "In exactly ONE brief, polite spoken sentence as Eva, inform the user what crashed or failed."
                    )
                    res = self.query_agent_callback(prompt)
                    if res and isinstance(res, dict) and res.get("response"):
                        speech = res["response"]
                except Exception:
                    pass

            if not speech:
                speech = f"An anomalous error was logged in the system journal: {raw_sample[:80]}."

            title = "System Anomaly Logged"
            msg = raw_sample
            self.trigger_alert("journal", title, msg, speech=speech, alert_type="warning")

    def _evaluate_weather(self):
        """Inspect weather for severe conditions or storm alerts."""
        w = self.check_weather_advisory()
        if not w:
            return

        desc = w.get("description", "").lower()
        temp = w.get("temp_c", "")
        self._last_weather = w
        self._current_stats["weather"] = w

        severe_keywords = ["thunderstorm", "blizzard", "tornado", "heavy rain", "gale", "storm", "hail"]
        if any(kw in desc for kw in severe_keywords) and self._can_alert("weather"):
            title = "Severe Weather Alert"
            msg = f"{w['description']} ({temp}°C)"
            speech = f"Sir, local weather advisory: {w['description']} with temperatures around {temp} degrees Celsius."
            self.trigger_alert("weather", title, msg, speech=speech, alert_type="warning")

    def get_status(self) -> Dict[str, Any]:
        """Return diagnostic status of awareness engine."""
        return {
            "enabled": self.enabled,
            "running": self.running,
            "stats": self._current_stats,
            "last_alerts": self._last_alerts,
            "cooldowns": self.cooldowns,
            "is_online": self._is_online,
            "last_weather": self._last_weather,
        }
