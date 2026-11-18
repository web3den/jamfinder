"""What the search reports when there is nothing: the calibration every threshold rests on.

If these drift, every reporting rule (v1, v2, v2.2) silently changes meaning. They must pass for the
current statistic and for every new one."""
import numpy as np

from tests.common import LAM
from jf import field

LN2 = float(np.log(2.0))


def test_whitened_noise_has_unit_mean_and_exponential_tail(noise_waterfall):
    """W * ln 2 is noise power in units of its mean; a Hann periodogram of white noise is exponential."""
    W, f = noise_waterfall["W"], noise_waterfall["f"]
    band = (np.abs(f) >= 3.0) & (np.abs(f) <= 140.0)
    u = W[:, band] * LN2
    assert abs(u.mean() - 1.0) < 0.02
    tail = (u > 10.0).mean()          # exponential: P(u > 10) = e^-10 = 4.5e-5
    assert 0.1 * np.exp(-10.0) < tail < 5.0 * np.exp(-10.0)


def test_field_score_is_standardised_on_pure_noise(noise_waterfall, lines, rx):
    """T is built to be 0 +- 1 away from any transmitter (field.py): check mean, spread and the largest value
    over a 21 x 21 grid. The largest value with no echoes at all was about 8 over 14,641 cells (THRESHOLD = 15
    is twice that).

    Measured 2026-11-15 with the baseline statistic on this track set: mean about -0.5, because the block z
    has a spread a little under 1 (the variance bookkeeping of the box averages is slightly conservative). The
    bound below leaves room for that and still catches a gross miscalibration. The registry
    field.STATISTICS records the measured null mean and variance per statistic instead of assuming 0 and 1."""
    fld = field.Field(noise_waterfall["t"], noise_waterfall["f"], noise_waterfall["W"], lines, rx, LAM)
    e, n, M = fld.grid((0.0, 0.0), 5000.0, 500.0)
    assert M.shape == (21, 21)
    assert abs(M.mean()) < 0.8, M.mean()
    assert 0.5 < M.std() < 1.6, M.std()
    assert M.max() < 8.0, M.max()


def test_phi_calibration_constants():
    """PHI_MEAN and PHI_VAR are the mean and variance of phi(z) for z ~ N(0, 1); the score divides by them."""
    rng = np.random.default_rng(2)
    z = rng.standard_normal(2_000_000)
    p = field._phi(z)
    assert abs(p.mean() - field.PHI_MEAN) < 0.005
    assert abs(p.var() - field.PHI_VAR) < 0.02


def test_block_and_pass_level_deflection_follow_theory():
    """The arithmetic behind the "pass" statistic, checked by Monte Carlo on the block model z_b ~ N(s, 1).

    deflection = (mean under signal - mean under noise) / spread under noise.
    - very weak and spread over all blocks: block-level sum of phi and pass-level phi of the summed z are both
      first-order in s (phi clips at zero, so it is sensitive to a mean shift): equal within 50 %;
    - moderate and spread (pass-level z near 2): pass-level wins clearly;
    - strong but in one block only: block-level wins clearly (why 30-s blocks were chosen for Helsinki).
    So neither is uniformly better; real recordings must decide, and a combined statistic is allowed."""
    rng = np.random.default_rng(0)
    n_blocks, trials = 8, 20000

    def blocks(z):
        return field._phi(z).sum(1)

    def passlvl(z):
        return field._phi(z.sum(1) / np.sqrt(n_blocks))

    def deflection(stat, z0, z1):
        a0, a1 = stat(z0), stat(z1)
        return (a1.mean() - a0.mean()) / a0.std()

    z0 = rng.standard_normal((trials, n_blocks))
    d_b, d_p = deflection(blocks, z0, z0 + 0.15), deflection(passlvl, z0, z0 + 0.15)
    assert 0.67 < d_p / d_b < 1.5, (d_b, d_p)
    d_b, d_p = deflection(blocks, z0, z0 + 0.7), deflection(passlvl, z0, z0 + 0.7)
    assert d_p > 1.3 * d_b, (d_b, d_p)
    z1 = z0.copy()
    z1[:, 0] += 4.0
    d_b, d_p = deflection(blocks, z0, z1), deflection(passlvl, z0, z1)
    assert d_b > 1.3 * d_p, (d_b, d_p)


def test_matched_weights_gain_follows_theory():
    """Weighting the blocks of one pass by the predicted echo profile a_b (radar equation shape) gains
    sqrt(n sum a^2) / sum a over uniform weights, for z_b ~ N(s a_b, 1). Checked by Monte Carlo."""
    rng = np.random.default_rng(1)
    a = np.array([0.2, 0.5, 1.0, 2.0, 1.0, 0.5, 0.2, 0.1])
    n, trials, s = len(a), 40000, 0.4
    z0 = rng.standard_normal((trials, n))
    z1 = z0 + s * a
    uniform = lambda z: z.sum(1) / np.sqrt(n)                   # noqa: E731
    matched = lambda z: (z * a).sum(1) / np.sqrt((a * a).sum())  # noqa: E731
    d_u = (uniform(z1).mean() - uniform(z0).mean()) / uniform(z0).std()
    d_m = (matched(z1).mean() - matched(z0).mean()) / matched(z0).std()
    expect = np.sqrt(n * (a * a).sum()) / a.sum()
    assert abs(d_m / d_u - expect) < 0.15 * expect, (d_m / d_u, expect)
