#!/bin/bash
# Start everything for the UWB setup: the website, the OSC bridge and SuperCollider.
#
#   ./startUwb.sh                  # anchor 1 at 10.10.10.183
#   ./startUwb.sh 10.10.10.200     # or give anchor 1's IP / hostname
#
# Esc (or Ctrl-C) stops all three and frees their ports.

cd "$(dirname "$0")" || exit 1

ANCHOR="${1:-10.10.10.183}"
SCLANG="/Applications/SuperCollider.app/Contents/MacOS/sclang"
# TCP 8000 website · UDP 4210 bridge (from anchor 1) · UDP 9100 sine.scd ·
# UDP 57110 audio server (scsynth) · UDP 57120 sclang
PORTS_TCP=(8000)
PORTS_UDP=(4210 9100 57110 57120)

pids=()
sclang_pid=
stty_saved=$(stty -g 2>/dev/null)

port_users() {
  for p in "${PORTS_TCP[@]}"; do lsof -nP -t -iTCP:"$p" -sTCP:LISTEN 2>/dev/null; done
  for p in "${PORTS_UDP[@]}"; do lsof -nP -t -iUDP:"$p" 2>/dev/null; done
}

stopping=
stop() {
  [ -n "$stopping" ] && return
  stopping=1
  IFS=$' \t\n'  # Ctrl-C can arrive mid-read, while IFS is cleared
  [ -n "$stty_saved" ] && stty "$stty_saved" 2>/dev/null
  echo
  echo "Stopping..."
  # sclang's audio server (scsynth) is its child; stop it with sclang.
  [ -n "$sclang_pid" ] && pkill -TERM -P "$sclang_pid" 2>/dev/null
  kill -TERM "${pids[@]}" 2>/dev/null
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    alive=
    for pid in "${pids[@]}"; do kill -0 "$pid" 2>/dev/null && alive=1; done
    [ -z "$alive" ] && break
    sleep 0.3
  done
  # Anything that ignored the polite request, or still holds one of our ports.
  kill -KILL "${pids[@]}" 2>/dev/null
  wait 2>/dev/null
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
  close_tabs
  echo "Stopped. Ports ${PORTS_TCP[*]} ${PORTS_UDP[*]} are free."
  exit 0
}

# Close every browser tab showing the website (Chrome and Safari, if open).
close_tabs() {
  osascript >/dev/null 2>&1 <<'EOF'
on isSite(u)
  return u starts with "http://localhost:8000" or u starts with "http://127.0.0.1:8000"
end isSite
if application "Google Chrome" is running then
  tell application "Google Chrome"
    repeat with w in windows
      repeat with i from (count of tabs of w) to 1 by -1
        if my isSite(URL of tab i of w) then close tab i of w
      end repeat
    end repeat
  end tell
end if
if application "Safari" is running then
  tell application "Safari"
    repeat with w in windows
      repeat with i from (count of tabs of w) to 1 by -1
        if my isSite(URL of tab i of w) then close tab i of w
      end repeat
    end repeat
  end tell
end if
EOF
}
trap stop INT TERM HUP EXIT

busy=$(port_users | sort -u)
if [ -n "$busy" ]; then
  echo "These ports are already in use (another copy running?):"
  ps -o pid=,comm= -p "$(echo $busy | tr ' ' ,)"
  trap - EXIT
  exit 1
fi

# The programs never read the keyboard, so Esc reaches this script.
echo "Website (anchor $ANCHOR)..."
python3 -u web/server.py --anchor "$ANCHOR" </dev/null &
pids+=($!)

echo "OSC bridge: /tagN -> 9000+ (Unreal) and 9100+ (SuperCollider)..."
python3 -u osc_bridge.py --anchor "$ANCHOR" </dev/null &
pids+=($!)

if [ -x "$SCLANG" ]; then
  echo "SuperCollider (supercollider/sine.scd)..."
  "$SCLANG" -D supercollider/sine.scd </dev/null &
  sclang_pid=$!
  pids+=($!)
else
  echo "SuperCollider not found at $SCLANG; skipping it."
fi

sleep 1
open "http://localhost:8000"

echo "Running. Press Esc (or Ctrl-C) to stop everything."
while true; do
  if IFS= read -rsn1 key; then
    if [ "$key" = $'\e' ]; then
      # Arrow and function keys also start with Esc; a lone Esc has nothing after it.
      # (macOS bash only takes whole-second timeouts; the rest of a sequence is already waiting.)
      rest=
      IFS= read -rsn5 -t 1 rest
      [ -z "$rest" ] && stop
    fi
  else
    # No keyboard (run in the background): wait until stopped some other way.
    wait
    stop
  fi
done
