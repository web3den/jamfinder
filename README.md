# jamfinder

Locate a VHF radio transmitter with one receiver, from the echoes of its signal off passing aircraft.

**Status:** experimental research code. It has been tried only on known, licensed transmitters,
not on real interference. It is not maintained, so issues and pull requests may go unanswered.

## How it works

A transmitter's signal reaches the receiver directly, and also as faint echoes off aircraft. Each
echo is shifted in frequency by the aircraft's motion (the Doppler effect). Aircraft broadcast
their position and velocity over ADS-B, and public networks share these reports.

For each point on a map, jamfinder predicts the echoes a transmitter there would produce and
compares them with the recording. The point that fits best is the answer. If no point fits
clearly better than control searches that cannot be right, it reports nothing.

It needs one receiver in a fixed place. No antenna array, no second site, no precise clock.

More in [docs/how_it_works.md](docs/how_it_works.md).

## Install

Requires Python 3.12. The shell scripts need zsh. Developed on macOS.

    git clone https://github.com/web3den/jamfinder.git
    cd jamfinder
    python3.12 -m venv .venv
    .venv/bin/pip install -r requirements.txt

## Quick start

The demo needs no radio and no network. It builds a synthetic scene, hides a transmitter in it,
and runs the real search:

    .venv/bin/python examples/demo_synthetic.py --plot map.png

Expected output. The time at the end varies.

    scene: 6 aircraft, 10 minutes, transmitter of 10 W planted 5.0 km from the receiver

    1. with aircraft echoes
      verdict: one   (score 984.9; the software answers only above 15.0)
      best spot: 2987 m east, 4020 m north of the receiver
      true spot: 3000 m east, 4000 m north   miss: 24 m
      evidence per aircraft: SIM2 442, SIM5 431, SIM3 431, SIM1 428, SIM0 419, SIM4 260

    2. control: the same scene without echoes
      verdict: nothing   (score 5.4; the software answers only above 15.0)

    map written to map.png

    done in 9 s

![Search map from the demo](docs/img/demo_synthetic_map.png)

| Option | Meaning |
|---|---|
| `--tx E N` | Place the transmitter E metres east and N metres north of the receiver |
| `--power-db X` | Make the transmitter X dB stronger, or weaker if X is negative |
| `--seed N` | Use a different noise draw |
| `--plot FILE` | Save the search map as a picture |

## Use it on a real signal

1. Pick a steady AM carrier with busy air traffic nearby, such as an airport weather broadcast (ATIS).
2. Record aircraft positions with `tools/record_adsb.py`.
3. At the same time, record the signal for one to three hours with `tools/spy_record.py`.
4. Run `tools/run_after.sh`. It prints the verdict: a position, or "nothing".

The step-by-step guide is [docs/usage.md](docs/usage.md).

## Limitations

- It needs air traffic: about 15 or more aircraft an hour within 30 km.
- It needs a steady, narrow carrier that stays on for tens of minutes. Short bursts, wideband and
  noise-like signals, including GPS jammers, are out of reach. It has not been shown to work on FM.
- It needs a strong signal at the receiver, about 45 dB-Hz. That usually means a receiver within
  a few kilometres of the transmitter.
- It needs the receiver's position to about 10 m.
- It cannot locate a transmitter that is itself on an aircraft.
- The rule that decides when to report a position was tuned on few recordings. Treat a reported
  position as a lead to check, not as proof.

## Project layout

| Path | Contents |
|---|---|
| `jf/` | The method: signal processing, aircraft tracks, map search, reporting rule |
| `sim/` | A simulator of a transmitter among aircraft |
| `examples/` | The demo |
| `tools/` | Recorders, checks and the analysis runner |
| `analysis/` | Analysis steps and plots |
| `tests/` | Tests, on simulated data |
| `data/`, `results/` | Your recordings and outputs. Empty in the repository. |
| `docs/` | Documentation |

## Tests

    .venv/bin/python -m pytest -q

## Related work

Locating a transmitter from aircraft echoes has been described before, mostly with antenna arrays:

- S. Luan et al., "Interference locating algorithm based on scattered plane signals",
  *Systems Engineering and Electronics* 36(12), 2014.
  [Link](https://www.sys-ele.com/EN/Y2014/V36/I12/2356)
- State Radio Monitoring Center of China, "Radio interference source location method and
  system", patent application CN105717486A, 2016.
  [Link](https://patents.google.com/patent/CN105717486A/en)
- M. Krueckemeier et al., "Passive Radar Transmitter Localization Using a Planar Approximation",
  *IEEE Transactions on Aerospace and Electronic Systems* 57(5), 2021.
  [Link](https://doi.org/10.1109/TAES.2021.3074133)

## Acknowledgements

- Aircraft positions: [adsb.fi](https://adsb.fi), [adsb.lol](https://adsb.lol) and the
  [OpenSky Network](https://opensky-network.org), built on receivers shared by volunteers.
- Airport and beacon frequencies: [OurAirports](https://ourairports.com).
- The volunteers who share software-defined radio receivers online. Please be a good guest, see
  [docs/usage.md](docs/usage.md#be-a-good-guest).

## Disclaimer

Experimental research code, written with an AI coding assistant and not independently reviewed.
Do not rely on it where safety is at stake. It only receives. Follow your local rules on
listening to radio signals.

## License

[AGPL-3.0-or-later](LICENSE). Copyright (C) 2026 the jamfinder authors.
