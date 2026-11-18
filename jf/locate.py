"""Find the transmitter: try candidate positions, keep the one whose predicted
aircraft Doppler tracks collect the most energy in the measured waterfall."""
import numpy as np
from scipy import optimize

from . import tracks


class Problem:
    def __init__(self, t, f, Sc, paths, rx, lam, f_lo=3.0, f_hi=140.0, dt=0.0, tx_h=60.0, folded=False):
        self.t, self.f, self.Sc = np.asarray(t, float), np.asarray(f, float), Sc
        self.df = float(self.f[1] - self.f[0])
        self.rx = np.asarray(rx, float)
        self.lam, self.f_lo, self.f_hi, self.tx_h = lam, f_lo, f_hi, tx_h
        self.folded = folded
        self.paths = paths
        self.set_dt(dt)

    def set_dt(self, dt):
        """dt is added to the IQ frame times before looking up aircraft states."""
        self.dt = dt
        self.ac = []
        for h, p in self.paths.items():
            tq = self.t + dt
            ok = p.valid(tq)
            if ok.sum() < 4:
                continue
            idx = np.where(ok)[0]
            pos, vel = p.pos(tq[idx]), p.vel(tq[idx])
            self.ac.append((h, idx, pos, vel))

    def _sample(self, idx, fd):
        """Sum of scores along predicted tracks. fd: (G, T) -> (G,)"""
        if self.folded:
            fd = np.abs(fd)
        use = (np.abs(fd) >= self.f_lo) & (np.abs(fd) <= self.f_hi)
        j = np.rint((fd - self.f[0]) / self.df).astype(np.int64)
        np.clip(j, 0, len(self.f) - 1, out=j)
        v = self.Sc[idx[None, :], j]
        return np.where(use, v, 0.0).sum(axis=1), use.sum(axis=1)

    def score(self, tx, rx=None, per_aircraft=False, chunk=400):
        """tx: (G, 3) candidates. Returns total score (G,), optionally a dict per aircraft."""
        tx = np.atleast_2d(np.asarray(tx, float))
        rx = self.rx if rx is None else np.asarray(rx, float)
        tot = np.zeros(len(tx))
        per = {}
        for h, idx, pos, vel in self.ac:
            s = np.zeros(len(tx))
            n = np.zeros(len(tx))
            for a in range(0, len(tx), chunk):
                fd = tracks.doppler_pv(pos, vel, tx[a:a + chunk], rx, self.lam)
                s[a:a + chunk], n[a:a + chunk] = self._sample(idx, fd)
            tot += s
            if per_aircraft:
                per[h] = (s, n)
        return (tot, per) if per_aircraft else tot

    def grid(self, e_range, n_range, step):
        e = np.arange(e_range[0], e_range[1] + step / 2, step)
        n = np.arange(n_range[0], n_range[1] + step / 2, step)
        E, N = np.meshgrid(e, n)
        tx = np.stack([E.ravel(), N.ravel(), np.full(E.size, self.tx_h)], axis=1)
        return e, n, self.score(tx).reshape(E.shape)

    def refine(self, tx0, fit_dt=True, fit_rx=False, dt_span=3.0, rx_span=1500.0):
        """Local polish with Nelder-Mead over transmitter east/north (+ clock offset, + receiver)."""
        x0 = [tx0[0], tx0[1]]
        if fit_dt:
            x0.append(self.dt)
        if fit_rx:
            x0 += [self.rx[0], self.rx[1]]
        dt_keep = self.dt

        def unpack(x):
            tx = np.array([x[0], x[1], self.tx_h])
            k = 2
            dt = dt_keep
            if fit_dt:
                dt = x[k]
                k += 1
            rx = self.rx
            if fit_rx:
                rx = np.array([x[k], x[k + 1], self.rx[2]])
            return tx, dt, rx

        def cost(x):
            tx, dt, rx = unpack(x)
            if fit_dt and abs(dt - dt_keep) > dt_span:
                return 0.0
            if fit_rx and np.hypot(rx[0] - self.rx[0], rx[1] - self.rx[1]) > rx_span:
                return 0.0
            if dt != self.dt:
                self.set_dt(dt)
            return -float(self.score(tx[None], rx=rx)[0])

        steps = [300.0, 300.0] + ([0.5] if fit_dt else []) + ([200.0, 200.0] if fit_rx else [])
        sim = np.array([x0] + [np.array(x0) + np.eye(len(x0))[i] * steps[i] for i in range(len(x0))])
        res = optimize.minimize(cost, x0, method="Nelder-Mead",
                                options=dict(initial_simplex=sim, xatol=2.0, fatol=0.5, maxiter=600))
        tx, dt, rx = unpack(res.x)
        self.set_dt(dt)
        return tx, dt, rx, -res.fun
