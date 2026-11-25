"""Differential testing: the same input through this code and through an independent implementation.

  geodesy        jf/geo.py        against pymap3d, a separately written geodesy library
  spectrogram    jf/iq.py         against scipy.signal.stft, the scientific Python reference
  Doppler        jf/tracks.py     against a first-principles version written here: the rate of change of the
                                  path length transmitter -> aircraft -> receiver, by finite differences
  constants      jf/geo.py        against their published definitions (WGS84, international foot, knot)

Agreement is evidence, not proof: two implementations can share a mistake. Disagreement is always worth a look.
The property tests in qa/properties check that the code agrees with itself; these check it agrees with others.
"""
import numpy as np
import pymap3d
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy import signal

from jf import geo, iq, tracks

lat = st.floats(-89.9, 89.9)                 # the poles are FINDING-002 (qa/properties/README.md)
lon = st.floats(-180.0, 180.0)
height = st.floats(-400.0, 15000.0)
ELLIPSOID = pymap3d.Ellipsoid.from_name("wgs84")


# ---- constants against their definitions -----------------------------------------------------------------------

def test_wgs84_and_unit_constants_match_their_definitions():
    assert geo.A == 6378137.0                              # WGS84 semi-major axis, metres (defining constant)
    assert geo.F == 1 / 298.257223563                      # WGS84 flattening (defining constant)
    assert geo.E2 == pytest.approx(6.69437999014e-3, rel=1e-11)   # first eccentricity squared (NGA tables)
    assert geo.FT == 0.3048                                # international foot, exact since 1959
    assert geo.KT == pytest.approx(1852.0 / 3600.0, rel=1e-6)    # knot: one nautical mile (1852 m) per hour


# ---- geodesy against pymap3d -----------------------------------------------------------------------------------

@given(lat, lon, height)
@settings(max_examples=300)
def test_earth_centred_coordinates_agree(la, lo, h):
    ours = geo.ecef(la, lo, h)
    theirs = pymap3d.geodetic2ecef(la, lo, h, ell=ELLIPSOID)
    assert np.allclose(ours, theirs, atol=1e-6, rtol=0)


@given(lat, lon, height, st.floats(-1.0, 1.0), st.floats(-1.0, 1.0), height)
@settings(max_examples=300)
def test_local_east_north_up_agrees(lat0, lon0, h0, dlat, dlon, h):
    la, lo = np.clip(lat0 + dlat, -89.9, 89.9), lon0 + dlon
    ours = geo.Frame(lat0, lon0, h0).to_enu(la, lo, h)
    theirs = pymap3d.geodetic2enu(la, lo, h, lat0, lon0, h0, ell=ELLIPSOID)
    assert np.allclose(ours, theirs, atol=1e-6, rtol=0)


@given(lat, lon, height, st.floats(-80e3, 80e3), st.floats(-80e3, 80e3), st.floats(-400.0, 15000.0))
@settings(max_examples=300)
def test_back_to_latitude_longitude_height_agrees(lat0, lon0, h0, e, n, u):
    la, lo, h = geo.Frame(lat0, lon0, h0).to_geo(np.array([e, n, u]))
    la2, lo2, h2 = pymap3d.enu2geodetic(e, n, u, lat0, lon0, h0, ell=ELLIPSOID)
    assert abs(la - la2) < 1e-9 and abs((lo - lo2 + 180) % 360 - 180) < 1e-9 and abs(h - h2) < 1e-4


# ---- spectrogram against SciPy ---------------------------------------------------------------------------------

@pytest.mark.parametrize("win_s, hop_s", [(1.0, 0.5), (2.0, 0.25)])
def test_spectrogram_agrees_with_scipy(win_s, hop_s):
    fs = 1250.0
    rng = np.random.default_rng(7)
    t = np.arange(int(30 * fs)) / fs
    z = (np.exp(2j * np.pi * 37.3 * t) + 0.1 * (rng.standard_normal(t.size) + 1j * rng.standard_normal(t.size)))
    z = z.astype(np.complex64)
    tt, f, P = iq.spectrogram(z, fs, win_s=win_s, hop_s=hop_s, f_max=250.0)

    nw, hop = int(round(win_s * fs)), int(round(hop_s * fs))
    nfft = 2 * (1 << int(np.ceil(np.log2(nw))))
    fr, ts, Z = signal.stft(z, fs, window=np.hanning(nw), nperseg=nw, noverlap=nw - hop, nfft=nfft,
                            return_onesided=False, boundary=None, padded=False, detrend=False, scaling="spectrum")
    fr, Z = np.fft.fftshift(fr), np.fft.fftshift(Z, axes=0)
    keep = np.abs(fr) <= 250.0
    assert np.allclose(f, fr[keep]) and np.allclose(tt, ts)
    assert np.allclose(P, (np.abs(Z[keep]) ** 2).T, rtol=1e-4, atol=1e-9)


# ---- Doppler against first principles --------------------------------------------------------------------------

def doppler_from_path_length(p, v, tx, rx, lam, dt=1e-5):
    """Doppler shift = -(rate of change of the path length tx -> aircraft -> rx) / wavelength.

    A central difference. With a step of 1 ms its own error reached 1e-4 Hz for a fast aircraft 220 m from the
    transmitter (Hypothesis found that case); at 10 us it is below 1e-8 Hz."""
    def path(q):
        return np.linalg.norm(q - tx) + np.linalg.norm(q - rx)
    return -(path(p + v * dt) - path(p - v * dt)) / (2 * dt) / lam


@given(st.tuples(*[st.floats(-20e3, 20e3)] * 2), st.floats(300.0, 11000.0),
       st.tuples(*[st.floats(-250.0, 250.0)] * 3), st.tuples(st.floats(-15e3, 15e3), st.floats(-15e3, 15e3)))
@settings(max_examples=300)
def test_doppler_agrees_with_the_path_length_derivative(xy, alt, v, tx_xy):
    p, v = np.array([*xy, alt]), np.array(v)
    tx, rx = np.array([*tx_xy, 80.0]), np.array([0.0, 0.0, 45.0])
    lam = tracks.C / 135.075e6
    ours = float(tracks.doppler_pv(p[None, :], v[None, :], tx, rx, lam)[0])
    assert ours == pytest.approx(doppler_from_path_length(p, v, tx, rx, lam), abs=1e-6)
