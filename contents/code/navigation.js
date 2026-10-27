// SPDX-License-Identifier: MIT
// Shared by QML and the Node regression tests. No window or desktop is modified here.
function contains(list, value) {
    for (var i = 0; i < list.length; ++i) {
        if (list[i] === value) return true;
    }
    return false;
}

function snapshot(list) {
    var result = [];
    for (var i = 0; i < list.length; ++i) result.push(list[i]);
    return result;
}

function sameLayout(before, after) {
    if (before.length !== after.length) return false;
    for (var i = 0; i < before.length; ++i) {
        if (before[i] !== after[i]) return false;
    }
    return true;
}

function occupied(workspace, desktop, output, activity) {
    var windows = workspace.stackingOrder;
    for (var i = 0; i < windows.length; ++i) {
        var w = windows[i];
        if (w.deleted || w.desktopWindow || w.dock || w.onAllDesktops ||
            (!w.normalWindow && !w.dialog) || w.output !== output ||
            !contains(w.desktops, desktop)) continue;
        if (w.activities.length && !contains(w.activities, activity)) continue;
        return true;
    }
    return false;
}

function capture(workspace, step) {
    if ((step !== 1 && step !== -1) || workspace.desktopGridHeight !== 1 ||
        workspace.desktops.length < 2 || !workspace.activeScreen) return null;
    return {
        output: workspace.activeScreen,
        origin: workspace.currentDesktopForScreen(workspace.activeScreen),
        layout: snapshot(workspace.desktops),
        activity: workspace.currentActivity,
        wraps: workspace.virtualDesktopNavigationWrapsAround,
        step: step
    };
}

// Compute the visual neighbour BEFORE the native desktop release action.
function plan(workspace, step) {
    var gesture = capture(workspace, step);
    if (!gesture) return null;
    var desktops = gesture.layout;
    var index = desktops.indexOf(gesture.origin);
    if (index < 0) return null;
    gesture.nativeTarget = gesture.origin;
    gesture.target = gesture.origin;
    for (var distance = 1; distance <= desktops.length; ++distance) {
        var position = index + step * distance;
        if (!gesture.wraps && (position < 0 || position >= desktops.length)) break;
        var candidate = desktops[(position % desktops.length + desktops.length) % desktops.length];
        if (distance === 1) gesture.nativeTarget = candidate;
        if (occupied(workspace, candidate, gesture.output, gesture.activity)) {
            gesture.target = candidate;
            break;
        }
    }
    return gesture;
}

function valid(workspace, gesture) {
    return gesture && contains(workspace.screens, gesture.output) &&
        workspace.currentActivity === gesture.activity &&
        workspace.desktopGridHeight === 1 &&
        workspace.virtualDesktopNavigationWrapsAround === gesture.wraps &&
        sameLayout(workspace.desktops, gesture.layout);
}

function releasedTarget(workspace, gesture) {
    if (!valid(workspace, gesture)) return null;
    var current = workspace.currentDesktopForScreen(gesture.output);
    if (current === gesture.origin) return gesture.origin;
    if (current !== gesture.nativeTarget) return null;
    // Use the same destination that was displayed under the fingers, unless its
    // last window closed during the swipe. In that case return to the origin.
    return occupied(workspace, gesture.target, gesture.output, gesture.activity) ?
        gesture.target : gesture.origin;
}
