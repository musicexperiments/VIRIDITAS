#!/usr/bin/env python3
"""Serve the distance and calibration pages locally and forward /api to the anchor."""
import argparse
import http.server
import json
import math
import socket
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PAGES = {'/': 'index.html', '/index.html': 'index.html',
         '/calibrate': 'calibrate.html', '/calibrate.html': 'calibrate.html'}
API = ('/api/distance', '/api/ranges', '/api/antenna-delay', '/api/tag-update')
SCRIPTS = {'/correction.js': 'correction.js'}
CORRECTION = ROOT / 'correction.json'
LAYOUT = ROOT / 'layout.json'


def valid_correction(data):
    """{} clears it; otherwise {"delay": int, "points": [[measured_cm, actual_cm], ...]}."""
    if data == {}:
        return True
    try:
        points, delay = data['points'], data['delay']
        numbers = [float(v) for point in points for v in point]
        return (isinstance(delay, int) and 0 <= delay <= 0xFFFF and 2 <= len(points) <= 50
                and all(len(point) == 2 for point in points)
                and all(math.isfinite(v) and 0 <= v <= 10000 for v in numbers)
                and all(a[0] < b[0] for a, b in zip(points, points[1:])))
    except (KeyError, TypeError, ValueError):
        return False


def valid_points(points, minimum):
    return (isinstance(points, dict) and minimum <= len(points) <= 10
            and all(key.isdigit() and 1 <= int(key) <= 255 for key in points)
            and all(isinstance(p, list) and len(p) == 2
                    and all(math.isfinite(float(v)) and abs(float(v)) <= 100000 for v in p)
                    for p in points.values()))


def valid_distances(distances):
    return (isinstance(distances, dict) and 1 <= len(distances) <= 45
            and all(isinstance(k, str) and k.count('-') == 1 and all(part.isdigit() for part in k.split('-'))
                    for k in distances)
            and all(isinstance(v, (int, float)) and math.isfinite(v) and 0 < v <= 100000
                    for v in distances.values()))


def valid_layout(data):
    """{} clears it. "anchors": positions in cm built from "distances" (tape-measured
    anchor-anchor cm, keyed "a-b"); "frame": grid coordinates the anchors stand for.
    Point maps are node id -> [x, y] for 3-10 anchors."""
    try:
        return (isinstance(data, dict) and set(data) <= {'anchors', 'frame', 'distances'}
                and all(valid_points(data[k], 3) for k in ('anchors', 'frame') if k in data)
                and ('distances' not in data or valid_distances(data['distances'])))
    except (TypeError, ValueError):
        return False


STORES = {'/api/correction': (CORRECTION, valid_correction), '/api/layout': (LAYOUT, valid_layout)}


class Anchor:
    """Resolve the anchor's name once; .local lookups can take seconds each."""

    def __init__(self, host):
        self.host, self.address = host, None

    def url(self, path):
        if self.address is None:
            self.address = socket.getaddrinfo(self.host, 80, socket.AF_INET)[0][4][0]
            print(f'Anchor {self.host} -> {self.address}', flush=True)
        return f'http://{self.address}{path}'

    def forget(self):
        self.address = None


class Handler(http.server.BaseHTTPRequestHandler):
    anchor = None

    def log_message(self, *args):
        pass

    def reply(self, code, body, content_type):
        self.send_response(code)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def forward(self, data=None):
        path = self.path.split('?', 1)[0]
        if path not in API:
            return self.reply(404, b'Not found', 'text/plain')
        try:
            request = urllib.request.Request(self.anchor.url(self.path), data=data)
            if data is not None:
                request.add_header('Content-Type', 'application/x-www-form-urlencoded')
            with urllib.request.urlopen(request, timeout=3) as response:
                self.reply(response.status, response.read(),
                           response.headers.get('Content-Type', 'application/json'))
        except urllib.error.HTTPError as error:
            self.reply(error.code, error.read(), error.headers.get('Content-Type', 'text/plain'))
        except (OSError, ValueError) as error:
            # The anchor may have a new address after a reboot; look it up again.
            self.anchor.forget()
            self.reply(502, f'Anchor unreachable: {error}'.encode(), 'text/plain')

    def do_GET(self):
        page = PAGES.get(self.path.split('?', 1)[0])
        if page:
            return self.reply(200, (ROOT / page).read_bytes(), 'text/html; charset=utf-8')
        script = SCRIPTS.get(self.path.split('?', 1)[0])
        if script:
            return self.reply(200, (ROOT / script).read_bytes(), 'text/javascript; charset=utf-8')
        if self.path in STORES:
            path = STORES[self.path][0]
            return self.reply(200, path.read_bytes() if path.exists() else b'{}', 'application/json')
        self.forward()

    def do_POST(self):
        length = int(self.headers.get('Content-Length') or 0)
        body = self.rfile.read(length)
        if self.path in STORES:
            path, valid = STORES[self.path]
            try:
                data = json.loads(body)
            except ValueError:
                data = None
            if not valid(data):
                return self.reply(400, b'Invalid data', 'text/plain')
            path.write_text(json.dumps(data))
            return self.reply(200, b'{"saved":true}', 'application/json')
        self.forward(body)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--anchor', default='uwb-anchor.local',
                        help='anchor hostname or IP address (default: uwb-anchor.local)')
    parser.add_argument('--port', type=int, default=8000)
    args = parser.parse_args()
    Handler.anchor = Anchor(args.anchor)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    print(f'Open http://localhost:{args.port}  (calibration: http://localhost:{args.port}/calibrate)',
          flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
