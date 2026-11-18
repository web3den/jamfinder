#!/usr/bin/env python3
"""How well does a short capture hear a steady carrier? Prints its offset and carrier-to-noise density.

usage: probe.py iq_prefix [f_lo_hz f_hi_hz]   (limits for the carrier search, relative to the capture centre)
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jf import iq, scatter  # noqa: E402

prefix = sys.argv[1]
lim = [float(v) for v in sys.argv[2:4]] if len(sys.argv) > 3 else [None, None]
x, fs, meta = iq.load(prefix)
t0, rate = iq.sample_clock(meta, len(x))
fc = iq.find_carrier(x, fs, lim[0], lim[1])
y, fs2 = iq.to_baseband(x, fs, fc)
bb = dict(y=y, fs=np.float64(fs2), t0=np.float64(t0), scale=np.float64(fs / rate), carrier_hz=np.float64(fc))
wf = scatter.waterfall(bb)
# the eight strongest lines of the whole capture, for orientation
n = 1 << 16
segs = max(1, len(x) // n)
P = np.zeros(n)
for i in range(segs):
    P += np.abs(np.fft.fftshift(np.fft.fft(x[i * n:(i + 1) * n] * np.hanning(n), n))) ** 2
f = np.fft.fftshift(np.fft.fftfreq(n, 1 / fs))
floor = np.median(P)
top = []
Q = P.copy()
for _ in range(8):
    k = int(np.argmax(Q))
    top.append((f[k], 10 * np.log10(Q[k] / floor)))
    Q[max(0, k - 40):k + 40] = 0
s0 = meta.get("sync0", {})
print(f"{os.path.basename(prefix)}: {len(x) / fs:.0f} s at {fs:.0f} Hz, {meta['kind']}, drops {meta['drops']}, "
      f"control {s0.get('can_control')}, gain {s0.get('gain')}, device centre {s0.get('dev_cf', 0) / 1e6:.4f} MHz")
print(f"   carrier at {fc:+.0f} Hz from the capture centre ({(meta['freq'] + fc) / 1e6:.5f} MHz), "
      f"C/N0 {-wf['n0_dbc_hz']:.1f} dB-Hz, drift {float(np.ptp(wf['drift'])):.1f} Hz")
print("   strongest lines (Hz: dB over the floor): " + "  ".join(f"{a:+.0f}: {b:.0f}" for a, b in top))
