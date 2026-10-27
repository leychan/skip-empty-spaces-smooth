// SPDX-License-Identifier: MIT
#include "core.h"
#include <cstdlib>
#include <iostream>
#include <vector>

void require(bool value, const char *reason) {
    if (!value) { std::cerr << reason << '\n'; std::exit(1); }
}
int main() {
    int cases = 0;
    for (int count = 1; count <= 7; ++count) {
        for (int bits = 0; bits < (1 << count); ++bits) {
            for (int origin = 0; origin < count; ++origin) {
                for (bool wraps : {false, true}) for (int step : {-1, 1}) {
                    const auto occupied = [&](int index) { return bits & (1 << index); };
                    const int found = Spaces::nextOccupied(count, origin, step, wraps, occupied);
                    require(found >= 0 && found < count, "navigation left the layout");
                    if (found != origin) {
                        require(occupied(found), "selected an empty destination");
                        require(wraps || (found - origin) * step > 0, "crossed a nonwrapping edge");
                    }
                    // No occupied desktop may be skipped before the chosen one.
                    for (int index = origin + step, distance = 1; distance < count; index += step, ++distance) {
                        if (!wraps && (index < 0 || index >= count)) break;
                        const int candidate = (index % count + count) % count;
                        if (candidate == found) break;
                        require(!occupied(candidate), "bypassed a nearer occupied desktop");
                    }
                    ++cases;
                }
            }
        }
    }
    for (int hz : {60, 144, 240}) for (double target : {0., 1.}) {
        double position = .4, velocity = 0, previous = position;
        for (int frame = 0; frame < hz * 2; ++frame) {
            Spaces::advance(position, velocity, target, 1, 1.0 / hz);
            require(position >= 0 && position <= 1, "spring overshot");
            require((position - previous) * (target == 1 ? 1 : -1) >= -1e-12, "spring reversed");
            previous = position;
        }
        require(std::abs(position - target) < 1e-8, "spring did not converge");
    }
    double slow = .4, fast = .4, v1 = 0, v2 = 0;
    for (int i=0; i<30; ++i) Spaces::advance(slow,v1,1,1,1./60);
    for (int i=0; i<120; ++i) Spaces::advance(fast,v2,1,1,1./240);
    require(std::abs(slow-fast) < 1e-12 && std::abs(v1-v2) < 1e-12, "refresh rate changed spring path");
    double p = .4, v = 2;
    Spaces::advance(p,v,1,0,.01);
    require(p == 1 && v == 0, "zero animation factor did not finish");
    std::vector<Spaces::GestureSample> samples{{0,.2},{.01,.24},{.02,.28},{.03,.32},{.04,.36},{.05,.4}};
    const double carried = Spaces::releaseVelocity(samples,.05,.4,1,1);
    require(std::abs(carried-4) < 1e-10, "release did not preserve finger velocity");
    p=.4; v=carried;
    Spaces::advance(p,v,1,1,1e-6);
    require(std::abs((p-.4)/1e-6-carried) < .001, "velocity jumps at release");
    require(Spaces::releaseVelocity(samples,.2,.4,1,1)==0, "a paused finger retained stale momentum");
    require(Spaces::releaseVelocity(samples,.05,.4,0,1)==0, "cancel started in the wrong direction");
    for (double target : {0.,1.}) for (double start : {.01,.2,.8,.99}) {
        const double direction = target == 1 ? 1 : -1;
        std::vector<Spaces::GestureSample> fast{{0,start-direction*.8},{.04,start}};
        p=start; v=Spaces::releaseVelocity(fast,.04,start,target,1);
        double previous = p;
        for (int i=0;i<480;++i) {
            Spaces::advance(p,v,target,1,1./240);
            require(p >= -1e-12 && p <= 1+1e-12, "fast release overshot the destination");
            require((p-previous)*direction>=-1e-12, "fast release bounced");
            previous=p;
        }
    }
    std::cout << cases << " navigation layouts and native spring checks passed\n";
}
