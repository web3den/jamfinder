"""End-to-end logic checks on synthetic scenes with exact truth (sim/synth.py).

These prove the chain is wired correctly. They do NOT measure sensitivity: the simulator is trusted to about
+-5 dB for echo strength, so any claim of a dB gain must come from real recordings with noise added."""
import numpy as np
import pytest

from tests.common import DUR, LAM, T0
from jf import field, scatter
from sim import synth


@pytest.fixture(scope="module")
def planted(lines, rx):
    scene = synth.Scene(lines, rx, LAM, T0, DUR)
    tx = np.array([3000.0, 4000.0, 85.0])
    bb, truth = scene.synth(tx, power_db=0.0, seed=3)
    wf = scatter.waterfall(bb)
    W, _ = scatter.whiten(wf["S"], wf["f"])
    return dict(tx=tx, wf=wf, W=W, truth=truth)


def test_planted_transmitter_is_found(planted, lines, rx):
    wf, W, tx = planted["wf"], planted["W"], planted["tx"]
    r = field.search(wf["t"], wf["f"], W, lines, rx, LAM, span=8000.0, step=500.0, k_peaks=3)
    err = float(np.hypot(r["tx"][0] - tx[0], r["tx"][1] - tx[1]))
    label, kept = field.verdict(r["cands"])
    assert err < 150.0, (err, r["cands"][:3])
    assert r["score"] > field.THRESHOLD
    assert label == "one", (label, r["cands"][:3])


def test_support_names_the_aircraft_that_carry_the_evidence(planted, lines, rx):
    wf, W, tx = planted["wf"], planted["W"], planted["tx"]
    r = field.search(wf["t"], wf["f"], W, lines, rx, LAM, span=8000.0, step=500.0, k_peaks=3)
    sup = field.support(r["field"], r["cands"][0], r["clocks"][0])
    strong = [h for z, h in sup if z >= 10.0]
    assert len(strong) >= 3, sup      # rule v2.2 (e): at least three aircraft with support >= 10


def test_no_echoes_means_nothing(lines, rx):
    scene = synth.Scene(lines, rx, LAM, T0, DUR)
    bb, _ = scene.synth(np.array([3000.0, 4000.0, 85.0]), power_db=0.0, only=set(), seed=4)   # direct signal only
    wf = scatter.waterfall(bb)
    W, _ = scatter.whiten(wf["S"], wf["f"])
    r = field.search(wf["t"], wf["f"], W, lines, rx, LAM, span=8000.0, step=500.0, k_peaks=3)
    label, _ = field.verdict(r["cands"])
    assert label == "nothing", r["cands"][:3]
    assert r["score"] < field.THRESHOLD, r["cands"][:3]


def test_blanking_the_found_spot_leaves_nothing(planted, lines, rx):
    """Rule v2 (c): after the best spot's predicted lines are blanked, no peak should survive."""
    wf, W = planted["wf"], planted["W"]
    r = field.search(wf["t"], wf["f"], W, lines, rx, LAM, span=8000.0, step=500.0, k_peaks=3)
    W2 = field.mask_tracks(wf["t"], wf["f"], W, lines, rx, LAM, r["cands"][0], r["clocks"][0])
    r2 = field.search(wf["t"], wf["f"], W2, lines, rx, LAM, span=8000.0, step=500.0, k_peaks=3)
    assert r2["cands"][0][0] < 0.25 * r["cands"][0][0], (r["cands"][0][0], r2["cands"][0][0])
