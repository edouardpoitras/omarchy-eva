import QtQuick
import Quickshell
import Quickshell.Io

Item {
  id: root

  property string omarchyPath: ""
  property var shell: null
  property var manifest: null
  property var barWidgetRegistry: null
  property var pluginRegistry: null

  // Plugin directory resolution
  readonly property string pluginRoot: {
    var url = Qt.resolvedUrl(".").toString()
    if (url.startsWith("file://")) {
      url = url.substring(7)
    }
    if (url.endsWith("/")) {
      url = url.substring(0, url.length - 1)
    }
    return url
  }

  // Runtime state
  property string evaState: "idle" // "idle", "listening", "transcribing", "deliberating", "clarifying", "executing", "error"
  property string lastCommand: ""
  property string lastAction: ""
  property string intent: ""
  property real confidence: 1.0
  property string agentResponse: ""
  property real latencyMs: 0.0

  readonly property string runtimeDir: Quickshell.env("XDG_RUNTIME_DIR") || ("/run/user/" + (Quickshell.env("UID") || "1000"))
  readonly property string voxtypeStatePath: runtimeDir + "/voxtype/state"
  readonly property string evaStatePath: runtimeDir + "/eva/state.json"
  readonly property string evaSocketPath: runtimeDir + "/eva/ipc.sock"

  // Watch Eva daemon state file (atomic state updates from daemon)
  FileView {
    id: evaWatcher
    path: root.evaStatePath
    watchChanges: true
    printErrors: false

    onLoaded: updateFromEva()
    onFileChanged: reload()
    onLoadFailed: {
      // Retain existing state if temporarily locked
    }
  }

  function updateFromEva() {
    var raw = (evaWatcher.text() || "").trim()
    if (!raw) return
    try {
      var data = JSON.parse(raw)
      if (data.state) root.evaState = data.state
      if (data.command !== undefined) root.lastCommand = data.command
      if (data.action !== undefined) root.lastAction = data.action
      if (data.intent !== undefined) root.intent = data.intent
      if (data.confidence !== undefined) root.confidence = data.confidence
      if (data.response !== undefined) root.agentResponse = data.response
    } catch (e) {}
  }

  // Watch Voxtype daemon state for fallback
  FileView {
    id: voxtypeWatcher
    path: root.voxtypeStatePath
    watchChanges: true
    printErrors: false

    onLoaded: updateFromVoxtype()
    onFileChanged: reload()
    onLoadFailed: {
      if (root.evaState !== "idle" && !evaWatcher.exists) root.evaState = "idle"
    }
  }

  function updateFromVoxtype() {
    var raw = (voxtypeWatcher.text() || "").trim().toLowerCase()
    if (raw === "recording") {
      root.evaState = "listening"
    } else if (raw === "transcribing") {
      root.evaState = "transcribing"
    } else if (raw === "idle") {
      if (root.evaState === "transcribing" || root.evaState === "listening") {
        root.evaState = "executing"
      }
    }
  }

  // Safety reset timer if state remains active without update
  Timer {
    id: safetyIdleTimer
    interval: 8000
    repeat: false
    onTriggered: {
      if (root.evaState !== "idle") {
        root.evaState = "idle"
      }
    }
  }

  // Process to trigger voice recording
  Process {
    id: triggerProcess
  }

  // Public action callable from BarWidget or keybindings
  function trigger() {
    triggerProcess.command = [root.pluginRoot + "/bin/omarchy-eva", "trigger"]
    triggerProcess.running = true
  }

  // Process to execute commands directly
  Process {
    id: execProcess
  }

  function executeQuery(text) {
    execProcess.command = [root.pluginRoot + "/bin/omarchy-eva", "exec", text]
    execProcess.running = true
  }

  // Process to restart daemon
  Process {
    id: restartProcess
  }

  function restartDaemon() {
    restartProcess.command = ["bash", "-c", "pkill -f omarchy-eva-daemon || true; sleep 0.5; " + root.pluginRoot + "/bin/omarchy-eva-daemon &"]
    restartProcess.running = true
  }

  // Ensure daemon is started when shell loads
  Process {
    id: daemonLauncher
    command: [root.pluginRoot + "/bin/omarchy-eva-daemon"]
    running: true
  }

  // Floating Arc-Reactor HUD Overlay
  HudOverlay {
    id: hud
    evaState: root.evaState
    transcription: root.lastCommand
    intent: root.intent
    lastAction: root.lastAction
    confidence: root.confidence
    agentResponse: root.agentResponse
  }
}
