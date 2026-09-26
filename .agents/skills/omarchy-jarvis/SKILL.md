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
- **Trigger**: `SUPER + CTRL + SHIFT + X` (configured in `~/.config/hypr/bindings.lua`).
- **Reflex Dispatcher (System 1)**: Sub-millisecond direct Unix socket client for Hyprland IPC (`$XDG_RUNTIME_DIR/hypr/$HYPRLAND_INSTANCE_SIGNATURE/.socket.sock`) and D-Bus MPRIS.
- **IPC Server**: Local Unix socket at `$XDG_RUNTIME_DIR/jarvis/ipc.sock`.
- **Omarchy Shell Plugin**: Quickshell QML plugin (`Service.qml`, `BarWidget.qml`) in `~/.config/omarchy/plugins/omarchy.jarvis`.

## CLI Usage

```bash
# Toggle recording (same as hotkey)
omarchy-jarvis trigger

# Push-to-talk controls
omarchy-jarvis record-start
omarchy-jarvis record-stop

# Direct command execution test
omarchy-jarvis exec "switch to workspace 3"
omarchy-jarvis exec "pause music"
omarchy-jarvis exec "set volume to 75 percent"
omarchy-jarvis exec "mute mic"

# Check daemon status
omarchy-jarvis status
```

## Adding New Reflex Commands

Reflex commands are implemented in `core/dispatcher.py`:
1. Add regex or substring pattern matching.
2. Direct to `self.hypr.dispatch(...)` or `self.media.*` or shell launcher.
3. Add corresponding unit test in `tests/test_core_dispatch.py`.
4. Run tests: `python3 -m unittest discover tests`.
