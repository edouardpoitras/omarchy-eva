"""System Control, Process Telemetry, and Window Operations for Omarchy Linux."""

import datetime
import glob
import json
import os
import re
import socket
import subprocess
import time
from typing import Any, Dict, List, Optional


class SystemControl:
    """Manages system power, application closing, top processes, and hardware telemetry."""

    def __init__(self):
        pass

    # --------------------------------------------------------- Window / App Close
    def close_app(self, target: str) -> Dict[str, Any]:
        """Find and gracefully close the window matching target app name or title."""
        t_clean = target.strip().lower()
        if not t_clean:
            return {"success": False, "error": "Empty target specified."}

        closed_windows = []
        try:
            # Query Hyprland clients
            proc = subprocess.run(
                ["hyprctl", "clients", "-j"],
                capture_output=True,
                text=True,
                check=False,
                timeout=2.0,
            )
            if proc.returncode == 0 and proc.stdout.strip():
                clients = json.loads(proc.stdout)
                for c in clients:
                    cls = c.get("class", "").lower()
                    init_cls = c.get("initialClass", "").lower()
                    title = c.get("title", "").lower()
                    addr = c.get("address", "")

                    if (
                        t_clean == cls
                        or t_clean in cls
                        or t_clean == init_cls
                        or t_clean in init_cls
                        or t_clean in title
                    ):
                        # Dispatch closewindow to specific address
                        subprocess.run(
                            ["hyprctl", "dispatch", "closewindow", f"address:{addr}"],
                            capture_output=True,
                            timeout=1.0,
                            check=False,
                        )
                        closed_windows.append(c.get("title", cls))

            if closed_windows:
                return {
                    "success": True,
                    "target": target,
                    "closed_count": len(closed_windows),
                    "windows": closed_windows,
                    "message": f"Closed {target} ({closed_windows[0]})."
                    if len(closed_windows) == 1
                    else f"Closed {len(closed_windows)} windows for {target}.",
                }

            # If no client window was found, try graceful pkill as fallback
            pk = subprocess.run(
                ["pkill", "-f", t_clean],
                capture_output=True,
                timeout=1.0,
                check=False,
            )
            if pk.returncode == 0:
                return {
                    "success": True,
                    "target": target,
                    "fallback_pkill": True,
                    "message": f"Terminated process {target}.",
                }

            return {
                "success": False,
                "target": target,
                "error": f"No running window or process found matching '{target}'.",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --------------------------------------------------------- Process Telemetry
    def get_top_processes(self, by: str = "cpu", count: int = 3) -> Dict[str, Any]:
        """Query top N processes by CPU or Memory usage in sub-10ms without LLM."""
        sort_key = "-%cpu" if by.lower() in ("cpu", "processor") else "-%mem"
        col_idx = 1 if by.lower() in ("cpu", "processor") else 2

        try:
            # Query ps with sort
            proc = subprocess.run(
                ["ps", "-eo", "comm,%cpu,%mem", f"--sort={sort_key}"],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.5,
            )
            lines = proc.stdout.splitlines()
            processes = []
            seen = set()

            # Ignore internal shell/monitoring tools
            ignored = {"ps", "grep", "sed", "awk", "systemd", "kworker", "bash", "sh"}

            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 3:
                    name = parts[0].strip("[]()")
                    base_name = os.path.basename(name)
                    if base_name in ignored or any(ign in base_name for ign in ["kworker", "rcu_"]):
                        continue

                    try:
                        cpu_val = float(parts[1])
                        mem_val = float(parts[2])
                    except ValueError:
                        continue

                    # Consolidate duplicate process names (e.g. multiple chrome threads)
                    if base_name in seen:
                        for p in processes:
                            if p["name"] == base_name:
                                p["cpu"] = round(p["cpu"] + cpu_val, 1)
                                p["mem"] = round(p["mem"] + mem_val, 1)
                                break
                    else:
                        seen.add(base_name)
                        processes.append({
                            "name": base_name,
                            "cpu": cpu_val,
                            "mem": mem_val,
                        })

                    if len(processes) >= count:
                        break

            # Sort consolidated results
            processes.sort(key=lambda x: x["cpu"] if by.lower() in ("cpu", "processor") else x["mem"], reverse=True)
            top = processes[:count]

            # Construct natural Butler spoken response
            metric_label = "CPU" if by.lower() in ("cpu", "processor") else "memory"
            if top:
                phrases = []
                for p in top:
                    val = p["cpu"] if metric_label == "CPU" else p["mem"]
                    phrases.append(f"{p['name']} at {val} percent")
                if len(phrases) == 1:
                    speech = f"The top process by {metric_label} is {phrases[0]}."
                elif len(phrases) == 2:
                    speech = f"The top processes by {metric_label} are {phrases[0]}, and {phrases[1]}."
                else:
                    speech = f"The top {len(phrases)} processes by {metric_label} are {', '.join(phrases[:-1])}, and {phrases[-1]}."
            else:
                speech = f"No significant processes currently consuming {metric_label}."

            return {
                "success": True,
                "by": metric_label,
                "count": len(top),
                "processes": top,
                "speech": speech,
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --------------------------------------------------------- Power / Session
    def power_action(self, action: str) -> Dict[str, Any]:
        """Execute system power state action."""
        act = action.strip().lower()
        if act in ("shutdown", "poweroff", "turn off"):
            subprocess.Popen(["systemctl", "poweroff"])
            return {"success": True, "action": "shutdown", "speech": "Initiating system shutdown."}
        elif act in ("reboot", "restart"):
            subprocess.Popen(["systemctl", "reboot"])
            return {"success": True, "action": "reboot", "speech": "Rebooting system."}
        elif act in ("suspend", "sleep"):
            subprocess.Popen(["systemctl", "suspend"])
            return {"success": True, "action": "suspend", "speech": "Putting system to sleep."}
        elif act in ("lock", "lock-session", "lock screen"):
            subprocess.Popen(["loginctl", "lock-session"])
            return {"success": True, "action": "lock", "speech": "Workstation locked."}
        elif act in ("logout", "exit", "log out"):
            subprocess.Popen(["hyprctl", "dispatch", "exit"])
            return {"success": True, "action": "logout", "speech": "Logging out of Hyprland."}
        return {"success": False, "error": f"Unknown power action '{action}'."}

    # --------------------------------------------------------- Hardware Telemetry
    def get_battery_status(self) -> Dict[str, Any]:
        """Read Linux power supply battery state."""
        bat_dir = "/sys/class/power_supply"
        if not os.path.exists(bat_dir):
            return {"success": False, "error": "No battery found."}

        for node in os.listdir(bat_dir):
            if node.startswith("BAT"):
                node_path = os.path.join(bat_dir, node)
                try:
                    with open(os.path.join(node_path, "capacity"), "r") as f:
                        cap = int(f.read().strip())
                    status = "discharging"
                    if os.path.exists(os.path.join(node_path, "status")):
                        with open(os.path.join(node_path, "status"), "r") as f:
                            status = f.read().strip().lower()
                    speech = f"Battery is at {cap} percent, {status}."
                    return {"success": True, "capacity": cap, "status": status, "speech": speech}
                except Exception:
                    pass

        return {"success": True, "capacity": 100, "status": "ac connected", "speech": "Running on AC wall power."}

    def get_disk_space(self) -> Dict[str, Any]:
        """Read root filesystem storage space."""
        try:
            st = os.statvfs("/")
            free_gb = round((st.f_bavail * st.f_frsize) / (1024**3), 1)
            total_gb = round((st.f_blocks * st.f_frsize) / (1024**3), 1)
            speech = f"You have {free_gb} gigabytes free out of {total_gb} gigabytes on your main drive."
            return {"success": True, "free_gb": free_gb, "total_gb": total_gb, "speech": speech}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_ram_status(self) -> Dict[str, Any]:
        """Read /proc/meminfo memory availability."""
        try:
            mem_total = 0
            mem_avail = 0
            with open("/proc/meminfo", "r") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        mem_total = int(line.split()[1])
                    elif line.startswith("MemAvailable:"):
                        mem_avail = int(line.split()[1])
            total_gb = round(mem_total / (1024 * 1024), 1)
            avail_gb = round(mem_avail / (1024 * 1024), 1)
            speech = f"You have {avail_gb} gigabytes of RAM available out of {total_gb} gigabytes total."
            return {"success": True, "available_gb": avail_gb, "total_gb": total_gb, "speech": speech}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_time_date(self) -> Dict[str, Any]:
        """Format current time and date for spoken readout."""
        now = datetime.datetime.now()
        time_str = now.strftime("%I:%M %p").lstrip("0")
        date_str = now.strftime("%A, %B %d")
        speech = f"The time is {time_str} on {date_str}."
        return {"success": True, "time": time_str, "date": date_str, "speech": speech}

    def get_local_ip(self) -> Dict[str, Any]:
        """Determine primary local IP address."""
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            speech = f"Your local IP address is {ip}."
            return {"success": True, "ip": ip, "speech": speech}
        except Exception:
            return {"success": False, "error": "Could not determine local IP address."}

    # --------------------------------------------------------- Clipboard
    def read_clipboard(self) -> Dict[str, Any]:
        """Read text from Wayland clipboard via wl-paste."""
        try:
            proc = subprocess.run(
                ["wl-paste", "--no-newline"],
                capture_output=True,
                text=True,
                check=False,
                timeout=1.0,
            )
            text = proc.stdout.strip()
            if not text:
                return {"success": True, "text": "", "speech": "Your clipboard is currently empty."}
            word_count = len(text.split())
            if word_count <= 25:
                speech = f"Clipboard contains: {text}"
            else:
                speech = f"Clipboard contains {word_count} words starting with: {text[:60]}."
            return {"success": True, "text": text, "speech": speech}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def clear_clipboard(self) -> Dict[str, Any]:
        """Clear Wayland clipboard via wl-copy --clear."""
        try:
            subprocess.run(["wl-copy", "--clear"], timeout=1.0, check=False)
            return {"success": True, "speech": "Clipboard cleared."}
        except Exception as e:
            return {"success": False, "error": str(e)}

    # --------------------------------------------------------- Window Management
    def center_active_window(self) -> bool:
        """Center the active window on screen."""
        res = subprocess.run(["hyprctl", "dispatch", "centerwindow"], capture_output=True, check=False)
        return res.returncode == 0

    def pin_active_window(self) -> bool:
        """Pin active window so it stays visible across all workspaces."""
        res = subprocess.run(["hyprctl", "dispatch", "pin"], capture_output=True, check=False)
        return res.returncode == 0

    def move_window_to_monitor(self, direction: str = "+1") -> bool:
        """Move active window to next/previous monitor."""
        target = "mon:+1" if direction in ("+1", "next", "right") else "mon:-1"
        res = subprocess.run(["hyprctl", "dispatch", "movewindow", target], capture_output=True, check=False)
        return res.returncode == 0

    # --------------------------------------------------------- Media Metadata Query
    def get_current_track(self) -> Dict[str, Any]:
        """Query active D-Bus MPRIS players for currently playing track and artist."""
        try:
            res = subprocess.run(
                ["dbus-send", "--session", "--dest=org.freedesktop.DBus", "--type=method_call",
                 "--print-reply", "/org/freedesktop/DBus", "org.freedesktop.DBus.ListNames"],
                capture_output=True, text=True, timeout=1.0, check=False,
            )
            players = [line.split('"')[1] for line in res.stdout.splitlines() if "org.mpris.MediaPlayer2." in line]
            if not players:
                return {"success": True, "playing": False, "speech": "No active media players detected."}

            for p in players:
                player_short = p.split(".")[-1].capitalize()
                # Query Status
                status_res = subprocess.run(
                    ["dbus-send", "--session", f"--dest={p}", "--type=method_call", "--print-reply",
                     "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties.Get",
                     "string:org.mpris.MediaPlayer2.Player", "string:PlaybackStatus"],
                    capture_output=True, text=True, timeout=1.0, check=False,
                )
                status_match = re.search(r'string\s+"(\w+)"', status_res.stdout)
                status = status_match.group(1).lower() if status_match else "unknown"

                # Query Metadata
                meta_res = subprocess.run(
                    ["dbus-send", "--session", f"--dest={p}", "--type=method_call", "--print-reply",
                     "/org/mpris/MediaPlayer2", "org.freedesktop.DBus.Properties.Get",
                     "string:org.mpris.MediaPlayer2.Player", "string:Metadata"],
                    capture_output=True, text=True, timeout=1.0, check=False,
                )
                title_match = re.search(r'dict entry\(\s*string "xesam:title"\s*variant\s*string "([^"]+)"', meta_res.stdout)
                artist_match = re.search(r'dict entry\(\s*string "xesam:artist"\s*variant\s*array \[\s*string "([^"]+)"', meta_res.stdout)

                title = title_match.group(1).strip() if title_match else ""
                artist = artist_match.group(1).strip() if artist_match else ""

                if status == "playing":
                    if title and artist:
                        speech = f"Currently playing '{title}' by {artist} on {player_short}."
                    elif title:
                        speech = f"Currently playing '{title}' on {player_short}."
                    else:
                        speech = f"{player_short} is currently playing."
                    return {"success": True, "playing": True, "player": player_short, "title": title, "artist": artist, "status": status, "speech": speech}
                elif status == "paused" and title:
                    speech = f"Playback is currently paused on {player_short} for '{title}'."
                    return {"success": True, "playing": False, "player": player_short, "title": title, "artist": artist, "status": status, "speech": speech}

            return {"success": True, "playing": False, "speech": "Media playback is currently paused or idle."}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": "Could not retrieve media playback details."}

    # --------------------------------------------------------- Hardware Diagnostics & Uptime
    def get_uptime(self) -> Dict[str, Any]:
        """Read system uptime from /proc/uptime."""
        try:
            with open("/proc/uptime", "r", encoding="utf-8") as f:
                secs = float(f.read().split()[0])
            days = int(secs // 86400)
            hours = int((secs % 86400) // 3600)
            mins = int((secs % 3600) // 60)

            parts = []
            if days > 0:
                parts.append(f"{days} day{'s' if days != 1 else ''}")
            if hours > 0:
                parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
            parts.append(f"{mins} minute{'s' if mins != 1 else ''}")
            uptime_str = ", ".join(parts)
            speech = f"The system has been running for {uptime_str}."
            return {"success": True, "seconds": secs, "days": days, "hours": hours, "minutes": mins, "speech": speech}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": "Could not determine system uptime."}

    def get_cpu_temperature(self) -> Dict[str, Any]:
        """Read CPU temperature from /sys/class/thermal or /sys/class/hwmon."""
        import glob
        try:
            temps = []
            files = glob.glob("/sys/class/hwmon/hwmon*/temp1_input") + glob.glob("/sys/class/thermal/thermal_zone*/temp")
            for f in files:
                try:
                    with open(f, "r", encoding="utf-8") as tf:
                        raw = float(tf.read().strip())
                        c = raw / 1000.0 if raw > 1000 else raw
                        if 10.0 < c < 115.0:
                            temps.append(c)
                except Exception:
                    pass
            if not temps:
                return {"success": False, "speech": "Thermal sensors are unavailable."}
            avg_temp = round(sum(temps) / len(temps), 1)
            speech = f"Current average hardware temperature is {avg_temp} degrees Celsius."
            return {"success": True, "temperature_c": avg_temp, "sensors_count": len(temps), "speech": speech}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": "Could not read temperature sensors."}

    # --------------------------------------------------------- Device & Network Controls
    def toggle_wifi(self, action: str = "toggle") -> Dict[str, Any]:
        """Turn WiFi on, off, or toggle via nmcli."""
        try:
            if action in ("on", "enable"):
                subprocess.run(["nmcli", "radio", "wifi", "on"], check=True, timeout=2.0)
                speech = "Wi-Fi is now enabled."
            elif action in ("off", "disable"):
                subprocess.run(["nmcli", "radio", "wifi", "off"], check=True, timeout=2.0)
                speech = "Wi-Fi has been disabled."
            else:
                proc = subprocess.run(["nmcli", "radio", "wifi"], capture_output=True, text=True, check=False)
                is_on = "enabled" in proc.stdout.lower()
                new_state = "off" if is_on else "on"
                subprocess.run(["nmcli", "radio", "wifi", new_state], check=True, timeout=2.0)
                speech = f"Wi-Fi is now {'disabled' if is_on else 'enabled'}."
            return {"success": True, "speech": speech}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": f"Failed to modify Wi-Fi state: {e}"}

    def toggle_bluetooth(self, action: str = "toggle") -> Dict[str, Any]:
        """Turn Bluetooth on, off, or toggle via bluetoothctl."""
        try:
            if action in ("on", "enable"):
                subprocess.run(["bluetoothctl", "power", "on"], check=True, timeout=2.0)
                speech = "Bluetooth is now enabled."
            elif action in ("off", "disable"):
                subprocess.run(["bluetoothctl", "power", "off"], check=True, timeout=2.0)
                speech = "Bluetooth has been disabled."
            else:
                proc = subprocess.run(["bluetoothctl", "show"], capture_output=True, text=True, check=False)
                is_on = "powered: yes" in proc.stdout.lower()
                new_state = "off" if is_on else "on"
                subprocess.run(["bluetoothctl", "power", new_state], check=True, timeout=2.0)
                speech = f"Bluetooth is now {'disabled' if is_on else 'enabled'}."
            return {"success": True, "speech": speech}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": f"Failed to modify Bluetooth state: {e}"}

    def toggle_dnd(self, action: str = "toggle") -> Dict[str, Any]:
        """Toggle do-not-disturb notification silencing in Omarchy."""
        try:
            subprocess.run(["omarchy-toggle-notification-silencing"], check=False, timeout=2.0)
            return {"success": True, "speech": "Do not disturb mode toggled."}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": "Could not toggle notification silencing."}

    def toggle_idle(self, action: str = "toggle") -> Dict[str, Any]:
        """Toggle stay-awake or normal idle behavior via omarchy-toggle-idle."""
        try:
            cmd = ["omarchy-toggle-idle"]
            if action in ("stay-awake", "awake", "on"):
                cmd.append("stay-awake")
                speech = "Stay-awake mode activated. The screen will not idle or lock."
            elif action in ("allow-idle", "idle", "off"):
                cmd.append("allow-idle")
                speech = "Standard idle behavior restored."
            else:
                cmd.append("toggle")
                speech = "System idle stay-awake behavior toggled."
            subprocess.run(cmd, check=False, timeout=2.0)
            return {"success": True, "speech": speech}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": "Could not toggle idle state."}

    def toggle_bar(self) -> Dict[str, Any]:
        """Toggle Omarchy top bar visibility."""
        try:
            subprocess.run(["omarchy-toggle-bar"], check=False, timeout=2.0)
            return {"success": True, "speech": "Top bar toggled."}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": "Could not toggle top bar."}

    def open_directory(self, target: str) -> Dict[str, Any]:
        """Open standard user folders in default file manager."""
        t_clean = target.lower().strip()
        home = os.path.expanduser("~")
        dir_map = {
            "downloads": os.path.join(home, "Downloads"),
            "pictures": os.path.join(home, "Pictures"),
            "screenshots": os.path.join(home, "Pictures"),
            "documents": os.path.join(home, "Documents"),
            "home": home,
            "config": os.path.join(home, ".config"),
            "music": os.path.join(home, "Music"),
            "videos": os.path.join(home, "Videos"),
        }
        dest = dir_map.get(t_clean, home)
        if not os.path.exists(dest):
            os.makedirs(dest, exist_ok=True)
        try:
            subprocess.Popen(["xdg-open", dest], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"success": True, "path": dest, "speech": f"Opening {t_clean} directory."}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": f"Could not open {t_clean}."}

    # --------------------------------------------------------- Audio Sinks & Sources
    def get_audio_devices(self) -> Dict[str, Any]:
        """Query wpctl status to enumerate active Audio Sinks (outputs) and Sources (microphones)."""
        try:
            proc = subprocess.run(["wpctl", "status"], capture_output=True, text=True, check=False, timeout=2.0)
            if proc.returncode != 0 or not proc.stdout.strip():
                return {"success": False, "sinks": [], "sources": [], "speech": "Audio subsystem status unavailable."}

            lines = proc.stdout.splitlines()
            sinks: List[Dict[str, Any]] = []
            sources: List[Dict[str, Any]] = []
            in_audio = False
            current_section = None

            for line in lines:
                stripped = line.strip()
                if stripped.startswith("Audio"):
                    in_audio = True
                    continue
                elif stripped.startswith("Video") or stripped.startswith("Settings"):
                    in_audio = False
                    current_section = None
                    continue

                if not in_audio:
                    continue

                if "Sinks:" in line:
                    current_section = "sinks"
                    continue
                elif "Sources:" in line:
                    current_section = "sources"
                    continue
                elif any(sec in line for sec in ("Filters:", "Streams:", "Devices:")):
                    current_section = None
                    continue

                if current_section in ("sinks", "sources"):
                    m = re.search(r"([*]?)\s*(\d+)\.\s+(.*?)(?:\s+\[vol:\s*([0-9\.]+)\]|\s*$)", line)
                    if m:
                        is_def = m.group(1) == "*"
                        dev_id = int(m.group(2))
                        dev_name = m.group(3).strip()
                        vol = float(m.group(4)) if m.group(4) else 1.0
                        item = {"id": dev_id, "name": dev_name, "is_default": is_def, "volume": vol}
                        if current_section == "sinks":
                            sinks.append(item)
                        else:
                            sources.append(item)

            return {"success": True, "sinks": sinks, "sources": sources}
        except Exception as e:
            return {"success": False, "sinks": [], "sources": [], "error": str(e), "speech": f"Could not inspect audio devices: {e}"}

    def _match_audio_device(self, query: str, devices: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Fuzzy-match target device by query string, aliases, or device IDs."""
        q = query.lower().strip()
        if not q or not devices:
            return None

        # Check exact integer ID
        if q.isdigit():
            target_id = int(q)
            for d in devices:
                if d["id"] == target_id:
                    return d

        # Semantic alias expansions
        ALIASES = {
            "headset": ["kraken", "headset", "headphones", "analog stereo"],
            "headphone": ["headphones", "headset", "kraken", "front headphones"],
            "headphones": ["headphones", "headset", "kraken", "front headphones"],
            "speaker": ["speaker", "speakers"],
            "speakers": ["speaker", "speakers"],
            "hdmi": ["hdmi", "digital stereo", "q27g2g4", "controller digital"],
            "monitor": ["hdmi", "digital stereo", "q27g2g4", "controller digital"],
            "tv": ["hdmi", "digital stereo"],
            "spdif": ["s/pdif", "spdif", "optical"],
            "optical": ["s/pdif", "spdif", "optical"],
            "webcam": ["webcam", "vitade", "camera"],
            "camera": ["webcam", "vitade", "camera"],
            "mic": ["microphone", "mic"],
            "microphone": ["microphone", "mic"],
            "usb": ["usb audio", "usb"],
            "line": ["line input", "line"],
        }

        # 1. Direct name substring match
        for d in devices:
            d_name = d["name"].lower()
            if q == d_name or q in d_name:
                return d

        # 2. Match against alias keywords
        expanded = ALIASES.get(q, [q])
        for kw in expanded:
            for d in devices:
                d_name = d["name"].lower()
                if kw in d_name:
                    return d

        # 3. Word token overlap
        q_tokens = set(re.findall(r"[a-z0-9]+", q))
        best_dev = None
        max_overlap = 0
        for d in devices:
            d_tokens = set(re.findall(r"[a-z0-9]+", d["name"].lower()))
            overlap = len(q_tokens & d_tokens)
            if overlap > max_overlap:
                max_overlap = overlap
                best_dev = d

        if max_overlap > 0:
            return best_dev
        return None

    def switch_audio_output(self, target: str) -> Dict[str, Any]:
        """Switch default PipeWire audio sink to target output device."""
        res = self.get_audio_devices()
        sinks = res.get("sinks", [])
        if not sinks:
            return {"success": False, "speech": "No audio output devices found."}

        matched = self._match_audio_device(target, sinks)
        if not matched:
            avail = ", ".join(s["name"] for s in sinks[:3])
            return {"success": False, "speech": f"Could not find output matching '{target}'. Available devices include: {avail}."}

        dev_id = matched["id"]
        dev_name = matched["name"]
        try:
            subprocess.run(["wpctl", "set-default", str(dev_id)], check=True, timeout=2.0)
            return {
                "success": True,
                "device_id": dev_id,
                "device_name": dev_name,
                "speech": f"Audio output switched to {dev_name}.",
            }
        except Exception as e:
            return {"success": False, "error": str(e), "speech": f"Failed to switch audio output: {e}"}

    def switch_audio_input(self, target: str) -> Dict[str, Any]:
        """Switch default PipeWire audio source (microphone) to target input device."""
        res = self.get_audio_devices()
        sources = res.get("sources", [])
        if not sources:
            return {"success": False, "speech": "No microphone or audio input devices found."}

        matched = self._match_audio_device(target, sources)
        if not matched:
            avail = ", ".join(s["name"] for s in sources[:3])
            return {"success": False, "speech": f"Could not find microphone matching '{target}'. Available mics include: {avail}."}

        dev_id = matched["id"]
        dev_name = matched["name"]
        try:
            subprocess.run(["wpctl", "set-default", str(dev_id)], check=True, timeout=2.0)
            return {
                "success": True,
                "device_id": dev_id,
                "device_name": dev_name,
                "speech": f"Microphone switched to {dev_name}.",
            }
        except Exception as e:
            return {"success": False, "error": str(e), "speech": f"Failed to switch microphone: {e}"}

    def list_audio_devices_speech(self, kind: str = "all") -> Dict[str, Any]:
        """Provide spoken readout of current audio outputs and microphones."""
        res = self.get_audio_devices()
        sinks = res.get("sinks", [])
        sources = res.get("sources", [])

        parts = []
        if kind in ("all", "output", "sinks"):
            cur_sink = next((s["name"] for s in sinks if s["is_default"]), None)
            if cur_sink:
                parts.append(f"Audio output is set to {cur_sink}. Total outputs: {len(sinks)}.")
            else:
                parts.append(f"Found {len(sinks)} output devices.")

        if kind in ("all", "input", "sources", "mics", "microphones"):
            cur_source = next((s["name"] for s in sources if s["is_default"]), None)
            if cur_source:
                parts.append(f"Microphone is set to {cur_source}. Total inputs: {len(sources)}.")
            else:
                parts.append(f"Found {len(sources)} microphone devices.")

        speech = " ".join(parts) if parts else "No audio devices found."
        return {"success": True, "sinks": sinks, "sources": sources, "speech": speech}

    # --------------------------------------------------------- WiFi Management
    def list_wifi_networks(self, rescan: bool = False) -> Dict[str, Any]:
        """List nearby WiFi networks using nmcli (sub-10ms with cached scan)."""
        try:
            cmd = ["nmcli", "-t", "-f", "SSID,SIGNAL,SECURITY", "dev", "wifi", "list"]
            if not rescan:
                cmd.extend(["--rescan", "no"])
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=3.0)
            if proc.returncode != 0 or not proc.stdout.strip():
                return {"success": False, "networks": [], "speech": "No Wi-Fi networks found."}

            networks = []
            seen = set()
            for line in proc.stdout.splitlines():
                parts = line.strip().split(":")
                if len(parts) >= 2:
                    ssid = parts[0].strip()
                    signal = parts[1].strip()
                    sec = parts[2].strip() if len(parts) > 2 else ""
                    if ssid and ssid not in seen:
                        seen.add(ssid)
                        networks.append({"ssid": ssid, "signal": signal, "security": sec})

            if not networks:
                return {"success": True, "networks": [], "speech": "No Wi-Fi access points currently in range."}

            names = [n["ssid"] for n in networks[:4]]
            speech = f"Found {len(networks)} Wi-Fi networks. Nearest are: {', '.join(names)}."
            return {"success": True, "networks": networks, "speech": speech}
        except Exception as e:
            return {"success": False, "error": str(e), "networks": [], "speech": f"Could not scan Wi-Fi: {e}"}

    def connect_wifi(self, ssid: str, password: Optional[str] = None) -> Dict[str, Any]:
        """Connect to a WiFi network via nmcli."""
        clean_ssid = ssid.strip().strip("\"'")
        if not clean_ssid:
            return {"success": False, "speech": "Please specify a Wi-Fi network SSID."}
        try:
            cmd = ["nmcli", "dev", "wifi", "connect", clean_ssid]
            if password:
                cmd.extend(["password", password])
            proc = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=12.0)
            if proc.returncode == 0:
                return {"success": True, "ssid": clean_ssid, "speech": f"Successfully connected to Wi-Fi {clean_ssid}."}
            else:
                err = proc.stderr.strip() or proc.stdout.strip()
                return {"success": False, "error": err, "speech": f"Failed to connect to {clean_ssid}: {err}"}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": f"Error connecting to Wi-Fi {clean_ssid}."}

    def disconnect_wifi(self) -> Dict[str, Any]:
        """Disconnect wireless interface."""
        try:
            proc = subprocess.run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE", "device"], capture_output=True, text=True, check=False)
            wifi_dev = None
            for line in proc.stdout.splitlines():
                parts = line.strip().split(":")
                if len(parts) >= 2 and parts[1] == "wifi":
                    wifi_dev = parts[0]
                    break
            if wifi_dev:
                subprocess.run(["nmcli", "device", "disconnect", wifi_dev], check=True, timeout=3.0)
                return {"success": True, "device": wifi_dev, "speech": "Disconnected from Wi-Fi."}
            subprocess.run(["nmcli", "radio", "wifi", "off"], check=True, timeout=2.0)
            return {"success": True, "speech": "Wi-Fi interface disabled."}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": f"Could not disconnect Wi-Fi: {e}"}

    def get_wifi_status(self) -> Dict[str, Any]:
        """Check active WiFi connection, SSID, and signal."""
        try:
            proc = subprocess.run(["nmcli", "-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device"], capture_output=True, text=True, check=False, timeout=2.0)
            wifi_conn = None
            for line in proc.stdout.splitlines():
                parts = line.split(":")
                if len(parts) >= 4 and parts[1] == "wifi" and parts[2] == "connected":
                    wifi_conn = parts[3]
                    break

            if wifi_conn:
                speech = f"Connected to Wi-Fi network {wifi_conn}."
                return {"success": True, "connected": True, "ssid": wifi_conn, "speech": speech}
            else:
                return {"success": True, "connected": False, "speech": "Wi-Fi is not currently connected to any network."}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": f"Could not check Wi-Fi status: {e}"}

    # --------------------------------------------------------- Bluetooth Management
    def list_bluetooth_devices(self) -> Dict[str, Any]:
        """Enumerate paired and available Bluetooth devices."""
        try:
            proc = subprocess.run(["bluetoothctl", "devices"], capture_output=True, text=True, check=False, timeout=2.0)
            devices = []
            for line in proc.stdout.splitlines():
                m = re.match(r"^Device\s+([0-9A-Fa-f:]+)\s+(.+)$", line.strip())
                if m:
                    devices.append({"mac": m.group(1), "name": m.group(2).strip()})

            proc_conn = subprocess.run(["bluetoothctl", "devices", "Connected"], capture_output=True, text=True, check=False, timeout=2.0)
            connected_macs = set()
            for line in proc_conn.stdout.splitlines():
                m = re.match(r"^Device\s+([0-9A-Fa-f:]+)", line.strip())
                if m:
                    connected_macs.add(m.group(1))

            for d in devices:
                d["connected"] = d["mac"] in connected_macs

            if not devices:
                return {"success": True, "devices": [], "speech": "No paired Bluetooth devices found."}

            names = [f"{d['name']} (connected)" if d.get("connected") else d["name"] for d in devices]
            speech = f"Paired Bluetooth devices: {', '.join(names)}."
            return {"success": True, "devices": devices, "speech": speech}
        except Exception as e:
            return {"success": False, "error": str(e), "devices": [], "speech": f"Could not list Bluetooth devices: {e}"}

    def connect_bluetooth(self, target: str) -> Dict[str, Any]:
        """Connect to a Bluetooth device matching name or MAC."""
        res = self.list_bluetooth_devices()
        devices = res.get("devices", [])
        q = target.lower().strip()
        matched = None
        for d in devices:
            if q == d["mac"].lower() or q in d["name"].lower() or d["name"].lower() in q:
                matched = d
                break

        target_mac = matched["mac"] if matched else target.strip()
        target_name = matched["name"] if matched else target.strip()

        try:
            proc = subprocess.run(["bluetoothctl", "connect", target_mac], capture_output=True, text=True, check=False, timeout=6.0)
            if proc.returncode == 0 and "Successful" in proc.stdout:
                return {"success": True, "mac": target_mac, "name": target_name, "speech": f"Connected to Bluetooth device {target_name}."}
            else:
                err = proc.stdout.strip() or proc.stderr.strip()
                if "already connected" in err.lower():
                    return {"success": True, "mac": target_mac, "name": target_name, "speech": f"{target_name} is already connected."}
                return {"success": False, "error": err, "speech": f"Failed to connect to {target_name}."}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": f"Bluetooth connection error: {e}"}

    def disconnect_bluetooth(self, target: Optional[str] = None) -> Dict[str, Any]:
        """Disconnect a specific or all connected Bluetooth devices."""
        try:
            if target:
                res = self.list_bluetooth_devices()
                devices = res.get("devices", [])
                q = target.lower().strip()
                matched = None
                for d in devices:
                    if q == d["mac"].lower() or q in d["name"].lower():
                        matched = d
                        break
                target_mac = matched["mac"] if matched else target.strip()
                subprocess.run(["bluetoothctl", "disconnect", target_mac], check=False, timeout=3.0)
                name = matched["name"] if matched else target
                return {"success": True, "speech": f"Disconnected Bluetooth device {name}."}
            else:
                proc = subprocess.run(["bluetoothctl", "devices", "Connected"], capture_output=True, text=True, check=False, timeout=2.0)
                disconnected = []
                for line in proc.stdout.splitlines():
                    m = re.match(r"^Device\s+([0-9A-Fa-f:]+)\s+(.+)$", line.strip())
                    if m:
                        subprocess.run(["bluetoothctl", "disconnect", m.group(1)], check=False, timeout=2.0)
                        disconnected.append(m.group(2).strip())
                if disconnected:
                    return {"success": True, "speech": f"Disconnected Bluetooth: {', '.join(disconnected)}."}
                return {"success": True, "speech": "No active Bluetooth connections to disconnect."}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": f"Could not disconnect Bluetooth: {e}"}

    # --------------------------------------------------------- Display & Brightness Controls
    def get_brightness(self) -> Dict[str, Any]:
        """Query current screen brightness percentage."""
        try:
            backlights = glob.glob("/sys/class/backlight/*")
            if backlights:
                bl_dir = backlights[0]
                with open(os.path.join(bl_dir, "brightness"), "r") as f:
                    cur = float(f.read().strip())
                with open(os.path.join(bl_dir, "max_brightness"), "r") as f:
                    mx = float(f.read().strip())
                pct = int(round((cur / mx) * 100.0))
                return {"success": True, "level": pct, "type": "backlight", "speech": f"Screen brightness is at {pct} percent."}

            proc = subprocess.run(["ddcutil", "--brief", "getvcp", "10", "--display", "1"], capture_output=True, text=True, check=False, timeout=2.0)
            if proc.returncode == 0:
                parts = proc.stdout.strip().split()
                if len(parts) >= 4 and parts[0] == "VCP" and parts[1] == "10":
                    pct = int(parts[3])
                    return {"success": True, "level": pct, "type": "ddcutil", "speech": f"Display brightness is at {pct} percent."}

            return {"success": False, "speech": "Brightness hardware controls unavailable on this display."}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": "Could not read brightness."}

    def set_brightness(self, level: int) -> Dict[str, Any]:
        """Set screen brightness percentage (0-100)."""
        clamped = max(1, min(100, level))
        try:
            backlights = glob.glob("/sys/class/backlight/*")
            if backlights:
                subprocess.run(["brightnessctl", "set", f"{clamped}%"], check=True, timeout=2.0)
                return {"success": True, "level": clamped, "speech": f"Brightness set to {clamped} percent."}

            subprocess.Popen(["ddcutil", "setvcp", "10", str(clamped)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return {"success": True, "level": clamped, "speech": f"Setting display brightness to {clamped} percent."}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": f"Could not set brightness: {e}"}

    def adjust_brightness(self, delta: int) -> Dict[str, Any]:
        """Step brightness up or down by delta percentage."""
        cur_res = self.get_brightness()
        cur_val = cur_res.get("level", 50)
        target = max(5, min(100, cur_val + delta))
        return self.set_brightness(target)

    def list_displays(self) -> Dict[str, Any]:
        """Query active Hyprland monitors, resolutions, and active workspaces."""
        try:
            proc = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True, text=True, check=False, timeout=1.0)
            if proc.returncode == 0 and proc.stdout.strip():
                monitors = json.loads(proc.stdout)
                descriptions = []
                for m in monitors:
                    name = m.get("name", "")
                    w = m.get("width", 0)
                    h = m.get("height", 0)
                    scale = m.get("scale", 1.0)
                    ws_id = m.get("activeWorkspace", {}).get("name", "")
                    focused = m.get("focused", False)
                    desc = f"{name} ({w}x{h}, scale {scale}, workspace {ws_id}{', focused' if focused else ''})"
                    descriptions.append(desc)
                speech = f"Connected displays: {'; '.join(descriptions)}."
                return {"success": True, "monitors": monitors, "speech": speech}
            return {"success": False, "speech": "Could not inspect connected monitors."}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": f"Display query failed: {e}"}

    def set_display_scale(self, monitor: str, scale: float) -> Dict[str, Any]:
        """Adjust Hyprland monitor display scale."""
        try:
            arg = f"{monitor},preferred,auto,{scale}"
            subprocess.run(["hyprctl", "keyword", "monitor", arg], check=True, timeout=1.0)
            return {"success": True, "monitor": monitor, "scale": scale, "speech": f"Display {monitor} scale set to {scale}."}
        except Exception as e:
            return {"success": False, "error": str(e), "speech": f"Could not change display scale: {e}"}


