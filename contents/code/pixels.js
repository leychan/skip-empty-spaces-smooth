// SPDX-License-Identifier: MIT
// Keep both pages on the output's physical pixel grid, including fractional DPI.
function stride(width, gap, scale) {
    return Math.max(1, Math.round((width + gap) * scale));
}

function offset(progress, physicalStride) {
    return Math.round(progress * physicalStride);
}

function landed(progress, target, physicalStride) {
    return offset(progress, physicalStride) === offset(target, physicalStride);
}
