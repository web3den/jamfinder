"""Search when the receiver cannot hear the transmitter itself.

With a direct signal, echoes are measured against it and sit exactly at the
Doppler shift D_k(t; x) of aircraft k for a transmitter at x. With no direct
signal there is nothing to measure against. The echoes then sit at

    f0(t) + D_k(t; x)

where f0(t) is unknown: the transmitter's frequency error plus the receiver's
drift. But f0 is the same for every aircraft and changes slowly. So for each
candidate x we look for the one smooth frequency path f0(t) that collects the
most evidence along all predicted tracks (dynamic programming over time
blocks). The right x is the one whose best path collects the most.

This is how the search-and-rescue satellites work (they solve for the beacon's
position and its unknown frequency together), turned around: the receiver
stands still and the "satellites" are passing aircraft.
"""
import numpy as np
from numba import njit, prange

from . import field as _field

Z0 = _field.Z0
PHI_MEAN = _field.PHI_MEAN
PHI_VAR = _field.PHI_VAR


@njit(cache=True, fastmath=True)
def _evidence(c, tx, CU, idx, pos, vel, vr2, gb, ac_off, shifts, v_tab, nblocks,
              f0, df, lam, f_lo, f_hi, h_min, h_max, step, E):
    """Fill E[block, shift] for candidate c. Returns the number of aircraft-blocks counted."""
    nS = len(shifts)
    nf = CU.shape[1] - 1
    num = np.zeros(nS)
    nfull = 0
    for k in range(len(ac_off) - 1):
        cur = -1
        cnt = 0
        used = 0
        var = 0.0
        for r in range(ac_off[k], ac_off[k + 1] + 1):
            last = r == ac_off[k + 1]
            b = -2 if last else gb[r]
            if b != cur:
                if cur >= 0 and cnt > 0 and used >= 0.5 * cnt and var > 0:
                    sd = np.sqrt(var)
                    for s in range(nS):
                        z = num[s] / sd
                        if z > 0:
                            E[cur, s] += (z * z if z < Z0 else 2 * Z0 * z - Z0 * Z0)
                        E[cur, s] -= PHI_MEAN
                    nfull += 1
                cur = b
                cnt = 0
                used = 0
                var = 0.0
                for s in range(nS):
                    num[s] = 0.0
            if last:
                break
            cnt += 1
            dE = pos[r, 0] - tx[c, 0]
            dN = pos[r, 1] - tx[c, 1]
            dU = pos[r, 2] - tx[c, 2]
            R1 = np.sqrt(dE * dE + dN * dN + dU * dU)
            dE /= R1
            dN /= R1
            dU /= R1
            vr1 = vel[r, 0] * dE + vel[r, 1] * dN + vel[r, 2] * dU
            fd = -(vr1 + vr2[r]) / lam
            g = (abs(vel[r, 0] - vr1 * dE) + abs(vel[r, 1] - vr1 * dN)) / (lam * R1)
            hh = min(h_min + 0.5 * step * g, h_max)
            af = abs(fd)
            lo = min(max(af - hh, f_lo), f_hi)
            hi = min(max(af + hh, f_lo), f_hi)
            if not (af + hh >= f_lo and af - hh <= f_hi and hi > lo):
                continue
            if fd < 0:
                fa, fb = -hi, -lo
            else:
                fa, fb = lo, hi
            j1 = int(np.rint((fa - f0) / df))
            j2 = int(np.rint((fb - f0) / df))
            n = j2 - j1 + 1
            used += 1
            var += v_tab[min(n, len(v_tab) - 1)]
            i = idx[r]
            inv = 1.0 / n
            for s in range(nS):
                a = j1 + shifts[s]
                e = j2 + 1 + shifts[s]
                if a >= 0 and e <= nf:
                    num[s] += (CU[i, e] - CU[i, a]) * inv
    return nfull


@njit(cache=True, fastmath=True)
def _best_path(E, w, path):
    """Largest sum along a path that moves at most w shifts per block. Fills `path` (shift index per block)."""
    nb, nS = E.shape
    M = np.empty((nb, nS))
    arg = np.zeros((nb, nS), np.int32)
    for s in range(nS):
        M[0, s] = E[0, s]
    for b in range(1, nb):
        for s in range(nS):
            best = -1e300
            bi = s
            for q in range(max(0, s - w), min(nS, s + w + 1)):
                if M[b - 1, q] > best:
                    best = M[b - 1, q]
                    bi = q
            M[b, s] = E[b, s] + best
            arg[b, s] = bi
    s = 0
    for q in range(nS):
        if M[nb - 1, q] > M[nb - 1, s]:
            s = q
    top = M[nb - 1, s]
    for b in range(nb - 1, -1, -1):
        path[b] = s
        s = arg[b, s]
    return top


@njit(parallel=True, cache=True, fastmath=True)
def _scan(tx, CU, idx, pos, vel, vr2, gb, ac_off, shifts, v_tab, nblocks,
          f0, df, lam, f_lo, f_hi, h_min, h_max, step, w, out, nfull):
    for c in prange(len(tx)):
        E = np.zeros((nblocks, len(shifts)))
        path = np.zeros(nblocks, np.int32)
        nfull[c] = _evidence(c, tx, CU, idx, pos, vel, vr2, gb, ac_off, shifts, v_tab, nblocks,
                             f0, df, lam, f_lo, f_hi, h_min, h_max, step, E)
        out[c] = _best_path(E, w, path)


class Blind:
    """Evidence for transmitter positions when the carrier frequency path is unknown.

    shift_hz     the range of f0 to try (relative to 0 Hz on the waterfall's frequency axis)
    shift_step   spacing of the tried f0 values, in frequency bins
    max_step     how many spacings f0 may move from one block to the next
    """

    def __init__(self, t, f, W, paths, rx, lam, shift_hz=(-30.0, 30.0), shift_step=2, max_step=2, block_s=15.0,
                 f_lo=3.0, f_hi=140.0, dt=0.0, tx_h=85.0, cap=10.0, h_min=0.5, h_max=25.0, stride=1):
        self.t = np.asarray(t, float)[::stride]
        self.f = np.asarray(f, float)
        self.df = float(self.f[1] - self.f[0])
        self.rx = np.asarray(rx, float)
        self.lam, self.f_lo, self.f_hi, self.tx_h = float(lam), f_lo, f_hi, tx_h
        self.h_min, self.h_max, self.block_s, self.w = h_min, h_max, block_s, int(max_step)
        self.paths = paths
        s0, s1 = int(np.floor(shift_hz[0] / self.df)), int(np.ceil(shift_hz[1] / self.df))
        self.shifts = np.arange(s0, s1 + 1, shift_step).astype(np.int64)
        u = np.minimum(np.asarray(W)[::stride] * _field.LN2, cap).astype(np.float64)
        u = (u - u.mean(axis=0, keepdims=True)) / u.std()
        K = 24
        r = np.array([1.0] + [float((u[:, :-k] * u[:, k:]).mean()) for k in range(1, K + 1)])
        r = np.clip(r, 0.0, 1.0)
        nmax = int(2 * h_max / self.df) + 8
        v = np.empty(nmax + 1)
        v[0] = 1.0
        for n in range(1, nmax + 1):
            k = np.arange(1, min(n - 1, K) + 1)
            v[n] = (n + 2.0 * ((n - k) * r[k]).sum()) / n ** 2
        self.v = v
        self.CU = np.ascontiguousarray(np.concatenate([np.zeros((len(u), 1)), np.cumsum(u, axis=1)], axis=1))
        self.nblocks = int(np.floor((self.t[-1] - self.t[0]) / block_s)) + 1
        self.set_dt(dt)

    def set_dt(self, dt, dt_ac=None):
        """dt is added to the frame times before looking up aircraft states (dt_ac: extra, per aircraft)."""
        self.dt = dt
        idx, pos, vel, vr2, gb, off = [], [], [], [], [], [0]
        self.hexes = []
        for h, p in self.paths.items():
            tq = self.t + dt + (dt_ac.get(h, 0.0) if dt_ac else 0.0)
            ok = p.valid(tq)
            if ok.sum() < 4:
                continue
            ii = np.where(ok)[0]
            ps, vl = p.pos(tq[ii]), p.vel(tq[ii])
            d2 = ps - self.rx
            R2 = np.sqrt((d2 ** 2).sum(1))
            idx.append(ii)
            pos.append(ps)
            vel.append(vl)
            vr2.append((vl * d2).sum(1) / R2)
            gb.append(np.floor((self.t[ii] - self.t[0]) / self.block_s).astype(np.int64))
            off.append(off[-1] + len(ii))
            self.hexes.append(h)
        self.idx = np.concatenate(idx).astype(np.int64)
        self.pos = np.ascontiguousarray(np.concatenate(pos), np.float64)
        self.vel = np.ascontiguousarray(np.concatenate(vel), np.float64)
        self.vr2 = np.concatenate(vr2).astype(np.float64)
        self.gb = np.concatenate(gb).astype(np.int64)
        self.off = np.array(off, np.int64)

    def _args(self, step):
        return (self.CU, self.idx, self.pos, self.vel, self.vr2, self.gb, self.off, self.shifts, self.v, self.nblocks,
                float(self.f[0]), self.df, self.lam, self.f_lo, self.f_hi, self.h_min, self.h_max, float(step))

    def score(self, tx, step):
        tx = np.ascontiguousarray(np.atleast_2d(tx), np.float64)
        out, nfull = np.zeros(len(tx)), np.zeros(len(tx), np.int64)
        _scan(tx, *self._args(step), self.w, out, nfull)
        return out / np.sqrt(PHI_VAR * max(float(np.median(nfull)), 1.0))

    def grid(self, centre, half, step):
        e = np.arange(centre[0] - half, centre[0] + half + step / 2, step)
        n = np.arange(centre[1] - half, centre[1] + half + step / 2, step)
        E, N = np.meshgrid(e, n)
        tx = np.stack([E.ravel(), N.ravel(), np.full(E.size, self.tx_h)], axis=1)
        return e, n, self.score(tx, step).reshape(E.shape)

    def path(self, tx, step=20.0):
        """Best frequency path for one position: (block mid times, f0 in Hz, evidence along the path)."""
        tx = np.ascontiguousarray(np.atleast_2d(tx), np.float64)
        E = np.zeros((self.nblocks, len(self.shifts)))
        _evidence(0, tx, *self._args(step), E)
        path = np.zeros(self.nblocks, np.int32)
        top = _best_path(E, self.w, path)
        tm = self.t[0] + (np.arange(self.nblocks) + 0.5) * self.block_s
        return tm, self.shifts[path] * self.df, E[np.arange(self.nblocks), path], float(top)


def recentre(t, f, W, tm, f0):
    """Slide every frame so that the frequency path (tm, f0) ends up at 0 Hz."""
    df = float(f[1] - f[0])
    s = np.rint(np.interp(t, tm, f0) / df).astype(int)
    out = np.full_like(W, 1.0 / _field.LN2)
    nf = W.shape[1]
    for sh in np.unique(s):
        rows = np.where(s == sh)[0]
        if sh >= 0:
            out[rows, :nf - sh] = W[rows, sh:]
        else:
            out[rows, -sh:] = W[rows, :nf + sh]
    return out


def smooth_path(tm, f0, ev, tau=60.0, cap=30.0, rounds=4):
    """A smooth curve through the path that the search found.

    The found path jumps about where there is little evidence, and is pulled aside where one
    aircraft's clock is off. The curve follows each block by its evidence (up to `cap`), cannot
    bend faster than about `tau` seconds, and counts blocks that sit far off it less and less.
    """
    f0 = np.asarray(f0, float)
    w0 = np.clip(np.asarray(ev, float), 0.0, cap)
    n = len(f0)
    if (w0 > 0).sum() < 4:
        return f0.copy()
    D = np.diff(np.eye(n), 2, axis=0)
    pen = float(np.median(w0[w0 > 0])) * (tau / float(tm[1] - tm[0])) ** 4 * (D.T @ D)
    w = w0.copy()
    z = f0
    for _ in range(rounds):
        z = np.linalg.solve(np.diag(w + 1e-9) + pen, w * f0)
        r = f0 - z
        s = 1.4826 * float(np.median(np.abs(r[w0 > 0]))) + 0.15
        w = w0 / (1.0 + (r / (2.0 * s)) ** 2)
    return z


def search(t, f, W, paths, rx, lam, tx_h=85.0, span=30e3, step=500.0, k_peaks=3, shift_hz=(-30.0, 30.0),
           block_s=15.0, max_step=2, rounds=3, tau=60.0, dt0=0.2, verbose=False):
    """Wide grid with unknown frequency path, then position and path are tightened in turn.

    1. Wide grid: for each spot, the best frequency path and the evidence along it.
    2. For each of the best few spots: read off the path, smooth it, slide the waterfall so the
       path sits at 0 Hz, and run the ordinary search near the spot (it also tunes the clocks).
       Then look again for what is left of the path (within 1.5 Hz), and repeat.
    Returns dict(cands=[(score, E, N, dt)], paths=[(tm, f0)], wide=(e, n, map), z_map).
    """
    bl = Blind(t, f, W, paths, rx, lam, shift_hz=shift_hz, block_s=block_s, max_step=max_step, tx_h=tx_h, stride=2,
               dt=dt0)
    eA, nA, mA = bl.grid((0.0, 0.0), span, step)
    med = float(np.median(mA))
    spread = float(1.4826 * np.median(np.abs(mA - med))) + 1e-9
    fine = Blind(t, f, W, paths, rx, lam, shift_hz=shift_hz, shift_step=1, max_step=2 * max_step, block_s=block_s,
                 tx_h=tx_h, dt=dt0)
    out, fpaths = [], []
    for val, e0, n0 in _field.peaks(eA, nA, mA, k=k_peaks):
        eB, nB, mB = bl.grid((e0, n0), 1.5 * step, step / 5.0)
        i, j = np.unravel_index(np.argmax(mB), mB.shape)
        x = np.array([eB[j], nB[i], tx_h])
        tm, f0, ev, top = fine.path(x, step / 5.0)
        f0s = smooth_path(tm, f0, ev, tau=tau)
        r = None
        for k in range(rounds):
            W2 = recentre(t, f, W, tm, f0s)
            r = _field.search(t, f, W2, paths, rx, lam, tx_h=tx_h, span=3.0 * step, step=step / 5.0, k_peaks=2,
                              centre=(x[0], x[1]))
            x = np.array([r["cands"][0][1], r["cands"][0][2], tx_h])
            if k == rounds - 1:
                break
            # what is left of the path, now with the clocks the ordinary search settled on
            res = Blind(t, f, W2, paths, rx, lam, shift_hz=(-1.5, 1.5), shift_step=1, max_step=1, block_s=block_s,
                        tx_h=tx_h, dt=r["dt"])
            res.set_dt(r["dt"], r["clocks"][0])
            _, d0, ev, _ = res.path(x, 20.0)
            f0s = f0s + smooth_path(tm, d0, ev, tau=tau)
        if verbose:
            print(f"  wide peak {val:6.1f} at E {e0:7.0f} N {n0:7.0f} -> {r['cands'][0][0]:6.1f} at E {x[0]:7.0f} N {x[1]:7.0f}", flush=True)
        out.append(r["cands"][0])
        fpaths.append((tm, f0s))
    order = np.argsort([-c[0] for c in out])
    return dict(cands=[out[i] for i in order], paths=[fpaths[i] for i in order], wide=(eA, nA, mA),
                z_map=float((mA.max() - med) / spread))
