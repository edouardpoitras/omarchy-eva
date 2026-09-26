---
name: omarchy-eva
description: >-
  Guide and reference for developing, running, and extending the Eva voice-enabled
  desktop automation suite on Omarchy Linux.
---

# Eva Voice Automation on Omarchy Linux

`omarchy.eva` is a real-time, voice-driven automation and task execution suite designed for Omarchy Linux and Hyprland.

## Architecture

- **ASR & Audio**: Voxtype daemon (Whisper ONNX / PipeWire audio).
- **Trigger**: Push-to-Talk via `SUPER + SHIFT + J` (press & hold to speak, release to execute, configured in `~/.config/hypr/bindings.lua`).
- **Reflex Dispatcher (System 1)**: Sub-millisecond direct Unix socket client for Hyprland IPC (`$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket.sock`) and D-Bus MPRIS.
- **Decision Engine (Laya)**: Non-autoregressive ModernBERT ONNX decision classifier (~25ms).
- **Proactive Awareness Engine**: Background sentinel monitoring CPU pressure, RAM starvation, low disk space, network drops/reconnections, systemd journal anomalies, and weather alerts with autonomous spoken warnings and HUD notifications.
- **Deliberative Reasoning (System 2)**: Omarchy agent CLI bridge (`gemini`, `claude`, `codex`) with live desktop telemetry and multi-turn voice clarification.
- **Neural TTS (Kokoro-82M)**: Sub-35ms local voice synthesis (British female `bf_emma` Eva voice) piped to PipeWire (`pw-play`).
- **Screen Perception**: Sub-35ms framebuffer capture via `grim` into memory/JPEG.
- **Visual Grounding (Two-Tier)**: Tier 1 high-speed Tesseract TSV OCR bounding boxes (~300ms, 0 tokens) for textual UI targets; Tier 2 Gemini CLI spatial grounding for visual/color/icon attributes.
- **Natural Virtual Input**: Subtle cadence typing via `wtype` and smooth cubic ease-out mouse gliding via Hyprland IPC.
- **App Indexer**: Instant sub-2ms XDG desktop file parser and launcher (`~/.local/share/applications`, `/usr/share/applications`, flatpaks).
- **System Control & Telemetry**: Instant non-LLM telemetry for top CPU/memory processes, battery, disk space, RAM, IP, and power actions (shutdown, reboot, suspend, lock, logout).
- **Context Memory & Pronouns**: Multi-turn antecedent tracking (`last_app`, `last_workspace`, `last_window_class`) enabling natural pronoun chaining (`"move spotify to workspace 3"` -> `"now close it"`).
- **Configurable Behavior**: `~/.config/eva/config.json` managing voice, verbosity (`minimal`, `verbose`, `silent`), sound effects, earcon volume, and HUD display.
- **IPC Server**: Local Unix socket at `$XDG_RUNTIME_DIR/eva/ipc.sock`.
- **Omarchy Shell Plugin**: Quickshell QML plugin (`Service.qml`, `BarWidget.qml`, `HudOverlay.qml`) registered in `~/.config/omarchy/plugins/eddie.eva`.
- **HUD & Soundscape**: Non-blocking layer-shell overlay with audio-reactive visualizer and 48kHz acoustic earcons (`pw-play`).

## CLI Usage

```bash
# Push-to-talk controls (also triggered natively by holding SUPER + SHIFT + J)
omarchy-eva record-start
omarchy-eva record-stop

# Configuration management
omarchy-eva config show
omarchy-eva config get verbosity
omarchy-eva config set verbosity minimal     # minimal | verbose | silent
omarchy-eva config set voice bf_emma         # British female default
omarchy-eva config set earcon_volume 0.25    # Subtle audio chimes

# Identity & Capabilities Knowledge Base (Central Single Source of Truth)
omarchy-eva info                     # Show Eva identity, persona, and architecture
omarchy-eva capabilities             # Matrix of all active domains and registered grammar counts
omarchy-eva capabilities <domain>    # Deep drill-down (audio, windows, hardware, system, vision...)

# Proactive awareness telemetry and alert testing
omarchy-eva awareness
omarchy-eva alert "All systems operating within normal parameters."

# Direct command execution (reflex or System 2)
omarchy-eva exec "who are you"                  # Identity overview (<30ms reflex)
omarchy-eva exec "what can you do"              # Capabilities overview (<30ms reflex)
omarchy-eva exec "what can you do with audio"   # Domain drill-down (<30ms reflex)
omarchy-eva exec "switch to workspace 3"
omarchy-eva exec "pause music"
omarchy-eva exec "top 3 processes by cpu"
omarchy-eva exec "click on Omarchy"
omarchy-eva exec "open ghostty"
omarchy-eva exec "close ghostty"
omarchy-eva exec "what window do I currently have open?"

# Visual UI Element Grounding & Auto-Click
omarchy-eva click "Omarchy"          # OCR text search -> ease-out glide -> click
omarchy-eva click "red button"       # Multimodal visual spatial search -> click
omarchy-eva click 500 500            # Direct coordinate click

# Fast Non-LLM Reflex Telemetry & Control
omarchy-eva apps                     # List indexed desktop apps
omarchy-eva move-window [app] <ws>   # Move active window or app to target workspace (e.g. 2, another, next)
omarchy-eva close <app_name>         # Gracefully close window/app
omarchy-eva system <action>          # battery | disk | ram | ip | time | uptime | temp | shutdown | reboot | suspend | lock
omarchy-eva clipboard [read|clear]   # Wayland clipboard operations
omarchy-eva audio [output|input|list] [dev] # Switch audio sinks or microphones (<60ms)
omarchy-eva wifi [list|connect|disconnect]  # Scan nearby networks and connect (<10ms)
omarchy-eva bluetooth [list|connect|disc]   # Manage Bluetooth device connections
omarchy-eva brightness [level|up|down]      # Query or adjust screen brightness
omarchy-eva display [list|scale]            # Inspect monitors or configure display scale

# Smart App Switching & Compound Commands
omarchy-eva exec "open spotify"                   # Switches workspace & focuses if open, launches if not
omarchy-eva exec "where is discord"               # Reports workspace & focuses window
omarchy-eva exec "move an open window to another workspace" # Moves active window to next active workspace
omarchy-eva exec "move this window to workspace 2" # Moves active window to workspace 2
omarchy-eva exec "move spotify to another workspace" # Moves specific open app to alternate workspace
omarchy-eva exec "open spotify on workspace 4"    # Moves or launches app onto target workspace
omarchy-eva exec "switch to workspace 2 and open ghostty" # Compound reflex chain (<50ms)
omarchy-eva exec "system uptime and current workspace"    # Compound telemetry chain
omarchy-eva exec "switch audio output to headset and dim screen" # Compound device chain

# Conversational Context & Pronouns
omarchy-eva exec "move spotify to workspace 3"
omarchy-eva exec "now close it"                   # Automatically resolves to "close spotify"

# Hardware & Device Voice Routing (System 1)
omarchy-eva exec "switch audio output device to headset" # PipeWire default sink switch
omarchy-eva exec "switch audio output to speakers"       # Switch sink to speakers
omarchy-eva exec "switch microphone to headset"          # PipeWire default source switch
omarchy-eva exec "list audio devices"                    # List active audio sinks & mics
omarchy-eva exec "list wifi networks"                    # Scan nearby Wi-Fi SSIDs
omarchy-eva exec "connect to wifi Baxter"                # Connect to specified network
omarchy-eva exec "wifi status"                           # Check active Wi-Fi connection
omarchy-eva exec "list bluetooth devices"                # Enumerate paired Bluetooth devices
omarchy-eva exec "set brightness to 70%"                 # Hardware display brightness
omarchy-eva exec "dim screen"                            # Lower brightness by 10%
omarchy-eva exec "list displays"                         # Hyprland monitor inspection

# Extended Deterministic Controls
omarchy-eva exec "focus left"        # Directional navigation (left/right/up/down)
omarchy-eva exec "toggle scratchpad" # Special scratchpad workspace
omarchy-eva exec "what song is this" # D-Bus MPRIS query
omarchy-eva exec "toggle wifi"       # NetworkManager radio
omarchy-eva exec "toggle bluetooth"  # Bluetooth controller
omarchy-eva exec "toggle dnd"        # Notification silencing
omarchy-eva exec "stay awake"        # Wayland idle inhibitor
omarchy-eva exec "open downloads"    # Directory shortcut in file manager

# Deliberative System 2 reasoning with spoken reply
omarchy-eva ask "Summarize my active workspace"

# Multimodal screen inspection & vision
omarchy-eva see "What is currently shown on my screen?"
omarchy-eva screenshot [--window]

# Natural virtual input execution (subtle delays)
omarchy-eva move 500 500
omarchy-eva type "Hello from Eva"

# Neural speech synthesis (Kokoro-82M)
omarchy-eva speak "Systems online and fully operational."
omarchy-eva voices

# Soundscape earcons & HUD visualizer demo
omarchy-eva sound [listening|success|deliberate|error]
omarchy-eva hud

# Evaluate Laya decision model over warm daemon
omarchy-eva classify "switch to workspace 2"

# Check daemon status
omarchy-eva status
```

## Adding New Reflex Commands

Reflex commands are implemented in `core/dispatcher.py`:
1. Add regex or substring pattern matching.
2. Direct to `self.hypr.*`, `self.system.*`, `self.apps.*`, `self.visual.*`, or `self.media.*`.
3. Add corresponding unit test in `tests/test_extended_dispatcher.py`, `tests/test_smart_app_switcher.py`, or `tests/test_compound_commands.py`.
4. Run tests: `.venv/bin/python3 -m unittest discover -s tests`.
