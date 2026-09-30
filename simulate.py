#!/usr/bin/env python3
"""Simulate people walking through the anchor space and send the same OSC as
osc_bridge.py, so software can be written and tested without the hardware.

  python3 simulate.py        # menu: shape, size, number of people

A single file with no dependencies beyond Python 3 (standard library only).

Each person is a tag: /tagN on UDP port 8999 + N (/tag1 on 9000, /tag2 on
9001, ...) at 127.0.0.1, one JSON string argument {"x": .., "y": .., "inside": .., "dNK": ..}.
x and y run -1 to 1 across the shape (A1 (-1, 1), A2 (1, 1), A3 (1, -1), A4 (-1, -1)); dNK is
the distance from tag N to tag K divided by the shape's diagonal. The data
behaves like the hardware: a few centimetres of noise, an occasional missing
tag-to-tag reading, and "N/A" when two people are within a few inches.
Anchor 1 is the top-left corner, then clockwise, as on the website.

/tag1-/tag4 always send, even with fewer people: a tag with nobody sends
every key as "N/A". The people you choose stay online the whole time.

On start it opens one Terminal window per port showing what that path receives (macOS; on
other systems run `python3 simulate.py --monitor 9000` etc. yourself). The
arrow keys switch to fully manual: everyone stops, readings have no noise,
and each press moves one person (1-8 picks which); a lets everyone wander again. q quits and closes those windows. Start your own receiving software after the
simulator, or close the port windows first.
"""
import argparse
import curses
import json
import math
import random
import os
import signal
import socket
import struct
import subprocess
import sys
import time

MISSING = 'N/A'
SELF = os.path.abspath(__file__)


def osc_string(text):
    data = text.encode() + b'\0'
    return data + b'\0' * (-len(data) % 4)


def osc_message(address, text):
    """An OSC message with one string argument."""
    return osc_string(address) + osc_string(',s') + osc_string(text)


def monitor(port):
    """Print every OSC message arriving on `port` (used for the port windows)."""
    def read_string(data, offset):
        end = data.index(b'\0', offset)
        return data[offset:end].decode(errors='replace'), (end + 4) & ~3
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', port))
    sys.stdout.write(f'\33]0;OSC port {port}\a')  # Window title.
    print(f'Listening for OSC on UDP {port} (Ctrl-C to stop)', flush=True)
    while True:
        data = sock.recvfrom(4096)[0]
        try:
            address, offset = read_string(data, 0)
            tags, offset = read_string(data, offset)
            text = read_string(data, offset)[0] if tags.startswith(',s') else ''
        except (ValueError, struct.error):
            continue
        print(f'{time.strftime("%H:%M:%S")}  {address}  {text}', flush=True)

FT = 30.48             # cm per foot
SEND_HZ = 20            # messages per tag per second, like the real bridge
NOISE_CM = 3.0          # UWB-like noise
DROP_RATE = 0.03        # chance a tag-to-tag reading is missing
TOO_CLOSE_CM = 8.0      # tags this close cannot range each other
HOST, FIRST_PORT = '127.0.0.1', 9000  # /tag1 -> 9000, /tag2 -> 9001, ...
SC_FIRST_PORT = 9100  # the same messages for SuperCollider: /tag1 -> 9100, ...
MIN_TAGS = 4  # Like the real bridge, /tag1-/tag4 always send; a tag with no person is all "N/A".
TRAIL = 14
NUDGE_FT = 0.25        # one arrow-key press; held keys repeat at about walking pace


class Person:
    """Wanders the space with curiosity: picks something to look at (a spot in
    the space, another person, or somewhere visited before), weaves toward it
    at a browsing or walking pace, lingers and looks around, then moves on."""

    def __init__(self, number, width, height, rng):
        self.number, self.width, self.height, self.rng = number, width, height, rng
        self.x, self.y = self.random_point()
        self.heading = rng.uniform(-math.pi, math.pi)
        self.turn = 0.0          # Wandering turn rate (rad/s), drifts randomly.
        self.speed = 0.0
        self.linger = rng.uniform(0.5, 2.0)
        self.visited = []
        self.target = None
        self.cruise = 0.0
        self.trail = []
        self.manual = False     # Moved by the arrow keys instead of wandering.

    def margin(self):
        # Destinations stay out of the edges: about 12% of the size in from each wall.
        return max(min(0.6, self.width / 5, self.height / 5), 0.12 * min(self.width, self.height))

    def random_point(self):
        m = self.margin()
        return (self.rng.uniform(m, self.width - m), self.rng.uniform(m, self.height - m))

    def choose_target(self, others):
        """Decide what to go and look at next."""
        m, r = self.margin(), self.rng.random()
        if r < 0.60:
            target = self.random_point()
        elif r < 0.85 and others:  # Wander over toward someone (stopping short of them).
            other = self.rng.choice(others)
            angle = self.rng.uniform(-math.pi, math.pi)
            gap = self.rng.uniform(1.5, 3.0)
            target = (min(self.width - m, max(m, other.x + gap * math.cos(angle))),
                      min(self.height - m, max(m, other.y + gap * math.sin(angle))))
        elif self.visited:  # Go back to have another look.
            target = self.rng.choice(self.visited)
        else:
            target = self.random_point()
        self.target = target
        # Browsing (~0.8 m/s) or walking with purpose (~1.3 m/s).
        self.cruise = self.rng.uniform(2.3, 3.0) if self.rng.random() < 0.4 else self.rng.uniform(3.8, 4.8)

    def step(self, dt, others=()):
        rng = self.rng
        if self.target is None:
            if self.linger > 0:  # Looking around: shift weight, turn a little.
                self.linger -= dt
                self.heading += rng.gauss(0, 1.5) * dt
                self.x += rng.gauss(0, 0.15) * dt
                self.y += rng.gauss(0, 0.15) * dt
                self.keep_inside()
                return
            self.choose_target([o for o in others if o is not self])

        dx, dy = self.target[0] - self.x, self.target[1] - self.y
        remaining = math.hypot(dx, dy)
        if remaining < 0.35:
            self.visited = (self.visited + [self.target])[-6:]
            self.target = None
            self.speed = 0.0
            self.linger = rng.uniform(1.0, 3.0) if rng.random() < 0.35 else rng.uniform(0.1, 0.5)
            return

        # Weave: a slowly drifting turn rate, plus steering toward the target
        # (stronger when close so they still arrive).
        self.turn += rng.gauss(0, 2.0) * dt - self.turn * 0.8 * dt
        want = math.atan2(dy, dx)
        error = (want - self.heading + math.pi) % (2 * math.pi) - math.pi
        pull = 1.2 + 3.0 / max(remaining, 0.5)
        self.heading += (error * pull + self.turn) * dt
        # Walls turn them back gently.
        m = self.margin()
        push_x = (m + 0.8 - self.x) if self.x < m + 0.8 else (self.width - m - 0.8 - self.x) if self.x > self.width - m - 0.8 else 0
        push_y = (m + 0.8 - self.y) if self.y < m + 0.8 else (self.height - m - 0.8 - self.y) if self.y > self.height - m - 0.8 else 0
        if push_x or push_y:
            away = math.atan2(push_y, push_x)
            self.heading += ((away - self.heading + math.pi) % (2 * math.pi) - math.pi) * 1.5 * dt
        # Ease into speed, slow when arriving or turning sharply.
        goal = self.cruise * min(1.0, 0.3 + remaining / 1.2) * (0.75 + 0.25 * math.cos(min(abs(error), math.pi / 2)))
        self.speed += (goal - self.speed) * min(1.0, 4.0 * dt)
        self.x += math.cos(self.heading) * self.speed * dt
        self.y += math.sin(self.heading) * self.speed * dt
        self.keep_inside()

    def nudge(self, dx, dy):
        """Arrow-key override: move by hand and stop wandering until released."""
        self.manual, self.target, self.speed = True, None, 0.0
        self.x += dx
        self.y += dy
        if dx or dy:
            self.heading = math.atan2(dy, dx)
        self.keep_inside()

    def release(self):
        """Back to wandering, after a short look around."""
        self.manual, self.linger = False, self.rng.uniform(0.3, 1.0)

    def keep_inside(self):
        self.x = min(self.width - 0.05, max(0.05, self.x))
        self.y = min(self.height - 0.05, max(0.05, self.y))


class Simulation:
    def __init__(self, config):
        self.config = config
        self.width, self.height = config['width'], config['height']
        self.diagonal = math.hypot(self.width, self.height)
        self.rng = random.Random(config.get('seed'))
        self.people = [Person(n, self.width, self.height, self.rng) for n in range(1, config['people'] + 1)]
        self.tag_count = max(MIN_TAGS, len(self.people))
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.last_messages = {}
        self.sent = 0
        self.controlled = 1  # The person the arrow keys move.
        self.manual = False  # Arrow keys in use: nobody wanders and readings are exact.

    def noisy(self, value_ft):
        return value_ft if self.manual else value_ft + self.rng.gauss(0, NOISE_CM) / FT

    def measure_pairs(self):
        """One reading per pair of tags, shared by both tags (as on the hardware)."""
        readings = {}
        for i, a in enumerate(self.people):
            for b in self.people[i + 1:]:
                distance = math.hypot(a.x - b.x, a.y - b.y)
                missing = distance * FT < TOO_CLOSE_CM or (not self.manual and self.rng.random() < DROP_RATE)
                readings[(a.number, b.number)] = (
                    MISSING if missing else round(min(1.0, max(0.0, self.noisy(distance)) / self.diagonal), 4))
        return readings

    def message(self, number, readings):
        """Every key is always present; unavailable values are "N/A"."""
        person = self.people[number - 1] if number <= len(self.people) else None
        if person is None:
            data = {'x': MISSING, 'y': MISSING, 'inside': MISSING}
        else:
            x = min(1.0, max(-1.0, 2 * self.noisy(person.x) / self.width - 1))
            y = min(1.0, max(-1.0, 2 * self.noisy(person.y) / self.height - 1))
            data = {'x': round(x, 4) + 0.0, 'y': round(y, 4) + 0.0, 'inside': 1}  # People never leave the shape; + 0.0 avoids -0.0.
        for other in range(1, self.tag_count + 1):
            if other != number:
                data[f'd{number}{other}'] = readings.get((min(number, other), max(number, other)), MISSING)
        return data

    def send_all(self):
        readings = self.measure_pairs()
        for number in range(1, self.tag_count + 1):
            data = self.message(number, readings)
            text = json.dumps(data, separators=(', ', ': '))
            packet = osc_message(f'/tag{number}', text)
            for first in (FIRST_PORT, SC_FIRST_PORT):
                self.sock.sendto(packet, (HOST, first + number - 1))
            self.last_messages[number] = data
            self.sent += 1

    def step(self, dt):
        for person in self.people:
            if not self.manual:
                person.step(dt, self.people)
            person.trail.append((person.x, person.y))
            del person.trail[:-TRAIL]


# ---------- Menu ----------

def ask(prompt, choices=None, default=None, kind=str, low=None, high=None):
    while True:
        suffix = f' [{default}]' if default is not None else ''
        answer = input(f'{prompt}{suffix}: ').strip() or (str(default) if default is not None else '')
        if choices:
            if answer in choices:
                return choices[answer]
            print('  Choose one of: ' + ', '.join(choices))
            continue
        try:
            value = kind(answer)
        except ValueError:
            print('  Please enter a number.')
            continue
        if (low is not None and value < low) or (high is not None and value > high):
            print(f'  Enter a value from {low} to {high}.')
            continue
        return value


def menu():
    print('\nVIRIDITAS movement simulator\n' + '=' * 28)
    print('Shape:  1) Square   2) Rectangle')
    shape = ask('Choose shape', {'1': 'square', '2': 'rectangle', 'square': 'square', 'rectangle': 'rectangle'}, '1')
    if shape == 'square':
        side = ask('Side length (ft)', kind=float, low=1, high=500)
        width = height = side
    else:
        width = ask('Width, Anchor 1 to Anchor 2 (ft)', kind=float, low=1, high=500)
        height = ask('Height, Anchor 2 to Anchor 3 (ft)', kind=float, low=1, high=500)
    people = ask('Number of people (tags)', default=4, kind=int, low=1, high=8)
    return {'shape': shape, 'width': width, 'height': height, 'people': people}


def free_ports(count):
    """Stop osc_bridge.py and anything else holding the ports we send to."""
    ports = f'{FIRST_PORT}-{FIRST_PORT + count - 1}'
    def output(command):
        try:
            return subprocess.run(command, capture_output=True, text=True).stdout.split()
        except FileNotFoundError:  # No lsof/pgrep (e.g. Windows): nothing to free.
            return []
    found = output(['lsof', '-t', '-nP', '-i', f'UDP:{ports}'])
    bridges = []
    for pid in output(['pgrep', '-f', 'osc_bridge.py']):
        # Only a Python process actually running osc_bridge.py, not any command line mentioning it.
        args = subprocess.run(['ps', '-o', 'command=', '-p', pid], capture_output=True, text=True).stdout.split()
        if len(args) > 1 and 'ython' in os.path.basename(args[0]) and args[1].endswith('osc_bridge.py'):
            bridges.append(pid)
    stopped = []
    for pid in sorted({int(p) for p in found + bridges} - {os.getpid()}):
        command = subprocess.run(['ps', '-o', 'command=', '-p', str(pid)], capture_output=True, text=True).stdout.split()
        # Show the script and its arguments rather than the interpreter's path.
        name = ' '.join(next((command[i:] for i, part in enumerate(command) if part.endswith('.py')), command[:1]))
        try:
            os.kill(pid, signal.SIGTERM)
            stopped.append(f'{pid} {name[:70]}')
        except ProcessLookupError:
            pass
    if stopped:
        print(f'Freed ports {ports}; stopped:\n  ' + '\n  '.join(stopped))
        time.sleep(0.5)


monitor_windows = []  # Terminal window ids opened by this simulator.


def close_monitors(count):
    """Stop the port listeners this simulator opened and close only their windows."""
    ports = range(FIRST_PORT, FIRST_PORT + count)
    try:
        pids = subprocess.run(['pgrep', '-f', '--', '--monitor'], capture_output=True, text=True).stdout.split()
    except FileNotFoundError:
        pids = []
    for pid in pids:
        args = subprocess.run(['ps', '-o', 'command=', '-p', pid], capture_output=True, text=True).stdout.split()
        if len(args) > 3 and 'ython' in os.path.basename(args[0]) and args[1] == SELF \
                and args[2] == '--monitor' and args[3].isdigit() and int(args[3]) in ports:
            try:
                os.kill(int(pid), signal.SIGTERM)
            except ProcessLookupError:
                pass
    if monitor_windows:
        time.sleep(0.5)  # Let the windows go idle so they close without asking.
        script = ['tell application "Terminal"'] + [
            f'  try\n    close (every window whose id is {window})\n  end try' for window in monitor_windows] + ['end tell']
        subprocess.run(['osascript', '-e', '\n'.join(script)], capture_output=True)
        monitor_windows.clear()


def open_monitors(count):
    """Open a Terminal window per port, each printing what its /tagN receives."""
    if sys.platform != 'darwin':
        print('To watch the ports, run in separate terminals: ' +
              ', '.join(f'python3 {os.path.basename(SELF)} --monitor {FIRST_PORT + n}' for n in range(count)))
        return
    lines = ['tell application "Terminal"', '  set opened to {}']
    for n in range(1, count + 1):
        port = FIRST_PORT + n - 1
        command = f"clear && echo '/tag{n}  (port {port})' && '{sys.executable}' '{SELF}' --monitor {port}"
        lines += [f'  do script "{command}"', '  set end of opened to id of front window']
    lines += ['  return opened', 'end tell']
    result = subprocess.run(['osascript', '-e', '\n'.join(lines)], capture_output=True, text=True).stdout
    monitor_windows.extend(int(v) for v in result.replace(',', ' ').split() if v.isdigit())


# ---------- Terminal view ----------

def draw(screen, sim, paused, rate):
    screen.erase()
    rows, cols = screen.getmaxyx()
    config = sim.config
    info_rows = sim.tag_count + 6
    map_rows = max(6, rows - info_rows - 1)
    map_cols = cols - 2
    # Terminal cells are about twice as tall as they are wide.
    scale = min((map_cols - 8) / sim.width, 2 * (map_rows - 3) / sim.height)
    box_w = max(2, int(round(sim.width * scale)))
    box_h = max(2, int(round(sim.height * scale / 2)))
    left = max(4, (cols - box_w) // 2)
    top = 2

    def put(r, c, text, attr=0):
        if 0 <= r < rows and 0 <= c < cols - 1:
            try:
                screen.addstr(r, c, text[:max(0, cols - 1 - c)], attr)
            except curses.error:
                pass

    shape_name = f'{sim.width:g} ft square' if config['shape'] == 'square' else f'{sim.width:g} × {sim.height:g} ft rectangle'
    last_port = FIRST_PORT + sim.tag_count - 1
    put(0, 1, f'VIRIDITAS simulator · {shape_name} · {len(sim.people)} people · '
              f'OSC /tag1-/tag{sim.tag_count} → {HOST}:{FIRST_PORT}-{last_port} · {rate:.0f} msg/s', curses.A_BOLD)
    # Shape outline and anchors (Anchor 1 top-left, clockwise).
    for c in range(left, left + box_w + 1):
        put(top, c, '─', curses.color_pair(9)); put(top + box_h, c, '─', curses.color_pair(9))
    for r in range(top, top + box_h + 1):
        put(r, left, '│', curses.color_pair(9)); put(r, left + box_w, '│', curses.color_pair(9))
    for (r, c, label, dc) in ((top, left, 'A1', -3), (top, left + box_w, 'A2', 2),
                              (top + box_h, left + box_w, 'A3', 2), (top + box_h, left, 'A4', -3)):
        put(r, c, '■', curses.color_pair(10) | curses.A_BOLD)
        put(r, c + dc, label, curses.color_pair(10))
    put(top + box_h // 2, left + box_w // 2, '+', curses.color_pair(9))  # Center (0.5, 0.5).

    def cell(x, y):
        return top + int(round((sim.height - y) / sim.height * box_h)), left + int(round(x / sim.width * box_w))

    for person in sim.people:
        color = curses.color_pair(person.number)
        for (x, y) in person.trail[:-1]:
            r, c = cell(x, y)
            put(r, c, '·', color)
    for person in sim.people:
        r, c = cell(person.x, person.y)
        put(r, c, str(person.number), curses.color_pair(person.number) | curses.A_BOLD | curses.A_REVERSE)

    # Values table: exactly what is being sent.
    row = top + box_h + 2
    put(row, 1, 'Tag   X      Y      (feet)          distances to other tags (0-1 of diagonal)', curses.A_UNDERLINE)
    for number in range(1, sim.tag_count + 1):
        row += 1
        data = sim.last_messages.get(number, {})
        fmt = lambda v: f'{v:.3f}' if isinstance(v, float) else str(v)
        dists = '  '.join(f'{k}={fmt(v)}' for k, v in data.items() if k.startswith('d'))
        put(row, 1, f'/tag{number}', curses.color_pair(number) | curses.A_BOLD)
        if number == sim.controlled:
            put(row, 0, '›', curses.color_pair(number) | curses.A_BOLD)
        person = sim.people[number - 1] if number <= len(sim.people) else None
        if person is None:
            put(row, 7, 'no person · still sending: ' + json.dumps(data, separators=(', ', ': '))[:max(0, cols - 40)],
                curses.color_pair(9) | curses.A_DIM)
            continue
        put(row, 7, f'{fmt(data.get("x", "-")):<6} {fmt(data.get("y", "-")):<6} '
                    f'({person.x:5.2f}, {person.y:5.2f} ft)  {dists}' + ('  MOVED BY HAND' if person.manual else ''))
    put(row + 2, 1, ('PAUSED · ' if paused else '') + ('MANUAL · ' if sim.manual else '') + f'arrows move tag {sim.controlled} · 1-{len(sim.people)} pick tag · '
                    'a auto · space pause · m back to menu · q quit', curses.color_pair(9))
    screen.refresh()


ARROWS = {curses.KEY_UP: (0, 1), curses.KEY_DOWN: (0, -1), curses.KEY_LEFT: (-1, 0), curses.KEY_RIGHT: (1, 0)}


def run(screen, sim):
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    for i, color in enumerate([curses.COLOR_GREEN, curses.COLOR_RED, curses.COLOR_BLUE, curses.COLOR_YELLOW,
                               curses.COLOR_MAGENTA, curses.COLOR_CYAN, curses.COLOR_WHITE, curses.COLOR_GREEN], 1):
        curses.init_pair(i, color, -1)
    curses.init_pair(9, curses.COLOR_WHITE, -1)
    curses.init_pair(10, curses.COLOR_YELLOW, -1)
    screen.nodelay(True)
    paused, last, next_send, next_draw = False, time.monotonic(), 0.0, 0.0
    rate_window, rate = [time.monotonic(), 0], 0.0
    while True:
        key = screen.getch()
        while key != -1:  # Handle every pending key so held arrows don't lag behind.
            if key in (ord('q'), ord('Q')):
                return 'quit'
            if key in (ord('m'), ord('M')):
                return 'menu'
            if key == ord(' '):
                paused = not paused
            if ord('1') <= key <= ord('9') and key - ord('0') <= len(sim.people):
                sim.controlled = key - ord('0')
            person = sim.people[sim.controlled - 1]
            if key in ARROWS:
                dx, dy = ARROWS[key]
                sim.manual = True
                person.nudge(dx * NUDGE_FT, dy * NUDGE_FT)
            if key in (ord('a'), ord('A')) and sim.manual:
                sim.manual = False
                for other in sim.people:
                    other.release()
            key = screen.getch()
        now = time.monotonic()
        dt, last = min(0.2, now - last), now
        if not paused:
            sim.step(dt)
            if now >= next_send:
                sim.send_all()
                next_send = now + 1 / SEND_HZ
        if now - rate_window[0] >= 1:
            rate = (sim.sent - rate_window[1]) / (now - rate_window[0])
            rate_window[:] = [now, sim.sent]
        if now >= next_draw:
            draw(screen, sim, paused, rate)
            next_draw = now + 0.1
        time.sleep(0.01)


def headless(sim, seconds):
    """No drawing: send for a while and report (for testing)."""
    end = time.monotonic() + seconds
    last = time.monotonic()
    while time.monotonic() < end:
        now = time.monotonic()
        sim.step(now - last)
        last = now
        sim.send_all()
        time.sleep(1 / SEND_HZ)
    print(f'Sent {sim.sent} messages in {seconds:g} s')


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--headless', type=float, metavar='SECONDS', help=argparse.SUPPRESS)  # For testing.
    parser.add_argument('--config', help=argparse.SUPPRESS)  # "shape,width,height,people", skips the menu.
    parser.add_argument('--monitor', type=int, metavar='PORT', help='just print what arrives on PORT')
    args = parser.parse_args()
    if args.monitor:
        try:
            monitor(args.monitor)
        except KeyboardInterrupt:
            pass
        return
    while True:
        if args.config:
            shape, width, height, people = args.config.split(',')
            config = {'shape': shape, 'width': float(width), 'height': float(height), 'people': int(people)}
        else:
            try:
                config = menu()
            except (EOFError, KeyboardInterrupt):
                return
        tags = max(MIN_TAGS, config['people'])
        # free_ports(tags)  # Disabled: leave other listeners (Unreal Engine) running.
        close_monitors(tags)  # Windows from a previous run (m -> menu).
        sim = Simulation(config)
        if not args.headless:
            open_monitors(tags)
            time.sleep(1)  # Let the windows start listening.
        if args.headless:
            headless(sim, args.headless)
            return
        try:
            result = curses.wrapper(run, sim)
        except KeyboardInterrupt:
            result = 'quit'
        if result == 'quit' or args.config:
            close_monitors(tags)  # q (or Ctrl-C) also closes the port windows it opened.
            print('Simulator stopped; port windows closed.')
            return


if __name__ == '__main__':
    main()
