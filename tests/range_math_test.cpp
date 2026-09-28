#include "../firmware/range_math.h"
#include <cassert>
#include <cmath>
#include <cstdio>

int main() {
  // Different response delays and clocks: independently construct each interval.
  const double tof = 100.25;
  const double clockA = 1.000020, clockB = 0.999985;
  const double delayA = 25000000, delayB = 40000000;
  const double result = RangeMath::meters(
      llround((delayB + 2 * tof) * clockA), llround(delayA * clockA),
      llround((delayA + 2 * tof) * clockB), llround(delayB * clockB));
  assert(std::abs(result - tof * RangeMath::METERS_PER_TICK) < 0.005);
  assert(std::isnan(RangeMath::meters(0, 1, 1, 1)));
  assert(std::isnan(RangeMath::meters(UINT32_MAX, 1, 1, 1)));
  assert(RangeMath::meters(100, 100, 100, 100) == 0);
  // Raising the TX and RX antenna delay on both boards by one tick shortens
  // Ra/Rb and lengthens Da/Db by two ticks each: -2 ticks of time of flight.
  const double shifted = RangeMath::meters(
      llround((delayB + 2 * tof) * clockA) - 2, llround(delayA * clockA) + 2,
      llround((delayA + 2 * tof) * clockB) - 2, llround(delayB * clockB) + 2);
  assert(std::abs((result - shifted) - 2 * RangeMath::METERS_PER_TICK) < 0.0005);
  uint32_t delta = 0;
  assert(RangeMath::interval(20, RangeMath::TIMESTAMP_MASK - 9, delta));
  assert(delta == 30);
  assert(!RangeMath::interval(RangeMath::MAX_INTERVAL + 1ULL, 0, delta));
  RangeMath::Median5 filter;
  filter.push(100); filter.push(101); filter.push(99); filter.push(1000);
  assert(filter.push(100) == 100);
  filter.reset();
  assert(filter.push(250) == 250);
  puts("Ranging math, clock skew, antenna delay, timestamp wrap, bounds, and median tests passed.");
}
