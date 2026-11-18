#!/usr/bin/env python3
"""First look at a running or finished SpyServer recording: is the carrier there, where, how strong, how clean?

Reads the first `seconds` of <prefix>.iq (format from <prefix>.json, which spy_record saves every minute) and prints
the carrier offset from the centre, its level against full scale, the carrier-to-noise density in a quiet band
3-140 Hz away, and the strongest lines within +-250 Hz of the carrier (a conventional VOR shows +-30 Hz).
Nothing here touches the search or the pipeline.
usage: quick_look.py prefix [seconds=60] [skip=5]"""
import json
import sys

import numpy as np

prefix = sys.argv[1]
seconds = float(sys.argv[2]) if len(sys.argv) > 2 else 60.0
skip = float(sys.argv[3]) if len(sys.argv) > 3 else 5.0
meta = json.load(open(prefix + ".json"))
fs, fmt = float(meta["rate"]), int(meta["fmt"])
dtype, bps = {1: (np.uint8, 1), 2: (np.int16, 2), 4: (np.float32, 4)}[fmt]
n0, n = int(skip * fs), int(seconds * fs)
raw = np.fromfile(prefix + ".iq", dtype=dtype, count=2 * n, offset=2 * n0 * bps)
if len(raw) < 4 * fs:
    sys.exit(f"only {len(raw) / 2 / fs:.1f} s of samples so far")
x = raw.astype(np.float32)
if fmt == 1:
    x = (x - 127.5) / 127.5
elif fmt == 2:
    x = x / 32768.0
z = x[0::2] + 1j * x[1::2]
peak_fs = 20 * np.log10(max(np.abs(z).max(), 1e-9))
rms_fs = 20 * np.log10(max(np.sqrt(np.mean(np.abs(z) ** 2)), 1e-9))
# coarse spectrum: 1 Hz bins over 1-s blocks, averaged
nfft = int(round(fs))
nb = len(z) // nfft
P = np.zeros(nfft)
w = np.hanning(nfft).astype(np.float32)
for k in range(nb):
    P += np.abs(np.fft.fft(z[k * nfft:(k + 1) * nfft] * w)) ** 2
P /= max(nb, 1)
f = np.fft.fftfreq(nfft, 1 / fs)
order = np.argsort(f)
f, P = f[order], P[order]
k = int(np.argmax(P))
fc = f[k]
pc_db = 10 * np.log10(P[k])
sel = (np.abs(f - fc) >= 3) & (np.abs(f - fc) <= 140)
n0_db = 10 * np.log10(np.median(P[sel]))      # per 1-Hz bin, so this is a density
print(f"{len(z) / fs:.0f} s read ({meta.get('kind', '?')} at {fs:.0f} Hz, centre {meta['freq'] / 1e6:.6f} MHz)")
print(f"peak |z| {peak_fs:+.1f} dBFS, rms {rms_fs:+.1f} dBFS" + ("  <-- clipping risk" if peak_fs > -1.0 else ""))
far = (np.abs(f - fc) >= 1000) & (np.abs(f - fc) <= 4000) & (np.abs(f) > 100)   # thermal floor away from the carrier's skirt and DC
n0_far_db = 10 * np.log10(np.median(P[far])) if far.any() else n0_db
# the near figure is pulled down by a wide carrier skirt (AGC hunting lines at +-2..5 Hz on the Helsinki dongle read 46
# when the floor said 56, 2026-11-16 07:50 UTC); the far figure is the one comparable to site_run's "direct C/N0", reading
# 3-4 dB under it (one recording: 57.0 here, 60.8 in site_run; no window correction, 50 s only)
print(f"carrier at {fc:+.1f} Hz from centre, C/N0 about {pc_db - n0_db:.1f} dB-Hz (median noise 3-140 Hz from the carrier), "
      f"{pc_db - n0_far_db:.1f} dB-Hz against the floor 1-4 kHz away")
near = (np.abs(f - fc) >= 2) & (np.abs(f - fc) <= 250)
top = sorted(zip(10 * np.log10(P[near]) - pc_db, f[near] - fc), reverse=True)[:8]
print("strongest lines within 250 Hz of the carrier (dB rel. carrier at offset Hz): " + ", ".join(f"{a:+.0f} @ {b:+.0f}" for a, b in top))
wide = np.abs(f - fc) > 250
if wide.any():
    kk = int(np.argmax(np.where(wide, P, 0)))
    print(f"strongest other signal in the passband: {10 * np.log10(P[kk]) - pc_db:+.0f} dB rel. carrier at {f[kk] - fc:+.0f} Hz")
