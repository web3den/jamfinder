# Try it yourself

There are three levels. The first needs nothing but Python. The second needs a network
receiver that someone lets you use. The third needs your own receiver, and that part was
never built or tested here.

Everything below was run on macOS with Python 3.12. The shell scripts are written for zsh.

## Level 1: the simulator, no radio

    python3.12 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    .venv/bin/python examples/demo_synthetic.py --plot map.png
    .venv/bin/python -m pytest -q

The demo plants a made-up transmitter among six made-up aircraft and runs the real search on
it. It takes about ten seconds. Options:

| Option | Meaning |
|---|---|
| `--tx E N` | Where to plant the transmitter, in metres east and north of the receiver |
| `--power-db X` | Make the transmitter stronger or weaker by X dB |
| `--seed N` | A different noise draw |
| `--plot FILE` | Save the search map as a picture |

Lower the power until the answer turns into "nothing". In this made-up scene the software
goes quiet before it goes wrong. We ran it at six lower powers with three noise draws each.
Down to 30 dB weaker, every answer was within 51 m of the planted spot. At 35 dB weaker one
of three draws still answered, 16 m off, and the other two said "nothing". At 40 and 45 dB
weaker all said "nothing". Real recordings were not that clean. Earlier versions of the
reporting rule reported wrong spots on them. See "What to expect" in the
[README](../README.md).

The tests run on simulated data. None needs a recording. Expect 45 passed and 1 expected
failure, in about a minute. The expected failure records a bound that one optional way of
scoring does not meet. The search does not use that one unless asked.

## Level 2: a real signal through a network receiver

This is how every real run in this project was made. The recorder speaks the SpyServer
protocol, which many volunteer-run public receivers use.

### Pick a target that can work

| Need | Why |
|---|---|
| An airport weather broadcast on AM, 118 to 137 MHz | A steady carrier at a known, licensed place |
| A receiver within about 10 km of it | The signal must reach about 45 dB-Hz or more |
| 15 or more aircraft an hour within 30 km | The echoes come from them. Daytime at a busy airport. |
| One to three hours | Helsinki worked within an hour. At Ottawa the first 72 minutes alone put the best spot 138 m from the reference, and the last 72 minutes alone put it 20 km off. |
| The receiver's position, to about 10 m | A listed position can be off by hundreds of metres |

Write down where you believe the transmitter is before you look at any result. Better, seal it
in a file and open it only after the software has given its answer.

### Be a polite guest

Public receivers belong to volunteers and have few listener slots.

- One session per receiver. Disconnect when done. Do not hold a slot overnight.
- Keep to the owner's session limit. Do not start a new session the moment one ends. This
  project did that on 16 November and should not have.
- If you change the gain of a shared receiver, set it back before you leave. The recorder
  here does not do that for you.
- Do not probe a server again and again. One server stopped answering this project after
  seven probes in eight minutes.
- Keep aircraft position requests at or under one per second per service, and read each
  service's terms. Some forbid commercial use.
- Only receive. Check your country's rules on listening. This project recorded weather
  broadcasts and navigation beacons, not conversations.
- Do not publish other people's receiver addresses or their owners' details. The description
  file that the recorder writes holds the server's address and the receiver's hardware serial
  number. Remove both before you share a recording.

### Record

First check that the receiver lets you tune and hears the carrier. Tune a little below the
carrier, so it does not sit on the receiver's centre frequency. Here the target is 121.150 MHz
and the tuning is 1.5 kHz below it.

    .venv/bin/python tools/spy_probe.py HOST PORT 121148500

The probe prints one line of JSON. The field `can_control` says whether the server lets you
set the radio at all. The field `tuned_sync` says whether it confirmed the frequency you asked
for.

Start the aircraft positions a minute early and let them run a minute long. Use a second
terminal, because both recorders run at the same time. The numbers in the address are the
receiver's latitude, longitude and a radius in nautical miles. The position `45.29 -75.73`
here and further down is only an example. Put in your receiver's own.

    mkdir -p data/iq/site1
    .venv/bin/python tools/record_adsb.py data/iq/site1/adsb_1.jsonl.gz \
        "https://opendata.adsb.fi/api/v3/lat/45.29/lon/-75.73/dist/40" 7320 5

Then record the signal, here for two hours.

    .venv/bin/python tools/spy_record.py HOST PORT 121148500 12000 7200 \
        data/iq/site1/site1 -1 12 require_tune=1 tune_timeout=240

The `-1` leaves the receiver's radio gain alone. The `12` asks for a fixed output gain of
12 dB. Always ask for a fixed output gain. The automatic one moves up and down a few times a
second and cost 3 to 7 dB of echo strength in our measurements.

`require_tune=1` stops the recording if the receiver does not confirm the frequency within
`tune_timeout` seconds. Some servers accept a frequency and silently stay where they were.
Servers that did retune took 21, 55 and 179 seconds to confirm, so the default of 60 is too
short for some. One server never confirmed although it had tuned. For that one we recorded
with `require_tune=0` and checked the carrier's place in the first-minute look instead.

Mind the radio gain too. A public receiver sits at whatever radio gain its owner or the last
listener left. At Helsinki the idle setting made the signal 15 dB weaker than the setting of
the good recordings. If the first look shows a weak carrier, a higher gain index in place of
the `-1` may help, where the server lets you set it. That changes the radio for every other
listener too, so do it sparingly.

While it records, look at the first minute:

    .venv/bin/python tools/quick_look.py data/iq/site1/site1

It prints where the carrier sits and two loudness figures. Read the second one, measured
against the noise 1 to 4 kHz away from the carrier. In the cases we compared, it read about
3 to 4 dB under the search's own `cn0`. The first figure is measured close to the carrier.
In two of our runs it read about 10 dB lower still, so do not judge by it. Below about
45 dB-Hz on the search's scale, expect "nothing".

### Analyse

One script runs the whole sequence: repair of lost samples, the search, the fit of
the receiver's own position, the wrong-track tests, and the first reporting rules.

    zsh tools/blind_pipeline.sh site1 data/iq/site1/site1 data/iq/site1/adsb_1.jsonl.gz \
        45.29 -75.73 121150000 80 95 80 "-1200,-600,-300,300,600,1200"

The arguments are: a name, the recording, the positions file, the receiver's latitude and
longitude, the carrier frequency in hertz, the receiver antenna's height, a guess of the
transmitter antenna's height, the height given to aircraft that report "on the ground", and
the time shifts in seconds for the wrong-track tests. Heights are in metres in the frame of
the aircraft's geometric altitude, which is the height a satellite navigation receiver
reports. It differs from height above sea level by up to tens of metres, depending on where
you are.

Then apply the final rule:

    .venv/bin/python analysis/rule_v31.py site1r data/iq/site1/adsb_1.jsonl.gz 45.29 -75.73 ground_h=80

It prints the verdicts of rules v3, v3.1 and v3.2. The last one is the final rule of this
project. On a small 2024 desktop with 16 GB of memory, the analysis took 15 to 20 minutes
for a one-hour recording with about 30 aircraft, and over two hours for a two-hour recording
with 229 aircraft. The repaired copy of a recording is stored as 32-bit numbers. That is twice
the size of a 16-bit recording and four times the size of an 8-bit one, so keep a few
gigabytes of disk free.

### Read the answer

| File | What it holds |
|---|---|
| `results/site1r_fix_rxfit.json` | Best spots, scores, loudness, aircraft used, the fitted receiver position |
| `results/site1r_null.jsonl` | Scores of the wrong-track tests |
| `results/site1r_rules.json` | Verdicts of the early rules and their six conditions, `a` to `f` |
| `results/site1r_rules_v31.json` | Verdicts of rules v3 to v3.2. Field `v32` is the final rule. |

Every field is explained in [results/README.md](../results/README.md).

Trust the verdict more than the map. A bright spot on the map means little by itself: the
wrong-track tests also produce bright spots. And do not adjust settings after seeing where the
spot lands. That is how a rule gets tuned to its own data, which happened here.

## Level 3: your own receiver

No recorder for a local receiver is included. Any software radio program that can save raw
samples will do, if you convert its output to the format below. The Helsinki volunteer's
receiver reported itself as an RTL-SDR, the 30 to 40 dollar kind, and that site gave the best
results. Use fixed gain, a band filter if a strong station is nearby, and an antenna with a
clear view of the sky. Measure the antenna's position with a phone or a map to about 10 m.

A recording is two files with the same name.

| File | Content |
|---|---|
| `name.iq` | Raw samples, in-phase and quadrature interleaved. Unsigned 8-bit, signed 16-bit little-endian, or 32-bit float. |
| `name.json` | A description, see below |

The description needs these fields:

| Field | Meaning |
|---|---|
| `kind` | `"u8"`, `"i16"` or `"f32"` |
| `rate` | Samples per second. 12,000 or more is plenty. |
| `freq` | The tuned centre frequency in hertz |
| `nsamp` | Number of samples |
| `partial` | `false` when the recording is complete |
| `msgs` | Time stamps. One row per block of samples as it arrived: `[unix time, index of the block's first sample, 0]` |

The software fits a straight line through the earliest time stamps to learn when each sample
was taken. The network recorder writes about 100 rows a second. Fewer rows a second were not
tested. There is one hard limit: the repair step stops with an error unless the whole
recording has more than 60 times the sample rate divided by 96 rows. That is 7,500 rows at
12,000 samples a second. The search also tries time offsets of up to about a second, for the
whole recording and for each aircraft. So a computer clock set by an ordinary internet time
service is good enough.

Aircraft positions are lines of JSON in a gzip file, one line per request, as
`tools/record_adsb.py` writes them: `{"t0": ..., "t1": ..., "now": ..., "ac": [...]}`, with the
aircraft list in the format of the readsb decoder. If you run your own ADS-B receiver, its
own aircraft list can be wrapped the same way.

This level is untested.

## More

- Every script has a one-line description in [script_index.md](script_index.md).
- The method is explained in plain language in [how_it_works.md](how_it_works.md).
- What to expect, and what the method cannot do, is in the [README](../README.md).
