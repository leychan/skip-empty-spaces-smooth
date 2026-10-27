// SPDX-License-Identifier: MIT
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { test } = require('node:test');
const { runInNewContext } = require('node:vm');
const nav = runInNewContext(readFileSync(join(__dirname, '../contents/code/navigation.js'), 'utf8') +
    '\n({ capture: plan, releasedTarget, occupied });');

function session({ count = 6, current = 0, occupied = [], wraps = true } = {}) {
    const desktops = Array.from({ length: count }, (_, id) => ({ id }));
    const outputs = [{ name: 'primary' }, { name: 'secondary' }];
    const currentByOutput = new Map([[outputs[0], desktops[current]], [outputs[1], desktops[4 % count]]]);
    const ws = {
        desktops, screens: outputs, activeScreen: outputs[0], stackingOrder: [],
        desktopGridHeight: 1, currentActivity: 'work', virtualDesktopNavigationWrapsAround: wraps,
        currentDesktopForScreen: output => currentByOutput.get(output)
    };
    function window(desktop, spec = {}) {
        const w = { normalWindow: true, dialog: false, deleted: false, desktopWindow: false,
            dock: false, onAllDesktops: false, minimized: false, activities: [],
            output: outputs[0], desktops: [desktops[desktop]], ...spec };
        ws.stackingOrder.push(w);
        return w;
    }
    occupied.forEach(i => window(i));
    return {
        ws, desktops, outputs, currentByOutput, window,
        gesture: step => nav.capture(ws, step),
        nativeMove: (index, output = outputs[0]) => currentByOutput.set(output, desktops[index]),
        target(g) {
            if (!g || ws.currentDesktopForScreen(g.output) === g.origin) return null;
            const target = nav.releasedTarget(ws, g);
            return target === ws.currentDesktopForScreen(g.output) ? null : target;
        }
    };
}

test('left swipe advances across several empty desktops', () => {
    const s = session({ occupied: [0, 4] });
    const g = s.gesture(1);
    s.nativeMove(1);
    assert.equal(s.target(g), s.desktops[4]);
});

test('right swipe follows the reverse direction', () => {
    const s = session({ current: 5, occupied: [1, 5] });
    const g = s.gesture(-1);
    s.nativeMove(4);
    assert.equal(s.target(g), s.desktops[1]);
});

test('an occupied adjacent destination is preserved', () => {
    const s = session({ occupied: [1, 4] });
    const g = s.gesture(1);
    s.nativeMove(1);
    assert.equal(s.target(g), null);
});

for (const [name, current, step, native, target] of [
    ['forward wrap', 5, 1, 0, 2], ['reverse wrap', 0, -1, 5, 3]
]) {
    test(name + ' keeps the actual gesture direction at the boundary', () => {
        const s = session({ current, occupied: [current, target] });
        const g = s.gesture(step);
        s.nativeMove(native);
        assert.equal(s.target(g), s.desktops[target]);
    });
}

test('only the origin occupied: return there after one bounded circuit', () => {
    const s = session({ occupied: [0] });
    const g = s.gesture(1);
    s.nativeMove(1);
    assert.equal(s.target(g), s.desktops[0]);
});

test('all desktops empty: return to origin without looping', () => {
    const s = session();
    const g = s.gesture(1);
    s.nativeMove(1);
    assert.equal(s.target(g), s.desktops[0]);
});

test('an empty origin can still reach an occupied desktop', () => {
    const s = session({ occupied: [3] });
    const g = s.gesture(1);
    s.nativeMove(1);
    assert.equal(s.target(g), s.desktops[3]);
});

test('a cancelled or insufficient swipe leaves the current desktop alone', () => {
    const s = session({ occupied: [3] });
    assert.equal(s.target(s.gesture(1)), null);
});

test('a short accepted native swipe is handled regardless of handler cancellation', () => {
    const s = session({ occupied: [0, 3] });
    const g = s.gesture(1);
    s.nativeMove(1); // Native .25 threshold can accept a handler-cancelled swipe.
    assert.equal(s.target(g), s.desktops[3]);
});

test('an unrelated non-adjacent desktop switch is left alone', () => {
    const s = session({ occupied: [5] });
    const g = s.gesture(1);
    s.nativeMove(3);
    assert.equal(s.target(g), null);
});

test('no gesture: direct desktop selections and other scripts are left alone', () => {
    const s = session({ occupied: [4] });
    s.nativeMove(1);
    assert.equal(s.target(null), null);
});

test('another screen does not make the destination occupied', () => {
    const s = session({ occupied: [0, 4] });
    s.window(1, { output: s.outputs[1] });
    const g = s.gesture(1);
    s.nativeMove(1);
    assert.equal(s.target(g), s.desktops[4]);
});

test('the gesture screen is used even if the active screen changes before settling', () => {
    const s = session({ occupied: [0, 3] });
    const g = s.gesture(1);
    const otherBefore = s.currentByOutput.get(s.outputs[1]);
    s.nativeMove(1);
    s.ws.activeScreen = s.outputs[1];
    assert.equal(s.target(g), s.desktops[3]);
    assert.equal(g.output, s.outputs[0]);
    assert.equal(s.currentByOutput.get(s.outputs[1]), otherBefore);
});

test('swiping on the secondary screen uses its own desktop and windows', () => {
    const s = session({ occupied: [0, 3] });
    s.ws.activeScreen = s.outputs[1];
    s.window(1, { output: s.outputs[1] });
    const g = s.gesture(1); // Secondary starts at 4.
    s.nativeMove(5, s.outputs[1]);
    assert.equal(s.target(g), s.desktops[1]);
    assert.equal(g.output, s.outputs[1]);
    assert.equal(s.currentByOutput.get(s.outputs[0]), s.desktops[0]);
});

for (const [name, spec] of [
    ['minimized windows', { minimized: true }],
    ['dialogs', { normalWindow: false, dialog: true }],
    ['normal windows with no activity restriction', { activities: [] }],
    ['windows in the current activity', { activities: ['work'] }]
]) {
    test(name + ' count as occupied', () => {
        const s = session({ occupied: [4] });
        s.window(1, spec);
        const g = s.gesture(1);
        s.nativeMove(1);
        assert.equal(s.target(g), null);
    });
}

for (const [name, spec] of [
    ['background', { normalWindow: false, desktopWindow: true }],
    ['panel', { normalWindow: false, dock: true }],
    ['notification or popup', { normalWindow: false }],
    ['deleted window', { deleted: true }],
    ['sticky window', { onAllDesktops: true, desktops: [] }],
    ['another activity', { activities: ['personal'] }]
]) {
    test(name + ' does not make an empty desktop occupied', () => {
        const s = session({ occupied: [4] });
        s.window(1, spec);
        const g = s.gesture(1);
        s.nativeMove(1);
        assert.equal(s.target(g), s.desktops[4]);
    });
}

test('a window assigned to several desktops occupies each of them', () => {
    const s = session();
    s.window(1, { desktops: [s.desktops[1], s.desktops[3]] });
    const g = s.gesture(1);
    s.nativeMove(1);
    assert.equal(s.target(g), null);
});

test('a new intermediate window does not replace the desktop already previewed', () => {
    const s = session({ occupied: [4] });
    const g = s.gesture(1);
    s.nativeMove(1);
    s.window(1);
    assert.equal(s.target(g), s.desktops[4]);
});

test('closing the previewed candidate during the swipe returns to the origin', () => {
    const s = session({ occupied: [2, 4] });
    const g = s.gesture(1);
    s.nativeMove(1);
    s.ws.stackingOrder[0].deleted = true;
    assert.equal(s.target(g), s.desktops[0]);
});

for (const [name, mutate] of [
    ['a desktop is added', s => s.ws.desktops.push({ id: 99 })],
    ['a desktop is removed', s => s.ws.desktops.pop()],
    ['desktops are reordered', s => s.ws.desktops.reverse()],
    ['activity changes', s => { s.ws.currentActivity = 'personal'; }],
    ['the gesture screen disconnects', s => { s.ws.screens = [s.outputs[1]]; }],
    ['desktop rows change', s => { s.ws.desktopGridHeight = 2; }],
    ['wrapping changes', s => { s.ws.virtualDesktopNavigationWrapsAround = false; }]
]) {
    test('skip is abandoned if ' + name + ' during the gesture', () => {
        const s = session({ occupied: [4] });
        const g = s.gesture(1);
        s.nativeMove(1);
        mutate(s);
        assert.equal(s.target(g), null);
    });
}

test('wrapping disabled: do not cross the boundary to find an occupied desktop', () => {
    const s = session({ current: 3, occupied: [1, 3], wraps: false });
    const g = s.gesture(1);
    s.nativeMove(4);
    assert.equal(s.target(g), s.desktops[3]);
});

test('wrapping disabled: search within the remaining direction normally', () => {
    const s = session({ occupied: [4], wraps: false });
    const g = s.gesture(1);
    s.nativeMove(1);
    assert.equal(s.target(g), s.desktops[4]);
});

test('a native edge bounce without wrapping does not redirect', () => {
    const s = session({ current: 5, occupied: [1], wraps: false });
    assert.equal(s.target(s.gesture(1)), null);
});

test('one desktop or multi-row grids do not capture horizontal gestures', () => {
    assert.equal(session({ count: 1 }).gesture(1), null);
    const s = session();
    s.ws.desktopGridHeight = 2;
    assert.equal(s.gesture(1), null);
    s.ws.desktopGridHeight = 1;
    assert.equal(s.gesture(0), null);
});

test('two desktops and an empty neighbour return to the occupied origin', () => {
    const s = session({ count: 2, occupied: [0] });
    const g = s.gesture(-1);
    s.nativeMove(1);
    assert.equal(s.target(g), s.desktops[0]);
});
