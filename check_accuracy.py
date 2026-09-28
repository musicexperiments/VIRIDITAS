#!/usr/bin/env python3
"""Measure raw ranging bias and noise against a tape-measured separation,
and suggest (or apply) the antenna delay that removes the bias."""
import argparse
import json
import math
import statistics
import time
import urllib.error
import urllib.parse
import urllib.request

# DW3000 timestamp tick in meters; matches RangeMath::METERS_PER_TICK.
METERS_PER_TICK = 299702547.0 / (499200000.0 * 128.0)
# One tick on TX and RX of both boards moves the range by two ticks of flight.
CM_PER_DELAY_TICK = 2 * METERS_PER_TICK * 100


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://uwb-anchor.local')
    parser.add_argument('--known-cm', type=float, required=True)
    parser.add_argument('--samples', type=int, default=200)
    parser.add_argument('--timeout', type=float, default=90)
    parser.add_argument('--apply', action='store_true',
                        help='send the suggested antenna delay to the anchor (and tag)')
    args = parser.parse_args()
    if not math.isfinite(args.known_cm) or args.known_cm <= 0 or args.samples < 2 or not math.isfinite(args.timeout) or args.timeout <= 0:
        parser.error('Use positive distance/timeout and at least two samples.')
    values, seen, delays = [], set(), set()
    deadline = time.monotonic() + args.timeout
    print('Keep both antennas stationary at the measured separation. Collecting raw samples…')
    while len(values) < args.samples and time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(args.url.rstrip('/') + '/api/distance', timeout=3) as response:
                data = json.load(response)
            if 'raw_cm' not in data:
                raise SystemExit('Install the accuracy firmware first: raw_cm is missing.')
            if 'antenna_delay' not in data:
                raise SystemExit('Install the antenna-delay firmware first: antenna_delay is missing.')
            value = float(data['raw_cm'])
            if data['valid'] and data['sequence'] not in seen and math.isfinite(value):
                seen.add(data['sequence'])
                values.append(value)
                delays.add(data['antenna_delay'])
        except (urllib.error.URLError, TimeoutError, ValueError, KeyError) as error:
            print(f'Waiting: {error}')
        time.sleep(0.1)
    if len(values) < 2:
        raise SystemExit('Not enough live samples; check power, network, and ranging.')
    errors = [value - args.known_cm for value in values]
    absolute = sorted(abs(error) for error in errors)
    print(f'Samples: {len(values)}/{args.samples}')
    print(f'Mean measured: {statistics.mean(values):.2f} cm')
    print(f'Mean error (positive = too far): {statistics.mean(errors):+.2f} cm')
    print(f'Raw standard deviation: {statistics.stdev(values):.2f} cm')
    print(f'RMSE: {math.sqrt(statistics.mean(e * e for e in errors)):.2f} cm')
    print(f'95th percentile absolute error: {absolute[math.ceil(.95 * len(absolute)) - 1]:.2f} cm')
    if len(values) < args.samples:
        raise SystemExit('Collection timed out; the results above are a partial sample.')
    if len(delays) != 1:
        raise SystemExit('The antenna delay changed during collection; run again.')
    current = delays.pop()
    suggested = current + round(statistics.mean(errors) / CM_PER_DELAY_TICK)
    if not 0 <= suggested <= 0xFFFF:
        raise SystemExit(f'Suggested antenna delay {suggested} is out of range; check the setup.')
    print(f'Antenna delay: current {current} (0x{current:04X}), '
          f'suggested {suggested} (0x{suggested:04X}); {CM_PER_DELAY_TICK:.3f} cm per tick')
    if not args.apply:
        print('No calibration was applied. Rerun with --apply to set the suggested value.')
    elif suggested == current:
        print('Already calibrated; nothing to apply.')
    else:
        body = urllib.parse.urlencode({'value': suggested}).encode()
        with urllib.request.urlopen(args.url.rstrip('/') + '/api/antenna-delay', data=body, timeout=5):
            pass
        print('Applied. The tag adopts it on the next exchange. Rerun to verify.')


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        raise SystemExit('Stopped.')
