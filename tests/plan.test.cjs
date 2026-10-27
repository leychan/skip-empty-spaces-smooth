// SPDX-License-Identifier: MIT
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { runInNewContext } = require('node:vm');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const nav = runInNewContext(readFileSync(join(__dirname, '../contents/code/navigation.js'), 'utf8') +
    '\n({ plan, releasedTarget, valid });');

function session({ current = 0, occupied = [0, 4], wraps = true } = {}) {
    const desktops = Array.from({ length: 6 }, (_, id) => ({ id }));
    const screens = [{ name: 'first' }, { name: 'second' }];
    const states = new Map([[screens[0], desktops[current]], [screens[1], desktops[2]]]);
    const ws = {
        desktops, screens, activeScreen: screens[0], desktopGridHeight: 1,
        currentActivity: 'work', virtualDesktopNavigationWrapsAround: wraps,
        currentDesktopForScreen: screen => states.get(screen),
        stackingOrder: occupied.map(i => ({ normalWindow: true, dialog: false,
            output: screens[0], desktops: [desktops[i]], activities: [] }))
    };
    return { ws, desktops, screens, states, move(i, screen = screens[0]) { states.set(screen, desktops[i]); } };
}

test('visual neighbour is selected while the native desktop is still the origin', () => {
    const s = session();
    const g = nav.plan(s.ws, 1);
    assert.equal(g.origin, s.desktops[0]);
    assert.equal(g.nativeTarget, s.desktops[1]);
    assert.equal(g.target, s.desktops[4]);
    assert.equal(s.ws.currentDesktopForScreen(s.screens[0]), s.desktops[0]);
});
test('reverse preview jumps over empty intermediate desktops', () => {
    const s = session({ current: 4, occupied: [1, 4] });
    const g = nav.plan(s.ws, -1);
    assert.equal(g.target, s.desktops[1]);
    assert.equal(g.nativeTarget, s.desktops[3]);
});
test('forward wrap shows the first occupied desktop rather than an empty boundary', () => {
    const s = session({ current: 5, occupied: [2, 5] });
    assert.equal(nav.plan(s.ws, 1).target, s.desktops[2]);
});
test('reverse wrap shows the last occupied desktop', () => {
    const s = session({ occupied: [0, 3] });
    assert.equal(nav.plan(s.ws, -1).target, s.desktops[3]);
});
test('one occupied desktop remains stationary instead of previewing emptiness', () => {
    const s = session({ occupied: [0] });
    const g = nav.plan(s.ws, 1);
    assert.equal(g.target, g.origin);
    s.move(1);
    assert.equal(nav.releasedTarget(s.ws, g), g.origin);
});
test('entirely empty output does not preview another output windows', () => {
    const s = session({ occupied: [] });
    s.ws.stackingOrder.push({ normalWindow: true, output: s.screens[1], desktops: [s.desktops[1]], activities: [] });
    const g = nav.plan(s.ws, 1);
    assert.equal(g.target, g.origin);
});
test('an occupied native neighbour is also the visual neighbour', () => {
    const s = session({ occupied: [0, 1, 4] });
    const g = nav.plan(s.ws, 1);
    assert.equal(g.target, g.nativeTarget);
});
test('cancelled release returns to the original visual desktop', () => {
    const s = session();
    const g = nav.plan(s.ws, 1);
    assert.equal(nav.releasedTarget(s.ws, g), s.desktops[0]);
});
test('accepted native release commits exactly the desktop previewed under the fingers', () => {
    const s = session();
    const g = nav.plan(s.ws, 1);
    s.move(1);
    assert.equal(nav.releasedTarget(s.ws, g), s.desktops[4]);
});
test('closing the previewed window mid-swipe returns to origin', () => {
    const s = session();
    const g = nav.plan(s.ws, 1);
    s.ws.stackingOrder[1].deleted = true;
    s.move(1);
    assert.equal(nav.releasedTarget(s.ws, g), s.desktops[0]);
});
test('does not suddenly substitute a newly occupied, unseen intermediate desktop', () => {
    const s = session();
    const g = nav.plan(s.ws, 1);
    s.ws.stackingOrder.push({ normalWindow: true, output: s.screens[0], desktops: [s.desktops[2]], activities: [] });
    s.move(1);
    assert.equal(nav.releasedTarget(s.ws, g), s.desktops[4]);
});
test('unrelated desktop switches during a swipe are not overridden', () => {
    const s = session();
    const g = nav.plan(s.ws, 1);
    s.move(3);
    assert.equal(nav.releasedTarget(s.ws, g), null);
});
test('wrapping disabled never previews a desktop beyond the boundary', () => {
    const s = session({ current: 4, occupied: [1, 4], wraps: false });
    assert.equal(nav.plan(s.ws, 1).target, s.desktops[4]);
});
test('a layout change invalidates the visual plan', () => {
    const s = session();
    const g = nav.plan(s.ws, 1);
    s.ws.desktops.push({ id: 99 });
    assert.equal(nav.valid(s.ws, g), false);
    assert.equal(nav.releasedTarget(s.ws, g), null);
});
test('secondary output preview and commit are independent of the primary', () => {
    const s = session();
    s.ws.activeScreen = s.screens[1];
    s.ws.stackingOrder.push({ normalWindow: true, output: s.screens[1], desktops: [s.desktops[5]], activities: [] });
    const g = nav.plan(s.ws, 1);
    assert.equal(g.origin, s.desktops[2]);
    assert.equal(g.target, s.desktops[5]);
    s.move(3, s.screens[1]);
    assert.equal(nav.releasedTarget(s.ws, g), s.desktops[5]);
    assert.equal(s.ws.currentDesktopForScreen(s.screens[0]), s.desktops[0]);
});
