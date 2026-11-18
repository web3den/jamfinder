"""Load spy_record captures and turn them into a clean carrier-referenced signal."""
import json
import os

import numpy as np
from scipy import signal


def load(prefix, kind=None, rate=None, dgain_db=None):
    """Return (complex64 samples, sample rate, meta or None).

    Works on a finished capture (with .json) or on a file still being
    written (pass kind, rate and dgain_db by hand).
    """
    meta = None
    if os.path.exists(prefix + ".json"):
        meta = json.load(open(prefix + ".json"))
        kind, rate = meta["kind"], meta["rate"]
    if kind == "u8":
        raw = np.fromfile(prefix + ".iq", dtype=np.uint8)
        raw = raw[: len(raw) // 2 * 2].astype(np.float32)
        raw = (raw - 128.0) / 128.0
    elif kind == "i16":
        raw = np.fromfile(prefix + ".iq", dtype="<i2")
        raw = raw[: len(raw) // 2 * 2].astype(np.float32) / 32768.0
    elif kind == "f32":
        raw = np.fromfile(prefix + ".iq", dtype="<f4")
        raw = raw[: len(raw) // 2 * 2]
    else:
        raise ValueError(f"unsupported sample kind {kind}")
    x = (raw[0::2] + 1j * raw[1::2]).astype(np.complex64)
    if meta is not None:
        msgs = meta["msgs"]
        if any(m[2] for m in msgs):
            idx = np.array([m[1] for m in msgs] + [len(x)])
            g = np.array([10 ** (-m[2] / 20.0) for m in msgs], dtype=np.float32)
            x = x * np.repeat(g, np.diff(idx))[: len(x)]
    elif dgain_db:
        x = x * np.float32(10 ** (-dgain_db / 20.0))
    return x, float(rate), meta


def sample_clock(meta, n):
    """Fit sample index -> unix time from message arrival times.

    Arrival = true time + delay, delay >= some minimum, so we fit the lower
    edge. Returns (t0, rate): time of sample 0 and true samples per second.
    """
    m = np.array([(a[0], a[1]) for a in meta["msgs"]], dtype=float)
    t, i = m[:, 0], m[:, 1]
    rate = meta["rate"]
    for _ in range(3):
        resid = t - i / rate
        # lower envelope in blocks
        nb = max(8, len(t) // 200)
        edges = np.linspace(0, len(t), nb + 1).astype(int)
        ti = np.array([i[a:b][np.argmin(resid[a:b])] for a, b in zip(edges[:-1], edges[1:]) if b > a])
        tt = np.array([t[a:b][np.argmin(resid[a:b])] for a, b in zip(edges[:-1], edges[1:]) if b > a])
        k, c = np.polyfit(ti, tt, 1)
        rate = 1.0 / k
    return c, rate


def find_carrier(x, fs, f_lo=None, f_hi=None, seconds=8.0):
    """Frequency (Hz, relative to centre) of the strongest steady line."""
    n = int(min(len(x), seconds * fs))
    nfft = 1 << int(np.ceil(np.log2(n)))
    spec = np.abs(np.fft.fftshift(np.fft.fft(x[:n] * np.hanning(n), nfft)))
    f = np.fft.fftshift(np.fft.fftfreq(nfft, 1 / fs))
    mask = np.abs(f) > 200.0  # stay off the receiver's DC spike
    if f_lo is not None:
        mask &= (f >= f_lo) & (f <= f_hi)
    k = np.argmax(np.where(mask, spec, 0))
    return float(f[k])


def to_baseband(x, fs, f_c, fs_out=1250.0, bw=400.0):
    """Shift the carrier to 0 Hz, low-pass and decimate. Returns (y, fs_out)."""
    n = np.arange(len(x), dtype=np.float64)
    y = x * np.exp(-2j * np.pi * f_c / fs * n).astype(np.complex64)
    q = int(round(fs / fs_out))
    # two-stage decimation keeps the filters short
    q1 = 1
    for cand in (10, 8, 6, 5, 4, 3, 2):
        if q % cand == 0 and q // cand >= 1:
            q1 = cand
            break
    q2 = q // q1
    if q1 > 1:
        h1 = signal.firwin(8 * q1 + 1, 0.8 / q1)
        y = signal.upfirdn(h1, y, down=q1)[4:]
    if q2 > 1:
        h2 = signal.firwin(16 * q2 + 1, bw / (fs / q1 / 2))
        y = signal.upfirdn(h2, y, down=q2)[8:]
    return y.astype(np.complex64), fs / q


def reference(y, fs, bw=1.5):
    """Estimate the direct signal as the part of y slower than `bw` Hz."""
    sos = signal.butter(4, bw / (fs / 2), output="sos")
    return signal.sosfiltfilt(sos, y).astype(np.complex64)


def self_reference(y, fs, bw=1.5):
    """z = y / d - 1: what is left once the direct signal is divided out.

    The direct signal carries the transmitter's drift and the receiver's
    oscillator noise; anything scattered off a moving aircraft shows up in z
    at its Doppler shift relative to the direct signal.
    """
    d = reference(y, fs, bw)
    z = y / d - 1.0
    return z.astype(np.complex64), d


def spectrogram(z, fs, win_s=2.0, hop_s=0.25, f_max=250.0, pad=2):
    """Two-sided short-time power spectrum. Returns (t, f, P[t, f])."""
    nw = int(round(win_s * fs))
    hop = int(round(hop_s * fs))
    nfft = pad * (1 << int(np.ceil(np.log2(nw))))
    w = np.hanning(nw).astype(np.float32)
    starts = np.arange(0, len(z) - nw + 1, hop)
    f = np.fft.fftshift(np.fft.fftfreq(nfft, 1 / fs))
    keep = np.abs(f) <= f_max
    out = np.empty((len(starts), int(keep.sum())), dtype=np.float32)
    for i, s in enumerate(starts):
        seg = z[s:s + nw] * w
        sp = np.fft.fftshift(np.fft.fft(seg, nfft))
        out[i] = (np.abs(sp[keep]) ** 2) / (w.sum() ** 2)
    t = (starts + nw / 2) / fs
    return t, f[keep], out


def remove_drift(y, fs, block_s=2.0, hop_s=0.5, search_hz=40.0, hold_db=10.0):
    """Follow the slow wander of the direct carrier and take it out.

    Cheap receivers drift by several Hz over minutes. We track the carrier
    peak block by block, smooth the track, and counter-rotate. Returns
    (y_flat, f_track_at_samples).

    hold_db: a block
    whose peak is more than hold_db below the running median peak of the last
    60 accepted blocks keeps the previous frequency instead of following noise,
    and the track never leaves +-search_hz of the baseband centre. One
    recording (from an HF+ server) had stream gaps 20-50 dB deep lasting about
    1.5 s every 10-20 s; the +-6 Hz follower jumped a few Hz at each one and
    walked 280 Hz off over 91 minutes, so the direct C/N0 read 7.6 dB-Hz
    instead of 55 and the search saw nothing. Recordings without deep gaps
    are unchanged (checked on four recordings at two sites).
    """
    nb, hop = int(block_s * fs), int(hop_s * fs)
    nfft = 8 * (1 << int(np.ceil(np.log2(nb))))
    w = np.hanning(nb)
    f = np.fft.fftfreq(nfft, 1 / fs)
    starts = np.arange(0, len(y) - nb + 1, hop)
    ft = np.empty(len(starts))
    prev = None
    accepted = []          # peak amplitudes of the blocks that were followed
    hold_amp = 10 ** (-hold_db / 20.0)
    for i, s in enumerate(starts):
        sp = np.abs(np.fft.fft(y[s:s + nb] * w, nfft))
        m = np.abs(f - (prev if prev is not None else 0.0)) <= (search_hz if prev is None else 6.0)
        k = int(np.argmax(np.where(m, sp, 0)))
        a, b, c = sp[k - 1], sp[k], sp[(k + 1) % nfft]
        if accepted and b < hold_amp * np.median(accepted[-60:]):
            ft[i] = prev           # gap or deep fade: hold the last good frequency
            continue
        delta = 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else 0.0
        est = f[k] + delta * fs / nfft
        if abs(est) > search_hz and prev is not None:
            ft[i] = prev           # never wander out of the search window around the centre
            continue
        ft[i] = est
        accepted.append(b)
        prev = ft[i]
    tc = (starts + nb / 2) / fs
    # smooth: median of 9 then moving average of 9 (about 4 s)
    fm = signal.medfilt(ft, 9) if len(ft) >= 9 else ft
    kern = np.ones(9) / 9
    fm = np.convolve(np.pad(fm, 4, mode="edge"), kern, mode="valid")
    t = np.arange(len(y)) / fs
    fs_track = np.interp(t, tc, fm)
    phase = 2 * np.pi * np.cumsum(fs_track) / fs
    return (y * np.exp(-1j * phase)).astype(np.complex64), fs_track
