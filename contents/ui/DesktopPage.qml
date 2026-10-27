// SPDX-License-Identifier: MIT
import QtQuick
import org.kde.kwin 3.0 as KWin

Item {
    id: page
    required property QtObject desktop
    required property QtObject screen
    // moving: ordinary windows; fixed: panels and sticky windows; all: passive screen.
    property string layerMode: "moving"

    KWin.DesktopBackground {
        anchors.fill: parent
        output: page.screen
        desktop: page.desktop
        activity: KWin.Workspace.currentActivity
        visible: page.layerMode !== "fixed"
    }

    Repeater {
        model: KWin.WindowFilterModel {
            activity: KWin.Workspace.currentActivity
            desktop: page.desktop
            screenName: page.screen.name
            windowModel: KWin.WindowModel {}
        }
        delegate: KWin.WindowThumbnail {
            required property var model
            readonly property var window: model.window
            readonly property bool fixed: window.dock || window.onAllDesktops
            wId: window.internalId
            x: window.x - page.screen.geometry.x
            y: window.y - page.screen.geometry.y
            z: window.stackingOrder
            visible: !window.deleted && !window.minimized && !window.desktopWindow &&
                (page.layerMode === "all" || (page.layerMode === "fixed" ? fixed : !fixed))
        }
    }
}
