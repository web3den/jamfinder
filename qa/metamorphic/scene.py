"""One synthetic scene, the full pipeline, and the transformations the metamorphic tests apply to the scene.

The pipeline is the one a real recording goes through: simulated receiver signal (sim/synth.py) -> waterfall and
whitening (jf/scatter.py) -> map search (jf/field.py). The transmitter is planted 5 km out, the search box is
+-8 km, so one run takes a few seconds.
"""
from dataclasses import dataclass

import numpy as np

from jf import field, scatter, tracks
from sim import synth

FREQ = 135.075e6
LAM = tracks.C / FREQ
T0, DUR = 1.7e9, 600.0
RX = np.array([0.0, 0.0, 45.0])
TX = np.array([3000.0, 4000.0, 85.0])
FLIGHTS = [((-9000.0, -2000.0, 1200.0), (100.0, 30.0, 0.0)), ((8000.0, 6000.0, 2500.0), (-80.0, -60.0, 0.0)),
           ((-6000.0, 9000.0, 1800.0), (60.0, -90.0, 0.0)), ((9000.0, -8000.0, 3000.0), (-110.0, 40.0, 0.0)),
           ((-9000.0, 5000.0, 900.0), (120.0, -20.0, -1.0)), ((2000.0, -9000.0, 2200.0), (-30.0, 110.0, 0.0))]


@dataclass
class Scene:
    tx: np.ndarray
    aircraft: dict           # hex -> synth.Line
    t0: float = T0


@dataclass
class Found:
    east: float
    north: float
    score: float
    verdict: str

    def distance(self, e, n):
        return float(np.hypot(self.east - e, self.north - n))


def base_scene():
    return Scene(TX.copy(), {f"sim{i:02d}": synth.Line(T0 + 20.0 * i, T0 + DUR - 20.0 * i, p0, v, name=f"SIM{i}")
                             for i, (p0, v) in enumerate(FLIGHTS)})


def signal(scene, seed=0):
    """The receiver's baseband signal for a scene. Position reports are exact (no lateness, no track error), so a
    turned or mirrored scene is exactly the same scene; with the simulator's default 10-m track errors, which are
    drawn in a fixed frame, it would not be."""
    sim = synth.Scene(scene.aircraft, RX, LAM, scene.t0, DUR)
    return sim.synth(scene.tx, seed=seed, latency=(0.0, 0.0), pos_sigma=0.0)[0]


def locate(bb, aircraft):
    wf = scatter.waterfall(bb)
    W, _ = scatter.whiten(wf["S"], wf["f"])
    r = field.search(wf["t"], wf["f"], W, aircraft, RX, LAM, span=8000.0, step=500.0, k_peaks=3)
    best = r["cands"][0]
    return Found(float(best[1]), float(best[2]), float(best[0]), field.verdict(r["cands"])[0])


# ---- transformations of a scene ---------------------------------------------------------------------------------

def shifted_in_time(scene, seconds):
    """Everything happens `seconds` later: the recording and every flight."""
    return Scene(scene.tx, {h: synth.Line(a.t0 + seconds, a.t1 + seconds, a.p0, a.v, a.flight)
                            for h, a in scene.aircraft.items()}, scene.t0 + seconds)


def turned(scene, quarter_turns):
    """The whole scene turned about the receiver by multiples of 90 degrees (the search grid maps onto itself)."""
    k = quarter_turns % 4
    c, s = [1, 0, -1, 0][k], [0, 1, 0, -1][k]
    rot = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], float)
    return Scene(rot @ scene.tx, {h: synth.Line(a.t0, a.t1, rot @ a.p0, rot @ a.v, a.flight)
                                  for h, a in scene.aircraft.items()}, scene.t0)


def mirrored(scene):
    """East and west swapped."""
    m = np.diag([-1.0, 1.0, 1.0])
    return Scene(m @ scene.tx, {h: synth.Line(a.t0, a.t1, m @ a.p0, m @ a.v, a.flight)
                                for h, a in scene.aircraft.items()}, scene.t0)


def with_transmitter_moved(scene, de, dn):
    return Scene(scene.tx + np.array([de, dn, 0.0]), scene.aircraft, scene.t0)


def reordered(aircraft):
    return dict(reversed(list(aircraft.items())))


def scaled(bb, gain):
    """A receiver with different gain: every sample multiplied by the same complex number."""
    return dict(bb, y=(bb["y"] * gain).astype(np.complex64))


def detuned(bb, hz):
    """A receiver tuned `hz` off the carrier: the whole spectrum slides by that much."""
    n = np.arange(len(bb["y"]))
    return dict(bb, y=(bb["y"] * np.exp(2j * np.pi * hz * n / float(bb["fs"]))).astype(np.complex64))
