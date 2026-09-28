#pragma once
#include <stdint.h>
#include <math.h>

namespace RangeMath {
// DW3000 timestamp clock: 499.2 MHz * 128. Speed of light in air.
constexpr double METERS_PER_TICK = 299702547.0 / (499200000.0 * 128.0);
constexpr uint64_t TIMESTAMP_MASK = (1ULL << 40) - 1;
// Wire intervals fit uint32_t; reject delays above 20 ms rather than truncating.
constexpr uint32_t MAX_INTERVAL = 1277952000;

inline bool interval(uint64_t end, uint64_t start, uint32_t &result) {
  const uint64_t delta = (end - start) & TIMESTAMP_MASK;
  if (!delta || delta > MAX_INTERVAL) return false;
  result = static_cast<uint32_t>(delta);
  return true;
}

// Asymmetric double-sided TWR, Qorvo APS013. Preserve fractional clock ticks.
inline double meters(uint32_t ra, uint32_t da, uint32_t rb, uint32_t db) {
  if (!ra || !da || !rb || !db || ra > MAX_INTERVAL || da > MAX_INTERVAL ||
      rb > MAX_INTERVAL || db > MAX_INTERVAL) return NAN;
  const double numerator = double(ra) * rb - double(da) * db;
  return numerator / (double(ra) + rb + da + db) * METERS_PER_TICK;
}

class Median5 {
 public:
  void reset() { count = next = 0; }
  double push(double value) {
    values[next] = value;
    next = (next + 1) % 5;
    if (count < 5) ++count;
    double sorted[5];
    for (unsigned i = 0; i < count; ++i) sorted[i] = values[i];
    for (unsigned i = 1; i < count; ++i) {
      double v = sorted[i];
      unsigned j = i;
      while (j && sorted[j - 1] > v) { sorted[j] = sorted[j - 1]; --j; }
      sorted[j] = v;
    }
    return count % 2 ? sorted[count / 2] :
        (sorted[count / 2 - 1] + sorted[count / 2]) / 2;
  }
 private:
  double values[5] = {};
  unsigned count = 0, next = 0;
};
}
