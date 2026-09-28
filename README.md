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

## Anchors and tag

| Board    | Firmware            | Node | Role                                      |
|----------|---------------------|------|-------------------------------------------|
| Anchor 1 | `firmware/anchor`   | 1    | On Wi-Fi; schedules ranging, serves `/api` |
| Tag      | `firmware/tag`      | 2    | The tracked board                         |
| Anchor 2 | `firmware/anchor2`  | 3    | Fixed reference                           |
| Anchor 3 | `firmware/anchor3`  | 4    | Fixed reference                           |
| Anchor 4 | `firmware/anchor4`  | 5    | Fixed reference                           |

Anchor 1 measures every pair of boards. The tag's four distances are measured
every cycle, at about 6 Hz each. The anchor-to-anchor distances are measured
in turn, at about 1 Hz each. For a pair that does not include Anchor 1, it
asks one of the two boards to range the other and relay the result, and the
two boards take turns starting. `/api/ranges` returns every pair.

The main page prints the tag's X and Y in large type, in grid units without
a unit label. The same position in feet is shown underneath. Below is a map
with each distance on its line. By default (0,0) is the center of the space, and the
anchors sit at the corners of a square. Anchor 1 is top-left (-1,1), and the
rest go clockwise: Anchor 2 (1,1), Anchor 3 (1,-1), Anchor 4 (-1,-1). The
feet shown are distances from the center. The grid
values are editable under **Anchor positions**. A least-squares affine fit
maps the real anchor positions onto the grid, so the square's physical size
does not matter. Anchor 1 is the origin and Anchor 2 lies on the +x axis.
The anchors are assumed to sit on the floor. Under **Anchor positions**,
choose **Rectangle or square** and enter only the tape-measured width
(Anchor 1 to Anchor 2) and height (Anchor 2 to Anchor 3). The other sides and
the diagonals follow from those. For any other layout, choose **Other shape**
and enter the distance between each pair of anchors: all four sides and both
diagonals, or at least five. The page builds the real shape (square,
rectangle or any other), maps it onto the grid corners and saves it to
`web/layout.json`. It warns if the distances do not fit together. With no
distances saved, it falls back to a live median of the UWB anchor-to-anchor
distances.
The tag is the least-squares fit to its distances from every anchor. With
three or more anchors, the fit also solves the tag's height above the floor,
so holding the tag up does not stretch its X and Y. With three or more anchors that are not in a straight line, the
position has no mirror ambiguity. Keep Anchor 1 and Anchor 2 well apart,
because they set the baseline. Every board uses the same antenna delay
(default 16400), which Anchor 1 pushes to the others.

## Update over Wi-Fi

After one USB flash of this firmware, both boards can be updated over the local
Wi-Fi (no internet needed):

```sh
python3 ota.py anchor
python3 ota.py tag
python3 ota.py anchor2
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
