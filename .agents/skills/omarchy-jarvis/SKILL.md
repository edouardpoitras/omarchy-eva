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
- **Decision Engine (Laya)**: Non-autoregressive ModernBERT ONNX decision classifier (~25ms).
- **Deliberative Reasoning (System 2)**: Omarchy agent CLI bridge (`gemini`, `claude`, `codex`) with live desktop telemetry and multi-turn voice clarification.
- **Neural TTS (Kokoro-82M)**: Sub-35ms local voice synthesis (`bm_george` Jarvis voice) piped to PipeWire (`pw-play`).
- **IPC Server**: Local Unix socket at `$XDG_RUNTIME_DIR/jarvis/ipc.sock`.
- **Omarchy Shell Plugin**: Quickshell QML plugin (`Service.qml`, `BarWidget.qml`) in `~/.config/omarchy/plugins/omarchy.jarvis`.

## CLI Usage

```bash
# Toggle recording (same as hotkey)
omarchy-jarvis trigger

# Push-to-talk controls
omarchy-jarvis record-start
omarchy-jarvis record-stop

# Direct command execution (reflex or System 2)
omarchy-jarvis exec "switch to workspace 3"
omarchy-jarvis exec "pause music"
omarchy-jarvis exec "Jarvis, what window do I currently have open?"

# Deliberative System 2 reasoning with spoken reply
omarchy-jarvis ask "Summarize my active workspace"

# Neural speech synthesis
omarchy-jarvis speak "Systems online and fully operational, sir."
omarchy-jarvis voices

# Evaluate Laya decision model over warm daemon
omarchy-jarvis classify "switch to workspace 2"

# Check daemon status
omarchy-jarvis status
```

## Adding New Reflex Commands

Reflex commands are implemented in `core/dispatcher.py`:
1. Add regex or substring pattern matching.
2. Direct to `self.hypr.dispatch(...)` or `self.media.*` or shell launcher.
3. Add corresponding unit test in `tests/test_core_dispatch.py`.
4. Run tests: `python3 -m unittest discover tests`.
