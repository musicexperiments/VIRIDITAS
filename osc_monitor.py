#!/usr/bin/env python3
"""Print the OSC messages arriving on one UDP port, e.g. `python3 osc_monitor.py 9001`."""
import json
import socket
import struct
import sys
import time


def read_string(data, offset):
    end = data.index(b'\0', offset)
    return data[offset:end].decode(errors='replace'), (end + 4) & ~3


def parse(data):
    address, offset = read_string(data, 0)
    tags, offset = read_string(data, offset)
    values = []
    for tag in tags[1:]:
        if tag == 's':
            value, offset = read_string(data, offset)
        elif tag in 'if':
            value = struct.unpack('>i' if tag == 'i' else '>f', data[offset:offset + 4])[0]
            offset += 4
        else:
            break
        values.append(value)
    return address, values


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9001
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('0.0.0.0', port))
    sys.stdout.write(f'\33]0;OSC port {port}\a')  # Terminal window title.
    print(f'Listening for OSC on UDP {port} (Ctrl-C to stop)', flush=True)
    while True:
        data, _ = sock.recvfrom(2048)
        try:
            address, values = parse(data)
        except (ValueError, struct.error):
            continue
        text = values[0] if values else ''
        try:
            text = json.dumps(json.loads(text))
        except (TypeError, ValueError):
            pass
        print(f'{time.strftime("%H:%M:%S")}  {address}  {text}', flush=True)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        pass
