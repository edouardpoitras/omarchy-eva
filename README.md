# Omarchy Eva Voice Automation Suite

`omarchy.eva` is a real-time, voice-driven automation and task execution engine designed for Omarchy Linux and the Hyprland Wayland compositor.

## Features

- **Sub-150ms Reflex Dispatch (System 1)**: Sub-millisecond direct Unix socket IPC to Hyprland compositor and D-Bus MPRIS / PipeWire audio.
- **Voxtype ASR Integration**: Seamlessly captures voice via Omarchy's native `voxtype` Whisper ONNX service.
- **Push-to-Talk Keybinding**: Configured to `SUPER + SHIFT + J` (press & hold to speak, release to execute).
- **Omarchy Shell Plugin**: Quickshell QML plugin (`BarWidget.qml`, `Service.qml`, `HudOverlay.qml`) displaying an animated Arc Reactor indicator and right-click quick actions menu in the Omarchy top bar.
- **Selective Spoken Feedback**: Silent for visual desktop actions (moving windows, switching workspaces, launching apps), audio feedback for questions, queries, alerts, and errors. Configurable via `omarchy-eva config`.
- **Conversational Context & Pronoun Memory**: Natural multi-turn pronoun tracking (`"move spotify to workspace 3"` -> `"now close it"`).
- **Proactive Awareness Sentinel**: Background monitoring for CPU pressure, memory starvation, disk space, network drops, and critical systemd errors.
- **Central Capabilities Knowledge Base**: Dynamic single source of truth for identity (`who are you`) and capabilities (`what can you do`).
- **CLI Utility**: `omarchy-eva` for trigger control, configuration, status monitoring, and direct execution testing.

## CLI Usage

```bash
# Push-to-talk controls (also triggered by holding SUPER + SHIFT + J)
omarchy-eva record-start
omarchy-eva record-stop

# Configuration management
omarchy-eva config show
omarchy-eva config set verbosity minimal     # minimal | verbose | silent
omarchy-eva config set voice bf_emma         # British female default
omarchy-eva config set earcon_volume 0.25    # Subtle audio chimes

# Identity & Capabilities
omarchy-eva info
omarchy-eva capabilities
omarchy-eva capabilities audio

# Direct command execution
omarchy-eva exec "switch to workspace 3"
omarchy-eva exec "pause music"
omarchy-eva exec "set volume to 80 percent"
omarchy-eva exec "mute mic"
omarchy-eva exec "open spotify"
omarchy-eva exec "now close it"

# Check daemon status
omarchy-eva status
```

## Running Unit Tests

```bash
.venv/bin/python3 -m unittest discover -s tests -p 'test_*.py'
```
