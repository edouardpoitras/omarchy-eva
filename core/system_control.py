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
