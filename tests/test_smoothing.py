#!/usr/bin/env python3
"""Tests for osc_bridge.py's smoothing, on simulated UWB readings with known truth.

  python3 tests/test_smoothing.py          # run the tests
  python3 tests/test_smoothing.py report   # raw vs smoothed numbers for each scenario

A tag in a 30 x 13 ft rectangle (the real layout) is ranged by four anchors at
20 Hz each, with UWB-like faults: about 8 cm of noise, missed readings, the odd
reflection reading metres too long, and an anchor blocked by a body (reads long
and noisier). The readings go through the real Bridge, and its OSC x, y are
compared with where the tag really was.
"""
import math
import random
import statistics
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import osc_bridge  # noqa: E402

WIDTH, HEIGHT = 914.4, 396.24  # cm
ANCHORS = {1: (0.0, 0.0), 3: (WIDTH, 0.0), 4: (WIDTH, HEIGHT), 5: (0.0, HEIGHT)}
TAG = 2
bridges = []  # closed after the tests


def tearDownModule():
    for bridge in bridges:
        bridge.osc.close()


def make_bridge(**tuning):
    args = SimpleNamespace(tags=2, smooth=False, raw=False, osc_host='127.0.0.1',
                           osc_port=39990, also_port=[])
    bridge = osc_bridge.Bridge(args)
    bridge.saved, bridge.frame = dict(ANCHORS), dict(osc_bridge.DEFAULT_FRAME)
    bridge.grid_box, bridge.geometry = (-1, 1, -1, 1), None
    bridge.tuning = dict(osc_bridge.FILTER_DEFAULTS, **tuning)
    bridges.append(bridge)
    return bridge


def to_cm(message):
    """OSC x, y back to cm in the layout (A1 at 0, 0; y down)."""
    if message['x'] == osc_bridge.MISSING:
        return None
    return (message['x'] + 1) / 2 * WIDTH, (1 - message['y']) / 2 * HEIGHT


def run(path, seconds, bridge, seed=1, noise=8.0, drop=0.08, spike=0.03, blocked=None, blocked_from=0.0,
        gaps=()):
    """Feed simulated readings for `seconds`. path(t) -> (x, y) in cm. blocked: an anchor
    that reads 60-120 cm long and noisier from `blocked_from` on. gaps: (start, end, anchors
    still heard).
    Returns [(t, truth, output or None, message)] for every message tag 1 sends."""
    rng = random.Random(seed)
    out = []
    # Anchor 1 ranges each pair in turn; one pass over the tag pairs every ~50 ms.
    pairs = [(TAG, a) for a in ANCHORS]
    step = 0.05 / len(pairs)
    t, i = 0.0, 0
    while t < seconds:
        a, b = pairs[i % len(pairs)]
        i += 1
        t += step
        where = lambda node: path(t) if node == TAG else ANCHORS[node]
        heard = next((g[2] for g in gaps if g[0] <= t < g[1]), None)
        anchor = b if b in ANCHORS else None
        if heard is not None and anchor is not None and anchor not in heard and a == TAG:
            bridge.heartbeat(t)
            continue
        if rng.random() < drop:
            bridge.heartbeat(t)
            continue
        cm = math.dist(where(a), where(b)) + rng.gauss(0, noise)
        if blocked is not None and anchor == blocked and a == TAG and t >= blocked_from:
            cm += rng.uniform(60, 120) + rng.gauss(0, 15)
        if rng.random() < spike:
            cm += rng.uniform(100, 600)
        before = bridge.total_sent
        bridge.on_range(min(a, b), max(a, b), cm, cm, t)
        bridge.heartbeat(t)
        if bridge.total_sent != before and 1 in bridge.last_message:
            out.append((t, path(t), to_cm(bridge.last_message[1]), dict(bridge.last_message[1])))
    return out


def still(x, y):
    return lambda t: (x, y)


def walk(t):
    """A loop around the middle of the space at about 1.2 m/s."""
    r, w = 150.0, 120.0 / 150.0
    return WIDTH / 2 + 2 * r * math.cos(w * t), HEIGHT / 2 + r * math.sin(w * t)


def jitter(samples, after=1.0):
    """Spread (cm) of the output while the truth stays put: SD and the 95th percentile
    of the distance from its own mean."""
    points = [o for t, _, o, _ in samples if o and t >= after]
    mx, my = statistics.mean(p[0] for p in points), statistics.mean(p[1] for p in points)
    d = sorted(math.dist(p, (mx, my)) for p in points)
    return math.sqrt(statistics.mean(v * v for v in d)), d[int(0.95 * len(d))]


def error(samples, after=1.0):
    """RMS and 95th percentile of the distance from the truth (cm)."""
    d = sorted(math.dist(o, truth) for t, truth, o, _ in samples if o and t >= after)
    return math.sqrt(statistics.mean(v * v for v in d)), d[int(0.95 * len(d))]


def step_jump(samples, after=1.0):
    """Largest jump (cm) between consecutive outputs."""
    points = [o for t, _, o, _ in samples if o and t >= after]
    return max(math.dist(p, q) for p, q in zip(points, points[1:]))


def missing(samples, start, end):
    return sum(1 for t, _, o, _ in samples if start <= t < end and o is None)


class Smoothing(unittest.TestCase):
    def compare(self, **scenario):
        raw = run(bridge=make_bridge(on=False), **scenario)
        smooth = run(bridge=make_bridge(), **scenario)
        return raw, smooth

    def test_standing_still_is_much_steadier(self):
        raw, smooth = self.compare(path=still(400, 200), seconds=20)
        self.assertLess(jitter(smooth)[0], jitter(raw)[0] / 3)
        self.assertLess(jitter(smooth)[1], 10)  # 95% within 10 cm of its own center
        self.assertLess(step_jump(smooth), 10)  # no visible twitches
        self.assertLess(error(smooth)[0], 15)   # and in the right place

    def test_reflection_spikes_are_dropped(self):
        raw, smooth = self.compare(path=still(400, 200), seconds=20, spike=0.08)
        self.assertGreater(step_jump(raw), 50)
        self.assertLess(step_jump(smooth), 10)

    def test_blocked_anchor_is_outvoted(self):
        raw, smooth = self.compare(path=still(300, 150), seconds=20, blocked=4)
        self.assertLess(error(smooth)[0], error(raw)[0] / 2)
        self.assertLess(error(smooth)[0], 20)

    def test_walking_keeps_up(self):
        raw, smooth = self.compare(path=walk, seconds=30)
        # Smoothing must not cost accuracy on the move: no worse than raw.
        self.assertLess(error(smooth)[0], error(raw)[0] * 1.1)
        self.assertLess(error(smooth)[1], 40)

    def test_brief_dropout_holds_then_reports_missing(self):
        # Two anchors gone for 0.4 s, then for 1.5 s. Their readings stay usable for
        # 0.3 s, then the position is held for 0.5 s, then "N/A".
        gaps = [(5.0, 5.4, {1, 3}), (10.0, 11.5, {1, 3})]
        smooth = run(path=still(400, 200), seconds=14, bridge=make_bridge(), gaps=gaps, drop=0, spike=0)
        self.assertEqual(missing(smooth, 5.0, 5.5), 0)       # bridged
        self.assertEqual(missing(smooth, 10.0, 10.75), 0)    # bridged for 0.3 + 0.5 s
        self.assertGreater(missing(smooth, 10.85, 11.5), 0)  # then "N/A"
        self.assertEqual(missing(smooth, 11.6, 14.0), 0)     # and back
        held = [m for t, _, _, m in smooth if 10.35 <= t < 10.75]
        self.assertTrue(held and all(m['x'] != osc_bridge.MISSING for m in held))

    def test_hold_zero_reports_missing_once_readings_are_old(self):
        smooth = run(path=still(400, 200), seconds=8, bridge=make_bridge(hold_s=0.0),
                     gaps=[(5.0, 5.6, {1, 3})], drop=0, spike=0)
        self.assertEqual(missing(smooth, 5.0, 5.25), 0)      # readings still recent
        self.assertGreater(missing(smooth, 5.35, 5.6), 0)    # then "N/A" at once

    def test_old_readings_are_not_mixed_in_while_walking(self):
        # One anchor gets through only 1 time in 5 (as on the real hardware).
        def flaky(bridge):
            rng, real = random.Random(7), bridge.on_range
            def on_range(a, b, raw, f, t):
                if (a, b) != (TAG, 5) or rng.random() > 0.8:
                    real(a, b, raw, f, t)
            bridge.on_range = on_range
            return bridge
        raw = run(path=walk, seconds=30, bridge=flaky(make_bridge(on=False)))
        smooth = run(path=walk, seconds=30, bridge=flaky(make_bridge()))
        self.assertLess(error(smooth)[0], 25)
        self.assertLess(error(smooth)[1], 45)

    def test_comes_back_at_the_new_place_after_a_long_gap(self):
        # Out of range for 2 s and moved meanwhile: no slow glide from the old place.
        path = lambda t: (300, 150) if t < 6 else (650, 250)
        smooth = run(path=path, seconds=10, bridge=make_bridge(), gaps=[(5.0, 7.0, {1})], drop=0, spike=0)
        first = next(o for t, _, o, _ in smooth if t >= 7.0 and o)
        self.assertLess(math.dist(first, (650, 250)), 30)

    def test_real_jump_is_accepted(self):
        # Every reading is off by a jump the gate thinks is impossible (the first ones
        # were reflections): it must give in once the new readings agree.
        bridge = make_bridge()
        key = (1, TAG)
        for k in range(10):
            bridge.on_range(1, TAG, 300.0, 300.0, k * 0.05)
        accepted = [bridge.gate(key, 800.0, 0.5 + k * 0.05) for k in range(5)]
        self.assertEqual(accepted[:2], [False, False])
        self.assertTrue(any(accepted))

    def test_raw_mode_passes_spikes_smoothing_drops_them(self):
        for on, kept in ((False, 2000.0), (True, 300.0)):
            bridge = make_bridge(on=on)
            for k in range(5):
                bridge.on_range(1, TAG, 300.0, 300.0, k * 0.05)
            bridge.on_range(1, TAG, 2000.0, 2000.0, 0.25)  # a reflection
            self.assertEqual(bridge.ranges[(1, TAG)][0], kept)

    def test_slow_ranging_still_gives_positions(self):
        # Four tags with failing links: each pair reports only about twice a second.
        bridge = make_bridge()
        t = 0.0
        for cycle in range(20):
            for anchor in ANCHORS:
                t += 0.12
                bridge.on_range(min(anchor, TAG), max(anchor, TAG), math.dist(ANCHORS[anchor], (400, 200)), 0, t)
        self.assertNotEqual(bridge.last_message[1]['x'], osc_bridge.MISSING)
        self.assertAlmostEqual(to_cm(bridge.last_message[1])[0], 400, delta=5)

    def test_every_key_present(self):
        bridge = make_bridge()
        bridge.heartbeat(100.0)
        self.assertEqual(set(bridge.last_message[1]), {'x', 'y', 'inside'})


def report():
    rows = [
        ('standing still', dict(path=still(400, 200), seconds=20)),
        ('still, many spikes', dict(path=still(400, 200), seconds=20, spike=0.08)),
        ('still, A3 blocked', dict(path=still(300, 150), seconds=20, blocked=4)),
        ('walking 1.2 m/s', dict(path=walk, seconds=30)),
        ('walking, A3 blocked', dict(path=walk, seconds=30, blocked=4)),
    ]
    print(f'{"scenario":22} {"":9} {"jitter":>7} {"jit95":>7} {"error":>7} {"err95":>7} {"jump":>7}   (cm)')
    for name, scenario in rows:
        for label, bridge in (('raw', make_bridge(on=False)), ('smoothed', make_bridge())):
            samples = run(bridge=bridge, **scenario)
            moving = scenario['path'] is walk
            j = ('', '') if moving else tuple(f'{v:7.1f}' for v in jitter(samples))
            e = error(samples)
            print(f'{name if label == "raw" else "":22} {label:9} {j[0]:>7} {j[1]:>7} {e[0]:7.1f} {e[1]:7.1f} '
                  f'{step_jump(samples):7.1f}')


if __name__ == '__main__':
    if sys.argv[1:] == ['report']:
        report()
    else:
        unittest.main()
