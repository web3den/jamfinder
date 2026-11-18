"""Shared constants and synthetic scenes for the tests. Nothing in here touches real recordings or truth files."""
import os
import sys

import numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from jf import tracks  # noqa: E402
from sim import synth  # noqa: E402

FREQ = 135.075e6
LAM = tracks.C / FREQ
T0 = 1.7e9          # an arbitrary absolute start time (unix seconds)
DUR = 600.0         # length of the synthetic scenes (s)
RX = np.array([0.0, 0.0, 45.0])


def make_lines(t0=T0, dur=DUR):
    """Six straight tracks crossing a 20 km box from different directions, 0.9-3 km up, 70-125 m/s.

    Different headings on purpose: a single flight line leaves the transmitter's mirror twin (docs/how_it_works.md).
    """
    specs = [((-9000.0, -2000.0, 1200.0), (100.0, 30.0, 0.0)),
             ((8000.0, 6000.0, 2500.0), (-80.0, -60.0, 0.0)),
             ((-6000.0, 9000.0, 1800.0), (60.0, -90.0, 0.0)),
             ((9000.0, -8000.0, 3000.0), (-110.0, 40.0, 0.0)),
             ((-9000.0, 5000.0, 900.0), (120.0, -20.0, -1.0)),
             ((2000.0, -9000.0, 2200.0), (-30.0, 110.0, 0.0))]
    out = {}
    for i, (p0, v) in enumerate(specs):
        out[f"sim{i:02d}"] = synth.Line(t0 + 20.0 * i, t0 + dur - 20.0 * i, p0, v, name=f"SIM{i}")
    return out
