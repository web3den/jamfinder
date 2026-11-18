#!/usr/bin/env python3
"""First look: carrier-referenced Doppler waterfall of a (possibly partial) capture.

usage: first_look.py prefix out.png [kind rate dgain_db]
"""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from jf import iq

prefix, out = sys.argv[1], sys.argv[2]
kw = {}
if len(sys.argv) > 3:
    kw = dict(kind=sys.argv[3], rate=float(sys.argv[4]), dgain_db=float(sys.argv[5]))
x, fs, meta = iq.load(prefix, **kw)
print(f"samples {len(x)}  fs {fs}  dur {len(x)/fs:.1f} s")
fc = iq.find_carrier(x, fs)
print(f"carrier at {fc:+.2f} Hz")
y, fs2 = iq.to_baseband(x, fs, fc)
# carrier level and noise floor
P = np.abs(np.fft.fft(y[: int(fs2 * 20)] * np.hanning(int(fs2 * 20)))) ** 2
print(f"carrier amp {np.abs(y).mean():.4f}; drift check: mean phase step {np.angle(np.mean(y[1:] * np.conj(y[:-1]))) * fs2 / 2 / np.pi:+.3f} Hz")
y, ftrack = iq.remove_drift(y, fs2)
print(f"carrier drift over the capture: {ftrack[0]:+.2f} -> {ftrack[-1]:+.2f} Hz")
z, d = iq.self_reference(y, fs2, bw=1.0)
t, f, S = iq.spectrogram(z, fs2, win_s=2.0, hop_s=0.5, f_max=250.0)
env = (np.abs(y) / np.abs(d) - 1.0).astype(np.float32)
te, fe, Se = iq.spectrogram(env.astype(np.complex64), fs2, win_s=2.0, hop_s=0.5, f_max=250.0)
med = np.median(S, axis=0, keepdims=True)
SdB = 10 * np.log10(S / med + 1e-12)
print(f"median floor rel. carrier: {10*np.log10(np.median(S)):.1f} dBc per bin (2 s Hann)")
print("strongest cells (dB over per-bin median):", np.round(np.sort(SdB.ravel())[-5:], 1))
fig, ax = plt.subplots(3, 1, figsize=(16, 13), constrained_layout=True)
ax[0].imshow(SdB.T, origin="lower", aspect="auto", extent=[t[0], t[-1], f[0], f[-1]], vmin=0, vmax=25, cmap="magma")
ax[0].set_title("z = y/d - 1, two-sided (dB over per-bin median)"); ax[0].set_ylabel("Doppler, Hz")
ax[1].imshow(10 * np.log10(S.T + 1e-15), origin="lower", aspect="auto", extent=[t[0], t[-1], f[0], f[-1]], vmin=-95, vmax=-50, cmap="viridis")
ax[1].set_title("same, absolute dBc per bin"); ax[1].set_ylabel("Doppler, Hz")
mede = np.median(Se, axis=0, keepdims=True)
ax[2].imshow(10 * np.log10(Se / mede + 1e-12).T, origin="lower", aspect="auto", extent=[te[0], te[-1], fe[0], fe[-1]], vmin=0, vmax=25, cmap="magma")
ax[2].set_title("envelope only (immune to oscillator phase noise; folds +/-)"); ax[2].set_ylabel("Hz"); ax[2].set_xlabel("seconds from start")
fig.savefig(out, dpi=80)
print("saved", out)
