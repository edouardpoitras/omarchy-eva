import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons

PanelWindow {
  id: root

  property string evaState: "idle" // "idle", "listening", "transcribing", "deliberating", "executing", "clarifying", "error"
  property string transcription: ""
  property string intent: ""
  property string lastAction: ""
  property real confidence: 1.0
  property string agentResponse: ""

  readonly property bool isHudActive: evaState !== "idle"

  // Status Theme Colors
  readonly property color stateColor: {
    if (evaState === "listening" || evaState === "recording") return "#00f0ff"    // Arc-Reactor Cyan
    if (evaState === "transcribing") return "#ffaa00" // Amber
    if (evaState === "deliberating") return "#b366ff" // Purple Resonance
    if (evaState === "clarifying") return "#00c3ff"   // Blue Dialog
    if (evaState === "executing") return "#00ff88"    // Emerald
    if (evaState === "alert") return "#ff9900"        // Warning Amber / Gold
    if (evaState === "error") return "#ff3344"        // Crimson
    return "#00f0ff"
  }

  anchors { top: true; bottom: true; left: true; right: true }
  color: "transparent"
  visible: card.opacity > 0.01

  WlrLayershell.namespace: "omarchy-eva-hud"
  WlrLayershell.layer: WlrLayer.Overlay
  WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
  exclusionMode: ExclusionMode.Ignore
  mask: Region {} // Visual-only surface: never blocks clicks to the desktop below

  // Floating HUD Glass Card
  Rectangle {
    id: card
    anchors.horizontalCenter: parent.horizontalCenter
    anchors.bottom: parent.bottom
    anchors.bottomMargin: 85
    width: Math.max(460, contentRow.implicitWidth + 48)
    height: 74
    radius: 20

    color: Qt.rgba(0.04, 0.06, 0.09, 0.92)
    border.color: root.stateColor
    border.width: 1.5

    opacity: root.isHudActive ? 1.0 : 0.0
    scale: root.isHudActive ? 1.0 : 0.94

    Behavior on opacity { NumberAnimation { duration: root.isHudActive ? 150 : 350; easing.type: Easing.OutQuad } }
    Behavior on scale { NumberAnimation { duration: root.isHudActive ? 200 : 350; easing.type: Easing.OutBack } }
    Behavior on border.color { ColorAnimation { duration: 200 } }

    // Outer subtle cyan/amber glow halo
    Rectangle {
      anchors.fill: parent
      anchors.margins: -4
      radius: parent.radius + 4
      color: "transparent"
      border.color: Qt.rgba(root.stateColor.r, root.stateColor.g, root.stateColor.b, 0.25)
      border.width: 2
      z: -1
    }

    Row {
      id: contentRow
      anchors.verticalCenter: parent.verticalCenter
      anchors.left: parent.left
      anchors.leftMargin: 20
      spacing: 18

      // Arc-Reactor Holographic Core
      Item {
        id: arcReactor
        width: 44
        height: 44
        anchors.verticalCenter: parent.verticalCenter

        // Rotating stator tick marks
        Repeater {
          model: 8
          Rectangle {
            id: statorTick
            width: 2
            height: 5
            radius: 1
            color: root.stateColor
            opacity: 0.75
            x: 22 - width / 2 + 18 * Math.cos(index * Math.PI / 4)
            y: 22 - height / 2 + 18 * Math.sin(index * Math.PI / 4)
            transformOrigin: Item.Center
            rotation: index * 45
          }
        }

        // Outer pulsing energy ring
        Rectangle {
          id: outerRing
          anchors.centerIn: parent
          width: 32
          height: 32
          radius: 16
          color: "transparent"
          border.color: root.stateColor
          border.width: 1.5
          opacity: 0.9

          SequentialAnimation on scale {
            running: root.isHudActive
            loops: Animation.Infinite
            NumberAnimation { from: 0.92; to: 1.15; duration: 550; easing.type: Easing.InOutSine }
            NumberAnimation { from: 1.15; to: 0.92; duration: 550; easing.type: Easing.InOutSine }
          }
        }

        // Inner glowing core orb
        Rectangle {
          id: coreOrb
          anchors.centerIn: parent
          width: 14
          height: 14
          radius: 7
          color: root.stateColor

          // Core intensity pulse
          SequentialAnimation on opacity {
            running: root.isHudActive
            loops: Animation.Infinite
            NumberAnimation { from: 0.7; to: 1.0; duration: 400; easing.type: Easing.InOutQuad }
            NumberAnimation { from: 1.0; to: 0.7; duration: 400; easing.type: Easing.InOutQuad }
          }
        }
      }

      // Middle: State Title & Recognized Speech Text
      Column {
        anchors.verticalCenter: parent.verticalCenter
        spacing: 3
        width: 260

        Row {
          spacing: 8
          Text {
            text: {
              if (root.evaState === "listening" || root.evaState === "recording") return "EVA // LISTENING"
              if (root.evaState === "transcribing") return "EVA // TRANSCRIBING"
              if (root.evaState === "deliberating") return "EVA // DELIBERATING"
              if (root.evaState === "clarifying") return "EVA // CLARIFYING"
              if (root.evaState === "executing") return "EVA // EXECUTING"
              if (root.evaState === "alert") return "EVA // SYSTEM ALERT"
              if (root.evaState === "error") return "EVA // ERROR"
              return "EVA"
            }
            font.family: "monospace"
            font.pixelSize: 10
            font.bold: true
            font.letterSpacing: 1.2
            color: root.stateColor
          }

          // Intent & Confidence Badge
          Rectangle {
            visible: root.intent !== "" && (root.evaState === "executing" || root.evaState === "idle" || root.evaState === "alert")
            height: 14
            width: badgeText.implicitWidth + 8
            radius: 4
            color: Qt.rgba(root.stateColor.r, root.stateColor.g, root.stateColor.b, 0.2)
            border.color: root.stateColor
            border.width: 1

            Text {
              id: badgeText
              anchors.centerIn: parent
              text: root.intent + (root.confidence < 1.0 ? " " + Math.round(root.confidence * 100) + "%" : "")
              font.family: "monospace"
              font.pixelSize: 9
              font.bold: true
              color: root.stateColor
            }
          }
        }

        // Live transcript or action text
        Text {
          width: parent.width
          elide: Text.ElideRight
          text: {
            if (root.evaState === "listening" || root.evaState === "recording") return "Listening to speech..."
            if (root.evaState === "transcribing") return "Analyzing audio waveform..."
            if (root.evaState === "deliberating") return root.transcription || "Synthesizing answer..."
            if (root.evaState === "alert") return root.lastCommand || "System warning detected"
            if (root.transcription) return "\"" + root.transcription + "\""
            if (root.lastAction) return root.lastAction
            return "Systems operational"
          }
          font.family: "sans-serif"
          font.pixelSize: 13
          font.bold: true
          color: "#ffffff"
        }
      }

      // Audio-Reactive Waveform Visualizer
      Row {
        id: waveRow
        anchors.verticalCenter: parent.verticalCenter
        spacing: 3
        height: 28

        Repeater {
          model: 12
          Rectangle {
            id: waveBar
            width: 3
            radius: 1.5
            color: root.stateColor
            anchors.verticalCenter: parent.verticalCenter

            // Dynamic oscillating height based on sinusoids when listening/speaking/alerting
            property real phaseOffset: index * 0.45
            property real activeMultiplier: (root.evaState === "listening" || root.evaState === "recording" || root.evaState === "deliberating" || root.evaState === "alert") ? 1.0 : 0.25

            height: root.isHudActive ? Math.max(4, 24 * activeMultiplier * (0.4 + 0.6 * Math.abs(Math.sin(waveTimer.tick + phaseOffset)))) : 4

            Behavior on height { NumberAnimation { duration: 60 } }
          }
        }
      }
    }
  }

  // Animation oscillator timer for live wave motion
  Timer {
    id: waveTimer
    interval: 50
    running: root.isHudActive
    repeat: true
    property real tick: 0.0
    onTriggered: {
      tick += 0.25
    }
  }
}
