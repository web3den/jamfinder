"""Pick the measured Doppler of each aircraft off the waterfall and solve for
the transmitter (and, if asked, the receiver and clock offsets) by least squares."""
import numpy as np
from scipy import optimize

from . import tracks


def extract(t, f, W, paths, tx, rx, lam, dt=0.0, dt_ac=None, half_hz=4.0, min_db=9.0,
            f_lo=3.0, f_hi=140.0, folded=False):
    """Strongest cell near each aircraft's predicted Doppler, frame by frame.

    Returns a list of dicts (one per aircraft with any hits):
      hex, i (frame index), t (frame time), f (measured Hz), snr_db, f0 (prediction used)
    """
    df = float(f[1] - f[0])
    hw = int(round(half_hz / df))
    D = 10.0 * np.log10(np.maximum(W, 1e-6))
    out = []
    for h, p in paths.items():
        tq = t + dt + (dt_ac.get(h, 0.0) if dt_ac else 0.0)
        ok = p.valid(tq)
        if ok.sum() < 4:
            continue
        idx = np.where(ok)[0]
        fp = tracks.doppler_pv(p.pos(tq[idx]), p.vel(tq[idx]), tx, rx, lam)
        if folded:
            fp = np.abs(fp)
        use = (np.abs(fp) >= f_lo) & (np.abs(fp) <= f_hi)
        rows = []
        for i, f0 in zip(idx[use], fp[use]):
            j0 = int(round((f0 - f[0]) / df))
            a, b = max(1, j0 - hw), min(len(f) - 1, j0 + hw + 1)
            seg = D[i, a:b]
            j = a + int(np.argmax(seg))
            if D[i, j] < min_db or j <= a or j >= b - 1:
                continue  # too weak, or the peak sits on the window edge (probably something else)
            y0, y1, y2 = D[i, j - 1], D[i, j], D[i, j + 1]
            den = y0 - 2 * y1 + y2
            off = 0.5 * (y0 - y2) / den if den < 0 else 0.0
            rows.append((i, t[i], f[j] + off * df, y1, f0))
        if rows:
            r = np.array(rows)
            out.append(dict(hex=h, i=r[:, 0].astype(int), t=r[:, 1], f=r[:, 2], snr_db=r[:, 3], f0=r[:, 4]))
    return out


class Fit:
    """Least squares over transmitter E/N, optionally receiver E/N, clock offset, per-aircraft offsets."""

    def __init__(self, meas, paths, lam, tx_h, rx, fit_rx=False, fit_dt=True, fit_dt_ac=False,
                 sig_hz=0.5, rx_prior=None, dt_ac_prior=0.5, folded=False):
        self.meas, self.paths, self.lam, self.tx_h = meas, paths, lam, tx_h
        self.rx0 = np.asarray(rx, float)
        self.fit_rx, self.fit_dt, self.fit_dt_ac = fit_rx, fit_dt, fit_dt_ac
        self.sig, self.rx_prior, self.dt_ac_prior, self.folded = sig_hz, rx_prior, dt_ac_prior, folded
        self.hexes = [m["hex"] for m in meas]

    def unpack(self, x):
        tx = np.array([x[0], x[1], self.tx_h])
        k = 2
        rx = self.rx0.copy()
        if self.fit_rx:
            rx[:2] = x[k:k + 2]
            k += 2
        dt = 0.0
        if self.fit_dt:
            dt = x[k]
            k += 1
        dta = np.zeros(len(self.meas))
        if self.fit_dt_ac:
            dta = np.asarray(x[k:k + len(self.meas)])
        return tx, rx, dt, dta

    def x0(self, tx, dt=0.0):
        x = [tx[0], tx[1]]
        if self.fit_rx:
            x += [self.rx0[0], self.rx0[1]]
        if self.fit_dt:
            x.append(dt)
        if self.fit_dt_ac:
            x += [0.0] * len(self.meas)
        return np.array(x, float)

    def predict(self, x, k):
        tx, rx, dt, dta = self.unpack(x)
        m = self.meas[k]
        p = self.paths[m["hex"]]
        tq = m["t"] + dt + dta[k]
        fp = tracks.doppler_pv(p.pos(tq), p.vel(tq), tx, rx, self.lam)
        return np.abs(fp) if self.folded else fp

    def resid(self, x, keep=None):
        r = []
        for k, m in enumerate(self.meas):
            if keep is not None and not keep[k]:
                continue
            r.append((m["f"] - self.predict(x, k)) / self.sig)
        tx, rx, dt, dta = self.unpack(x)
        if self.fit_rx and self.rx_prior:
            r.append((rx[:2] - self.rx0[:2]) / self.rx_prior)
        if self.fit_dt_ac:
            r.append(dta / self.dt_ac_prior)
        return np.concatenate(r)

    def jac(self, x, keep=None):
        """Central differences with fixed steps (1 m, 0.01 s).

        The library default step is far below the resolution of a unix
        timestamp, which would make the clock columns come out as zero.
        """
        h = np.where(self.scales() < 1.0, 0.01, 1.0)
        cols = []
        for k in range(len(x)):
            e = np.zeros(len(x))
            e[k] = h[k]
            cols.append((self.resid(x + e, keep) - self.resid(x - e, keep)) / (2 * h[k]))
        return np.stack(cols, axis=1)

    def solve(self, x0, keep=None, f_scale=2.0):
        res = optimize.least_squares(self.resid, x0, jac=self.jac, args=(keep,), loss="soft_l1", f_scale=f_scale,
                                     x_scale=self.scales(), method="trf")
        return res

    def scales(self):
        s = [100.0, 100.0]
        if self.fit_rx:
            s += [100.0, 100.0]
        if self.fit_dt:
            s.append(0.2)
        if self.fit_dt_ac:
            s += [0.2] * len(self.meas)
        return np.array(s)

    def cov(self, res):
        """Formal covariance, scaled by the robust spread of the residuals."""
        J = self.jac(res.x)
        r = self.resid(res.x)
        n_m = sum(len(m["f"]) for m in self.meas)
        s = 1.4826 * np.median(np.abs(r[:n_m] - np.median(r[:n_m])))
        JTJ = J.T @ J
        return np.linalg.inv(JTJ) * max(s, 1e-6) ** 2, s * self.sig
