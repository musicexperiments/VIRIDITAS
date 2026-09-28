"""Exercise the actual driver serializer with a captured SPI transport."""
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
driver = (root / 'third_party/DW3000/src/DW3000.cpp').read_text()
start = driver.index('uint32_t DW3000Class::readOrWriteFullAddress(')
end = driver.index('\n}\n', start) + 3
method = driver[start:end]
harness = r'''
#include <cstdint>
#include <cassert>
#include <vector>
#include <cstdio>
#define DEBUG_OUTPUT 0
struct SerialStub { void println(const char*) {} } Serial;
std::vector<int> captured;
struct DW3000Class {
  static uint32_t readOrWriteFullAddress(uint32_t, uint32_t, uint32_t, uint32_t, uint32_t);
  static unsigned countBits(unsigned value) {
    unsigned bits = 0; while(value) { ++bits; value >>= 1; } return bits;
  }
  static uint32_t sendBytes(int* bytes, int size, int) {
    captured.assign(bytes, bytes + size); return 0;
  }
};
'''
checks = r'''
int main() {
  // Offset zero uses a one-byte header: no extra byte may be sent.
  DW3000Class::readOrWriteFullAddress(0x14, 0, 1, 0, 1);
  assert((captured == std::vector<int>{0xA8, 1}));
  DW3000Class::readOrWriteFullAddress(0x14, 4, 0x12345678, 4, 1);
  assert((captured == std::vector<int>{0xE8, 0x10, 0x78, 0x56, 0x34, 0x12}));
  // Smaller replacements must clear the upper bytes of the timing field.
  DW3000Class::readOrWriteFullAddress(0x14, 4, 0x12, 4, 1);
  assert((captured == std::vector<int>{0xE8, 0x10, 0x12, 0, 0, 0}));
  DW3000Class::readOrWriteFullAddress(0x14, 8, 0, 4, 1);
  assert((captured == std::vector<int>{0xE8, 0x20, 0, 0, 0, 0}));
  puts("SPI serializer regression tests passed.");
}
'''
with tempfile.TemporaryDirectory(prefix='viriditas-spi-') as directory:
    binary = str(Path(directory) / 'test')
    subprocess.run(['c++', '-std=c++11', '-fsanitize=address,undefined',
                    '-x', 'c++', '-', '-o', binary],
                   input=harness + method + checks, text=True, check=True)
    subprocess.run([binary], check=True)
