"""The geometry the whole method rests on, checked against finite differences."""
import numpy as np

from tests.common import LAM
from jf import tracks
from sim import synth


def test_doppler_equals_minus_range_rate_over_lambda():
    """f_k = -(1/lambda) d/dt (R1 + R2): the bistatic Doppler of the self-referenced echo."""
    line = synth.Line(0.0, 100.0, (-5000.0, 2000.0, 1500.0), (90.0, 40.0, 0.0))
    tx = np.array([1200.0, -800.0, 85.0])
    rx = np.array([0.0, 0.0, 45.0])
    t = np.linspace(5.0, 95.0, 50)
    fd = tracks.doppler_pv(line.pos(t), line.vel(t), tx, rx, LAM)

    def rsum(tt):
        p = line.pos(tt)
        return np.linalg.norm(p - tx, axis=1) + np.linalg.norm(p - rx, axis=1)

    h = 1e-3
    fd_num = -(rsum(t + h) - rsum(t - h)) / (2 * h) / LAM
    assert np.max(np.abs(fd - fd_num)) < 1e-6 * np.max(np.abs(fd)) + 1e-7


def test_doppler_gradient_formula():
    """grad_x f = (v - (v.u1) u1) / (lambda R1), u1 from the transmitter to the aircraft."""
    rng = np.random.default_rng(0)
    rx = np.array([0.0, 0.0, 45.0])
    for _ in range(25):
        p = rng.uniform(-5000.0, 5000.0, 3)
        p[2] = rng.uniform(500.0, 3000.0)
        v = rng.uniform(-120.0, 120.0, 3)
        v[2] = rng.uniform(-5.0, 5.0)
        tx = rng.uniform(-5000.0, 5000.0, 3)
        tx[2] = 85.0

        def f0(x):
            return tracks.doppler_pv(p[None], v[None], x, rx, LAM)[0]

        g_num = np.array([(f0(tx + d) - f0(tx - d)) / 2e-3 for d in np.eye(3) * 1e-3])
        u1 = (p - tx) / np.linalg.norm(p - tx)
        g = (v - (v @ u1) * u1) / (LAM * np.linalg.norm(p - tx))
        assert np.allclose(g_num, g, rtol=1e-5, atol=1e-9)


def test_mirror_twin_gives_identical_doppler():
    """A transmitter and its mirror image across the vertical plane through a straight track are indistinguishable
    from that one track. Different flight lines are what break the tie."""
    line = synth.Line(0.0, 600.0, (-20000.0, 3000.0, 2000.0), (100.0, 0.0, 0.0))   # flies east along N = 3000
    rx = np.array([700.0, -400.0, 45.0])
    tx = np.array([4000.0, 3000.0 + 2500.0, 85.0])
    twin = np.array([4000.0, 3000.0 - 2500.0, 85.0])
    t = np.linspace(0.0, 600.0, 300)
    f1 = tracks.doppler_pv(line.pos(t), line.vel(t), tx, rx, LAM)
    f2 = tracks.doppler_pv(line.pos(t), line.vel(t), twin, rx, LAM)
    assert np.max(np.abs(f1 - f2)) < 1e-9
    # and a second line with another heading tells them apart by tens of Hz
    other = synth.Line(0.0, 600.0, (2000.0, -20000.0, 2000.0), (0.0, 100.0, 0.0))
    g1 = tracks.doppler_pv(other.pos(t), other.vel(t), tx, rx, LAM)
    g2 = tracks.doppler_pv(other.pos(t), other.vel(t), twin, rx, LAM)
    assert np.max(np.abs(g1 - g2)) > 10.0
