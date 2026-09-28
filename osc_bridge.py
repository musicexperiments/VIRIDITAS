#!/usr/bin/env python3
"""Send each tag's position and its distances to the other tags as OSC, as fast
as the ranges arrive.

Anchor 1 pushes every new range to this program over UDP (no polling). For each
range that involves a tag, the tag is re-located and one OSC message goes out:

  /tag1 -> port 9000, /tag2 -> 9001, ... (tag N on base port + N - 1)
  argument: a JSON string {"x": .., "y": .., "d12": .., "d13": .., ...}

x and y run 0 to 1 across the anchors' grid (0 = left/bottom, 1 = right/top).
dNK is the directly measured distance from tag N to tag K, divided by the
farthest distance in the anchor shape (so 1 = as far apart as the shape allows).
A value that has not been read (no fresh range) is the string "N/A". Every
tag's port keeps sending, twice a second at least, with every key present, even
when that tag, anchor 1 or the anchor layout is unavailable.
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
LAYOUT = ROOT / 'web' / 'layout.json'
# Anchor 1 top-left, then clockwise; the same default as the website.
DEFAULT_FRAME = {1: (-1.0, 1.0), 3: (1.0, 1.0), 4: (1.0, -1.0), 5: (-1.0, -1.0)}
FRESH_S = 1.0  # A range older than this is not used.
MISSING = "N/A"


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
        self.anchor_history = {}  # (a, b) -> recent cm, for the fallback layout
        self.last_point = {}
        # Tags that always get messages: --tags N means /tag1 to /tagN, plus any
        # further tags anchor 1 reports.
        self.configured_tags = {2} | set(range(6, args.tags + 5))
        self.known_tags = set(self.configured_tags)
        self.sent = {}
        self.last_sent = {}  # tag node -> time of its last message
        self.layout_mtime = None
        self.load_layout()

    def load_layout(self):
        mtime = LAYOUT.stat().st_mtime if LAYOUT.exists() else None
        if mtime == self.layout_mtime and hasattr(self, 'frame'):
            return
        self.layout_mtime = mtime
        data = json.loads(LAYOUT.read_text()) if mtime else {}
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
        mapper = fit_affine(pos, self.frame)
        span = max((math.dist(pos[a], pos[b]) for a in pos for b in pos if a < b), default=0)
        self.geometry = (pos, mapper, span) if mapper and span else None

    def on_range(self, a, b, raw, filtered, now):
        cm = filtered if self.args.smooth else raw
        key = (min(a, b), max(a, b))
        self.ranges[key] = (cm, now)
        if not is_tag(a) and not is_tag(b):
            history = self.anchor_history.setdefault(key, [])
            history.append(filtered)
            del history[:-25]
            if not self.saved:
                self.geometry = None
            return
        for tag in (a, b):
            if is_tag(tag):
                self.send(tag, now)

    def heartbeat(self, now):
        """A tag with no new ranges (offline) still reports, with "N/A" values."""
        for tag in self.known_tags | self.configured_tags:
            if now - self.last_sent.get(tag, 0) >= 0.5:
                self.send(tag, now)

    def send(self, tag, now):
        if self.geometry is None:
            self.update_geometry()
        # Without a layout (no saved anchors, anchor 1 unreachable) everything is N/A,
        # but the message still goes out with every key.
        pos, mapper, span = self.geometry or ({}, None, 0)
        fresh = lambda k: k in self.ranges and now - self.ranges[k][1] < FRESH_S and span
        anchor_ranges = {}
        for anchor in pos:
            k = (min(tag, anchor), max(tag, anchor))
            if fresh(k):
                anchor_ranges[anchor] = self.ranges[k][0]
        message = {'x': MISSING, 'y': MISSING}
        if len(anchor_ranges) >= 3:
            start = self.last_point.get(tag) or (
                sum(pos[a][0] for a in anchor_ranges) / len(anchor_ranges),
                sum(pos[a][1] for a in anchor_ranges) / len(anchor_ranges))
            point = locate(pos, anchor_ranges, start)
            self.last_point[tag] = point
            gx, gy = mapper(point)
            x0, x1, y0, y1 = self.grid_box
            clamp = lambda v: min(1.0, max(0.0, v))
            message['x'] = round(clamp((gx - x0) / (x1 - x0)), 4)
            message['y'] = round(clamp((gy - y0) / (y1 - y0)), 4)
        me = tag_number(tag)
        seen = {n for pair in self.ranges for n in pair if is_tag(n)}
        others = sorted((seen | self.known_tags | self.configured_tags) - {tag}, key=tag_number)
        for other in others:
            k = (min(tag, other), max(tag, other))
            message[f'd{me}{tag_number(other)}'] = round(min(1.0, self.ranges[k][0] / span), 4) if fresh(k) else MISSING
        text = json.dumps(message, separators=(', ', ': '))
        self.osc.sendto(osc_message(f'/tag{me}', text), (self.args.osc_host, self.args.osc_port + me - 1))
        self.sent[me] = self.sent.get(me, 0) + 1
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
                bridge.known_tags = bridge.configured_tags | {n['id'] for n in json.load(response)['nodes'] if is_tag(n['id'])}
        except OSError as error:
            print(f'Could not subscribe to anchor 1 ({error}); retrying', flush=True)
            host = args.anchor
        stop.wait(5)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--anchor', default='10.10.10.183', help='anchor 1 IP or hostname')
    parser.add_argument('--listen-port', type=int, default=4210, help='UDP port anchor 1 streams to')
    parser.add_argument('--osc-host', default='127.0.0.1')
    parser.add_argument('--osc-port', type=int, default=9000, help='port for /tag1; tag N uses this + N - 1')
    parser.add_argument('--tags', type=int, default=4, help='always send /tag1 to /tagN (default 4)')
    parser.add_argument('--smooth', action='store_true', help='use the 5-reading median (steadier, ~0.5 s more lag)')
    args = parser.parse_args()

    bridge = Bridge(args)
    listener = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    listener.bind(('0.0.0.0', args.listen_port))
    listener.settimeout(0.1)
    stop = threading.Event()
    threading.Thread(target=subscribe, args=(args, stop, bridge), daemon=True).start()
    print(f'OSC out: /tagN -> {args.osc_host}:{args.osc_port}+N-1 · listening for anchor 1 on UDP {args.listen_port}'
          f' · {"median-smoothed" if args.smooth else "raw (lowest latency)"}', flush=True)
    last_report = time.monotonic()
    try:
        while True:
            try:
                data, _ = listener.recvfrom(512)
            except socket.timeout:
                data = b''
            now = time.monotonic()
            for line in data.decode(errors='replace').splitlines():
                parts = line.split(',')
                if len(parts) == 6 and parts[0] == 'R':
                    try:
                        bridge.on_range(int(parts[1]), int(parts[2]), float(parts[3]), float(parts[4]), now)
                    except ValueError:
                        pass
            bridge.heartbeat(now)
            if now - last_report >= 5:
                bridge.load_layout()
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
