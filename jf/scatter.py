"""From a raw capture to a whitened Doppler waterfall, ready for track matching."""
import os

import numpy as np
from scipy import ndimage

from . import iq


def baseband(prefix, cache=None, t_iq0=None, **load_kw):
    """Carrier shifted to 0 Hz at 1250 samples/s, with the absolute time of sample 0.

    Returns dict(y, fs, t0, scale, carrier_hz). `scale` stretches nominal
    sample time to true time (the receiver's sample clock is a little off).
    """
    if cache and os.path.exists(cache):
        return dict(np.load(cache))
    x, fs, meta = iq.load(prefix, **load_kw)
    scale = 1.0
    if meta is not None:
        t_iq0, true_rate = iq.sample_clock(meta, len(x))
        scale = fs / true_rate
    elif t_iq0 is None:
        raise ValueError("unfinished capture: pass t_iq0")
    fc = iq.find_carrier(x, fs)
    y, fs2 = iq.to_baseband(x, fs, fc)
    bb = dict(y=y, fs=np.float64(fs2), t0=np.float64(t_iq0), scale=np.float64(scale), carrier_hz=np.float64(fc))
    if cache:
        np.savez(cache, **bb)
    return bb


def waterfall(bb, win_s=1.0, hop_s=0.5, f_max=250.0, ref_bw=1.0, add_noise_db=0.0, seed=0, floor_dbc_hz=None):
    """Self-referenced spectrogram. Returns dict: t (unix), f, S, Sq, car, enbw, n0_dbc_hz.

    add_noise_db > 0 buries the signal in extra white noise so that the
    carrier-to-noise ratio drops by that many dB: the same scene as seen
    from a transmitter that many dB weaker.
    """
    y, fs2 = bb["y"], float(bb["fs"])
    nw = int(round(win_s * fs2))
    enbw = 1.5 * fs2 / nw  # Hann
    if add_noise_db > 0:
        if floor_dbc_hz is None:
            base = waterfall(bb, win_s, hop_s, f_max, ref_bw)
            floor_dbc_hz = base["n0_dbc_hz"]
        yd, _ = iq.remove_drift(y, fs2)
        car = float(np.mean(np.abs(iq.reference(yd, fs2, ref_bw)) ** 2))
        n0 = car * 10 ** (floor_dbc_hz / 10.0)
        sig2 = (10 ** (add_noise_db / 10.0) - 1.0) * n0 * fs2
        rng = np.random.default_rng(seed)
        y = y + (np.sqrt(sig2 / 2) * (rng.standard_normal(len(y)) + 1j * rng.standard_normal(len(y)))).astype(np.complex64)
    y, ftrack = iq.remove_drift(y, fs2)
    z, d = iq.self_reference(y, fs2, bw=ref_bw)
    t, f, S = iq.spectrogram(z, fs2, win_s=win_s, hop_s=hop_s, f_max=f_max)
    _, _, Sq = iq.spectrogram((z.imag + 0j).astype(np.complex64), fs2, win_s=win_s, hop_s=hop_s, f_max=f_max)
    hop = int(round(hop_s * fs2))
    p = np.abs(d) ** 2
    c = np.concatenate([[0.0], np.cumsum(p, dtype=np.float64)])
    starts = np.arange(0, len(d) - nw + 1, hop)
    car_t = (c[starts + nw] - c[starts]) / nw
    m = (np.abs(f) >= 20) & (np.abs(f) <= 140)
    n0_dbc_hz = 10 * np.log10(np.median(S[:, m]) / np.log(2) / enbw)
    return dict(t=float(bb["t0"]) + t * float(bb["scale"]), f=f, S=S, Sq=Sq, car=car_t.astype(np.float32),
                enbw=float(enbw), n0_dbc_hz=float(n0_dbc_hz), drift=ftrack[::int(fs2)].astype(np.float32),
                win_s=win_s, hop_s=hop_s)


def waterfall_blind(bb, win_s=1.0, hop_s=0.5, f_max=250.0, ref_bw=1.0, hide_hz=4.0, add_noise_db=0.0, seed=0,
                    floor_dbc_hz=None, has_carrier=True):
    """Whitened waterfall of the echoes alone: what a receiver that cannot hear the transmitter would see.

    From a real capture (has_carrier=True) the direct carrier is followed, subtracted, and its
    neighbourhood blanked. The receiver's drift is left in, so echoes sit at f0(t) + Doppler.
    Returns dict(t, f, W, f0): f0 is the hidden carrier's frequency in each frame. It is only
    for checking afterwards; the search must not use it.
    """
    y, fs2 = bb["y"], float(bb["fs"])
    nw, hop = int(round(win_s * fs2)), int(round(hop_s * fs2))
    if add_noise_db > 0:
        yd, _ = iq.remove_drift(y, fs2)
        car = float(np.mean(np.abs(iq.reference(yd, fs2, ref_bw)) ** 2))
        n0 = car * 10 ** (floor_dbc_hz / 10.0)
        sig2 = (10 ** (add_noise_db / 10.0) - 1.0) * n0 * fs2
        rng = np.random.default_rng(seed)
        y = y + (np.sqrt(sig2 / 2) * (rng.standard_normal(len(y)) + 1j * rng.standard_normal(len(y)))).astype(np.complex64)
    f0 = None
    if has_carrier:
        y_flat, ftrack = iq.remove_drift(y, fs2)
        d = iq.reference(y_flat, fs2, ref_bw)
        phase = 2 * np.pi * np.cumsum(ftrack) / fs2
        y = ((y_flat - d) * np.exp(1j * phase)).astype(np.complex64)
    t, f, S = iq.spectrogram(y, fs2, win_s=win_s, hop_s=hop_s, f_max=f_max)
    W, _ = whiten(S, f)
    if has_carrier:
        starts = np.arange(0, len(y) - nw + 1, hop)
        f0 = ftrack[starts + nw // 2]
        if hide_hz > 0:
            W[np.abs(f[None, :] - f0[:, None]) <= hide_hz] = 1.0 / np.log(2.0)
    return dict(t=float(bb["t0"]) + t * float(bb["scale"]), f=f, W=W, f0=f0, win_s=win_s, hop_s=hop_s)


def prepare(prefix, win_s=1.0, hop_s=0.5, f_max=250.0, ref_bw=1.0, t_iq0=None, **load_kw):
    """One call from capture to waterfall (kept for older scripts)."""
    bb = baseband(prefix, t_iq0=t_iq0, **load_kw)
    out = waterfall(bb, win_s, hop_s, f_max, ref_bw)
    out.update(t_iq0=float(bb["t0"]), fs=float(bb["fs"]), carrier_hz=float(bb["carrier_hz"]))
    return out


def whiten(S, f, quiet=(20.0, 140.0)):
    """Divide each frequency bin by its median over time, and each frame by its own noise level.

    Returns (W, floor): W is power in units of the local noise median; floor is the
    median noise power per bin relative to the carrier.
    """
    med_f = np.median(S, axis=0, keepdims=True)
    W = S / np.maximum(med_f, 1e-30)
    m = (np.abs(f) >= quiet[0]) & (np.abs(f) <= quiet[1])
    med_t = np.median(W[:, m], axis=1, keepdims=True)
    W = W / np.maximum(med_t, 1e-30)
    return W.astype(np.float32), float(np.median(med_f[0, m]))


def score_matrix(W, thr_db=6.0, cap_db=20.0, blur_bins=0):
    """Per-cell evidence that a line is present: dB over threshold, clipped."""
    D = 10.0 * np.log10(np.maximum(W, 1e-6))
    if blur_bins > 0:
        D = ndimage.maximum_filter1d(D, size=2 * blur_bins + 1, axis=1, mode="nearest")
    return np.clip(D - thr_db, 0.0, cap_db).astype(np.float32)
