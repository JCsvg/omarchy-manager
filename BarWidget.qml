import QtQuick
import Quickshell
import qs.Ui

// Ícone na barra que abre a TUI do Omarchy Manager em um terminal.
// O comando vai em lista para o execDetached: nada passa por um shell.
BarWidget {
  id: root
  moduleName: "io.github.jcsvg.omarchy-manager"

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  readonly property string launcher:
    Quickshell.env("HOME") + "/.config/omarchy/plugins/io.github.jcsvg.omarchy-manager/bin/omarchy-manager"

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: "󰒓"
    tooltipText: "Omarchy Manager"
    onPressed: function(b) {
      Quickshell.execDetached(["omarchy-launch-tui", root.launcher])
    }
  }
}
