"""Noise injection: add_noise_db must lower the carrier-to-noise ratio by exactly the requested amount, because
every "how weak can it be" figure measured on a real recording is read off this axis."""
import numpy as np

from tests.common import LAM, T0
from jf import scatter
from sim import synth


def test_added_noise_raises_the_floor_by_the_requested_db(lines, rx):
    scene = synth.Scene(lines, rx, LAM, T0, 150.0)
    bb, _ = scene.synth(np.array([3000.0, 4000.0, 85.0]), power_db=0.0, only=set(), seed=5)
    base = scatter.waterfall(bb)
    for x_db in (6.0, 12.0, 20.0):
        wf = scatter.waterfall(bb, add_noise_db=x_db, floor_dbc_hz=base["n0_dbc_hz"], seed=7)
        rise = wf["n0_dbc_hz"] - base["n0_dbc_hz"]
        assert abs(rise - x_db) < 0.6, (x_db, rise)


def test_noise_injection_is_reproducible_by_seed(lines, rx):
    scene = synth.Scene(lines, rx, LAM, T0, 60.0)
    bb, _ = scene.synth(np.array([3000.0, 4000.0, 85.0]), power_db=0.0, only=set(), seed=5)
    base = scatter.waterfall(bb)
    a = scatter.waterfall(bb, add_noise_db=10.0, floor_dbc_hz=base["n0_dbc_hz"], seed=11)
    b = scatter.waterfall(bb, add_noise_db=10.0, floor_dbc_hz=base["n0_dbc_hz"], seed=11)
    c = scatter.waterfall(bb, add_noise_db=10.0, floor_dbc_hz=base["n0_dbc_hz"], seed=12)
    assert np.array_equal(a["S"], b["S"])
    assert not np.array_equal(a["S"], c["S"])
