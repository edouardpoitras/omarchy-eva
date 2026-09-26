# Omarchy Jarvis Voice Automation Suite

`omarchy.jarvis` is a real-time, voice-driven automation and task execution engine designed for Omarchy Linux and the Hyprland Wayland compositor.

## Features

- **Sub-150ms Reflex Dispatch (System 1)**: Sub-millisecond direct Unix socket IPC to Hyprland compositor and D-Bus MPRIS / PipeWire audio.
- **Voxtype ASR Integration**: Seamlessly captures voice via Omarchy's native `voxtype` Whisper ONNX service.
- **Dedicated Keybinding**: Configured to `SUPER + CTRL + SHIFT + X`.
- **Omarchy Shell Plugin**: Quickshell QML plugin (`BarWidget.qml`, `Service.qml`) displaying an animated Arc Reactor indicator in the Omarchy top bar.
- **CLI Utility**: `omarchy-jarvis` for trigger control, status monitoring, and direct execution testing.

## CLI Usage

```bash
# Toggle voice recording (same as hotkey)
omarchy-jarvis trigger

# Push-to-talk controls
omarchy-jarvis record-start
omarchy-jarvis record-stop

# Execute command directly
omarchy-jarvis exec "switch to workspace 3"
omarchy-jarvis exec "pause music"
omarchy-jarvis exec "set volume to 80 percent"
omarchy-jarvis exec "mute mic"

# Check daemon status
omarchy-jarvis status
```

## Running Unit Tests

```bash
python3 -m unittest discover tests
```
