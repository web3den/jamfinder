"""Position feeds at 20-s cadence (OpenSky, adsb.fi far from a receiver) must not silently empty the tracks.

Found 2026-11-15: Path.max_gap = 12 s left 14 % of the tracks of one recording valid and 0 % of some others;
one "nothing" had been computed on one-seventh of its tracks, and a simulation ran on empty tracks without
any error. The search must be run with max_gap=30 on such feeds, and the positions
the spline gives between 20-s reports must still be good for straight flight."""
import gzip
import json

import numpy as np

from jf import geo, tracks

LAT0, LON0 = 46.0, -94.0
SPEED, ALT, DUR = 230.0, 10000.0, 400.0     # +-46 km: the frame is a local tangent plane, keep the track near


def _write_feed(path, cadence_s):
    """One airliner flying straight east at 230 m/s, 10 km up, through the receiver's zenith."""
    frame = geo.Frame(LAT0, LON0, 0.0)
    t0 = 1.7e9
    with gzip.open(path, "wt") as f:
        for k in range(int(DUR / cadence_s) + 1):
            t = t0 + k * cadence_s
            e = -SPEED * DUR / 2 + SPEED * k * cadence_s
            lat, lon, _ = frame.to_geo(np.array([e, 0.0, ALT]))
            ac = dict(hex="abc123", type="adsb_icao", flight="TEST1", t="B738", category="A3",
                      alt_baro=32000, alt_geom=int(round(ALT / geo.FT)), gs=SPEED / geo.KT, track=90.0,
                      geom_rate=0, baro_rate=0, lat=float(lat), lon=float(lon), nic=8, rc=186,
                      seen_pos=0.1, seen=0.1)
            f.write(json.dumps(dict(t0=t, t1=t + 0.2, now=int(t * 1000), ac=[ac])) + "\n")
    return frame, t0


def _valid_fraction(paths):
    p = paths["abc123"]
    tc = np.arange(p.t0, p.t1, 1.0)
    return float(p.valid(tc).mean())


def test_twenty_second_feed_is_empty_at_the_default_gap_and_full_at_thirty(tmp_path):
    fn = str(tmp_path / "feed20.jsonl.gz")
    frame, _ = _write_feed(fn, 20.0)
    paths12, _ = tracks.load_paths(fn, frame, ground_h=0.0)
    paths30, _ = tracks.load_paths(fn, frame, ground_h=0.0, max_gap=30.0)
    assert _valid_fraction(paths12) < 0.05, "the trap: a 20-s feed is silently invalid at max_gap 12"
    assert _valid_fraction(paths30) > 0.95


def test_dense_feed_is_valid_at_the_default_gap(tmp_path):
    fn = str(tmp_path / "feed2.jsonl.gz")
    frame, _ = _write_feed(fn, 2.0)
    paths, _ = tracks.load_paths(fn, frame, ground_h=0.0)
    assert _valid_fraction(paths) > 0.95


def test_spline_between_twenty_second_reports_follows_straight_flight(tmp_path):
    """Between reports the path is a spline through positions and reported velocities: for straight flight it
    must stay within tens of metres and a few m/s of the truth, or the Doppler prediction is wrong."""
    fn = str(tmp_path / "feed20.jsonl.gz")
    frame, t0 = _write_feed(fn, 20.0)
    paths, _ = tracks.load_paths(fn, frame, ground_h=0.0, max_gap=30.0)
    p = paths["abc123"]
    tc = np.arange(p.t0 + 30.0, p.t1 - 30.0, 1.0)
    pos, vel = p.pos(tc), p.vel(tc)
    e_true = -SPEED * DUR / 2 + SPEED * (tc - t0)
    err = np.hypot(pos[:, 0] - e_true, pos[:, 1])
    assert np.sqrt(np.mean(err ** 2)) < 30.0, err.max()
    assert err.max() < 80.0, err.max()
    assert np.abs(vel[:, 0] - SPEED).max() < 3.0
    assert np.abs(vel[:, 1]).max() < 3.0
