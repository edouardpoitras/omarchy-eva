---
name: omarchy-jarvis
description: >-
  Guide and reference for developing, running, and extending the Jarvis voice-enabled
  desktop automation suite on Omarchy Linux.
---

# Jarvis Voice Automation on Omarchy Linux

`omarchy.jarvis` is a real-time, voice-driven automation and task execution suite designed for Omarchy Linux and Hyprland.

## Architecture

- **ASR & Audio**: Voxtype daemon (Whisper ONNX / PipeWire audio).
- **Trigger**: Push-to-Talk via `SUPER + SHIFT + J` (press & hold to speak, release to execute, configured in `~/.config/hypr/bindings.lua`).
- **Reflex Dispatcher (System 1)**: Sub-millisecond direct Unix socket client for Hyprland IPC (`$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket.sock`) and D-Bus MPRIS.
- **Decision Engine (Laya)**: Non-autoregressive ModernBERT ONNX decision classifier (~25ms).
- **Proactive Awareness Engine**: Background sentinel monitoring CPU pressure, RAM starvation, low disk space, network drops/reconnections, systemd journal anomalies, and weather alerts with autonomous spoken Butler warnings and HUD notifications.
- **Deliberative Reasoning (System 2)**: Omarchy agent CLI bridge (`gemini`, `claude`, `codex`) with live desktop telemetry and multi-turn voice clarification.
- **Neural TTS (Kokoro-82M)**: Sub-35ms local voice synthesis (`bm_george` Jarvis voice) piped to PipeWire (`pw-play`).
- **Screen Perception**: Sub-35ms framebuffer capture via `grim` into memory/JPEG.
- **Visual Grounding (Two-Tier)**: Tier 1 high-speed Tesseract TSV OCR bounding boxes (~300ms, 0 tokens) for textual UI targets; Tier 2 Gemini CLI spatial grounding for visual/color/icon attributes.
- **Natural Virtual Input**: Subtle cadence typing via `wtype` and smooth cubic ease-out mouse gliding via Hyprland IPC.
- **App Indexer**: Instant sub-2ms XDG desktop file parser and launcher (`~/.local/share/applications`, `/usr/share/applications`, flatpaks).
- **System Control & Telemetry**: Instant non-LLM telemetry for top CPU/memory processes, battery, disk space, RAM, IP, and power actions (shutdown, reboot, suspend, lock, logout).
- **IPC Server**: Local Unix socket at `$XDG_RUNTIME_DIR/jarvis/ipc.sock`.
- **Omarchy Shell Plugin**: Quickshell QML plugin (`Service.qml`, `BarWidget.qml`, `HudOverlay.qml`) registered in `~/.config/omarchy/plugins/eddie.jarvis`.
- **HUD & Soundscape**: Non-blocking layer-shell Arc-Reactor overlay with audio-reactive visualizer and 48kHz acoustic earcons (`pw-play`).

## CLI Usage

```bash
# Push-to-talk controls (also triggered natively by holding SUPER + SHIFT + J)
omarchy-jarvis record-start
omarchy-jarvis record-stop

# Proactive awareness telemetry and alert testing
omarchy-jarvis awareness
omarchy-jarvis alert "Sir, all systems operating within normal parameters."

# Toggle recording manually

# Direct command execution (reflex or System 2)
omarchy-jarvis exec "switch to workspace 3"
omarchy-jarvis exec "pause music"
omarchy-jarvis exec "top 3 processes by cpu"
omarchy-jarvis exec "click on Omarchy"
omarchy-jarvis exec "open ghostty"
omarchy-jarvis exec "close ghostty"
omarchy-jarvis exec "Jarvis, what window do I currently have open?"

# Visual UI Element Grounding & Auto-Click
omarchy-jarvis click "Omarchy"          # OCR text search -> ease-out glide -> click
omarchy-jarvis click "red button"       # Multimodal visual spatial search -> click
omarchy-jarvis click 500 500            # Direct coordinate click

# Fast Non-LLM Reflex Telemetry & Control
omarchy-jarvis apps                     # List indexed desktop apps
omarchy-jarvis top [--by cpu|memory]    # Instant top resource consumers (<10ms)
omarchy-jarvis close <app_name>         # Gracefully close window/app
omarchy-jarvis system <action>          # battery | disk | ram | ip | time | uptime | temp | shutdown | reboot | suspend | lock
omarchy-jarvis clipboard [read|clear]   # Wayland clipboard operations

# Smart App Switching & Compound Commands
omarchy-jarvis exec "open spotify"                   # Switches workspace & focuses if open, launches if not
omarchy-jarvis exec "where is discord"               # Reports workspace & focuses window
omarchy-jarvis exec "open spotify on workspace 4"    # Moves or launches app onto target workspace
omarchy-jarvis exec "switch to workspace 2 and open ghostty" # Compound reflex chain (<50ms)
omarchy-jarvis exec "system uptime and current workspace"    # Compound telemetry chain

# Extended Deterministic Controls
omarchy-jarvis exec "focus left"        # Directional navigation (left/right/up/down)
omarchy-jarvis exec "toggle scratchpad" # Special scratchpad workspace
omarchy-jarvis exec "what song is this" # D-Bus MPRIS query
omarchy-jarvis exec "toggle wifi"       # NetworkManager radio
omarchy-jarvis exec "toggle bluetooth"  # Bluetooth controller
omarchy-jarvis exec "toggle dnd"        # Notification silencing
omarchy-jarvis exec "stay awake"        # Wayland idle inhibitor
omarchy-jarvis exec "open downloads"    # Directory shortcut in file manager

# Deliberative System 2 reasoning with spoken reply
omarchy-jarvis ask "Summarize my active workspace"

# Multimodal screen inspection & vision
omarchy-jarvis see "What is currently shown on my screen?"
omarchy-jarvis screenshot [--window]

# Natural virtual input execution (subtle delays)
omarchy-jarvis move 500 500
omarchy-jarvis type "Hello from Jarvis"

# Neural speech synthesis (Kokoro-82M)
omarchy-jarvis speak "Systems online and fully operational, sir."
omarchy-jarvis voices

# Soundscape earcons & HUD visualizer demo
omarchy-jarvis sound [listening|success|deliberate|error]
omarchy-jarvis hud

# Evaluate Laya decision model over warm daemon
omarchy-jarvis classify "switch to workspace 2"

# Check daemon status
omarchy-jarvis status
```

## Adding New Reflex Commands

Reflex commands are implemented in `core/dispatcher.py`:
1. Add regex or substring pattern matching.
2. Direct to `self.hypr.*`, `self.system.*`, `self.apps.*`, `self.visual.*`, or `self.media.*`.
3. Add corresponding unit test in `tests/test_extended_dispatcher.py`, `tests/test_smart_app_switcher.py`, or `tests/test_compound_commands.py`.
4. Run tests: `.venv/bin/python3 -m unittest discover -s tests`.


