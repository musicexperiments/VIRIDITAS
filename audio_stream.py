#!/usr/bin/env python3
"""Stream SuperCollider's audio to the ESP32 speaker (firmware/audio_stream) over UDP.

supercollider/sine_stream.scd writes its sound into a ring buffer on the
SuperCollider server (buffer 900) and the write position onto control bus 900.
This program reads new samples straight from the server, converts them to
16 kHz mono 16-bit, and sends 10 ms packets to the board on UDP 4220.

Each packet: b"VAU1", stream id, sequence (little-endian uint32), then 160
samples of this frame and 160 of the previous one, so a single lost packet
loses nothing. The board's stats come back once a second; they are printed
and forwarded to sclang as /speaker so the window can show them.

  python3 audio_stream.py                    # finds uwb-speaker.local
  python3 audio_stream.py --host 10.10.10.50
"""
import argparse
import random
import socket
import struct
import time

import numpy as np

RATE = 16000
FRAME = 160  # 10 ms
PORT = 4220


def osc_string(text):
    data = text.encode() + b'\0'
    return data + b'\0' * (-len(data) % 4)


def osc_message(address, *args):
    tags = ',' + ''.join('i' if isinstance(a, int) else 'f' if isinstance(a, float) else 's' for a in args)
    data = osc_string(address) + osc_string(tags)
    for a in args:
        if isinstance(a, int):
            data += struct.pack('>i', a)
        elif isinstance(a, float):
            data += struct.pack('>f', a)
        else:
            data += osc_string(a)
    return data


def osc_parse(data):
    """(address, args) for a plain OSC message; float runs stay as one numpy array."""
    def read_string(i):
        end = data.index(b'\0', i)
        return data[i:end].decode(), (end + 4) & ~3
    address, i = read_string(0)
    tags, i = read_string(i)
    args = []
    k = 1
    while k < len(tags):
        t = tags[k]
        if t == 'f':
            run = len(tags[k:]) - len(tags[k:].lstrip('f'))
            args.append(np.frombuffer(data, '>f4', run, i).astype(np.float32))
            i += 4 * run
            k += run
            continue
        if t == 'i':
            args.append(struct.unpack_from('>i', data, i)[0])
            i += 4
        elif t == 'd':
            args.append(struct.unpack_from('>d', data, i)[0])
            i += 8
        elif t == 's':
            s, i = read_string(i)
            args.append(s)
        k += 1
    return address, args


class Server:
    """Reads the ring buffer and position bus from scsynth."""

    def __init__(self, addr, buf, bus):
        self.addr, self.buf, self.bus = addr, buf, bus
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(0.2)

    def ask(self, request, reply, match):
        self.sock.sendto(request, self.addr)
        deadline = time.monotonic() + 0.2
        while time.monotonic() < deadline:
            try:
                address, args = osc_parse(self.sock.recv(65536))
            except (socket.timeout, ConnectionRefusedError):
                return None
            except (ValueError, struct.error):
                continue
            if address == reply and match(args):
                return args
        return None

    def info(self):
        """(frames, sample rate) of the ring buffer, or None until it exists."""
        args = self.ask(osc_message('/b_query', self.buf), '/b_info', lambda a: a[0] == self.buf)
        if not args or args[1] <= 0:
            return None
        return args[1], float(args[3][0] if isinstance(args[3], np.ndarray) else args[3])

    def position(self):
        args = self.ask(osc_message('/c_get', self.bus), '/c_set', lambda a: a[0] == self.bus)
        return None if args is None else int(args[1][0])

    def read(self, start, count):
        args = self.ask(osc_message('/b_getn', self.buf, start, count), '/b_setn',
                        lambda a: a[0] == self.buf and a[1] == start)
        if args is None or len(args) < 4 or len(args[3]) != count:
            return None
        return args[3]


class Resampler:
    """Low-pass at 7 kHz, then interpolate down to 16 kHz, across calls."""

    def __init__(self, rate):
        self.step = rate / RATE
        n = np.arange(127) - 63
        cutoff = 7000 / rate
        self.taps = (2 * cutoff * np.sinc(2 * cutoff * n) * np.blackman(127)).astype(np.float32)
        self.history = np.zeros(len(self.taps) - 1, np.float32)
        self.pending = np.zeros(0, np.float32)
        self.t = 0.0

    def __call__(self, x):
        x = np.concatenate([self.history, x])
        self.history = x[-(len(self.taps) - 1):]
        self.pending = np.concatenate([self.pending, np.convolve(x, self.taps, 'valid')])
        count = max(0, int(np.ceil((len(self.pending) - 1 - self.t) / self.step)))
        pos = self.t + self.step * np.arange(count)
        i = pos.astype(int)
        frac = (pos - i).astype(np.float32)
        out = self.pending[i] * (1 - frac) + self.pending[np.minimum(i + 1, len(self.pending) - 1)] * frac
        self.t += self.step * count
        used = min(int(self.t), len(self.pending))
        self.pending = self.pending[used:]
        self.t -= used
        return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--host', default='uwb-speaker.local', help='the board (default uwb-speaker.local)')
    p.add_argument('--port', type=int, default=PORT)
    p.add_argument('--scsynth', default='127.0.0.1:57110', help='SuperCollider server address')
    p.add_argument('--sclang', type=int, default=57120, help='sclang port for /speaker status (0 = off)')
    p.add_argument('--buf', type=int, default=900, help='ring buffer number')
    p.add_argument('--bus', type=int, default=900, help='control bus with the write position')
    args = p.parse_args()

    host, port = args.scsynth.rsplit(':', 1)
    server = Server((host, int(port)), args.buf, args.bus)
    out = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    out.setblocking(False)
    lang = ('127.0.0.1', args.sclang) if args.sclang else None

    def status(text):
        print(text, flush=True)
        if lang:
            try:
                out.sendto(osc_message('/speaker', text), lang)
            except OSError:
                pass

    while True:
        try:
            board = (socket.gethostbyname(args.host), args.port)
            break
        except OSError:
            status(f'STREAM,waiting,cannot find {args.host}')
            time.sleep(2)
    status(f'STREAM,board,{board[0]}:{board[1]}')

    stream = random.getrandbits(32)
    seq = 0
    prev = np.zeros(FRAME, np.int16)
    queue = np.zeros(0, np.float32)
    info = None
    last = None
    last_board = 0.0
    next_send = 0.0
    while True:
        if info is None:
            info = server.info()
            if info is None:
                status('STREAM,waiting,start supercollider/sine_stream.scd')
                time.sleep(1)
                continue
            frames, rate = info
            resample = Resampler(rate)
            last = None
            status(f'STREAM,server,{rate:.0f} Hz -> {RATE} Hz')

        pos = server.position()
        if pos is None:
            info = None  # server gone; wait for it again
            continue
        if last is None:
            last = pos
        count = (pos - last) % frames
        if count > frames // 2:  # fell far behind or the server restarted
            last = pos
            count = 0
        chunks = []
        while count > 0:
            n = min(count, frames - last, 1024)
            data = server.read(last, n)
            if data is None:
                break
            chunks.append(data)
            last = (last + n) % frames
            count -= n
        if chunks:
            queue = np.concatenate([queue, resample(np.concatenate(chunks))])

        # One packet every 10 ms, so Wi-Fi sees a steady stream rather than the
        # server's bursts; catch up if more than 30 ms has piled up.
        now = time.monotonic()
        while len(queue) >= FRAME and (now >= next_send or len(queue) > 3 * FRAME):
            next_send = max(next_send + FRAME / RATE, now - 0.02)
            cur = (np.clip(queue[:FRAME], -1, 1) * 32767).astype('<i2')
            queue = queue[FRAME:]
            packet = b'VAU1' + struct.pack('<II', stream, seq) + cur.tobytes() + prev.tobytes()
            try:
                out.sendto(packet, board)
            except OSError:
                pass  # Wi-Fi hiccup on the laptop; the board conceals it
            prev = cur
            seq = (seq + 1) & 0xFFFFFFFF

        try:
            while True:
                line = out.recv(512).decode(errors='replace')
                if time.monotonic() - last_board >= 5:
                    last_board = time.monotonic()
                    status(line)
        except (BlockingIOError, ConnectionRefusedError):
            pass
        time.sleep(0.002)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
