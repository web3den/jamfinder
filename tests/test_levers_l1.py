"""The optional statistics of jf/field.py, weight="pass" and weight="multi": the logic, checked on synthetic inputs.

- the matched weights of weight="pass" follow sim/synth.py's echo-power law (shape only);
- weight="multi" is (T_blocks + T_pass) / sqrt(2 + 2 rho);
- support for "pass" is the per-aircraft matched z; clock_gains agrees with tune_clocks; the search options at
  their defaults change nothing.
The pure-noise level of "pass" itself is tests/test_levers_spec.py::test_pass_level_statistic_is_standardised_on_noise.
The default statistic of the search is weight="blocks"."""
import numpy as np
import pytest

from tests.common import LAM
from jf import field
from sim import synth


def test_matched_power_is_the_sim_synth_law():
    rng = np.random.default_rng(3)
    n = 2000
    tx = np.array([500.0, -300.0, 60.0])
    rx = np.array([0.0, 0.0, 45.0])
    pos = np.c_[rng.uniform(-30e3, 30e3, n), rng.uniform(-30e3, 30e3, n), rng.uniform(50.0, 11e3, n)]
    pos[:20, :2] = tx[:2] + rng.uniform(-50, 50, (20, 2))        # a few right over the transmitter (R1 R2 floor)
    vel = np.c_[rng.uniform(-250, 250, n), rng.uniform(-250, 250, n), rng.uniform(-10, 10, n)]
    d1, d2 = pos - tx, pos - rx
    R1, R2 = np.linalg.norm(d1, axis=1), np.linalg.norm(d2, axis=1)
    el = np.degrees(np.arcsin(d2[:, 2] / R2))
    law_db = -20 * np.log10(np.maximum(R1 * R2, 1e4)) + synth.sky_mask_db(el) + synth.aspect_db(vel, d1, d2)
    u1, u2 = d1 / R1[:, None], d2 / R2[:, None]
    vb = (vel * (u1 + u2)).sum(1)
    got = field.matched_power(R1, R2, (u1 * u2).sum(1), vb, (vel * vel).sum(1), 10 ** (field._sky_db(el) / 10))
    assert np.allclose(10 * np.log10(got), law_db, atol=1e-6)
    assert np.allclose(field._sky_db(el), synth.sky_mask_db(el))


def _scene(lines, rx, noise_waterfall):
    return noise_waterfall["t"], noise_waterfall["f"], noise_waterfall["W"], lines, rx


def test_multi_is_the_stated_combination(noise_waterfall, lines, rx):
    t, f, W, paths, rx = _scene(lines, rx, noise_waterfall)
    rng = np.random.default_rng(6)
    tx = np.c_[rng.uniform(-8000, 8000, 300), rng.uniform(-8000, 8000, 300), np.full(300, 85.0)]
    Tb = field.Field(t, f, W, paths, rx, LAM, weight="blocks").score(tx, 500.0)
    Tp = field.Field(t, f, W, paths, rx, LAM, weight="pass").score(tx, 500.0)
    Tm = field.Field(t, f, W, paths, rx, LAM, weight="multi", rho=0.3).score(tx, 500.0)
    assert np.allclose(Tm, (Tb + Tp) / np.sqrt(2.6), atol=1e-9)
    rho = field.STATISTICS["multi"].get("rho")
    if rho is None:                                              # without a measured rho, multi needs it passed
        with pytest.raises(ValueError):
            field.Field(t, f, W, paths, rx, LAM, weight="multi")
    else:                                                        # afterwards the registry's rho is the default
        T0 = field.Field(t, f, W, paths, rx, LAM, weight="multi").score(tx, 500.0)
        assert np.allclose(T0, (Tb + Tp) / np.sqrt(2.0 + 2.0 * rho), atol=1e-9)


def test_pass_support_is_the_matched_z_and_clocks_work(noise_waterfall, lines, rx):
    t, f, W, paths, rx = _scene(lines, rx, noise_waterfall)
    fld = field.Field(t, f, W, paths, rx, LAM, weight="pass")
    cand = (0.0, 2500.0, 1500.0, 0.0)
    _, per = fld.score(np.array([[cand[1], cand[2], 85.0]]), 20.0, per_aircraft=True)
    sup = dict((h, z) for z, h in field.support(fld, cand))
    assert sup and all(abs(sup[h] - per[h][2][0]) < 1e-12 for h in sup)
    for weight, kw in (("pass", {}), ("multi", {"rho": 0.3}), ("blocks", {})):
        fl = field.Field(t, f, W, paths, rx, LAM, weight=weight, **kw)
        gains = field.clock_gains(fl, (cand[1], cand[2], 85.0), 0.0)
        for g in (0.0, 0.3, 1.0, 3.0):
            want = {h: o for h, (o, v) in gains.items() if o != 0.0 and v >= g}
            assert field.tune_clocks(fl, (cand[1], cand[2], 85.0), 0.0, min_gain=g) == want, (weight, g)


def test_pass_z_is_close_to_standard_normal_on_noise(noise_waterfall, lines, rx):
    """The per-aircraft matched z of weight="pass" on pure noise, over many candidate spots."""
    t, f, W, paths, rx = _scene(lines, rx, noise_waterfall)
    rng = np.random.default_rng(7)
    tx = np.c_[rng.uniform(-15000, 15000, 400), rng.uniform(-15000, 15000, 400), np.full(400, 85.0)]
    _, per = field.Field(t, f, W, paths, rx, LAM, weight="pass").score(tx, 500.0, per_aircraft=True)
    z = np.concatenate([v[2][v[1] > 0] for v in per.values()])
    assert abs(z.mean()) < 0.2 and 0.85 < z.std() < 1.2, (z.mean(), z.std())


def test_new_search_options_run(noise_waterfall, lines, rx):
    t, f, W, paths, rx = _scene(lines, rx, noise_waterfall)
    r = field.search(t, f, W, paths, rx, LAM, span=3000.0, step=500.0, k_peaks=3, stride_wide=1, weight="pass", min_gain=2.0)
    assert len(r["cands"]) == 3 and r["units_A"].shape == r["mapA"][2].shape
    r = field.search(t, f, W, paths, rx, LAM, span=3000.0, step=500.0, k_peaks=2, weight="multi", rho=0.4, f_lo=1.5, f_hi=200.0)
    assert len(r["cands"]) == 2
