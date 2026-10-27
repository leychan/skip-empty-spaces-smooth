// SPDX-License-Identifier: MIT
import QtQuick
import QtQml.Models
import org.kde.kwin 3.0 as KWin
import "../code/navigation.js" as Navigation

KWin.SceneEffect {
    id: root
    visible: false
    property var activeGesture: null
    property real progress: 0
    property bool tracking: false
    property bool internalSwitch: false
    readonly property int duration: 180

    delegate: SlideView { controller: root }

    function update(handler) {
        if (!handler.gesture) {
            var gesture = Navigation.plan(KWin.Workspace, handler.modelData.step);
            if (!gesture) return;
            if (root.visible && root.tracking && root.activeGesture !== gesture) return;
            settle.stop();
            handler.gesture = gesture;
            activeGesture = gesture;
            progress = 0;
            tracking = true;
            visible = true;
        }
        if (activeGesture !== handler.gesture || !Navigation.valid(KWin.Workspace, activeGesture)) return;
        progress = activeGesture.target === activeGesture.origin ? 0 : Math.min(handler.progress, 1);
        watchdog.restart();
    }

    function finish(handler) {
        var gesture = handler.gesture;
        handler.gesture = null;
        if (!gesture || activeGesture !== gesture) return;
        // Native release actions may be queued. Keep the two rendered desktops
        // in place until the final desktop is committed underneath the overlay.
        Qt.callLater(function () { root.release(gesture); });
    }

    function release(gesture) {
        if (activeGesture !== gesture) return;
        tracking = false;
        var target = Navigation.releasedTarget(KWin.Workspace, gesture);
        if (!target) { abort(); return; }
        internalSwitch = true;
        KWin.Workspace.setCurrentDesktopForScreen(target, gesture.output);
        internalSwitch = false;
        settle.to = target === gesture.origin ? 0 : 1;
        settle.duration = Math.max(70, duration * Math.abs(settle.to - progress));
        settle.restart();
    }

    function abort() {
        settle.stop();
        tracking = false;
        visible = false;
        watchdog.stop();
        // Allow the view to be removed before dropping its desktop references.
        Qt.callLater(function () { if (!root.visible) root.activeGesture = null; });
    }

    NumberAnimation {
        id: settle
        target: root
        property: "progress"
        easing.type: Easing.OutCubic
        onFinished: root.abort()
    }
    Timer {
        id: watchdog
        interval: 4000
        repeat: false
        onTriggered: root.abort()
    }

    property Instantiator gestures: Instantiator {
        model: [
            { fingers: 3, direction: KWin.SwipeGestureHandler.Left, step: 1 },
            { fingers: 3, direction: KWin.SwipeGestureHandler.Right, step: -1 },
            { fingers: 4, direction: KWin.SwipeGestureHandler.Left, step: 1 },
            { fingers: 4, direction: KWin.SwipeGestureHandler.Right, step: -1 }
        ]
        delegate: KWin.SwipeGestureHandler {
            id: swipe
            required property var modelData
            property var gesture: null
            fingerCount: modelData.fingers
            direction: modelData.direction
            deviceType: KWin.SwipeGestureHandler.Touchpad
            onProgressChanged: if (progress > 0) root.update(swipe)
            onActivated: root.finish(swipe)
            onCancelled: root.finish(swipe)
        }
    }

    Connections {
        target: KWin.Workspace
        function onDesktopsChanged() { if (root.activeGesture) root.abort(); }
        function onScreensChanged() { if (root.activeGesture) root.abort(); }
        function onCurrentActivityChanged() { if (root.activeGesture) root.abort(); }
        function onCurrentDesktopChanged(previous, current, output) {
            if (root.activeGesture || root.internalSwitch || !previous || !current || previous === current) return;
            var desktops = KWin.Workspace.desktops;
            var step = desktops.indexOf(current) >= desktops.indexOf(previous) ? 1 : -1;
            root.activeGesture = {
                output: output, origin: previous, target: current, step: step
            };
            root.progress = 0;
            root.tracking = false;
            root.visible = true;
            Qt.callLater(function () {
                settle.to = 1;
                settle.duration = root.duration;
                settle.restart();
            });
        }
    }
}
