# Usage

How to record a real signal and find where it comes from. To try the method without a radio
first, run the demo in the [README](../README.md#quick-start).

Run all commands from the repository's root folder, after the install steps in the README. The
shell scripts need zsh.

## 1. Choose a target

The method needs a steady AM carrier with busy air traffic around it. An airport weather
broadcast (ATIS) is a good first target.

| You need | Why |
|---|---|
| A carrier that stays on, AM, 118 to 137 MHz | The search follows one steady tone |
| A strong signal at the receiver, about 45 dB-Hz or more | The echoes are 40 to 60 dB weaker than the direct signal |
| 15 or more aircraft an hour within 30 km | The aircraft make the echoes |
| One to three hours of recording | The evidence builds up slowly |
| The receiver's position, to about 10 m | An error here becomes an error in the answer |

To list airport frequencies and VOR beacons near a point, download `airports.csv`,
`airport-frequencies.csv` and `navaids.csv` from [OurAirports](https://ourairports.com/data/)
into one folder, and give the folder, a latitude, a longitude and a radius in kilometres:

    .venv/bin/python tools/nearby.py path/to/ourairports 41.88 -87.63 30

## 2. Check the receiver

The recorder in this repository speaks SpyServer, the protocol of many public receivers run by
volunteers. To use your own receiver instead, see [Your own receiver](#your-own-receiver).

The examples use these values. Replace them with yours.

| | Example |
|---|---|
| Receiver address and port | `HOST` and `PORT` |
| Receiver position | 41.88, -87.63 |
| Carrier frequency | 121.150 MHz |
| Tuning frequency | 121.1485 MHz, 1.5 kHz below the carrier, so that the carrier does not sit on the receiver's centre |

Check that the receiver lets you tune and hears the carrier:

    .venv/bin/python tools/spy_probe.py HOST PORT 121148500

It holds the connection for less than a minute and prints one line of JSON. `can_control` tells
whether you may set the frequency. `tuned_sync` tells whether the receiver confirmed it.

## 3. Record

Record the aircraft positions and the signal at the same time, in two terminals. Start the
positions a minute before the signal.

Terminal 1, aircraft positions within 40 nautical miles, every 5 seconds, for 7,320 seconds:

    mkdir -p data/iq/site1
    .venv/bin/python tools/record_adsb.py data/iq/site1/adsb_1.jsonl.gz \
        "https://opendata.adsb.fi/api/v3/lat/41.88/lon/-87.63/dist/40" 7320 5

Terminal 2, two hours of signal at 12,000 samples per second:

    .venv/bin/python tools/spy_record.py HOST PORT 121148500 12000 7200 \
        data/iq/site1/site1 -1 12 require_tune=1 tune_timeout=240

| Argument | Meaning |
|---|---|
| `-1` | Leave the receiver's radio gain as it is |
| `12` | A fixed digital gain of 12 dB. Always use a fixed gain. Automatic gain weakens the echoes. |
| `require_tune=1` | Stop if the receiver does not confirm the frequency |
| `tune_timeout=240` | Wait up to 240 seconds for that confirmation. Some servers are slow. |

Some servers retune but never confirm. For those, use `require_tune=0` and check the carrier
with the quick look below.

While it records, check the first minute:

    .venv/bin/python tools/quick_look.py data/iq/site1/site1

It prints where the carrier sits and two strength figures. Use the second one, measured against
the noise 1 to 4 kHz away. It reads a few dB below the analysis's own figure. Below about
41 dB-Hz, expect the answer "nothing".

If the carrier is weak, a higher gain index in place of `-1` may help, where the server allows
it. That changes the radio for every listener, so set it back when you are done.

Other sources of aircraft positions:

- Any other API in the readsb format works with `tools/record_adsb.py`. Record two sources at
  once into `adsb_1.jsonl.gz` and `adsb_2.jsonl.gz`, and the analysis merges them.
- `tools/record_opensky.py` records from the OpenSky Network. Its positions are 15 seconds or
  more apart, so add `max_gap=30` at the end of the analysis command.

## 4. Analyse

One command runs the whole analysis and prints the verdict:

    zsh tools/run_after.sh site1 data/iq/site1/site1 41.88 -87.63 121150000 170 180 170 \
        "-1200,-600,-300,300,600,1200"

| Argument | Meaning |
|---|---|
| `site1` | A name for the run |
| `data/iq/site1/site1` | The recording, without `.iq` |
| `41.88 -87.63` | The receiver's latitude and longitude |
| `121150000` | The carrier frequency in Hz |
| `170` | The receiver antenna's height |
| `180` | The transmitter antenna's height. A guess is fine. |
| `170` | The height used for aircraft that report "on ground" |
| `"-1200,...,1200"` | Time shifts in seconds for the control searches. Keep this list. |

Heights are in metres above the WGS84 ellipsoid, the reference of the aircraft's GPS altitude.
That can differ from height above sea level by tens of metres, depending on where you are.

You can start the command while the recording runs. It waits until the recording is finished,
then uses every `adsb_*.jsonl.gz` file in the recording's folder.

Expect 15 to 20 minutes per hour of recording, more with heavy traffic. The analysis makes a
temporary copy about four times the size of the recording, so keep a few gigabytes of disk free.
The copy is deleted at the end. Your recording is kept.

## 5. Read the result

The last line printed shows the verdicts and the best spot:

    v3: ...   v3.1: ...   v3.2: one   best spot <latitude>, <longitude> ...

Read `v3.2`. It is the current rule. The two before it are older rules, kept for comparison.

- `one`: the best spot is the answer.
- `nothing`: no spot stood clearly above the control searches. The best spot is still printed.
  Do not trust it.

The same result is saved in `results/site1r_rules_v31.json`.
[results/README.md](../results/README.md) explains the output files.

Some advice:

- A bright spot on a map is not an answer. The control searches produce bright spots too.
- Do not change settings after seeing where the spot lands. That tunes the method to its own data.
- If you test against a transmitter whose position you know, write the position down before you
  look at the answer.

## Your own receiver

No recorder for a local receiver is included, and this path has not been tested. Any
software-defined radio program that saves raw IQ samples can work, once its output is converted
to the format below. A cheap RTL-SDR dongle can be enough. Use a fixed gain and an antenna with a
clear view of the sky. Measure the antenna's position to about 10 m.

A recording is two files with the same name:

| File | Content |
|---|---|
| `name.iq` | Raw samples, I and Q interleaved: unsigned 8-bit, signed 16-bit little-endian, or 32-bit float |
| `name.json` | A description, with the fields below |

| Field | Meaning |
|---|---|
| `kind` | `"u8"`, `"i16"` or `"f32"` |
| `rate` | Samples per second. 12,000 or more is plenty. |
| `freq` | The tuned centre frequency in Hz |
| `nsamp` | The number of samples |
| `partial` | `false` when the recording is complete |
| `msgs` | Time stamps, one row per block of samples as it arrived: `[unix time, index of the block's first sample, digital gain in dB, or 0]` |

The software fits a straight line through the time stamps to learn when each sample was taken.
The network recorder writes about 100 rows a second. Fewer were not tested. The repair step needs
more than 60 × rate / 96 rows in total, which is 7,500 rows at 12,000 samples a second. A
computer clock set by an ordinary internet time service is accurate enough.

Aircraft positions are gzip files of JSON lines, one line per request, as `tools/record_adsb.py`
writes them: `{"t0": ..., "t1": ..., "now": ..., "ac": [...]}`, with the aircraft list in the
readsb format. The aircraft list of your own ADS-B receiver can be wrapped the same way.

## Be a good guest

Public receivers belong to volunteers and have few listener slots.

- Use one session per receiver, and disconnect when you are done.
- Keep to the owner's session limit. Do not reconnect the moment a session ends.
- If you change a shared receiver's gain, set it back before you leave. The recorder does not
  do this for you.
- Do not probe a server again and again.
- Keep requests for aircraft positions at or under one per second per service, and follow each
  service's terms. Some forbid commercial use.
- Only receive. Check your country's rules on listening to radio signals.
- Do not publish receiver addresses or their owners' details. The `.json` file of a recording
  holds the server's address and the receiver's serial number. Remove both before you share a
  recording.

## Scripts

| Script | What it does |
|---|---|
| `tools/nearby.py` | Lists airport frequencies and VOR beacons near a point |
| `tools/spy_probe.py` | Checks a SpyServer receiver: can you tune it, is the carrier there |
| `tools/spy_record.py` | Records IQ samples from a SpyServer receiver |
| `tools/record_adsb.py` | Records aircraft positions from an API in the readsb format |
| `tools/record_opensky.py` | Records aircraft positions from the OpenSky Network |
| `tools/quick_look.py` | Checks the first minute of a recording |
| `tools/run_after.sh` | Runs the whole analysis once a recording is finished |

The other scripts in `tools/` and `analysis/` are steps of the analysis and helpers. Each one
describes itself at the top of the file.
