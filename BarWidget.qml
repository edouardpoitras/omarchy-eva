import QtQuick
import Quickshell
import qs.Ui
import qs.Commons

BarWidget {
  id: root
  moduleName: "omarchy.jarvis"

  readonly property var jarvisService: bar && bar.shell
      ? bar.shell.serviceFor(moduleName)
      : null

  readonly property string currentState: jarvisService ? jarvisService.jarvisState : "idle"
  readonly property string lastCommand: jarvisService ? jarvisService.lastCommand : ""
  readonly property string lastAction: jarvisService ? jarvisService.lastAction : ""

  readonly property color barFg: bar ? bar.foreground : Color.foreground
  readonly property string barFont: bar ? bar.fontFamily : "monospace"

  // Status colors
  readonly property color stateColor: {
    if (currentState === "listening") return "#00f0ff"    // Arc Reactor Cyan
    if (currentState === "transcribing") return "#ffaa00" // Amber
    if (currentState === "executing") return "#00ff88"    // Emerald
    if (currentState === "error") return "#ff3344"        // Crimson
    return barFg                                          // Default theme color
  }

  // Bar Widget layout container
  Rectangle {
    id: chip
    anchors.verticalCenter: parent.verticalCenter
    height: bar ? Math.min(bar.height - 6, 26) : 24
    width: labelText.visible ? contentRow.implicitWidth + 14 : height
    radius: height / 2
    color: currentState !== "idle" ? Qt.rgba(stateColor.r, stateColor.g, stateColor.b, 0.18) : "transparent"
    border.color: currentState !== "idle" ? stateColor : "transparent"
    border.width: 1

    Behavior on color { ColorAnimation { duration: 180 } }
    Behavior on border.color { ColorAnimation { duration: 180 } }

    Row {
      id: contentRow
      anchors.centerIn: parent
      spacing: 6

      // Animated Arc-Reactor / Voice glyph
      Item {
        id: iconContainer
        width: 16
        height: 16
        anchors.verticalCenter: parent.verticalCenter

        // Outer pulse ring when active
        Rectangle {
          id: pulseRing
          anchors.centerIn: parent
          width: 16
          height: 16
          radius: 8
          color: "transparent"
          border.color: root.stateColor
          border.width: 1.5
          opacity: currentState === "listening" ? 1.0 : 0.6

          SequentialAnimation on scale {
            running: currentState === "listening" || currentState === "transcribing"
            loops: Animation.Infinite
            NumberAnimation { from: 0.9; to: 1.25; duration: 600; easing.type: Easing.InOutQuad }
            NumberAnimation { from: 1.25; to: 0.9; duration: 600; easing.type: Easing.InOutQuad }
          }
        }

        // Inner glowing core
        Rectangle {
          anchors.centerIn: parent
          width: 6
          height: 6
          radius: 3
          color: root.stateColor
        }
      }

      // State label when active or executing
      Text {
        id: labelText
        anchors.verticalCenter: parent.verticalCenter
        visible: currentState !== "idle"
        font.family: root.barFont
        font.pixelSize: 11
        font.bold: true
        color: root.stateColor
        text: {
          if (currentState === "listening") return "Listening..."
          if (currentState === "transcribing") return "Processing..."
          if (currentState === "executing") return lastAction ? lastAction : "Executed"
          return ""
        }
      }
    }

    MouseArea {
      anchors.fill: parent
      cursorShape: Qt.PointingHandCursor
      hoverEnabled: true

      onClicked: function(mouse) {
        if (mouse.button === Qt.LeftButton) {
          if (jarvisService) jarvisService.trigger()
        }
      }
    }
  }

  // Tooltip
  ToolTip {
    id: tip
    visible: chipMouse.containsMouse
    text: {
      if (lastCommand) {
        return "Jarvis Voice AI\nLast: \"" + lastCommand + "\"\nAction: " + lastAction + "\n(SUPER + SHIFT + CTRL + X)"
      }
      return "Jarvis Voice AI (SUPER + SHIFT + CTRL + X)\nClick to speak"
    }
  }

  MouseArea {
    id: chipMouse
    anchors.fill: chip
    hoverEnabled: true
    acceptedButtons: Qt.NoButton
  }
}
