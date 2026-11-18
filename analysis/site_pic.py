"""Picture: wide search map with the candidates, and the whitened waterfall with the predicted echo lines of the
strongest aircraft drawn for the best spot. Truth-blind: only the candidate and public map points are drawn."""
import sys, os
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
P = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..") + "/"
sys.path.insert(0, P)
from jf import field, geo, scatter, tracks
name, out = sys.argv[1], sys.argv[2]
rx_lat, rx_lon, freq = map(float, sys.argv[3:6])
opt = dict(a.split("=", 1) for a in sys.argv[6:])
rx = np.array([float(opt.get("rx_e", 0)), float(opt.get("rx_n", 0)), float(opt.get("rx_h", 45))])
tx_h = float(opt.get("tx_h", 85))
lam = tracks.C / freq
fr = geo.Frame(rx_lat, rx_lon, 0.0)
paths, off = tracks.load_paths(opt["adsb"], fr, ground_h=float(opt.get("ground_h", 73)))
bb = dict(np.load(P + f"results/{name}_bb.npz"))
wf = scatter.waterfall(bb)
t, f = wf["t"], wf["f"]
W, _ = scatter.whiten(wf["S"], f)
print("t[0]", t[0], "bb t0", float(bb["t0"]))
r = field.search(t, f, W, paths, rx, lam, tx_h=tx_h, span=30e3)
label, _ = field.verdict(r["cands"])
eA, nA, mA = r["mapA"]
best = r["cands"][0]
sup = field.support(r["field"], best, r["clocks"][0])
top = [h for z, h in sup[:7]]
fig, axs = plt.subplots(1, 2, figsize=(16, 7.2), gridspec_kw=dict(width_ratios=[1, 1.35]))
ax = axs[0]
im = ax.imshow(mA, origin="lower", extent=(eA[0] / 1e3, eA[-1] / 1e3, nA[0] / 1e3, nA[-1] / 1e3), cmap="magma", vmin=0, aspect="equal")
plt.colorbar(im, ax=ax, shrink=0.8, label="evidence (noise units)")
for p in paths.values():
    tt = np.arange(p.t0, p.t1, 4.0)
    tt = tt[p.valid(tt)]
    if len(tt) > 3:
        q = p.pos(tt) / 1e3
        ax.plot(q[:, 0], q[:, 1], color="w", lw=0.4, alpha=0.5)
for k, c in enumerate(r["cands"]):
    ax.plot(c[1] / 1e3, c[2] / 1e3, "r*" if k == 0 else "c^", ms=16 if k == 0 else 9, mec="k", label=(f"best spot {c[0]:.0f}" if k == 0 else (f"other candidates {c[0]:.0f}…" if k == 1 else None)))
ax.plot(rx[0] / 1e3, rx[1] / 1e3, "w+", ms=14, mew=2, label="receiver (listed position)")
if "mark" in opt:          # a public map point to orient by, e.g. the airport reference point
    la, lo = map(float, opt["mark"].split(","))
    q = fr.to_enu(la, lo, 0.0)
    ax.plot(q[0] / 1e3, q[1] / 1e3, "ws", ms=7, mfc="none", mew=1.5, label=opt.get("mark_name", "airport reference point"))
ax.set_xlim(eA[0] / 1e3, eA[-1] / 1e3); ax.set_ylim(nA[0] / 1e3, nA[-1] / 1e3)
ax.set_xlabel("km east of the receiver"); ax.set_ylabel("km north")
ax.set_title(f"{name}: wide search map (500 m cells), verdict by the frozen rule: {label}\nbest {best[0]:.1f} at E {best[1]:.0f} N {best[2]:.0f}; next {r['cands'][1][0]:.1f}, {r['cands'][2][0]:.1f}", fontsize=10)
ax.legend(loc="lower left", fontsize=8)
# waterfall window: 20 minutes holding the most close passes of the strongest aircraft
tc = []
for h in top:
    p = paths[h]
    tt = np.arange(p.t0, p.t1, 2.0)
    tt = tt[p.valid(tt)]
    if len(tt):
        d = np.linalg.norm(p.pos(tt)[:, :2] - rx[:2], axis=1)
        tc.append(tt[np.argmin(d)])
tc = np.array(tc)
win = float(opt.get("win", 1200))
starts = np.arange(t[0], t[-1] - win, 60.0)
n_in = [np.sum((tc >= s) & (tc <= s + win)) for s in starts]
s0 = starts[int(np.argmax(n_in))]
m = (t >= s0) & (t <= s0 + win)
ax = axs[1]
dB = 10 * np.log10(np.maximum(W[m] * field.LN2, 1e-3))
ax.imshow(dB.T, origin="lower", aspect="auto", extent=((t[m][0] - t[0]) / 60, (t[m][-1] - t[0]) / 60, f[0], f[-1]), cmap="gray_r", vmin=-2, vmax=8)
cols = plt.cm.tab10(np.arange(10))
tx = np.array([best[1], best[2], tx_h])
for k, h in enumerate(top):
    p = paths[h]
    tq = t[m] + best[3] + r["clocks"][0].get(h, 0.0)
    ok = p.valid(tq)
    if ok.sum() < 3:
        continue
    fd = p.doppler(tq[ok], tx, rx, lam)
    ax.plot((t[m][ok] - t[0]) / 60, fd + 9, color=cols[k], lw=0.9, ls="--", alpha=0.9)
    ax.plot((t[m][ok] - t[0]) / 60, fd - 9, color=cols[k], lw=0.9, ls="--", alpha=0.9, label=f"{(p.flight or h).strip()} (evidence {dict((hh, z) for z, hh in sup)[h]:.0f})")
ax.set_ylim(-140, 140)
ax.set_xlabel("minutes into the recording"); ax.set_ylabel("Doppler shift relative to the direct signal (Hz)")
ax.set_title("whitened waterfall (dark = power above noise); dashed pairs: predicted echo line ±9 Hz\nfor the best spot, strongest aircraft", fontsize=10)
ax.legend(loc="upper right", fontsize=8)
fig.suptitle(opt.get("title", name), fontsize=12)
fig.tight_layout()
fig.savefig(out, dpi=105)
print("written", out, "window start", (s0 - t[0]) / 60, "min")
