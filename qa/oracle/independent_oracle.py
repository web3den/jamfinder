"""Expected values for the bistatic Doppler shift that do not come from any implementation of it.

Each check takes an implementation `f(p, v, tx, rx, lam)` and returns what it got wrong (empty list = passed).
The sources of truth, none of which reads the code under test:
  first principles   the shift is -(d/dt of the path length tx -> aircraft -> rx) / wavelength
  textbook limit     with transmitter and receiver in one place it must reduce to radar's -2 v.u / wavelength
  symmetry           the path is as long one way as the other, so tx and rx may swap
  hand calculation   one geometry worked out on paper
"""
import numpy as np

LAM = 2.2195   # metres, about 135 MHz


def path_rate(p, v, tx, rx, dt=1e-3):
    length = lambda q: np.linalg.norm(q - tx) + np.linalg.norm(q - rx)   # noqa: E731
    return (length(p + v * dt) - length(p - v * dt)) / (2 * dt)


GEOMETRIES = [   # (aircraft position, velocity, transmitter, receiver), metres and m/s
    (np.array([3000.0, 4000.0, 2000.0]), np.array([-120.0, 30.0, -5.0]), np.array([-2000.0, 500.0, 80.0]),
     np.array([0.0, 0.0, 45.0])),
    (np.array([-8000.0, 1000.0, 9000.0]), np.array([200.0, 10.0, 0.0]), np.array([5000.0, -3000.0, 60.0]),
     np.array([0.0, 0.0, 45.0])),
    (np.array([500.0, -6000.0, 1200.0]), np.array([0.0, 90.0, 4.0]), np.array([1500.0, 2000.0, 20.0]),
     np.array([-300.0, 100.0, 10.0])),
]


def check_first_principles(f):
    bad = []
    for p, v, tx, rx in GEOMETRIES:
        want = -path_rate(p, v, tx, rx) / LAM
        got = f(p, v, tx, rx, LAM)
        if abs(got - want) > 1e-3:
            bad.append(f"path-length rate: expected {want:.3f} Hz, got {got:.3f} Hz")
    return bad


def check_radar_limit(f):
    p, v, site = np.array([4000.0, 3000.0, 1500.0]), np.array([-150.0, 20.0, 0.0]), np.array([0.0, 0.0, 30.0])
    u = (p - site) / np.linalg.norm(p - site)
    want, got = -2 * np.dot(v, u) / LAM, f(p, v, site, site, LAM)
    return [] if abs(got - want) < 1e-6 else [f"radar limit (tx = rx): expected {want:.3f} Hz, got {got:.3f} Hz"]


def check_swap(f):
    bad = []
    for p, v, tx, rx in GEOMETRIES:
        a, b = f(p, v, tx, rx, LAM), f(p, v, rx, tx, LAM)
        if abs(a - b) > 1e-9:
            bad.append(f"swapping tx and rx changed the shift: {a:.3f} vs {b:.3f} Hz")
    return bad


def check_hand_calculation(f):
    """Aircraft 1 km above the midpoint of tx and rx, 2 km apart, climbing at 100 m/s.
    Each leg is at 45 degrees and lengthens at 100 cos 45 = 70.71 m/s: shift = -141.42 / lambda."""
    got = f(np.array([0.0, 0.0, 1000.0]), np.array([0.0, 0.0, 100.0]), np.array([-1000.0, 0.0, 0.0]),
            np.array([1000.0, 0.0, 0.0]), LAM)
    want = -2 * 100.0 * np.cos(np.pi / 4) / LAM
    return [] if abs(got - want) < 1e-6 else [f"hand calculation: expected {want:.3f} Hz, got {got:.3f} Hz"]


CHECKS = [check_first_principles, check_radar_limit, check_swap, check_hand_calculation]


def judge(f):
    """All failures of an implementation against the independent oracle."""
    return [msg for check in CHECKS for msg in check(f)]
