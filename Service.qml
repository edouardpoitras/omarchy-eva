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
  property string jarvisState: "idle" // "idle", "listening", "transcribing", "executing", "error"
  property string lastCommand: ""
  property string lastAction: ""
  property real latencyMs: 0.0

  readonly property string runtimeDir: Quickshell.env("XDG_RUNTIME_DIR") || ("/run/user/" + (Quickshell.env("UID") || "1000"))
  readonly property string voxtypeStatePath: runtimeDir + "/voxtype/state"
  readonly property string jarvisSocketPath: runtimeDir + "/jarvis/ipc.sock"

  // Watch Voxtype daemon state
  FileView {
    id: voxtypeWatcher
    path: root.voxtypeStatePath
    watchChanges: true
    printErrors: false

    onLoaded: updateFromVoxtype()
    onFileChanged: reload()
    onLoadFailed: {
      if (root.jarvisState !== "idle") root.jarvisState = "idle"
    }
  }

  function updateFromVoxtype() {
    var raw = (voxtypeWatcher.text() || "").trim().toLowerCase()
    if (raw === "recording") {
      root.jarvisState = "listening"
    } else if (raw === "transcribing") {
      root.jarvisState = "transcribing"
    } else if (raw === "idle") {
      if (root.jarvisState === "transcribing" || root.jarvisState === "listening") {
        root.jarvisState = "executing"
        pollStatusTimer.restart()
      }
    }
  }

  // Poll status after execution to capture recognized command and latency
  Timer {
    id: pollStatusTimer
    interval: 150
    repeat: false
    onTriggered: {
      statusProcess.command = [root.pluginRoot + "/bin/omarchy-jarvis", "status"]
      statusProcess.running = true
    }
  }

  // Reset executing state back to idle after display flash
  Timer {
    id: resetExecutingTimer
    interval: 2500
    repeat: false
    onTriggered: {
      if (root.jarvisState === "executing") {
        root.jarvisState = "idle"
      }
    }
  }

  // Process to trigger voice recording
  Process {
    id: triggerProcess
    stdout: StdioCollector { id: triggerOut; waitForEnd: true }
    stderr: StdioCollector { id: triggerErr; waitForEnd: true }
  }

  // Process to query daemon status
  Process {
    id: statusProcess
    stdout: StdioCollector {
      id: statusOut
      waitForEnd: true
      onTextCollected: {
        var txt = statusOut.text || ""
        var lines = txt.split("\n")
        for (var i = 0; i < lines.length; i++) {
          var l = lines[i].trim()
          if (l.startsWith("Last Command:")) {
            root.lastCommand = l.substring(13).trim()
          } else if (l.startsWith("Last Action:")) {
            root.lastAction = l.substring(12).trim()
          }
        }
        resetExecutingTimer.restart()
      }
    }
  }

  // Public action callable from BarWidget or keybindings
  function trigger() {
    triggerProcess.command = [root.pluginRoot + "/bin/omarchy-jarvis", "trigger"]
    triggerProcess.running = true
  }

  // Ensure daemon is started when shell loads
  Process {
    id: daemonLauncher
    command: [root.pluginRoot + "/bin/omarchy-jarvis-daemon"]
    running: true
  }
}
