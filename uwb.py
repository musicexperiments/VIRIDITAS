#!/usr/bin/env python3
"""The UWB setup in the terminal: anchor layout, live map and OSC out.

  python3 uwb.py                  # anchor 1 at 10.10.10.183
  python3 uwb.py --anchor HOST    # or give anchor 1's IP / hostname

Runs osc_bridge.py's bridge (same OSC: /tagN on 8999 + N and 9099 + N) and shows
what it sends. On start, a menu keeps the saved anchor layout or takes new
tape-measured distances (saved to layout.json). Then a live view: the anchors at
their corners (Anchor 1 top-left, clockwise), each tag where its x, y put it,
every tag's message, and the UWB anchor-to-anchor distances next to the tape.

The OSC keeps sending the whole time, including while the layout menu is open.
Keys: l layout menu · s smoothing on/off · , . calmer/livelier when still ·
[ ] slower/faster to follow movement · h hold time · 0 smoothing defaults ·
space freeze the view · q quit. Smoothing settings are saved to filter.json.
Ctrl-Z is ignored: pausing would stop the OSC.
"""
import curses
import json
import math
import signal
import statistics
import threading
import time

import osc_bridge
from osc_bridge import DEFAULT_FRAME, LAYOUT, MISSING, is_tag, tag_number

FT = 30.48
ANCHORS = {1: 'A1', 3: 'A2', 4: 'A3', 5: 'A4'}  # node -> name, clockwise from top-left
SIDES = [(1, 3), (3, 4), (4, 5), (1, 5), (1, 4), (3, 5)]  # four sides, then both diagonals
TRAIL = 14


def pair_name(a, b):
    return f'{ANCHORS[a]}–{ANCHORS[b]}'


def node_of(tag):
    return 2 if tag == 1 else tag + 4


# ---------- Layout menu ----------

def uwb_ft(bridge, a, b):
    """Median of the recent UWB readings between two anchors, in feet, or None."""
    history = bridge.anchor_history.get((min(a, b), max(a, b)))
    return statistics.median(history) / FT if history else None


def describe_layout(bridge):
    d = bridge.distances
    if not d:
        return 'No layout saved: anchor positions come from the live UWB distances.'
    sides = [d.get(f'{a}-{b}') for a, b in SIDES[:4]]
    if all(sides) and abs(sides[0] - sides[2]) < 0.5 and abs(sides[1] - sides[3]) < 0.5:
        return f'Saved layout: {sides[0] / FT:.2f} × {sides[1] / FT:.2f} ft rectangle (A1→A2 × A2→A3).'
    return 'Saved layout: ' + ', '.join(f'{pair_name(a, b)} {d[f"{a}-{b}"] / FT:.2f}'
                                        for a, b in SIDES if f'{a}-{b}' in d) + ' ft.'


def ask_ft(bridge, prompt, a, b, required=True):
    measured = uwb_ft(bridge, a, b)
    hint = f' (UWB reads {measured:.2f})' if measured else ''
    while True:
        answer = input(f'  {prompt}{hint}, ft{"" if required else " (blank to skip)"}: ').strip()
        if not answer and not required:
            return None
        try:
            value = float(answer)
        except ValueError:
            print('    Please enter a number of feet.')
            continue
        if 0.5 <= value <= 500:
            return value * FT
        print('    Enter a value from 0.5 to 500.')


def save_layout(anchors, distances):
    data = {'frame': {str(k): list(v) for k, v in DEFAULT_FRAME.items()},
            'anchors': {str(k): [round(v[0], 2), round(v[1], 2)] for k, v in anchors.items()},
            'distances': {k: round(v, 2) for k, v in distances.items()}}
    LAYOUT.write_text(json.dumps(data))


def layout_menu(bridge, lock):
    """Keep the saved layout or enter a new one. Returns False if the user wants to quit."""
    print('\nVIRIDITAS UWB · anchor layout\n' + '=' * 29)
    with lock:
        print(describe_layout(bridge))
    print('Anchor 1 is top-left, then clockwise: A2 top-right, A3 bottom-right, A4 bottom-left.')
    print('  Enter) keep it   r) rectangle or square   o) other shape (distance between each pair)'
          + ('   u) use live UWB' if bridge.distances else '') + '   q) quit')
    while True:
        choice = input('Choose [Enter]: ').strip().lower()
        if choice in ('', 'r', 'o', 'q') or (choice == 'u' and bridge.distances):
            break
        print('  Choose Enter, r, o' + (', u' if bridge.distances else '') + ' or q.')
    if choice == 'q':
        return False
    if choice == 'u':
        LAYOUT.write_text('{}')
        print('Cleared: positions now come from the live UWB anchor distances.')
    elif choice == 'r':
        width = ask_ft(bridge, 'Width, A1 → A2 (top)', 1, 3)
        height = ask_ft(bridge, 'Height, A2 → A3 (right)', 3, 4)
        diagonal = math.hypot(width, height)
        save_layout({1: (0, 0), 3: (width, 0), 4: (width, height), 5: (0, height)},
                    {'1-3': width, '4-5': width, '3-4': height, '1-5': height, '1-4': diagonal, '3-5': diagonal})
        print(f'Saved a {width / FT:.2f} × {height / FT:.2f} ft rectangle.')
    elif choice == 'o':
        print('  Tape-measure along the floor between each pair; at least five of the six.')
        distances = {}
        for a, b in SIDES:
            value = ask_ft(bridge, pair_name(a, b), a, b, required=len(distances) < 4 or (a, b) in SIDES[:4])
            if value:
                distances[f'{a}-{b}'] = value
        d = lambda a, b: distances.get(f'{min(a, b)}-{max(a, b)}', 0)
        anchors = osc_bridge.build_shape(sorted(ANCHORS), d)
        if not anchors:
            print('Those distances do not make a shape; layout not changed.')
        else:
            worst = max(abs(math.dist(anchors[a], anchors[b]) - d(a, b)) for a, b in SIDES if d(a, b))
            if worst > 15:
                print(f'Warning: the distances do not fit together (off by up to {worst / FT:.2f} ft). '
                      'Check the measurements.')
            save_layout(anchors, distances)
            print('Saved.')
    with lock:
        bridge.layout_mtime = None
        bridge.load_layout()
    return True


# ---------- Bridge loop (runs the whole time, menu or not) ----------

def pump(bridge, listener, stop, lock):
    listener.settimeout(0.05)
    last_layout = time.monotonic()
    while not stop.is_set():
        try:
            data = listener.recvfrom(512)[0]
        except OSError:
            data = b''
        now = time.monotonic()
        with lock:
            bridge.feed(data, now)
            bridge.heartbeat(now)
            if now - last_layout >= 5:
                bridge.load_layout()
                bridge.load_filter()
                last_layout = now


# ---------- Live view ----------

def draw(screen, bridge, args, state):
    screen.erase()
    rows, cols = screen.getmaxyx()
    now = time.monotonic()

    def put(r, c, text, attr=0):
        if 0 <= r < rows and 0 <= c < cols - 1:
            try:
                screen.addstr(r, c, text[:max(0, cols - 1 - c)], attr)
            except curses.error:
                pass

    dim, bold = curses.color_pair(9) | curses.A_DIM, curses.A_BOLD
    good, bad, warn = curses.color_pair(1), curses.color_pair(2), curses.color_pair(4)
    tags = sorted({tag_number(n) for n in bridge.known_tags | bridge.configured_tags})
    pos = bridge.geometry[0] if bridge.geometry else {}
    online = bridge.nodes

    # Header.
    if bridge.anchor_error:
        link, link_attr = f'anchor 1 unreachable ({bridge.anchor_error[:40]})', bad | bold
    elif online:
        link, link_attr = 'anchor 1 connected', good
    else:
        link, link_attr = 'connecting to anchor 1…', warn
    put(0, 1, 'VIRIDITAS UWB', bold)
    put(0, 15, f'{args.anchor} · ', dim)
    put(0, 18 + len(args.anchor), link, link_attr)
    ports = ' & '.join(f'{p}+' for p in [args.osc_port] + args.also_port)
    put(1, 1, f'OSC /tag1-/tag{tags[-1]} → {args.osc_host}:{ports} · {state["rate"]:.0f} msg/s'
              + (" · anchor 1's median ranges" if args.smooth else '')
              + ('' if bridge.saved else ' · layout: live UWB'), dim)
    tuning = bridge.tuning
    if tuning['on']:
        put(2, 1, 'Smoothing ON', good | bold)
        put(2, 14, f'· calm when still {tuning["still_hz"]:.2f} Hz (, calmer  . livelier) · '
                   f'follow movement {tuning["follow"]:.4f} ([ slower  ] faster) · '
                   f'hold {tuning["hold_s"]:g} s (h) · 0 defaults', dim)
    else:
        put(2, 1, 'Smoothing OFF', warn | bold)
        put(2, 15, '· raw positions, spikes and all (s turns it on)', dim)

    # Map: real proportions from the layout, Anchor 1 top-left.
    width = math.dist(pos[1], pos[3]) if 1 in pos and 3 in pos else 1
    height = math.dist(pos[3], pos[4]) if 3 in pos and 4 in pos else 1
    info_rows = len(tags) + 9
    map_rows, map_cols = max(5, rows - info_rows - 4), cols - 12
    scale = min(map_cols / width, 2 * map_rows / height)  # cells are about twice as tall as wide
    box_w, box_h = max(4, round(width * scale)), max(2, round(height * scale / 2))
    left, top = max(5, (cols - box_w) // 2), 4
    for c in range(left, left + box_w + 1):
        put(top, c, '─', dim); put(top + box_h, c, '─', dim)
    for r in range(top, top + box_h + 1):
        put(r, left, '│', dim); put(r, left + box_w, '│', dim)
    put(top + box_h // 2, left + box_w // 2, '+', dim)
    if width > 1 and height > 1:
        put(top, left + box_w // 2 - 4, f' {width / FT:.2f} ft ', dim)
        put(top + box_h // 2, left + box_w + 2, f'{height / FT:.2f} ft', dim)
    for node, (r, c, dc) in zip(ANCHORS, ((top, left, -3), (top, left + box_w, 2),
                                          (top + box_h, left + box_w, 2), (top + box_h, left, -3))):
        attr = good if online.get(node) else bad if online else dim
        put(r, c, '■', attr | bold)
        put(r, c + dc, ANCHORS[node], attr)

    def cell(x, y):
        return top + round((1 - y) / 2 * box_h), left + round((x + 1) / 2 * box_w)

    for tag in tags:
        for (x, y) in state['trails'].get(tag, [])[:-1]:
            put(*cell(x, y), '·', curses.color_pair(tag))
    for tag in tags:
        trail = state['trails'].get(tag)
        if trail:
            put(*cell(*trail[-1]), str(tag), curses.color_pair(tag) | bold | curses.A_REVERSE)

    # Tags: exactly what is being sent, plus their distance to each anchor.
    row = top + box_h + 2
    put(row, 1, 'Tag    status   x        y        inside   A1     A2     A3     A4  (ft)   '
                'smoothing      to other tags (0-1 of shape)', curses.A_UNDERLINE)
    for tag in tags:
        row += 1
        node, message = node_of(tag), bridge.last_message.get(tag, {})
        fmt = lambda v: f'{v:+.3f}' if isinstance(v, float) else str(v)
        put(row, 1, f'/tag{tag}', curses.color_pair(tag) | bold)
        status = 'online' if online.get(node) else 'offline' if online else '?'
        put(row, 8, status, good if status == 'online' else bad if status == 'offline' else dim)
        live = message.get('x', MISSING) != MISSING
        put(row, 17, f'{fmt(message.get("x", MISSING)):<8} {fmt(message.get("y", MISSING)):<8} '
                     f'{message.get("inside", MISSING)!s:<8}', 0 if live else dim)
        for i, anchor in enumerate(ANCHORS):
            cm = bridge.range_cm(node, anchor, now)
            put(row, 44 + 7 * i, f'{cm / FT:5.2f}' if cm is not None else '  –', 0 if cm is not None else dim)
        # What the smoothing is doing for this tag: holding, an anchor outvoted, spikes dropped.
        stats = bridge.stats.get(node, {})
        if tuning['on'] and stats.get('held'):
            put(row, 78, 'held', warn)
        elif tuning['on'] and stats.get('outvoted'):
            put(row, 78, f'{ANCHORS[stats["outvoted"]]} left out', warn)
        spikes = state['spike_rate'].get(node, 0)
        if tuning['on'] and spikes:
            put(row, 87 if stats.get('held') or stats.get('outvoted') else 78, f'{spikes:.0f} spk/s', dim)
        others = '  '.join(f'{k}={v:.3f}' if isinstance(v, float) else f'{k}={v}'
                           for k, v in message.items() if k.startswith('d'))
        put(row, 93, others, 0 if live else dim)

    # Anchors: UWB against the tape.
    row += 2
    put(row, 1, 'Anchors  UWB vs tape (ft)', curses.A_UNDERLINE)
    for i, (a, b) in enumerate(SIDES):
        r, c = row + 1 + i // 3, 1 + (i % 3) * 30
        uwb, tape = uwb_ft(bridge, a, b), bridge.distances.get(f'{a}-{b}')
        put(r, c, f'{pair_name(a, b)}', bold)
        text = f'{uwb:6.2f}' if uwb else '     –'
        if uwb and tape:
            off = uwb - tape / FT
            put(r, c + 6, f'{text} / {tape / FT:6.2f}  ', 0)
            put(r, c + 23, f'{off:+.2f}', warn if abs(off) > 0.5 else dim)
        else:
            put(r, c + 6, text + (f' / {tape / FT:6.2f}' if tape else ''), dim)

    put(rows - 1, 1, ('FROZEN · ' if state['frozen'] else '') +
        'l layout · s smoothing on/off · , . [ ] h 0 tune it · space freeze · q quit', dim)
    screen.refresh()


TUNING_KEYS = {ord(k) for k in 'sS,.[]hH0'}
HOLDS = [0.0, 0.25, 0.5, 1.0]


def tune(bridge, key):
    """Change the smoothing from the keyboard and save it to filter.json."""
    t = bridge.tuning
    key = chr(key).lower()
    if key == 's':
        t['on'] = not t['on']
    elif key in ',.':
        t['still_hz'] = round(min(5.0, max(0.05, t['still_hz'] * (1 / 1.25 if key == ',' else 1.25))), 3)
    elif key in '[]':
        t['follow'] = round(min(0.2, max(0.0005, t['follow'] * (1 / 1.25 if key == '[' else 1.25))), 5)
    elif key == 'h':
        t['hold_s'] = HOLDS[(HOLDS.index(t['hold_s']) + 1) % len(HOLDS)] if t['hold_s'] in HOLDS else 0.5
    elif key == '0':
        t.update({k: v for k, v in osc_bridge.FILTER_DEFAULTS.items() if k != 'on'})
    bridge.save_filter()


def view(screen, bridge, args, lock):
    curses.curs_set(0)
    curses.start_color()
    curses.use_default_colors()
    for i, color in enumerate([curses.COLOR_GREEN, curses.COLOR_RED, curses.COLOR_BLUE, curses.COLOR_YELLOW,
                               curses.COLOR_MAGENTA, curses.COLOR_CYAN, curses.COLOR_WHITE, curses.COLOR_GREEN], 1):
        curses.init_pair(i, color, -1)
    curses.init_pair(9, curses.COLOR_WHITE, -1)
    screen.timeout(100)
    state = {'trails': {}, 'frozen': False, 'rate': 0.0, 'spike_rate': {}}
    rate_window = [time.monotonic(), bridge.total_sent, {}]
    while True:
        key = screen.getch()
        if key in (ord('q'), ord('Q')):
            return 'quit'
        if key in (ord('l'), ord('L')):
            return 'layout'
        if key in TUNING_KEYS:
            with lock:
                tune(bridge, key)
        if key == ord(' '):
            state['frozen'] = not state['frozen']
        if state['frozen']:
            continue
        now = time.monotonic()
        with lock:
            if now - rate_window[0] >= 1:
                spikes = {node: stats.get('spikes', 0) for node, stats in bridge.stats.items()}
                state['rate'] = (bridge.total_sent - rate_window[1]) / (now - rate_window[0])
                state['spike_rate'] = {node: (n - rate_window[2].get(node, n)) / (now - rate_window[0])
                                       for node, n in spikes.items()}
                rate_window[:] = [now, bridge.total_sent, spikes]
            for tag, message in bridge.last_message.items():
                trail = state['trails'].setdefault(tag, [])
                if message.get('x', MISSING) != MISSING:
                    trail.append((message['x'], message['y']))
                    del trail[:-TRAIL]
                else:
                    trail.clear()
            draw(screen, bridge, args, state)


def main():
    args = osc_bridge.make_parser(__doc__).parse_args()
    # Ctrl-Z would pause the bridge and silently stop the OSC (with the ports still held).
    signal.signal(signal.SIGTSTP, signal.SIG_IGN)
    bridge, listener, stop = osc_bridge.start(args)
    bridge.load_filter()
    lock = threading.Lock()
    threading.Thread(target=pump, args=(bridge, listener, stop, lock), daemon=True).start()
    time.sleep(1.5)  # A moment of anchor-to-anchor readings for the menu's UWB hints.
    try:
        result = 'layout'
        while True:
            if result == 'layout' and not layout_menu(bridge, lock):
                break
            result = curses.wrapper(view, bridge, args, lock)
            if result == 'quit':
                break
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        stop.set()
    print('\nStopped.')


if __name__ == '__main__':
    main()
