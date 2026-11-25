"""The function under test in the oracle experiment, in two versions.

`bistatic_doppler` is what the model is shown: a plausible implementation with one planted mistake, the sign of
the transmitter leg. It is the kind of slip a person or a model makes once and then tests against itself.
`bistatic_doppler_correct` is the repository's own physics (jf/tracks.py, doppler_pv) for a single point.

Requirement (the independent source of truth): the echo's frequency shift is minus the rate at which the path
transmitter -> aircraft -> receiver gets longer, divided by the wavelength.
"""
import numpy as np

from jf import tracks

REQUIREMENT = ("Return the Doppler shift in Hz of the echo that a transmitter at `tx` produces off an aircraft at "
               "position `p` moving with velocity `v`, as heard by a receiver at `rx`. Positions in metres in one "
               "local frame, velocity in m/s, wavelength `lam` in metres.")

BUGGY_SOURCE = '''import numpy as np


def bistatic_doppler(p, v, tx, rx, lam):
    """Doppler shift (Hz) of the echo off an aircraft at p (m) moving at v (m/s), transmitter tx, receiver rx."""
    p, v, tx, rx = (np.asarray(a, float) for a in (p, v, tx, rx))
    u_rx = (p - rx) / np.linalg.norm(p - rx)      # unit vector receiver -> aircraft
    u_tx = (p - tx) / np.linalg.norm(p - tx)      # unit vector transmitter -> aircraft
    return -(np.dot(v, u_rx) - np.dot(v, u_tx)) / lam
'''

CORRECT_SOURCE = '''import numpy as np

from jf import tracks


def bistatic_doppler(p, v, tx, rx, lam):
    """The repository's implementation (jf/tracks.py, doppler_pv) for one point."""
    p, v = np.asarray(p, float)[None, :], np.asarray(v, float)[None, :]
    return float(tracks.doppler_pv(p, v, np.asarray(tx, float), np.asarray(rx, float), lam)[0])
'''


def bistatic_doppler_correct(p, v, tx, rx, lam):
    p, v = np.asarray(p, float)[None, :], np.asarray(v, float)[None, :]
    return float(tracks.doppler_pv(p, v, np.asarray(tx, float), np.asarray(rx, float), lam)[0])
