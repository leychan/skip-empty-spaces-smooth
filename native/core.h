// SPDX-License-Identifier: MIT
#pragma once
#include <algorithm>
#include <cmath>
#include <span>

namespace Spaces {
struct GestureSample { double time; double position; };

inline double releaseVelocity(std::span<const GestureSample> samples, double now,
                              double position, double target, double factor)
{
    if (samples.size() < 2 || factor <= 0 || now - samples.back().time > .05) return 0;
    double sumTime = 0, sumPosition = 0, sumTimeSquared = 0, sumProduct = 0;
    double first = now, last = now;
    int count = 0;
    for (const auto &sample : samples) {
        if (sample.time < now - .05 || sample.time > now) continue;
        const double time = sample.time - now;
        sumTime += time;
        sumPosition += sample.position;
        sumTimeSquared += time * time;
        sumProduct += time * sample.position;
        first = std::min(first, sample.time);
        last = sample.time;
        ++count;
    }
    const double denominator = count * sumTimeSquared - sumTime * sumTime;
    if (count < 2 || last - first < .008 || denominator <= 1e-10) return 0;
    const double velocity = (count * sumProduct - sumTime * sumPosition) / denominator;
    const double distance = target - position;
    // The fast eigenvalue bounds a monotone overdamped trajectory. Retain the
    // measured velocity only toward the chosen desktop, without overshoot.
    const double maximum = std::sqrt(300.0 / std::max(.001, factor)) *
        (1.1 + std::sqrt(1.1 * 1.1 - 1)) * std::abs(distance);
    const double direction = distance >= 0 ? 1 : -1;
    return direction * std::clamp(direction * velocity, 0.0, maximum);
}

template<class Occupied>
int nextOccupied(int count, int origin, int step, bool wraps, Occupied occupied)
{
    if (count < 1 || origin < 0 || origin >= count || (step != 1 && step != -1)) return origin;
    for (int distance = 1; distance <= count; ++distance) {
        const int position = origin + step * distance;
        if (!wraps && (position < 0 || position >= count)) break;
        const int candidate = (position % count + count) % count;
        if (occupied(candidate)) return candidate;
    }
    return origin;
}

// Independent analytical spring, shared parameters with contents/code/spring.js.
inline void advance(double &position, double &velocity, double target, double factor, double seconds)
{
    if (!(seconds > 0)) return;
    if (factor == 0) { position = target; velocity = 0; return; }
    const double omega = std::sqrt(300.0 / std::max(0.001, factor));
    const double spread = std::sqrt(1.1 * 1.1 - 1);
    const double slow = -omega * (1.1 - spread), fast = -omega * (1.1 + spread);
    const double distance = position - target;
    const double a = (velocity - fast * distance) / (slow - fast), b = distance - a;
    const double slowPart = a * std::exp(slow * seconds), fastPart = b * std::exp(fast * seconds);
    position = target + slowPart + fastPart;
    velocity = slow * slowPart + fast * fastPart;
}
}
