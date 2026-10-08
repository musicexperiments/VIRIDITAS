# VIRIDITAS

One ESP32/DW3000 anchor, one ESP32/DW3000 tag, and a live wireless distance
display. The anchor joins the Wi-Fi network set in `firmware/secrets.h`, ranges with the tag, and
hosts the web app. The Mac can remain connected to the same router by Ethernet.

## Flash the boards

First copy `firmware/secrets.example.h` to `firmware/secrets.h`, then fill in
the Wi-Fi name and password and an update password. `secrets.h` is not
committed.

Connect one board at a time, find its port, and upload the appropriate firmware:

```sh
arduino-cli board list
arduino-cli --config-file arduino-cli.yaml compile --upload -p PORT --fqbn esp32:esp32:esp32 --libraries third_party firmware/anchor
arduino-cli --config-file arduino-cli.yaml compile --upload -p PORT --fqbn esp32:esp32:esp32 --libraries third_party firmware/tag
```

After flashing, the boards only need power. The tag responds to UWB ranging
requests. The anchor continuously measures the distance and sends the result
over Wi-Fi.

## View the distance

With the Mac connected by Ethernet to the same router, open:

<http://uwb-anchor.local>

The page shows the tag-to-anchor distance in feet, centered in large bold type,
with one decimal place. If the name does not resolve, open the anchor's numeric
IP address instead. It is printed to the serial monitor at startup and is also
visible in the router's client list.

The router must allow traffic between its Wi-Fi and Ethernet clients. Do not
put the ESP32 on an isolated guest network.

The anchor starts ranging even if Wi-Fi cannot connect. It retries the router
every 15 seconds and logs Wi-Fi disconnect reasons and its assigned IP over
serial at 115200 baud. The browser retries failed requests without accumulating
overlapping polls. On startup, the anchor also logs matching access points and
their signal strengths to help distinguish reception from authentication issues.

## Anchors and tags

| Board    | Firmware            | Node | Role                                      |
|----------|---------------------|------|-------------------------------------------|
| Anchor 1 | `firmware/anchor`   | 1    | On Wi-Fi; schedules ranging, serves `/api` |
| Tag 1    | `firmware/tag`      | 2    | Tracked board                             |
| Anchor 2 | `firmware/anchor2`  | 3    | Fixed reference                           |
| Anchor 3 | `firmware/anchor3`  | 4    | Fixed reference                           |
| Anchor 4 | `firmware/anchor4`  | 5    | Fixed reference                           |
| Tag 2    | `firmware/tag2`     | 6    | Tracked board                             |
| Tag 3    | `firmware/tag3`     | 7    | Tracked board                             |
| Tag 4    | `firmware/tag4`     | 8    | Tracked board                             |

Tag N (N ≥ 2) is node N + 4, `firmware/tagN` and `uwb-tagN`. To add a tag:

1. Raise `NODE_COUNT` in `firmware/ranging.h`.
2. Create `firmware/tagN/tagN.ino` with `#define NODE_ID <N+4>`.
3. USB-flash the new tag once, then run `python3 ota.py anchor`.

The website picks up new tags automatically.

Anchor 1 measures every pair that includes a tag each cycle: each tag to
each anchor, and every tag to every other tag. With four tags that is 22
pairs, each at about 4.3 Hz. Each exchange takes about 10 ms, so the rate
falls as tags are added. Beyond this, a one-poll-many-responders scheme
would be needed to keep it fast. It measures the anchor-to-anchor pairs in turn, at
about 1 Hz each. Each tag is located separately and has its own row of X/Y
and its own color on the map. The directly measured distance between each
pair of tags is listed under the coordinates and drawn as a labelled dashed
line. N tags give N×(N−1)/2 such pairs. Tag-to-anchor lines are drawn
unlabelled; **Tag–anchor distances** shows their numbers. Tags held within a few centimetres of each other can fail to range,
because the signal is too strong at that distance. A board not heard from
for 2 s (a tag switched off, for example) is skipped, so the others keep
their rate. It is probed once a second and rejoins on its own. For a pair that does not include Anchor 1, it
asks one of the two boards to range the other and relay the result, and the
two boards take turns starting. `/api/ranges` returns every pair.

The main page prints the tag's X and Y in large type, in grid units without
a unit label. The same position in feet is shown underneath. Below is a map
of the anchors' real shape: true proportions, Anchor 1 top-left, each side
labelled in feet, with the grid lines mapped onto it. A caption names the
shape, for example "4.00 × 6.00 ft rectangle". By default (0,0) is the center of the space, and the
anchors sit at the corners of a square. Anchor 1 is top-left (-1,1), and the
rest go clockwise: Anchor 2 (1,1), Anchor 3 (1,-1), Anchor 4 (-1,-1). The
feet shown are distances from the center. The grid
values are editable under **Anchor positions**. With four anchors forming a
convex shape, a perspective map puts each anchor exactly on its grid corner, so
any four-sided space (square, rectangle, trapezoid or irregular) spans -1 to 1
and its physical size does not matter. With three anchors, or a shape that is
not convex, a least-squares affine fit is used instead.
Under **Anchor positions**,
choose **Rectangle or square** and enter only the tape-measured width
(Anchor 1 to Anchor 2) and height (Anchor 2 to Anchor 3). The other sides and
the diagonals follow from those. For any other layout, choose **Other shape**
and enter the distance between each pair of anchors: all four sides and both
diagonals, or at least five. The page builds the real shape (square,
rectangle or any other), maps it onto the grid corners and saves it to
`web/layout.json`. It warns if the distances do not fit together. With no
distances saved, it falls back to a live median of the UWB anchor-to-anchor
distances.
The tag is the least-squares fit to its distances from every anchor. The
anchors and the tag are assumed to be at the same height (a flat, 2D
problem), so mount the anchors at about the height where the tag is worn. A
tag far above or below the anchors reads slightly too far from the center. With three or more anchors that are not in a straight line, the
position has no mirror ambiguity. Keep Anchor 1 and Anchor 2 well apart,
because they set the baseline. Every board uses the same antenna delay
(default 16400), which Anchor 1 pushes to the others.

## OSC output

`osc_bridge.py` sends each tag's position and its distances to the other tags
as OSC, straight from Anchor 1 (the website is not involved):

```sh
python3 osc_bridge.py                 # /tagN -> 127.0.0.1:8999+N (/tag1 on 9000)
python3 osc_monitor.py 9000           # print what /tag1 receives
```

Anchor 1 pushes every new range to the bridge over UDP the moment it is
measured, with no polling. The bridge subscribes with `POST /api/stream`,
renewed every 5 s. Each range that involves a tag immediately produces one
message, about 20 per second per tag with four tags. The message goes to
`/tagN` on port 8999 + N (`/tag1` on 9000), with one JSON string argument:

```
{"x": 0.24, "y": -0.18, "inside": 1, "d12": 0.33, "d13": 0.58, "d14": "N/A"}
```

- `x`, `y`: -1 to 1 across the anchor grid, the same frame as the website:
  A1 (-1, 1), A2 (1, 1), A3 (1, -1), A4 (-1, -1); the center is (0, 0).
  A tag outside the shape reads as the nearest edge.
- `inside`: 1 while the tag is within the anchor shape, 0 when it is outside.
  The simulator's people never leave, so it always sends 1.
- `dNK`: the directly measured distance from tag N to tag K, divided by the
  farthest distance in the anchor shape (1 = as far apart as the shape
  allows).
- `"N/A"`: no reading in the last second. Every key is always present;
  unavailable values are `"N/A"`, never omitted.

Every tag's port stays open. `/tag1` to `/tag4` (`--tags N` for more) always
send at least twice a second, even when that tag is offline, anchor 1 is
unreachable, or no layout is saved. In those cases every value is `"N/A"`, so
a receiver never holds a stale position.

Positions use each newest reading, unsmoothed, for the least latency.
`--smooth` uses the 5-reading median instead: steadier, with about 0.5 s more
lag. `--osc-host` and `--osc-port` change the destination. The anchor layout
comes from `web/layout.json`, as saved under **Anchor positions**.

## Simulator

`simulate.py` produces the same OSC as `osc_bridge.py` with no hardware, so
software can be written and tested against realistic data. It is a single,
self-contained file (Python 3 standard library only), so it can be sent to
someone on its own:

```sh
python3 simulate.py     # menu: shape (square or rectangle), size in feet, number of people
```

People wander with curiosity. Each picks something to look at: an open spot
away from the walls, another person, or somewhere visited before. They weave
toward it along a curving path at a browsing or purposeful pace (about 0.8
m/s on average, up to 1.4 m/s), linger and look around for a moment, then
move on. They always stay inside the shape. `/tag1` goes to port 9000, `/tag2` to 9001, and so on, on
127.0.0.1. The JSON, normalisation and `"N/A"` rules are the same as the
real bridge's.

- `/tag1` to `/tag4` always send, even with fewer people. A tag with nobody
  sends every key as `"N/A"`.
- The data behaves like the hardware: a few centimetres of noise, occasional
  missing tag-to-tag readings, and `"N/A"` when two people are within a few
  inches.
- The people you choose stay online the whole time.

It leaves anything already listening on its ports (Unreal Engine, for
example) running. On macOS it opens one Terminal window per port, showing what
that path receives. Elsewhere, run `python3 simulate.py --monitor 9000` and
so on yourself. The main window draws the shape (Anchor 1 top-left,
clockwise), the people with trails, and the values being sent. Keys: the arrows
switch to fully manual (everyone stops, readings have no noise) and move
one person per press (1-8 picks which, a lets everyone wander again), space pauses, m returns to the menu, q quits and closes only the port windows it
opened. Start your own receiving software after the simulator, or close the
port windows first.

## Stream audio to a board's speaker

A board with the MAX98357A amp (wired as in `firmware/speaker_test`) can play
16 kHz mono 16-bit audio sent over UDP port 4220. Tag 4 does this while it keeps
ranging: `firmware/tag4` defines `AUDIO_STREAM`, which keeps its Wi-Fi on (as
`uwb-tag4.local`, so `ota.py tag4` needs no wake-up from the anchor). Any other
board can do the same with that one line. `firmware/audio_stream` is a speaker
only, with no UWB, as `uwb-speaker.local`. The audio code is in
`firmware/audio_stream.h`.

```sh
arduino-cli --config-file arduino-cli.yaml compile --upload -p PORT --fqbn esp32:esp32:esp32 firmware/audio_stream
/Applications/SuperCollider.app/Contents/MacOS/sclang supercollider/sine_stream.scd
```

`sine_stream.scd` opens a window to control a sine: on/off, frequency, volume,
and an option to also play it on the laptop. It starts `audio_stream.py`, which
reads the sound from the SuperCollider server, converts it to 16 kHz and sends
it to the board named in `~speaker` (tag 4 by default) in 10 ms packets. Each packet also carries the
previous 10 ms, so a single lost packet loses nothing. The board keeps about
60 ms buffered, fades over any gap instead of clicking, and adds or drops a
sample now and then to stay in step with the laptop's clock. Its stats show
at the bottom of the window. Use `python3 audio_stream.py --host IP` if the
`.local` name does not resolve.

## Update over Wi-Fi

After one USB flash of this firmware, both boards can be updated over the local
Wi-Fi (no internet needed):

```sh
python3 ota.py anchor
python3 ota.py tag
python3 ota.py anchor2   # also anchor3, anchor4, tag2
```

The anchor always accepts updates. The tag keeps its Wi-Fi off. `ota.py tag`
asks the anchor to wake the tag over UWB. The tag then joins Wi-Fi as
`uwb-tag.local` and waits up to 10 minutes for the upload, with ranging
paused. Without an upload, it reboots into normal ranging. Updates use the
password in `OTA_PASSWORD` (`firmware/ranging.h`). Use `--ip` or `--anchor`
if a `.local` name does not resolve.

## Website on the laptop

The pages are also in `web/` and run on the Mac. Edits there take effect after
a browser reload, with no reflashing. The local server forwards the `/api`
requests to the anchor over Wi-Fi:

```sh
python3 web/server.py                      # finds uwb-anchor.local
python3 web/server.py --anchor 10.10.10.183  # or use the anchor's IP
```

Then open <http://localhost:8000> for the distance and
<http://localhost:8000/calibrate> for the antenna delay.

### Calibrating across distances

The antenna delay shifts every reading by the same amount. The error at close
range changes with distance, so one delay cannot fix every distance. On
`/calibrate`:

1. Measure every distance you use, for example 1, 1.5, 2, 3, 4, 5 and 5.5 ft
   for a 4×4 ft square. Then press **Apply best delay**. This sets the delay
   that makes the average error zero.
2. Clear the table and measure the same distances again. Then press **Save as
   correction**. The pages map each reading onto the tape-measured distances
   in between (`web/correction.json`). The correction only applies at the
   delay it was measured with.

## Accuracy firmware

The ranging calculation uses asymmetric double-sided TWR with double precision
and the DW3000 clock period. Timestamp differences handle the 40-bit wrap and
reject intervals longer than 20 ms. Transmissions must complete before their
timestamps are used. HTTP requests are served between ranging exchanges.

The display uses a rolling five-sample median to reduce isolated spikes (about
200 ms of lag during steady motion at 10 Hz). This improves stability, not
absolute calibration. The API retains `raw_cm` for accuracy measurements and
reports `failed_exchanges`. Invalid readings do not refresh the last-good time;
the display expires after two seconds without a valid reading.

One decimal place in feet has 3.048 cm steps, so use the raw API or this test
for centimeter comparisons. After flashing both boards, place the antennas at
a tape-measured distance, stationary, clear of the floor/metal and with line of
sight. For example, for an actual measured 200 cm separation:

```sh
python3 check_accuracy.py --url http://10.10.10.185 --known-cm 200 --samples 200
```

Repeat at several distances and orientations. The script reports raw bias,
standard deviation, RMSE and 95th percentile absolute error; it applies no
calibration unless `--apply` is given. A stable offset is corrected with the
antenna delay (see below). Obstruction and reflections can introduce additional bias.
Default antenna values alone do not guarantee centimeter accuracy.

## Antenna delay

Both boards use one antenna-delay value for TX (`0x01:04`) and RX (`0x0E:00`).
The DW3000 library sets only the TX delay. The default is 0x3FCA (16330). The
value is stored in flash on each board. Changing it needs no USB connection:
set it on the anchor over Wi-Fi, and the anchor sends it to the tag in every
UWB poll. The anchor discards ranges until the tag reports the same value,
which takes one exchange. Two devices can only calibrate the combined delay,
so both get the same value. One tick changes the distance by about 0.94 cm,
and a higher value gives a shorter distance.

To calibrate, run the accuracy check at a tape-measured distance and apply the
suggested value, then run it again to verify:

```sh
python3 check_accuracy.py --url http://uwb-anchor.local --known-cm 200 --samples 200 --apply
```

To set or read the value directly:

```sh
curl -X POST 'http://uwb-anchor.local/api/antenna-delay?value=16330'
curl http://uwb-anchor.local/api/antenna-delay
```

`/api/distance` also reports `antenna_delay` and `tag_antenna_delay`. At boot,
each board prints `ANTENNA_DELAY,reset_tx=…,reset_rx=…,using=…` over serial.

Math reference: [Qorvo/Decawave APS013](https://forum.qorvo.com/uploads/short-url/x34DrF7EW5fQP9wY3aNESqPKz8z.pdf).
