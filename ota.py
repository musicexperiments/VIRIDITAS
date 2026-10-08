#!/usr/bin/env python3
"""Build and install firmware over the local Wi-Fi, without USB.

  python3 ota.py anchor
  python3 ota.py tag      # asks the anchor to wake the tag's Wi-Fi first
  python3 ota.py anchor2  # also anchor3, anchor4, tag2, tag3, ...; woken by anchor 1 over UWB
  python3 ota.py audio_stream  # the Wi-Fi speaker board
"""
import argparse
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
import re
# The update password is OTA_PASSWORD in firmware/secrets.h (not committed).
_secrets = (ROOT / 'firmware' / 'secrets.h')
_match = _secrets.exists() and re.search(r'OTA_PASSWORD\[\]\s*=\s*"([^"]*)"', _secrets.read_text())
PASSWORD = _match.group(1) if _match else None
HOSTS = {'anchor': 'uwb-anchor.local', 'tag': 'uwb-tag.local', 'anchor2': 'uwb-anchor2.local',
         'anchor3': 'uwb-anchor3.local', 'anchor4': 'uwb-anchor4.local',
         'audio_stream': 'uwb-speaker.local'}  # Wi-Fi always on; no wake needed
NODES = {'tag': 2, 'anchor2': 3, 'anchor3': 4, 'anchor4': 5}
# Tag N (N >= 2) is node N + 4, firmware/tagN, hostname uwb-tagN.
for n in range(2, 10):
    HOSTS[f'tag{n}'] = f'uwb-tag{n}.local'
    NODES[f'tag{n}'] = n + 4
ESPOTA = next((ROOT / '.arduino').rglob('tools/espota.py'), None)


def resolve(host, timeout):
    deadline = time.monotonic() + timeout
    while True:
        try:
            return socket.getaddrinfo(host, 3232, socket.AF_INET)[0][4][0]
        except OSError:
            if time.monotonic() >= deadline:
                raise SystemExit(f'Could not find {host} on the network.')
            time.sleep(2)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('board', choices=[b for b in HOSTS if (ROOT / 'firmware' / b).is_dir()])
    parser.add_argument('--anchor', default=HOSTS['anchor'], help='anchor hostname or IP')
    parser.add_argument('--ip', help='board IP, if its .local name does not resolve')
    args = parser.parse_args()
    if PASSWORD is None:
        raise SystemExit('Set OTA_PASSWORD in firmware/secrets.h (copy firmware/secrets.example.h).')
    if ESPOTA is None:
        raise SystemExit('espota.py not found; install the esp32 core with arduino-cli first.')

    build = ROOT / 'build' / args.board
    subprocess.run(['arduino-cli', '--config-file', str(ROOT / 'arduino-cli.yaml'), 'compile',
                    '--fqbn', 'esp32:esp32:esp32', '--libraries', str(ROOT / 'third_party'),
                    '--output-dir', str(build), str(ROOT / 'firmware' / args.board)], check=True)

    # A board with AUDIO_STREAM keeps Wi-Fi on; only wake the others.
    awake = None
    if args.board in NODES:
        try:
            awake = socket.getaddrinfo(HOSTS[args.board], 3232, socket.AF_INET)[0][4][0]
        except OSError:
            pass
    if args.board in NODES and not awake:
        anchor = args.anchor if args.anchor[0].isdigit() else resolve(args.anchor, 10)
        urllib.request.urlopen(urllib.request.Request(
            f'http://{anchor}/api/tag-update?node={NODES[args.board]}', data=b''), timeout=5).read()
        print(f'{args.board} asked to join Wi-Fi; it stays in update mode for up to 10 minutes.')
    ip = args.ip or awake or resolve(HOSTS[args.board], 60)
    print(f'Uploading to {args.board} at {ip}…')
    result = subprocess.run([sys.executable, str(ESPOTA), '-i', ip, '-p', '3232', '-a', PASSWORD,
                             '-f', str(build / f'{args.board}.ino.bin')])
    raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
