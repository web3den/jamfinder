#!/usr/bin/env python3
"""Smallest end-to-end demonstration: plant a transmitter in a made-up scene and let the search find it.

No recording, no network and no receiver are needed. The simulator (sim/synth.py) makes ten minutes of
receiver signal: one hidden transmitter, six made-up aircraft flying straight lines, and noise. The real
search code (jf/field.py) then gets only what it would get in the field: the signal and the aircraft
tracks. It does not get the transmitter's place.

A second run is the control: the same scene with the aircraft echoes switched off. The software should
then say "nothing".

This shows that the chain is wired correctly and what the output looks like. It does NOT show how weak a
real transmitter can be: the simulator's echo strength is trusted to about +-5 dB (see sim/synth.py) and
real sites are harder than this scene. For that, read "What to expect" in the README.

usage: python examples/demo_synthetic.py [--tx E N] [--power-db P] [--seed S] [--plot map.png]
"""
import argparse
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from jf import field, scatter, tracks  # noqa: E402
from sim import synth  # noqa: E402

FREQ = 135.075e6               # an aviation voice frequency (Hz)
LAM = tracks.C / FREQ          # wavelength (m)
T0 = 1.7e9                     # an arbitrary start time (unix seconds)
DUR = 600.0                    # ten minutes
RX = np.array([0.0, 0.0, 45.0])   # the receiver is the origin of the map, 45 m up
SPAN, STEP = 8000.0, 500.0     # search box: +-8 km around the receiver, 500 m cells before the zoom


def make_aircraft():
    """Six straight flights crossing the area from different directions, 0.9 to 3 km up, 70 to 125 m/s.

    Different headings matter: one flight line alone cannot tell the transmitter from its mirror image
    across that line (docs/how_it_works.md, "The mirror problem").
    """
    specs = [((-9000.0, -2000.0, 1200.0), (100.0, 30.0, 0.0)),
             ((8000.0, 6000.0, 2500.0), (-80.0, -60.0, 0.0)),
             ((-6000.0, 9000.0, 1800.0), (60.0, -90.0, 0.0)),
             ((9000.0, -8000.0, 3000.0), (-110.0, 40.0, 0.0)),
             ((-9000.0, 5000.0, 900.0), (120.0, -20.0, -1.0)),
             ((2000.0, -9000.0, 2200.0), (-30.0, 110.0, 0.0))]
    return {f"sim{i:02d}": synth.Line(T0 + 20.0 * i, T0 + DUR - 20.0 * i, p0, v, name=f"SIM{i}")
            for i, (p0, v) in enumerate(specs)}


def locate(bb, aircraft):
    """The same three steps the real pipeline runs on a recording."""
    wf = scatter.waterfall(bb)                       # spectra over time, +-250 Hz around the carrier
    W, _ = scatter.whiten(wf["S"], wf["f"])          # divide out the noise floor
    return field.search(wf["t"], wf["f"], W, aircraft, RX, LAM, span=SPAN, step=STEP, k_peaks=3)


def report(title, r, aircraft, tx=None):
    label, _ = field.verdict(r["cands"])
    best = r["cands"][0]
    print(f"\n{title}")
    print(f"  verdict: {label}   (score {best[0]:.1f}; the software answers only above {field.THRESHOLD:.1f})")
    if label == "nothing":
        return label
    print(f"  best spot: {best[1]:.0f} m east, {best[2]:.0f} m north of the receiver")
    if tx is not None:
        print(f"  true spot: {tx[0]:.0f} m east, {tx[1]:.0f} m north"
              f"   miss: {np.hypot(best[1] - tx[0], best[2] - tx[1]):.0f} m")
    sup = field.support(r["field"], best, r["clocks"][0])
    print("  evidence per aircraft: " + ", ".join(f"{aircraft[h].flight} {z:.0f}" for z, h in sup))
    return label


def plot(r, tx, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    e, n, m = r["mapA"]
    best = r["cands"][0]
    fig, ax = plt.subplots(figsize=(6.4, 5.6))
    im = ax.imshow(m, origin="lower", extent=[e[0] / 1e3, e[-1] / 1e3, n[0] / 1e3, n[-1] / 1e3], cmap="viridis")
    ax.plot(0, 0, "w^", ms=9, label="receiver")
    ax.plot(tx[0] / 1e3, tx[1] / 1e3, "wx", ms=11, mew=2, label="planted transmitter")
    ax.plot(best[1] / 1e3, best[2] / 1e3, "o", mfc="none", mec="r", ms=14, mew=2, label="software's answer")
    ax.set_xlabel("east of the receiver (km)")
    ax.set_ylabel("north of the receiver (km)")
    ax.set_title("How well each place explains the echoes (synthetic scene)")
    ax.legend(loc="lower left", fontsize=8)
    fig.colorbar(im, ax=ax, label="score")
    fig.tight_layout()
    fig.savefig(path, dpi=130)
    print(f"\nmap written to {path}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--tx", nargs=2, type=float, default=[3000.0, 4000.0], metavar=("E", "N"),
                    help="where to plant the transmitter, metres east and north of the receiver")
    ap.add_argument("--power-db", type=float, default=0.0, help="transmitter power relative to 10 W")
    ap.add_argument("--seed", type=int, default=3)
    ap.add_argument("--plot", metavar="PNG", help="also write the search map as a picture")
    a = ap.parse_args()

    aircraft = make_aircraft()
    scene = synth.Scene(aircraft, RX, LAM, T0, DUR)
    tx = np.array([a.tx[0], a.tx[1], 85.0])
    t_run = time.time()
    print(f"scene: {len(aircraft)} aircraft, {DUR / 60:.0f} minutes, transmitter of "
          f"{10 ** (1 + a.power_db / 10):.3g} W planted {np.hypot(tx[0], tx[1]) / 1e3:.1f} km from the receiver")

    bb, _ = scene.synth(tx, power_db=a.power_db, seed=a.seed)
    r = locate(bb, aircraft)
    report("1. with aircraft echoes", r, aircraft, tx)

    bb0, _ = scene.synth(tx, power_db=a.power_db, only=set(), seed=a.seed + 1)   # direct signal only
    report("2. control: the same scene without echoes", locate(bb0, aircraft), aircraft)

    if a.plot:
        plot(r, tx, a.plot)
    print(f"\ndone in {time.time() - t_run:.0f} s")
