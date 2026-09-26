import QtQuick
import Quickshell
import qs.Ui
import qs.Commons

BarWidget {
  id: root
  moduleName: "eddie.eva"

  readonly property var evaService: bar && bar.shell
      ? bar.shell.serviceFor(moduleName)
      : null

  readonly property string currentState: evaService ? evaService.evaState : "idle"
  readonly property string lastCommand: evaService ? evaService.lastCommand : ""
  readonly property string lastAction: evaService ? evaService.lastAction : ""

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

  readonly property string tooltipMessage: {
    if (lastCommand) {
      return "Eva Voice AI (" + currentState + ")\nLast: \"" + lastCommand + "\"\n(Left: Speak, Right: Menu)"
    }
    return "Eva Voice AI (" + currentState + ")\nLeft: Speak (SUPER+SHIFT+E / J)\nRight: Menu"
  }

  visible: true
  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  // Standard Omarchy Bar Button Integration
  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    slotSize: Style.bar.statusSlot
    active: root.currentState !== "idle"
    activeColor: root.stateColor
    useActiveColor: true
    tooltipText: root.tooltipMessage

    // Holographic Arc-Reactor Glyph & State Animation
    iconComponent: Component {
      Item {
        anchors.fill: parent

        // Outer pulsing ring when listening / transcribing / executing
        Rectangle {
          id: pulseRing
          anchors.centerIn: parent
          width: parent.width * 0.85
          height: width
          radius: width / 2
          color: "transparent"
          border.color: root.stateColor
          border.width: root.currentState !== "idle" ? 1.5 : 1
          opacity: root.currentState === "listening" ? 1.0 : (root.currentState === "idle" ? 0.65 : 0.85)

          SequentialAnimation on scale {
            running: root.currentState === "listening" || root.currentState === "transcribing"
            loops: Animation.Infinite
            NumberAnimation { from: 0.85; to: 1.25; duration: 600; easing.type: Easing.InOutQuad }
            NumberAnimation { from: 1.25; to: 0.85; duration: 600; easing.type: Easing.InOutQuad }
          }
        }

        // Inner glowing core orb
        Rectangle {
          id: coreOrb
          anchors.centerIn: parent
          width: root.currentState !== "idle" ? parent.width * 0.35 : parent.width * 0.28
          height: width
          radius: width / 2
          color: root.stateColor

          SequentialAnimation on opacity {
            running: root.currentState !== "idle"
            loops: Animation.Infinite
            NumberAnimation { from: 0.6; to: 1.0; duration: 400; easing.type: Easing.InOutQuad }
            NumberAnimation { from: 1.0; to: 0.6; duration: 400; easing.type: Easing.InOutQuad }
          }
        }
      }
    }

    onPressed: function(b) {
      if (b === Qt.RightButton) {
        quickPopup.open = !quickPopup.open
      } else {
        if (root.evaService) root.evaService.trigger()
      }
    }
  }

  // Quick Actions Popup Menu (Right-Click)
  PopupCard {
    id: quickPopup
    anchorItem: button
    bar: root.bar
    contentWidth: 220
    contentHeight: actionColumn.implicitHeight + 24
    open: false

    Rectangle {
      anchors.fill: parent
      color: Qt.rgba(0.08, 0.10, 0.14, 0.96)
      radius: 12
      border.color: Qt.rgba(root.stateColor.r, root.stateColor.g, root.stateColor.b, 0.3)
      border.width: 1

      Column {
        id: actionColumn
        anchors.top: parent.top
        anchors.topMargin: 12
        anchors.left: parent.left
        anchors.leftMargin: 12
        anchors.right: parent.right
        anchors.rightMargin: 12
        spacing: 6

        // Title and Status
        Row {
          spacing: 8
          width: parent.width

          Rectangle {
            width: 8
            height: 8
            radius: 4
            color: root.stateColor
            anchors.verticalCenter: parent.verticalCenter
          }

          Text {
            text: "Eva Assistant (" + root.currentState + ")"
            font.family: root.barFont
            font.pixelSize: 12
            font.bold: true
            color: "#ffffff"
          }
        }

        Rectangle {
          width: parent.width
          height: 1
          color: Qt.rgba(1, 1, 1, 0.1)
        }

        // Action: Trigger
        Rectangle {
          width: parent.width
          height: 28
          radius: 6
          color: action1Mouse.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : "transparent"

          Row {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 8
            spacing: 8

            Text { text: "🎤"; font.pixelSize: 12 }
            Text {
              text: "Listen / Speak"
              font.family: root.barFont
              font.pixelSize: 11
              color: "#e0e0e0"
            }
          }

          MouseArea {
            id: action1Mouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
              quickPopup.open = false
              if (root.evaService) root.evaService.trigger()
            }
          }
        }

        // Action: Identity
        Rectangle {
          width: parent.width
          height: 28
          radius: 6
          color: action2Mouse.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : "transparent"

          Row {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 8
            spacing: 8

            Text { text: "ℹ️"; font.pixelSize: 12 }
            Text {
              text: "Who are you?"
              font.family: root.barFont
              font.pixelSize: 11
              color: "#e0e0e0"
            }
          }

          MouseArea {
            id: action2Mouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
              quickPopup.open = false
              if (root.evaService) root.evaService.executeQuery("who are you")
            }
          }
        }

        // Action: Capabilities
        Rectangle {
          width: parent.width
          height: 28
          radius: 6
          color: action3Mouse.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : "transparent"

          Row {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 8
            spacing: 8

            Text { text: "⚡"; font.pixelSize: 12 }
            Text {
              text: "What can you do?"
              font.family: root.barFont
              font.pixelSize: 11
              color: "#e0e0e0"
            }
          }

          MouseArea {
            id: action3Mouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
              quickPopup.open = false
              if (root.evaService) root.evaService.executeQuery("what can you do")
            }
          }
        }

        // Action: Restart Daemon
        Rectangle {
          width: parent.width
          height: 28
          radius: 6
          color: action4Mouse.containsMouse ? Qt.rgba(1, 1, 1, 0.12) : "transparent"

          Row {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.leftMargin: 8
            spacing: 8

            Text { text: "🔄"; font.pixelSize: 12 }
            Text {
              text: "Restart Daemon"
              font.family: root.barFont
              font.pixelSize: 11
              color: "#e0e0e0"
            }
          }

          MouseArea {
            id: action4Mouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
              quickPopup.open = false
              if (root.evaService) root.evaService.restartDaemon()
            }
          }
        }
      }
    }
  }
}
