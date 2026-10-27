// SPDX-License-Identifier: MIT
import QtQuick
import QtQml.Models
import org.kde.kwin 3.0 as KWin
import "../code/navigation.js" as Navigation
import "../code/spring.js" as Spring
import "../code/pixels.js" as Pixels

KWin.SceneEffect {
    id: root
    visible: false
    readonly property string buildId: "@SKIP_EMPTY_BUILD@"
    property var activeGesture: null
    property real progress: 0
    property bool tracking: false
    property bool internalSwitch: false
    property bool settling: false
    property var motion: null
    property real motionScale: 1
    property real lastFrameTime: 0
    // Bounded, in-memory lifecycle diagnostics; no window contents are stored.
    property string traceLog: "[]"
    readonly property real animationTimeFactor: configuration && configuration.AnimationTimeFactor !== undefined ? Math.max(0, configuration.AnimationTimeFactor) : 1
    readonly property real horizontalGap: configuration && configuration.HorizontalGap !== undefined ? configuration.HorizontalGap : 45
    readonly property bool slideBackground: !configuration || configuration.SlideBackground === undefined ? true : configuration.SlideBackground

    delegate: SlideView { controller: root }

    function recordTrace(event) {
        var rows = JSON.parse(traceLog || "[]");
        rows.push({ time: Date.now(), event: event, progress: progress,
            visible: visible, tracking: tracking, settling: settling,
            output: activeGesture && activeGesture.output ? activeGesture.output.name : "" });
        traceLog = JSON.stringify(rows.slice(-48));
    }

    onActivated: recordTrace("effect-activated")
    onDeactivated: {
        recordTrace("effect-deactivated");
        Qt.callLater(function () { root.recordTrace("effect-stopped"); });
    }

    function update(handler) {
        if (!handler.gesture) {
            var gesture = Navigation.plan(KWin.Workspace, handler.modelData.step);
            if (!gesture) return;
            if (root.visible && root.tracking && root.activeGesture !== gesture) return;
            settling = false;
            motion = null;
            handler.gesture = gesture;
            activeGesture = gesture;
            progress = 0;
            tracking = true;
            visible = true;
            recordTrace("gesture-start");
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
        recordTrace("release");
        var target = Navigation.releasedTarget(KWin.Workspace, gesture);
        if (!target) { abort(); return; }
        internalSwitch = true;
        KWin.Workspace.setCurrentDesktopForScreen(target, gesture.output);
        internalSwitch = false;
        startSettling(target === gesture.origin ? 0 : 1);
    }

    function startSettling(target) {
        // Native Slide measures the spring in virtual-space pixels and ends
        // below one pixel of displacement and one pixel/second of velocity.
        motionScale = Math.max(1, KWin.Workspace.virtualScreenSize.width);
        motion = Spring.create(progress * motionScale, target * motionScale, animationTimeFactor, 0);
        if (animationTimeFactor === 0 || !Spring.moving(motion)) {
            progress = target;
            abort();
            return;
        }
        lastFrameTime = Date.now();
        settling = true;
        recordTrace("settle-start");
        var view = root.viewForScreen(activeGesture.output);
        if (view) view.scheduleRepaint();
        watchdog.restart();
    }

    function advanceFrame(now) {
        if (!settling || !motion) return;
        // The active output owns this clock. A standalone FrameAnimation can
        // wake between compositor frames and leave periodic gaps on high-Hz
        // outputs. afterAnimating runs before this view's scene graph sync.
        var elapsed = Math.max(0, now - lastFrameTime) / 1000;
        lastFrameTime = Math.max(lastFrameTime, now);
        Spring.advance(motion, elapsed);
        progress = motion.position / motionScale;
        var output = activeGesture.output;
        var physicalStride = Pixels.stride(output.geometry.width, horizontalGap, output.devicePixelRatio);
        // Once the page has landed on the destination's physical pixel, its
        // preview would only prolong the softer thumbnail image. Hand off to
        // the real desktop instead of waiting for subpixel spring velocity.
        if (!Spring.moving(motion) || Pixels.landed(progress, motion.target / motionScale, physicalStride)) {
            progress = motion.target / motionScale;
            settling = false;
            recordTrace("landed");
            var completed = motion;
            // Destroy the scene views only after their current render returns.
            Qt.callLater(function () {
                if (root.motion === completed && !root.tracking && !root.settling) root.abort();
            });
        }
    }

    function abort() {
        recordTrace("abort-begin");
        settling = false;
        motion = null;
        tracking = false;
        visible = false;
        recordTrace("abort-end");
        watchdog.stop();
        // Allow the view to be removed before dropping its desktop references.
        Qt.callLater(function () { if (!root.visible) root.activeGesture = null; });
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
                root.startSettling(1);
            });
        }
    }
}
