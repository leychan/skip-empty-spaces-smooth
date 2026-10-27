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
            readonly property real stride: view.width + controller.horizontalGap
            Rectangle {
                anchors.fill: parent
                color: "black"
            }
            KWin.DesktopBackground {
                anchors.fill: parent
                output: view.screen
                desktop: view.gesture.origin
                activity: KWin.Workspace.currentActivity
                visible: !controller.slideBackground
            }
            DesktopPage {
                width: view.width
                height: view.height
                desktop: view.gesture.origin
                screen: view.screen
                showWallpaper: controller.slideBackground
                x: -view.gesture.step * controller.progress * parent.stride
            }
            DesktopPage {
                width: view.width
                height: view.height
                desktop: view.gesture.target
                screen: view.screen
                showWallpaper: controller.slideBackground
                x: view.gesture.step * (1 - controller.progress) * parent.stride
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

    Connections {
        target: view.Window.window
        function onAfterAnimating() {
            if (view.moving) controller.advanceFrame(Date.now());
        }
        function onAfterRendering() {
            // Request the next compositor frame on this output only. The
            // passive screen keeps its own refresh rate and stays idle.
            // Queue it after the current render has returned, so the next
            // repaint cannot be consumed by this frame on a slower output.
            Qt.callLater(function () {
                if (view.moving && controller.settling) view.KWin.SceneView.scheduleRepaint();
            });
        }
    }
}
