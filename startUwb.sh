#!/bin/bash
# Start everything for the UWB setup: SuperCollider in the background (when
# SOUND=1 below) and the terminal view (uwb.py: anchor layout, live map, OSC
# bridge) in this window.
#
#   ./startUwb.sh                  # anchor 1 at 10.10.10.183
#   ./startUwb.sh 10.10.10.200     # or give anchor 1's IP / hostname
#
# q in the view (or Ctrl-C) stops both and frees their ports.

cd "$(dirname "$0")" || exit 1

ANCHOR="${1:-10.10.10.183}"
SOUND=0  # 1 starts SuperCollider (supercollider/sine.scd); 0 leaves the sound off.
SCLANG="/Applications/SuperCollider.app/Contents/MacOS/sclang"
SCLANG_LOG="build/sclang.log"
# UDP 4210 bridge (from anchor 1) · UDP 9100 sine.scd ·
# UDP 57110 audio server (scsynth) · UDP 57120 sclang
PORTS_UDP=(4210 9100 57110 57120)

sclang_pid=

port_users() {
  for p in "${PORTS_UDP[@]}"; do lsof -nP -t -iUDP:"$p" 2>/dev/null; done
}

stopping=
stop() {
  [ -n "$stopping" ] && return
  stopping=1
  if [ -n "$sclang_pid" ]; then
    echo "Stopping SuperCollider..."
    # sclang's audio server (scsynth) is its child; stop it with sclang.
    pkill -TERM -P "$sclang_pid" 2>/dev/null
    kill -TERM "$sclang_pid" 2>/dev/null
    for _ in 1 2 3 4 5 6 7 8 9 10; do
      kill -0 "$sclang_pid" 2>/dev/null || break
      sleep 0.3
    done
    kill -KILL "$sclang_pid" 2>/dev/null
    wait 2>/dev/null
  fi
  # Anything that ignored the polite request, or still holds one of our ports.
  left=$(port_users | sort -u)
  if [ -n "$left" ]; then
    kill -KILL $left 2>/dev/null
    sleep 0.3
  fi
  left=$(port_users | sort -u)
  if [ -n "$left" ]; then
    echo "Still in use by: $(ps -o pid=,comm= -p $(echo $left | tr ' ' ,))"
    exit 1
  fi
  echo "Stopped. Ports ${PORTS_UDP[*]} are free."
  exit 0
}
trap stop INT TERM HUP EXIT
# Ctrl-Z would pause everything (and the OSC) with the ports still held; ignore it
# here and in everything started from here.
trap '' TSTP

busy=$(port_users | sort -u)
if [ -n "$busy" ]; then
  echo "These ports are already in use (another copy running?):"
  ps -o pid=,comm= -p "$(echo $busy | tr ' ' ,)"
  trap - EXIT
  exit 1
fi

if [ "$SOUND" != 1 ]; then
  echo "SuperCollider sound is off (SOUND=0 in startUwb.sh)."
elif [ -x "$SCLANG" ]; then
  mkdir -p build
  echo "SuperCollider (supercollider/sine.scd), log in $SCLANG_LOG..."
  "$SCLANG" -D supercollider/sine.scd </dev/null >"$SCLANG_LOG" 2>&1 &
  sclang_pid=$!
else
  echo "SuperCollider not found at $SCLANG; skipping it."
fi

# The terminal view runs the OSC bridge: /tagN -> 9000+ (Unreal) and 9100+ (SuperCollider).
python3 uwb.py --anchor "$ANCHOR"
