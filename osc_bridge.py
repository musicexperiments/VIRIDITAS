#!/usr/bin/env python3
"""Send each tag's position and its distances to the other tags as OSC, as fast
as the ranges arrive.

Anchor 1 pushes every new range to this program over UDP (no polling). For each
range that involves a tag, the tag is re-located and one OSC message goes out:

  /tag1 -> port 9000, /tag2 -> 9001, ... (tag N on base port + N - 1)
  the same messages also go to 9100, 9101, ... for SuperCollider (--also-port)
  argument: a JSON string {"x": .., "y": .., "inside": ..}

x and y run -1 to 1 across the anchors' grid: A1 (-1, 1), A2 (1, 1), A3 (1, -1), A4 (-1, -1).
A value that has not been read (no fresh range) is the string "N/A". Every
tag's port keeps sending, twice a second at least, with every key present, even
when that tag, anchor 1 or the anchor layout is unavailable.

Smoothing (on by default; --raw or filter.json turns it off):
  1. Spikes: a tag reading that jumps further than a person can move since the
     last good one (a reflection) is dropped, unless the next readings agree on it.
  2. Outvoted anchor: with four anchors, one whose distance does not fit the
     other three (blocked by a body, say) is left out of that fix.
  3. One Euro filter on the position: heavy
     smoothing when still, less the faster the tag moves, so it keeps up.
  4. Fresh readings only: a fix uses readings from the last 0.3 s (not 1 s), as
     an older one is out of date for a walking tag; when one round of ranging
     takes longer (many tags, failing links), 1.5 x that round, up to 1 s.
  5. Hold: when a tag briefly has fewer than three anchors, its last position is
     sent for up to hold_s before "N/A".
The settings live in filter.json (uwb.py tunes them live); see FILTER_DEFAULTS.
"""
import argparse
import json
import math
import socket
import statistics
import threading
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
LAYOUT = ROOT / 'layout.json'  # Written by uwb.py's layout menu.
# Anchor 1 top-left, then clockwise.
DEFAULT_FRAME = {1: (-1.0, 1.0), 3: (1.0, 1.0), 4: (1.0, -1.0), 5: (-1.0, -1.0)}
FRESH_S = 1.0  # A range older than this is not used.
MISSING = "N/A"
FILTER = ROOT / 'filter.json'  # Smoothing settings, written by uwb.py.
FILTER_DEFAULTS = {
    'on': True,
    'still_hz': 0.3,   # One Euro cutoff at rest: lower is calmer when standing still
    'follow': 0.004,   # cutoff rise per cm/s of speed: higher keeps up faster when moving
    'hold_s': 0.5,     # keep the last position this long when anchors drop out; 0 = "N/A" at once
}
POSITION_AGE_S = 0.3   # with smoothing, a fix uses only readings this recent (an older one is
                       # out of date for a walking tag)...
AGE_PER_INTERVAL = 1.5  # ...or 1.5 x one round of ranging, when that is slower (many tags,
                       # failing links), up to FRESH_S
MAX_SPEED_CM_S = 400   # faster than anyone walks: a bigger jump in a reading is a reflection
GATE_MARGIN_CM = 30    # plus this much for noise
GATE_AGREE = 3         # this many rejected readings in a row that agree are a real jump
OUTVOTE_CM = 35        # an anchor reading this much longer than the others' fix is left out
EXCESS_ALPHA = 0.2     # how fast that excess is averaged, per fix
OUTVOTE_SWITCH_CM = 5  # another anchor must fit this much better to be left out instead


class OneEuro:
    """The One Euro filter (Casiez et al., 2012) for a point of any dimension:
    a low-pass whose cutoff rises with speed. dcutoff smooths the speed estimate."""

    def __init__(self, dcutoff=0.3):
        self.dcutoff, self.value, self.at = dcutoff, None, None

    @staticmethod
    def alpha(dt, cutoff):
        return 1.0 / (1.0 + 1.0 / (2 * math.pi * cutoff * dt))

    def __call__(self, value, now, still_hz, follow):
        if self.value is None or now - self.at > 1.0:
            self.value, self.speed, self.at = tuple(value), (0.0,) * len(value), now
            return self.value
        dt = max(now - self.at, 1e-3)
        self.at = now
        a = self.alpha(dt, self.dcutoff)
        self.speed = tuple(a * (v - p) / dt + (1 - a) * s for v, p, s in zip(value, self.value, self.speed))
        a = self.alpha(dt, still_hz + follow * math.hypot(*self.speed))
        self.value = tuple(a * v + (1 - a) * p for v, p in zip(value, self.value))
        return self.value


def is_tag(node):
    return node == 2 or node >= 6


def tag_number(node):
    return 1 if node == 2 else node - 4


def osc_string(text):
    data = text.encode() + b'\0'
    return data + b'\0' * (-len(data) % 4)


def osc_message(address, text):
    return osc_string(address) + osc_string(',s') + osc_string(text)


def solve3(m, b):
    """Solve a 3x3 linear system by Cramer's rule; None if singular."""
    def det(a):
        return (a[0][0] * (a[1][1] * a[2][2] - a[1][2] * a[2][1]) - a[0][1] * (a[1][0] * a[2][2] - a[1][2] * a[2][0])
                + a[0][2] * (a[1][0] * a[2][1] - a[1][1] * a[2][0]))
    d = det(m)
    if abs(d) < 1e-9:
        return None
    return [det([[b[i] if j == k else m[i][j] for j in range(3)] for i in range(3)]) / d for k in range(3)]


def fit_affine(pos, frame):
    """Least-squares map from anchor positions (cm) to their grid coordinates."""
    ids = [i for i in frame if i in pos]
    if len(ids) < 3:
        return None
    m = [[0.0] * 3 for _ in range(3)]
    bu, bv = [0.0] * 3, [0.0] * 3
    for i in ids:
        row = (pos[i][0], pos[i][1], 1.0)
        for r in range(3):
            for c in range(3):
                m[r][c] += row[r] * row[c]
            bu[r] += row[r] * frame[i][0]
            bv[r] += row[r] * frame[i][1]
    cu, cv = solve3(m, bu), solve3(m, bv)
    if not cu or not cv:
        return None
    return lambda p: (cu[0] * p[0] + cu[1] * p[1] + cu[2], cv[0] * p[0] + cv[1] * p[1] + cv[2])


def solve(a, b):
    """Gaussian elimination with partial pivoting; None if singular."""
    n = len(b)
    m = [list(row) + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[p][c]) < 1e-12:
            return None
        m[c], m[p] = m[p], m[c]
        for r in range(n):
            if r != c:
                f = m[r][c] / m[c][c]
                m[r] = [v - f * w for v, w in zip(m[r], m[c])]
    return [m[i][n] / m[i][i] for i in range(n)]


def convex(points):
    """True if the points, in order, make a convex polygon."""
    n = len(points)
    turns = [(points[(i + 1) % n][0] - points[i][0]) * (points[(i + 2) % n][1] - points[(i + 1) % n][1]) -
             (points[(i + 1) % n][1] - points[i][1]) * (points[(i + 2) % n][0] - points[(i + 1) % n][0])
             for i in range(n)]
    return all(t > 1e-9 for t in turns) or all(t < -1e-9 for t in turns)


def fit_grid(pos, frame):
    """Map from anchor positions (cm) to the grid. With four anchors forming a convex
    shape, a perspective map puts each anchor exactly on its grid corner, so any
    four-sided space spans -1 to 1. Otherwise the least-squares affine fit."""
    ids = [i for i in frame if i in pos]
    if len(ids) == 4:
        cx, cy = sum(frame[i][0] for i in ids) / 4, sum(frame[i][1] for i in ids) / 4
        ids.sort(key=lambda i: math.atan2(frame[i][1] - cy, frame[i][0] - cx))
        src, dst = [pos[i] for i in ids], [frame[i] for i in ids]
        if convex(src) and convex(dst):
            a, b = [], []
            for (x, y), (u, v) in zip(src, dst):
                a += [[x, y, 1, 0, 0, 0, -u * x, -u * y], [0, 0, 0, x, y, 1, -v * x, -v * y]]
                b += [u, v]
            h = solve(a, b)
            if h:
                def mapper(p):
                    w = h[6] * p[0] + h[7] * p[1] + 1
                    return ((h[0] * p[0] + h[1] * p[1] + h[2]) / w, (h[3] * p[0] + h[4] * p[1] + h[5]) / w)
                return mapper
    return fit_affine(pos, frame)


def build_shape(ids, d):
    """Anchor positions from anchor-anchor distances (used only without a saved layout)."""
    pairs = [(a, b) for a in ids for b in ids if a < b and d(a, b)]
    if not pairs:
        return None
    a0, a1 = pairs[0]
    pos = {a0: [0.0, 0.0], a1: [d(a0, a1), 0.0]}
    progress = True
    while progress:
        progress = False
        for k in ids:
            if k in pos:
                continue
            refs = [j for j in pos if d(j, k)]
            if len(refs) < 2:
                continue
            p, q = refs[0], refs[1]
            base = math.dist(pos[p], pos[q])
            if base < 1e-6:
                continue
            r1, r2 = d(p, k), d(q, k)
            a = (r1 * r1 - r2 * r2 + base * base) / (2 * base)
            h = math.sqrt(max(0.0, r1 * r1 - a * a))
            ex = ((pos[q][0] - pos[p][0]) / base, (pos[q][1] - pos[p][1]) / base)
            candidates = [[pos[p][0] + a * ex[0] - s * h * ex[1], pos[p][1] + a * ex[1] + s * h * ex[0]] for s in (1, -1)]
            error = lambda c: sum((math.dist(c, pos[j]) - d(j, k)) ** 2 for j in refs[2:])
            pos[k] = min(candidates, key=error)
            progress = True
    if any(i not in pos for i in ids):
        return None
    for _ in range(300):
        for i, j in pairs:
            P, Q = pos[i], pos[j]
            current = math.dist(P, Q) or 1e-6
            step = 0.1 * (current - d(i, j)) / current
            dx, dy = (Q[0] - P[0]) * step, (Q[1] - P[1]) * step
            P[0] += dx; P[1] += dy; Q[0] -= dx; Q[1] -= dy
    return pos


def fit_error(anchors, ranges, point):
    """Largest and RMS difference (cm) between each range and the point's distance."""
    errors = [abs(math.dist(point, anchors[a]) - r) for a, r in ranges.items()]
    return max(errors), math.sqrt(sum(e * e for e in errors) / len(errors))


def locate(anchors, ranges, start):
    """Gauss-Newton fit of a 2D point to its anchor distances, from `start`."""
    x, y = start
    for _ in range(15):
        jtj = [[0.0, 0.0], [0.0, 0.0]]
        jtr = [0.0, 0.0]
        for a, r in ranges.items():
            ax, ay = anchors[a]
            dist = math.hypot(x - ax, y - ay) or 1e-6
            jx, jy, e = (x - ax) / dist, (y - ay) / dist, dist - r
            jtj[0][0] += jx * jx; jtj[0][1] += jx * jy; jtj[1][1] += jy * jy
            jtr[0] += jx * e; jtr[1] += jy * e
        jtj[1][0] = jtj[0][1]
        det = jtj[0][0] * jtj[1][1] - jtj[0][1] ** 2
        if abs(det) < 1e-9:
            break
        dx = (jtj[1][1] * jtr[0] - jtj[0][1] * jtr[1]) / det
        dy = (jtj[0][0] * jtr[1] - jtj[1][0] * jtr[0]) / det
        x, y = x - dx, y - dy
        if abs(dx) + abs(dy) < 0.05:
            break
    return x, y


class Bridge:
    def __init__(self, args):
        self.args = args
        self.osc = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.ranges = {}         # (a, b) -> (cm, time)
        self.interval = {}       # (a, b) -> average time between its readings (s)
        self.anchor_history = {}  # (a, b) -> recent cm, for the fallback layout
        self.last_point = {}
        # Tags that always get messages: --tags N means /tag1 to /tagN, plus any
        # further tags anchor 1 reports.
        self.configured_tags = {2} | set(range(6, args.tags + 5))
        self.known_tags = set(self.configured_tags)
        self.sent = {}
        self.total_sent = 0
        self.last_message = {}  # tag number -> the last message sent
        self.last_sent = {}  # tag node -> time of its last message
        self.layout_mtime = None
        self.filter_mtime = None
        self.tuning = dict(FILTER_DEFAULTS, on=not getattr(args, 'raw', False))
        self.gate_last = {}      # (a, b) -> the last three accepted (cm, time)
        self.gate_pending = {}   # (a, b) -> rejected readings since then
        self.point_filter = {}   # tag node -> OneEuro on its position (cm)
        self.held = {}           # tag node -> (x, y, inside, time of the fix)
        self.excess = {}         # tag node -> anchor -> its average excess reading (cm)
        self.agreement = {}      # tag node -> anchor -> average fit error of the others (cm)
        self.blocked = {}        # tag node -> the anchor left out of its last fix
        self.stats = {}          # tag node -> {'spikes': n, 'outvoted': anchor or None, 'held': bool}
        self.nodes = {}           # node id -> online, as anchor 1 last reported
        self.anchor_error = None  # Why anchor 1 cannot be reached, or None.
        self.load_layout()

    def load_filter(self):
        mtime = FILTER.stat().st_mtime if FILTER.exists() else None
        if mtime is None or mtime == self.filter_mtime:
            return
        self.filter_mtime = mtime
        try:
            data = json.loads(FILTER.read_text())
        except ValueError:
            return
        for key, default in FILTER_DEFAULTS.items():
            if isinstance(data.get(key), type(default)):
                self.tuning[key] = data[key]
        if getattr(self.args, 'raw', False):
            self.tuning['on'] = False

    def save_filter(self):
        FILTER.write_text(json.dumps(self.tuning))
        self.filter_mtime = FILTER.stat().st_mtime

    def load_layout(self):
        mtime = LAYOUT.stat().st_mtime if LAYOUT.exists() else None
        if mtime == self.layout_mtime and hasattr(self, 'frame'):
            return
        self.layout_mtime = mtime
        data = json.loads(LAYOUT.read_text()) if mtime else {}
        self.distances = data.get('distances', {})  # Tape-measured, "a-b" -> cm.
        self.saved = {int(k): tuple(v) for k, v in data.get('anchors', {}).items()} or None
        self.frame = {int(k): tuple(v) for k, v in data.get('frame', {}).items()} or DEFAULT_FRAME
        xs = [g[0] for g in self.frame.values()]; ys = [g[1] for g in self.frame.values()]
        self.grid_box = (min(xs), max(xs), min(ys), max(ys))
        self.geometry = None

    def anchor_positions(self):
        if self.saved:
            return self.saved
        ids = sorted({n for pair in self.anchor_history for n in pair})
        d = lambda a, b: statistics.median(self.anchor_history.get((min(a, b), max(a, b)), [0])) or 0
        return build_shape(ids, d)

    def update_geometry(self):
        pos = self.anchor_positions()
        if not pos:
            self.geometry = None
            return
        mapper = fit_grid(pos, self.frame)
        span = max((math.dist(pos[a], pos[b]) for a in pos for b in pos if a < b), default=0)
        self.geometry = (pos, mapper, span) if mapper and span else None

    def gate(self, key, cm, now):
        """False for a reading that jumps further than a person can move (a spike).
        It is compared with the median of the last three accepted readings, so a
        spike that slipped through cannot make the good readings after it look bad."""
        recent = self.gate_last.get(key, [])
        if recent and now - recent[-1][1] < FRESH_S:
            reference = statistics.median(r[0] for r in recent)
            if abs(cm - reference) > MAX_SPEED_CM_S * (now - recent[-1][1]) + GATE_MARGIN_CM:
                pending = self.gate_pending.setdefault(key, [])
                pending.append(cm)
                del pending[:-GATE_AGREE]
                # A real jump (the first reading was the bad one, or the tag came out
                # from behind something) keeps reading the same: accept it then.
                if len(pending) < GATE_AGREE or max(pending) - min(pending) > 2 * GATE_MARGIN_CM:
                    for tag in filter(is_tag, key):
                        stats = self.stats.setdefault(tag, {})
                        stats['spikes'] = stats.get('spikes', 0) + 1
                    return False
        self.gate_pending.pop(key, None)
        if recent and now - recent[-1][1] >= FRESH_S:
            recent = []
        self.gate_last[key] = (recent + [(cm, now)])[-3:]
        return True

    def on_range(self, a, b, raw, filtered, now):
        cm = filtered if self.args.smooth else raw
        key = (min(a, b), max(a, b))
        tag_pair = is_tag(a) or is_tag(b)
        if tag_pair and self.tuning['on'] and not self.gate(key, cm, now):
            return
        if key in self.ranges:
            gap = now - self.ranges[key][1]
            if gap < FRESH_S:
                average = self.interval.get(key, gap)
                self.interval[key] = average + 0.2 * (gap - average)
        self.ranges[key] = (cm, now)
        if not tag_pair:
            history = self.anchor_history.setdefault(key, [])
            history.append(filtered)
            del history[:-25]
            if not self.saved:
                self.geometry = None
            return
        for tag in (a, b):
            if is_tag(tag):
                self.send(tag, now)

    def feed(self, data, now):
        """Handle one UDP packet from anchor 1: lines of "R,a,b,raw_cm,filtered_cm,seq"."""
        for line in data.decode(errors='replace').splitlines():
            parts = line.split(',')
            if len(parts) == 6 and parts[0] == 'R':
                try:
                    self.on_range(int(parts[1]), int(parts[2]), float(parts[3]), float(parts[4]), now)
                except ValueError:
                    pass

    def range_cm(self, a, b, now):
        """The latest fresh reading between two nodes, or None."""
        reading = self.ranges.get((min(a, b), max(a, b)))
        return reading[0] if reading and now - reading[1] < FRESH_S else None

    def heartbeat(self, now):
        """A tag with no new ranges (offline) still reports, with "N/A" values."""
        for tag in self.known_tags | self.configured_tags:
            if now - self.last_sent.get(tag, 0) >= 0.5:
                self.send(tag, now)

    def outvote(self, tag, pos, ranges, point):
        """With four or more anchors, leave out one that reads too long for where the
        others put the tag (blocked by a body, say). Returns the fix and the anchor
        left out, or None.

        For each anchor, the other anchors fix the tag; two running averages are
        kept: how much longer the anchor reads than that fix (a blocked signal takes
        a longer path) and how well the others agree with each other. Opposite
        corners look alike (one reading long shifts the fix like the other reading
        short), so of the anchors reading long, the one whose others agree best is
        left out, and the same anchor stays left out unless another is clearly
        better."""
        excess = self.excess.setdefault(tag, {})
        agree = self.agreement.setdefault(tag, {})
        fits = {}
        for anchor in ranges:
            rest = {a: r for a, r in ranges.items() if a != anchor}
            fits[anchor] = locate(pos, rest, point)
            over = ranges[anchor] - math.dist(fits[anchor], pos[anchor])
            spread = fit_error(pos, rest, fits[anchor])[1]
            excess[anchor] = excess.get(anchor, over) + EXCESS_ALPHA * (over - excess.get(anchor, over))
            agree[anchor] = agree.get(anchor, spread) + EXCESS_ALPHA * (spread - agree.get(anchor, spread))
        long = [a for a in ranges if excess[a] > OUTVOTE_CM]
        previous = self.blocked.get(tag)
        if not long:
            self.blocked.pop(tag, None)
            return point, None
        anchor = min(long, key=agree.get)
        if previous in long and agree[anchor] > agree[previous] - OUTVOTE_SWITCH_CM:
            anchor = previous
        rest = {a: r for a, r in ranges.items() if a != anchor}
        if fit_error(pos, rest, fits[anchor])[1] >= OUTVOTE_CM / 2:  # the other three disagree too
            self.blocked.pop(tag, None)
            return point, None
        self.blocked[tag] = anchor
        return fits[anchor], anchor

    def send(self, tag, now):
        if self.geometry is None:
            self.update_geometry()
        # Without a layout (no saved anchors, anchor 1 unreachable) everything is N/A,
        # but the message still goes out with every key.
        pos, mapper, span = self.geometry or ({}, None, 0)
        fresh = lambda k, age=FRESH_S: k in self.ranges and now - self.ranges[k][1] < age and span
        # How long one round of ranging takes, from the tag's best-reporting anchor
        # (a flaky anchor's rare readings must not stretch it).
        keys = [(min(tag, a), max(tag, a)) for a in pos]
        cycle = min((self.interval[k] for k in keys if k in self.interval), default=0)
        age = min(FRESH_S, max(POSITION_AGE_S, AGE_PER_INTERVAL * cycle)) if self.tuning['on'] else FRESH_S
        anchor_ranges = {}
        for anchor in pos:
            k = (min(tag, anchor), max(tag, anchor))
            if fresh(k, age):
                anchor_ranges[anchor] = self.ranges[k][0]
        message = {'x': MISSING, 'y': MISSING, 'inside': MISSING}
        tuning, stats = self.tuning, self.stats.setdefault(tag, {})
        stats['outvoted'], stats['held'] = None, False
        if len(anchor_ranges) >= 3:
            start = self.last_point.get(tag) or (
                sum(pos[a][0] for a in anchor_ranges) / len(anchor_ranges),
                sum(pos[a][1] for a in anchor_ranges) / len(anchor_ranges))
            point = locate(pos, anchor_ranges, start)
            if tuning['on'] and len(anchor_ranges) >= 4:
                point, stats['outvoted'] = self.outvote(tag, pos, anchor_ranges, point)
            self.last_point[tag] = point
            if tuning['on']:
                smoother = self.point_filter.setdefault(tag, OneEuro())
                point = smoother(point, now, tuning['still_hz'], tuning['follow'])
            gx, gy = mapper(point)
            x0, x1, y0, y1 = self.grid_box
            x, y = 2 * (gx - x0) / (x1 - x0) - 1, 2 * (gy - y0) / (y1 - y0) - 1
            clamp = lambda v: min(1.0, max(-1.0, v))
            message['x'] = round(clamp(x), 4) + 0.0  # + 0.0 turns -0.0 into 0.0
            message['y'] = round(clamp(y), 4) + 0.0
            message['inside'] = int(-1 <= x <= 1 and -1 <= y <= 1)
            self.held[tag] = (message['x'], message['y'], message['inside'], now)
        elif tuning['on'] and tag in self.held and now - self.held[tag][3] <= tuning['hold_s']:
            message['x'], message['y'], message['inside'], _ = self.held[tag]
            stats['held'] = True
        else:
            # Gone for longer than the hold: start the smoothing afresh when it is back.
            self.point_filter.pop(tag, None)
        me = tag_number(tag)
        text = json.dumps(message, separators=(', ', ': '))
        packet = osc_message(f'/tag{me}', text)
        for base in [self.args.osc_port] + self.args.also_port:
            self.osc.sendto(packet, (self.args.osc_host, base + me - 1))
        self.last_message[me] = message
        self.sent[me] = self.sent.get(me, 0) + 1
        self.total_sent += 1
        self.last_sent[tag] = now


def subscribe(args, stop, bridge):
    """Keep Anchor 1 streaming to us (the lease is 15 s; renew every 5 s), and
    learn which tags exist so each message lists every other tag."""
    host = args.anchor
    while not stop.is_set():
        try:
            if not host[0].isdigit():
                host = socket.getaddrinfo(args.anchor, 80, socket.AF_INET)[0][4][0]
            request = urllib.request.Request(f'http://{host}/api/stream?port={args.listen_port}', data=b'')
            urllib.request.urlopen(request, timeout=3).read()
            with urllib.request.urlopen(f'http://{host}/api/ranges', timeout=3) as response:
                nodes = json.load(response)['nodes']
            bridge.nodes = {n['id']: n['online'] for n in nodes}
            bridge.known_tags = bridge.configured_tags | {n['id'] for n in nodes if is_tag(n['id'])}
            bridge.anchor_error = None
        except (OSError, ValueError, KeyError) as error:
            bridge.anchor_error = str(error)
            bridge.nodes = {}
            host = args.anchor
        stop.wait(5)


def make_parser(description=__doc__):
    parser = argparse.ArgumentParser(description=description, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--anchor', default='10.10.10.183', help='anchor 1 IP or hostname')
    parser.add_argument('--listen-port', type=int, default=4210, help='UDP port anchor 1 streams to')
    parser.add_argument('--osc-host', default='127.0.0.1')
    parser.add_argument('--osc-port', type=int, default=9000, help='port for /tag1; tag N uses this + N - 1')
    parser.add_argument('--also-port', type=int, nargs='*', default=[9100],
                        help='extra base ports that get the same messages (default 9100, for SuperCollider)')
    parser.add_argument('--tags', type=int, default=4, help='always send /tag1 to /tagN (default 4)')
    parser.add_argument('--smooth', action='store_true',
                        help="use anchor 1's 5-reading median for every range (steadier, ~0.5 s more lag)")
    parser.add_argument('--raw', action='store_true',
                        help='turn off the spike, outvote, One Euro and hold filtering (see filter.json)')
    return parser


def start(args):
    """The bridge, a socket bound to anchor 1's stream, and the stop event for the subscriber."""
    bridge = Bridge(args)
    bridge.load_filter()
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.bind(('0.0.0.0', args.listen_port))
    stop = threading.Event()
    threading.Thread(target=subscribe, args=(args, stop, bridge), daemon=True).start()
    return bridge, listener, stop


def main():
    args = make_parser().parse_args()
    bridge, listener, stop = start(args)
    listener.settimeout(0.1)
    print(f'OSC out: /tagN -> {args.osc_host}:' + ', '.join(f'{p}+N-1' for p in [args.osc_port] + args.also_port) + f' · listening for anchor 1 on UDP {args.listen_port}'
          f' · {"median ranges" if args.smooth else "raw ranges"}'
          f' · smoothing {"on" if bridge.tuning["on"] else "off"}', flush=True)
    last_report = time.monotonic()
    last_error = None
    try:
        while True:
            try:
                data, _ = listener.recvfrom(512)
            except socket.timeout:
                data = b''
            now = time.monotonic()
            bridge.feed(data, now)
            bridge.heartbeat(now)
            if bridge.anchor_error != last_error:
                last_error = bridge.anchor_error
                print(f'Could not subscribe to anchor 1 ({last_error}); retrying' if last_error
                      else 'Subscribed to anchor 1', flush=True)
            if now - last_report >= 5:
                bridge.load_layout()
                bridge.load_filter()
                rates = ', '.join(f'/tag{t} {n / (now - last_report):.0f}/s' for t, n in sorted(bridge.sent.items()))
                print(f'Sending: {rates or "nothing yet (waiting for ranges)"}', flush=True)
                bridge.sent.clear()
                last_report = now
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()


if __name__ == '__main__':
    main()
