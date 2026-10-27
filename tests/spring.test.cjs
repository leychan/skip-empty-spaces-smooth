// SPDX-License-Identifier: MIT
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { runInNewContext } = require('node:vm');
const spring = runInNewContext(readFileSync(join(__dirname, '../contents/code/spring.js'), 'utf8') +
    '\n({create, advance, moving});');

test('release accelerates gently and converges without overshooting', () => {
    const motion = spring.create(0, 4960, 1, 0);
    spring.advance(motion, 1 / 60);
    assert.ok(motion.position > 0 && motion.position < 0.04 * 4960);
    let previous = motion.position;
    let frames = 1;
    while (spring.moving(motion) && frames < 180) {
        spring.advance(motion, 1 / 60);
        assert.ok(motion.position >= previous - 1e-9);
        assert.ok(motion.position <= 4960 + 1e-9);
        previous = motion.position;
        frames++;
    }
    assert.ok(frames > 11, 'must not abruptly end at the previous 180 ms duration');
    assert.ok(frames < 180);
    assert.ok(Math.abs(motion.position - 4960) <= 1);
    assert.ok(Math.abs(motion.velocity) <= 1);
});

test('the same elapsed time gives the same motion at 60 Hz and 144 Hz', () => {
    const slow = spring.create(0, 4960, 1, 0);
    const fast = spring.create(0, 4960, 1, 0);
    for (let i = 0; i < 30; i++) spring.advance(slow, 1 / 60);
    for (let i = 0; i < 72; i++) spring.advance(fast, 1 / 144);
    assert.ok(Math.abs(slow.position - fast.position) < 1e-8);
    assert.ok(Math.abs(slow.velocity - fast.velocity) < 1e-8);
});

test('variable and dropped frames do not change the physical path', () => {
    const regular = spring.create(1800, 4960, 1, 0);
    const variable = spring.create(1800, 4960, 1, 0);
    spring.advance(regular, 0.3);
    [0.008, 0.022, 0.12, 0.01, 0.14].forEach(dt => spring.advance(variable, dt));
    assert.ok(Math.abs(regular.position - variable.position) < 1e-8);
    assert.ok(Math.abs(regular.velocity - variable.velocity) < 1e-8);
});

test('cancelled swipe eases back from the actual finger position', () => {
    const motion = spring.create(0.65 * 2048, 0, 1, 0);
    let previous = motion.position;
    for (let i = 0; i < 120 && spring.moving(motion); i++) {
        spring.advance(motion, 1 / 60);
        assert.ok(motion.position <= previous + 1e-9 && motion.position >= -1e-9);
        previous = motion.position;
    }
    assert.equal(spring.moving(motion), false);
});

test('system animation speed scales the spring and zero disables settling', () => {
    const normal = spring.create(0, 2048, 1, 0);
    const slower = spring.create(0, 2048, 2, 0);
    const disabled = spring.create(0, 2048, 0, 0);
    [normal, slower, disabled].forEach(m => spring.advance(m, 0.1));
    assert.ok(normal.position > slower.position);
    assert.equal(disabled.position, 2048);
    assert.equal(disabled.velocity, 0);
});

test('zero frame time is safe and small pixel motions retain native thresholds', () => {
    const motion = spring.create(100, 400, 1, 0);
    spring.advance(motion, 0);
    assert.equal(motion.position, 100);
    assert.equal(motion.velocity, 0);
    assert.equal(spring.moving(spring.create(399.5, 400, 1, 0)), false);
    assert.equal(spring.moving(spring.create(399.5, 400, 1, 2)), true);
});
