#!/bin/bash
# Start everything for the UWB setup: the terminal view (uwb.py: anchor layout,
# live map, OSC bridge) in this window and, when SOUND=1 below, SuperCollider's
# Four Tags FX in the background (its window opens on its own).
#
# Four Tags FX draws its pad from the anchor layout, so uwb.py starts it only
# once the layout menu is done (and restarts it if the layout is changed later
# from the view). Both get the same settings from here: the tag count, the base
# port the bridge sends /tag1-/tagN to for SuperCollider, and this folder
# (layout.json, audio_stream.py). Four Tags FX moves each tag's dot from /tagN
# and streams each tag's sound to that tag's speaker.
#
#   ./startUwb.sh                  # anchor 1 at 10.10.10.183
#   ./startUwb.sh 10.10.10.200     # or give anchor 1's IP / hostname
#
# q in the view (or Ctrl-C) stops both and frees their ports.

cd "$(dirname "$0")" || exit 1

ANCHOR="${1:-10.10.10.183}"
SOUND=1  # 1 starts SuperCollider (Four Tags FX, SC_SCRIPT); 0 leaves the sound off.
SC_SCRIPT="$PWD/supercollider/four-tags-fx.scd"   # with its SynthDefs/ and pbind-demos/ beside it
TAGS=4         # /tag1 to /tagN, always sent
SC_PORT=9100   # /tag1 to SuperCollider on this port, /tag2 on the next, ...
SCLANG_LOG="build/sclang.log"
# UDP 4210 bridge (from anchor 1) · UDP 9100-9103 Four Tags FX's /tagN ·
# UDP 57110 audio server (scsynth) · UDP 57120 sclang ·
# UDP 57200-57203 each tag's audio_stream.py status
PORTS_UDP=(4210 $(seq "$SC_PORT" $((SC_PORT + TAGS - 1))) 57110 57120 $(seq 57200 $((57200 + TAGS - 1))))

port_users() {
  for p in "${PORTS_UDP[@]}"; do lsof -nP -t -iUDP:"$p" 2>/dev/null; done
}

stopping=
stop() {
  [ -n "$stopping" ] && return
  stopping=1
  # uwb.py stops SuperCollider when it quits; this catches anything left
  # (uwb.py killed, say) that still holds one of our ports.
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

sound=()
if [ "$SOUND" != 1 ]; then
  echo "SuperCollider sound is off (SOUND=0 in startUwb.sh)."
elif [ ! -f "$SC_SCRIPT" ]; then
  echo "SuperCollider script not found at $SC_SCRIPT; skipping it."
else
  echo "SuperCollider ($(basename "$SC_SCRIPT")) starts once the anchor layout is set, log in $SCLANG_LOG."
  sound=(--sound-script "$SC_SCRIPT" --sound-log "$SCLANG_LOG")
fi

# The terminal view runs the OSC bridge: /tagN -> 9000+ (Unreal) and 9100+ (SuperCollider).
python3 uwb.py --anchor "$ANCHOR" --tags "$TAGS" --also-port "$SC_PORT" "${sound[@]}"
