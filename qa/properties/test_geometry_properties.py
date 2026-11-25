"""Property-based tests of the geometry everything else stands on: WGS84 coordinates (jf/geo.py) and the
bistatic Doppler shift of an echo (jf/tracks.py, doppler_pv).

Each property is a fact of geometry or physics, true for every input, so no expected value is copied from the
code under test.

FINDING-002 (strict xfail below): Frame.to_geo returns a height hundreds of kilometres off for a point exactly at
a pole. See README.md.
"""
import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from jf import geo, tracks

lat = st.floats(-90.0, 90.0)
lon = st.floats(-180.0, 180.0)
height = st.floats(-400.0, 15000.0)            # from below sea level to above any airliner
vec = st.tuples(*[st.floats(-30000.0, 30000.0)] * 3).map(np.array)
velocity = st.tuples(*[st.floats(-300.0, 300.0)] * 3).map(np.array)
LAM = tracks.C / 135.075e6                      # an aviation voice frequency


def same_place(a, b):
    """Two geodetic positions agree to 1 mm in height and 1e-7 degree (1 cm), longitude modulo 360."""
    dlon = (a[1] - b[1] + 180.0) % 360.0 - 180.0
    return abs(a[0] - b[0]) < 1e-7 and (abs(dlon) < 1e-7 or abs(a[0]) > 89.9999) and abs(a[2] - b[2]) < 1e-3


# ---- WGS84 coordinates ---------------------------------------------------------------------------------------

@given(lat, lon, height)
@settings(max_examples=300)
def test_the_frame_origin_is_zero(lat0, lon0, h0):
    assert np.allclose(geo.Frame(lat0, lon0, h0).to_enu(lat0, lon0, h0), 0.0, atol=1e-6)


@given(lat, lon)
@settings(max_examples=300)
def test_the_local_axes_are_orthonormal(lat0, lon0):
    r = geo.enu_matrix(lat0, lon0)
    assert np.allclose(r @ r.T, np.eye(3), atol=1e-12) and np.isclose(np.linalg.det(r), 1.0)


@given(lat, lon, height, lat, lon, height)
@settings(max_examples=300)
def test_distances_do_not_depend_on_the_frame(la1, lo1, h1, la2, lo2, h2):
    """Moving to a local frame is a rotation and a shift: it cannot stretch distances."""
    frame = geo.Frame(la1, lo1, 0.0)
    d_local = np.linalg.norm(frame.to_enu(la1, lo1, h1) - frame.to_enu(la2, lo2, h2))
    d_earth = np.linalg.norm(geo.ecef(la1, lo1, h1) - geo.ecef(la2, lo2, h2))
    assert abs(d_local - d_earth) < 1e-6 * max(1.0, d_earth)


@given(st.floats(-89.0, 89.0), lon, height, st.floats(-1.0, 1.0), st.floats(-1.0, 1.0), height)
@settings(max_examples=500)
def test_enu_round_trip_near_the_frame(lat0, lon0, h0, dlat, dlon, h):
    """Where the software works (within about 100 km of the receiver), there and back is exact."""
    frame = geo.Frame(lat0, lon0, h0)
    p = (lat0 + dlat, lon0 + dlon, h)
    assert same_place(p, frame.to_geo(frame.to_enu(*p)))


@pytest.mark.xfail(strict=True, reason="FINDING-002: Frame.to_geo divides by cos(latitude), so a point at a pole "
                                       "comes back with a height hundreds of km off; see qa/properties/README.md")
@given(lat, lon, height, lat, lon, height)
@settings(max_examples=1000)
def test_enu_round_trip_everywhere_on_earth(lat0, lon0, h0, la, lo, h):
    frame = geo.Frame(lat0, lon0, h0)
    back = frame.to_geo(frame.to_enu(la, lo, h))
    assert same_place((la, lo, h), back), f"({la}, {lo}, {h} m) came back as {tuple(float(v) for v in back)}"


# ---- bistatic Doppler of an echo -------------------------------------------------------------------------------

def doppler(p, v, tx, rx):
    return float(tracks.doppler_pv(p[None, :], v[None, :], tx, rx, LAM)[0])


apart = lambda p, tx, rx: min(np.linalg.norm(p - tx), np.linalg.norm(p - rx)) > 1.0   # noqa: E731


@given(vec, velocity, vec, vec)
@settings(max_examples=500)
def test_no_echo_shifts_more_than_twice_speed_over_wavelength(p, v, tx, rx):
    """Each of the two path legs can shorten at most at the aircraft's speed."""
    if apart(p, tx, rx):
        assert abs(doppler(p, v, tx, rx)) <= 2 * np.linalg.norm(v) / LAM + 1e-9


@given(vec, velocity, vec, vec)
@settings(max_examples=500)
def test_transmitter_and_receiver_can_swap_places(p, v, tx, rx):
    """The path transmitter -> aircraft -> receiver has the same length both ways."""
    if apart(p, tx, rx):
        assert np.isclose(doppler(p, v, tx, rx), doppler(p, v, rx, tx), rtol=1e-9, atol=1e-9)


@given(vec, velocity, vec, vec)
@settings(max_examples=500)
def test_flying_backwards_flips_the_sign(p, v, tx, rx):
    if apart(p, tx, rx):
        assert np.isclose(doppler(p, -v, tx, rx), -doppler(p, v, tx, rx), rtol=1e-9, atol=1e-9)


@given(vec, vec, vec, st.floats(1.0, 300.0))
@settings(max_examples=500)
def test_flying_square_to_both_legs_gives_no_shift(p, tx, rx, speed):
    """Velocity perpendicular to both lines of sight changes neither path length."""
    u1, u2 = p - tx, p - rx
    n = np.cross(u1, u2)
    if apart(p, tx, rx) and np.linalg.norm(n) > 1e-3 * np.linalg.norm(u1) * np.linalg.norm(u2):
        v = speed * n / np.linalg.norm(n)
        assert abs(doppler(p, v, tx, rx)) < 1e-6
