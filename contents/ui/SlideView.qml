// SPDX-License-Identifier: MIT
import QtQuick
import org.kde.kwin 3.0 as KWin

Item {
    id: view
    required property QtObject controller
    property QtObject screen: KWin.SceneView.screen
    readonly property var gesture: controller.activeGesture
    readonly property bool moving: gesture && gesture.output === screen
    readonly property QtObject currentDesktop: KWin.Workspace.currentDesktopForScreen(screen)
    clip: true
    focus: true

    Loader {
        anchors.fill: parent
        active: !view.moving
        sourceComponent: DesktopPage {
            desktop: view.currentDesktop
            screen: view.screen
            layerMode: "all"
        }
    }
    Loader {
        anchors.fill: parent
        active: view.moving
        sourceComponent: Item {
            DesktopPage {
                width: view.width
                height: view.height
                desktop: view.gesture.origin
                screen: view.screen
                x: -view.gesture.step * controller.progress * view.width
            }
            DesktopPage {
                width: view.width
                height: view.height
                desktop: view.gesture.target
                screen: view.screen
                x: view.gesture.step * (1 - controller.progress) * view.width
                visible: view.gesture.target !== view.gesture.origin
            }
            DesktopPage {
                anchors.fill: parent
                desktop: view.gesture.origin
                screen: view.screen
                layerMode: "fixed"
            }
        }
    }
    Keys.onEscapePressed: controller.abort()
}
