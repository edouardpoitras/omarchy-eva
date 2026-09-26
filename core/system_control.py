"""System Control, Process Telemetry, and Window Operations for Omarchy Linux."""

import datetime
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

