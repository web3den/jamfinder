#!/usr/bin/env python3
"""Waterfall with predicted aircraft Doppler tracks drawn on top.

usage: overlay.py iq_prefix adsb.jsonl.gz out.png rx_lat rx_lon tx_lat tx_lon freq_hz
                  [t_iq0 kind rate dgain_db]
"""
import sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[1]))
from jf import geo, iq, tracks

a = sys.argv
prefix, adsb, out = a[1], a[2], a[3]
rx_lat, rx_lon, tx_lat, tx_lon, freq = map(float, a[4:9])
kw, t_iq0 = {}, None
if len(a) > 9:
    t_iq0 = float(a[9])
    kw = dict(kind=a[10], rate=float(a[11]), dgain_db=float(a[12]))
x, fs, meta = iq.load(prefix, **kw)
rate_scale = 1.0
if meta is not None:
    t_iq0, true_rate = iq.sample_clock(meta, len(x))
    print(f"sample clock: t0 {t_iq0:.3f}, rate {true_rate:.3f} Hz (nominal {fs})")
    rate_scale = fs / true_rate
fc = iq.find_carrier(x, fs)
y, fs2 = iq.to_baseband(x, fs, fc)
y, ftrack = iq.remove_drift(y, fs2)
z, d = iq.self_reference(y, fs2, bw=1.0)
t, f, S = iq.spectrogram(z, fs2, win_s=2.0, hop_s=0.5, f_max=250.0)
t_abs = t_iq0 + t * rate_scale
med = np.median(S, axis=0, keepdims=True)
SdB = 10 * np.log10(S / med + 1e-12)

fr = geo.Frame(rx_lat, rx_lon, 0.0)
rx = np.array([0.0, 0.0, 45.0])
tx = fr.to_enu(tx_lat, tx_lon, 85.0)
lam = tracks.C / freq
paths, off = tracks.load_paths(adsb, fr, ground_h=73.0)
print(f"{len(paths)} aircraft paths; geometric minus barometric height {off:+.0f} m")
n_rows = max(1, int(np.ceil((t_abs[-1] - t_abs[0]) / 300.0)))
fig, ax = plt.subplots(n_rows, 1, figsize=(20, 5.2 * n_rows), constrained_layout=True, squeeze=False)
cols = plt.cm.tab10(np.linspace(0, 1, 10))
tq_all = t_abs
for r in range(n_rows):
    A = ax[r, 0]
    lo, hi = r * 300.0, (r + 1) * 300.0
    m = (t_abs - t_iq0 >= lo) & (t_abs - t_iq0 < hi)
    if m.sum() < 2:
        continue
    A.imshow(SdB[m].T, origin="lower", aspect="auto",
             extent=[t_abs[m][0] - t_iq0, t_abs[m][-1] - t_iq0, f[0], f[-1]], vmin=0, vmax=25, cmap="magma")
    A.set_ylabel("Doppler, Hz")
    A.set_xlim(lo, hi)
for i, (h, p) in enumerate(paths.items()):
    ok = p.valid(tq_all)
    if ok.sum() < 4:
        continue
    tq = tq_all[ok]
    fd = p.doppler(tq, tx, rx, lam)
    r1, r2 = p.ranges(tq, tx, rx)
    if np.all(np.abs(fd) > 250) or (np.nanmax(np.abs(fd)) < 1.5):
        continue
    c = cols[i % 10]
    for r in range(n_rows):
        lo, hi = r * 300.0, (r + 1) * 300.0
        m = (tq - t_iq0 >= lo) & (tq - t_iq0 < hi)
        if m.sum() < 2:
            continue
        seg = np.where(np.diff(tq[m]) > 2.0)[0]
        fdm = fd[m].copy()
        fdm[seg] = np.nan
        ax[r, 0].plot(tq[m] - t_iq0, fdm, color=c, lw=0.7, alpha=0.85, ls=(0, (6, 6)))
        j = np.argmin(np.abs(fd[m])) if np.any(np.abs(fd[m]) < 240) else len(fdm) // 2
        ax[r, 0].text(tq[m][j] - t_iq0, np.clip(fd[m][j], -235, 235) + 6, f"{p.flight or h}", color=c, fontsize=8)
    print(f"{h} {p.flight:8s} {p.actype:5s} {p.src:10s} t {tq[0]-t_iq0:6.0f}..{tq[-1]-t_iq0:6.0f}s  "
          f"fd {fd.min():+7.1f}..{fd.max():+7.1f} Hz  R1 {r1.min()/1e3:5.1f} km  R2 {r2.min()/1e3:5.1f} km  "
          f"fit {p.res_p:5.1f} m {p.res_v:4.2f} m/s")
ax[0, 0].set_title("scatter relative to the direct carrier (dB over per-bin median); dashed: predicted from ADS-B for the assumed transmitter site")
ax[-1, 0].set_xlabel("seconds from start of IQ")
fig.savefig(out, dpi=70)
print("saved", out)
