// SPDX-License-Identifier: MIT
const { test } = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { join } = require('node:path');
const { runInNewContext } = require('node:vm');
const pixels = runInNewContext(readFileSync(join(__dirname, '../contents/code/pixels.js'), 'utf8') +
    '\n({stride, offset, landed});');
const spring = runInNewContext(readFileSync(join(__dirname, '../contents/code/spring.js'), 'utf8') +
    '\n({create, advance, moving});');

test('both page positions and their gap stay on physical pixels at fractional DPI', () => {
    for (const scale of [1, 1.25, 1.5, 1.75, 2]) {
        const stride = pixels.stride(2048, 45, scale);
        for (const progress of [0, 0.1, 0.4997, 0.9999, 1]) {
            const offset = pixels.offset(progress, stride);
            for (const step of [-1, 1]) {
                const origin = -step * offset;
                const target = step * (stride - offset);
                assert.ok(Number.isInteger(origin) && Number.isInteger(target));
                assert.equal(Math.abs(target - origin), stride);
            }
        }
        assert.ok(Math.abs(stride - (2048 + 45) * scale) <= 0.5);
    }
});

test('handoff only happens when the displayed page reaches its exact endpoint pixel', () => {
    const stride = pixels.stride(2048, 45, 1.25);
    assert.equal(pixels.landed(1 - 0.51 / stride, 1, stride), false);
    assert.equal(pixels.landed(1 - 0.49 / stride, 1, stride), true);
    assert.equal(pixels.landed(0.51 / stride, 0, stride), false);
    assert.equal(pixels.landed(0.49 / stride, 0, stride), true);
    assert.equal(pixels.offset(1, stride), stride);
    assert.equal(pixels.offset(0, stride), 0);
});

test('completion and cancellation release the preview before the invisible velocity tail', () => {
    const stride = pixels.stride(2048, 45, 1.25);
    for (const hz of [60, 240]) {
        for (const target of [0, 1]) {
            const motion = spring.create(0.4 * 3968, target * 3968, 1, 0);
            let frames = 0;
            while (!pixels.landed(motion.position / 3968, target, stride) && frames < hz * 2) {
                spring.advance(motion, 1 / hz);
                frames++;
            }
            assert.ok(frames / hz > 0.5 && frames / hz < 0.9);
            assert.ok(spring.moving(motion), 'native velocity threshold would still retain the preview');
            assert.ok(Math.abs(motion.position / 3968 - target) * stride < 0.5);
        }
    }
});
