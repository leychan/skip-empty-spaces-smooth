// SPDX-License-Identifier: MIT
// Independent closed-form solution of x'' + 2*zeta*sqrt(k)*x' + k*x = k*target.
// Matches the native Slide effect's physical parameters, without copying its
// GPL-licensed RK4 implementation. Position and velocity are measured in pixels.
function create(position, target, factor, velocity) {
    return {
        position: position,
        target: target,
        velocity: velocity || 0,
        stiffness: factor === 0 ? Infinity : 300 / Math.max(0.001, factor),
        dampingRatio: 1.1,
        epsilon: 1
    };
}

function moving(motion) {
    return Math.abs(motion.position - motion.target) > motion.epsilon ||
        Math.abs(motion.velocity) > motion.epsilon;
}

function advance(motion, seconds) {
    if (!moving(motion)) return;
    if (!isFinite(motion.stiffness) || seconds === Infinity) {
        motion.position = motion.target;
        motion.velocity = 0;
        return;
    }
    if (!(seconds > 0)) return;
    var omega = Math.sqrt(motion.stiffness);
    var spread = Math.sqrt(motion.dampingRatio * motion.dampingRatio - 1);
    var slow = -omega * (motion.dampingRatio - spread);
    var fast = -omega * (motion.dampingRatio + spread);
    var distance = motion.position - motion.target;
    var a = (motion.velocity - fast * distance) / (slow - fast);
    var b = distance - a;
    var slowPart = a * Math.exp(slow * seconds);
    var fastPart = b * Math.exp(fast * seconds);
    motion.position = motion.target + slowPart + fastPart;
    motion.velocity = slow * slowPart + fast * fastPart;
}
