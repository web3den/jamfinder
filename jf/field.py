"""Matched-field search that also works when no single line is visible.

For a candidate transmitter position, every aircraft has a predicted Doppler
track through the waterfall. We add up the (noise-normalised) power found
along all those tracks. Nothing is thresholded, so lines far below the noise
in any one cell still add up over hundreds of cells.

Three details matter:
  * the box around each predicted track is as wide as the Doppler can change
    within one grid step, so close passes (which move tens of Hz per km of
    transmitter shift) are not missed by a coarse grid;
  * power is first added up in blocks of ~30 s per aircraft, and each block
    then counts by how far it stands above its own noise (squared when small,
    linear when large). Blocks with nothing in them add almost nothing, so no
    model of echo strength is needed. Measured echo strength is 20 dB or more
    off the radar equation here (the receiver's view of the sky is much
    clearer than its view of the transmitter), so a model would mislead;
  * each cell is capped, so one bright crossing line cannot fake a peak.
The result is in units of its own noise spread: about 0 +- 1 away from the transmitter.
"""
import numpy as np

LN2 = float(np.log(2.0))
Z0 = 4.0


def _phi(z):
    """Block evidence: z^2 for small z, linear beyond Z0, nothing for negative z."""
    z = np.maximum(z, 0.0)
    return np.where(z < Z0, z * z, 2 * Z0 * z - Z0 * Z0)


_zz = np.linspace(-8, 8, 16001)
_pz = np.exp(-0.5 * _zz ** 2) / np.sqrt(2 * np.pi)
PHI_MEAN = float(np.sum(_phi(_zz) * _pz) * (_zz[1] - _zz[0]))
PHI_VAR = float(np.sum(_phi(_zz) ** 2 * _pz) * (_zz[1] - _zz[0]) - PHI_MEAN ** 2)

# Matched weights of weight="pass": the relative shape of the echo-power law of
# sim/synth.py (1/(R1 R2)^2 with the product floored at 1e4 m^2, receiver sky mask, aspect), without its absolute
# level and without the size factor (constant within one aircraft). tests/test_levers_l1.py checks these against
# sim.synth.sky_mask_db and sim.synth.aspect_db.
SKY_PLATEAU_DEG = 8.0
ASPECT_DEPTH_DB = -12.0
W_FLOOR = 1e-3          # weights are floored at this fraction of the aircraft's largest
MIN_PASS_FRAMES = 4     # an aircraft counts in weight="pass" when at least this many frames are in band
ASPECT_LN = ASPECT_DEPTH_DB * np.log(10.0) / 10.0     # 10^(depth c^2 / 10) = exp(ASPECT_LN c^2)


def _sky_db(el_deg):
    """Receiver gain towards an aircraft at this elevation (dB): sim.synth.sky_mask_db with its 8-degree plateau."""
    el = np.radians(np.maximum(np.asarray(el_deg, float), 0.05))
    return np.minimum(0.0, 20 * np.log10(np.sin(el) / np.sin(np.radians(SKY_PLATEAU_DEG))))


def matched_power(R1, R2, cos12, vb, vnorm2, sky_lin):
    """Predicted relative echo power of weight="pass" (no absolute level): sim.synth's law without K and size,
    10^((-20 log10(max(R1 R2, 1e4)) + sky_mask_db + aspect_db) / 10).

    R1, R2   transmitter-aircraft and aircraft-receiver distances
    cos12    u1 . u2 (unit vectors from transmitter and from receiver to the aircraft)
    vb       v . (u1 + u2) = -lam f_d (only its square enters: |v . b| with b = -(u1 + u2))
    vnorm2   |v|^2
    sky_lin  10^(sky_mask_db(elevation seen from the receiver) / 10)
    The aspect term uses c^2 = (v . b)^2 / (|b|^2 |v|^2) with |b|^2 = 2 + 2 u1 . u2."""
    c2 = np.minimum(vb * vb / np.maximum((2.0 + 2.0 * cos12) * vnorm2, 1e-18), 1.0)
    return sky_lin * np.exp(ASPECT_LN * c2) / np.maximum(R1 * R2, 1e4) ** 2


class Field:
    def __init__(self, t, f, W, paths, rx, lam, f_lo=3.0, f_hi=140.0, dt=0.0, tx_h=85.0, cap=10.0,
                 weight="blocks", r_min=300.0, h_min=0.5, h_max=25.0, folded=False, stride=1, block_s=30.0, rho=None):
        self.t = np.asarray(t, float)[::stride]
        self.f = np.asarray(f, float)
        self.df = float(self.f[1] - self.f[0])
        self.rx = np.asarray(rx, float)
        self.lam, self.f_lo, self.f_hi, self.tx_h = lam, f_lo, f_hi, tx_h
        self.weight, self.r_min, self.h_min, self.h_max, self.folded = weight, r_min, h_min, h_max, folded
        if weight == "multi":
            # T_multi = (T_blocks + T_pass) / sqrt(2 + 2 rho), rho measured on pure noise
            rho = STATISTICS["multi"].get("rho") if rho is None else rho
            if rho is None:
                raise ValueError("weight='multi' needs rho (the pure-noise correlation of T_blocks and T_pass)")
            self.rho = float(rho)
        self.paths = paths
        self.block_s = block_s
        u = np.minimum(np.asarray(W)[::stride] * LN2, cap).astype(np.float64)
        band = (np.abs(self.f) >= f_lo) & (np.abs(self.f) <= f_hi)
        mu = u[:, band].mean(axis=0, keepdims=True)
        full = np.ones((1, len(self.f)))
        full[:, band] = mu
        u = (u - full) / u[:, band].std()
        # how alike neighbouring bins are (window overlap), for the noise of a box average
        K = 24
        ub = u[:, band]
        r = np.array([1.0] + [float((ub[:, :-k] * ub[:, k:]).mean()) for k in range(1, K + 1)])
        r = np.clip(r, 0.0, 1.0)
        nmax = int(2 * h_max / self.df) + 8
        v = np.empty(nmax + 1)
        v[0] = 1.0
        for n in range(1, nmax + 1):
            k = np.arange(1, min(n - 1, K) + 1)
            v[n] = (n + 2.0 * ((n - k) * r[k]).sum()) / n ** 2
        self.v = v
        self.CU = np.concatenate([np.zeros((len(u), 1)), np.cumsum(u, axis=1)], axis=1)
        self.set_dt(dt)

    def set_dt(self, dt, dt_ac=None):
        """dt is added to the frame times before looking up aircraft states."""
        self.dt = dt
        self.ac = []
        for h, p in self.paths.items():
            tq = self.t + dt + (dt_ac.get(h, 0.0) if dt_ac else 0.0)
            ok = p.valid(tq)
            if ok.sum() < 4:
                continue
            idx = np.where(ok)[0]
            pos, vel = p.pos(tq[idx]), p.vel(tq[idx])
            b = np.floor((self.t[idx] - self.t[0]) / self.block_s).astype(int)
            b -= b.min()
            ind = np.zeros((len(idx), b.max() + 1))
            ind[np.arange(len(idx)), b] = 1.0
            self.ac.append((h, idx, pos.astype(np.float32), vel.astype(np.float32), ind))

    def score(self, tx, step, rx=None, per_aircraft=False, chunk=256):
        """tx: (G, 3) candidates; step: grid spacing in metres (sets the box width).

        Returns the statistic (G,), and with per_aircraft a dict hex -> (numerator, noise variance).
        """
        tx = np.atleast_2d(np.asarray(tx, np.float32))
        rx = (self.rx if rx is None else np.asarray(rx, float)).astype(np.float32)
        G = len(tx)
        num, den = np.zeros(G), np.zeros(G)
        per = {}
        f0, df, lam = self.f[0], self.df, np.float32(self.lam)
        nf = len(self.f)
        matched = self.weight in ("pass", "multi")
        if matched:
            p_tot, pd_tot = np.zeros(G), np.zeros(G)     # the pass-level part (for "multi"; "pass" uses num/den)
        for h, idx, pos, vel, ind in self.ac:
            d2 = pos - rx
            R2 = np.sqrt((d2 ** 2).sum(1))
            vr2 = (vel * d2).sum(1) / R2
            w2 = 1.0 / np.maximum(R2, self.r_min) ** 2
            a_num, a_den = np.zeros(G), np.zeros(G)
            if matched:
                # candidate-independent parts of the matched weights: receiver sky mask, receiver-side unit vector
                u2 = d2 / R2[:, None]
                sky_lin = (10.0 ** (_sky_db(np.degrees(np.arcsin(np.clip(d2[:, 2] / R2, -1.0, 1.0)))) / 10.0)).astype(np.float64)
                vnorm2 = (vel.astype(np.float64) ** 2).sum(1)
                p_num, p_den, a_z = np.zeros(G), np.zeros(G), np.zeros(G)
            for a in range(0, G, chunk):
                c = tx[a:a + chunk]
                dE = pos[None, :, 0] - c[:, None, 0]
                dN = pos[None, :, 1] - c[:, None, 1]
                dU = pos[None, :, 2] - c[:, None, 2]
                R1 = np.sqrt(dE * dE + dN * dN + dU * dU)
                dE /= R1
                dN /= R1
                dU /= R1
                vr1 = vel[None, :, 0] * dE + vel[None, :, 1] * dN + vel[None, :, 2] * dU
                fd = -(vr1 + vr2[None]) / lam
                g = (np.abs(vel[None, :, 0] - vr1 * dE) + np.abs(vel[None, :, 1] - vr1 * dN)) / (lam * R1)
                hh = np.minimum(self.h_min + 0.5 * step * g, self.h_max)
                af = np.abs(fd)
                lo = np.clip(af - hh, self.f_lo, self.f_hi)
                hi = np.clip(af + hh, self.f_lo, self.f_hi)
                use = (af + hh >= self.f_lo) & (af - hh <= self.f_hi) & (hi > lo)
                neg = (fd < 0) & (not self.folded)
                fa = np.where(neg, -hi, lo)
                fb = np.where(neg, -lo, hi)
                j1 = np.clip(np.rint((fa - f0) / df).astype(np.int64), 0, nf - 1)
                j2 = np.clip(np.rint((fb - f0) / df).astype(np.int64), 0, nf - 1)
                n = j2 - j1 + 1
                m = (self.CU[idx[None, :], j2 + 1] - self.CU[idx[None, :], j1]) / n
                vv = self.v[np.minimum(n, len(self.v) - 1)]
                if self.weight == "detail":
                    u_ = use.astype(np.float64)
                    zb = ((m * u_) @ ind) / np.sqrt((vv * u_) @ ind + 1e-30)
                    cnt = ind.sum(0)
                    for b in range(ind.shape[1]):
                        sel = ind[:, b] > 0
                        if cnt[b] > 0 and (u_[0] @ ind[:, b]) >= 0.5 * cnt[b]:
                            self._detail.append((h, float(self.t[idx[sel][0]]), float(zb[0, b]), float(np.median(af[0, sel])),
                                                 float(np.median(R1[0, sel])), float(np.median(R2[sel]))))
                    continue
                if matched:
                    # weight="pass": one matched-weight z per aircraft over its whole pass. w_i = predicted relative
                    # echo power (1/(R1 R2)^2, sky mask, aspect) normalised to the aircraft's largest in-band value,
                    # floored at W_FLOOR; z = sum w m / sqrt(sum w^2 v) over the in-band frames; evidence phi(z).
                    # Aspect as sim.synth.aspect_db: c = |v.b| / (|b| |v|), b = -(u1 + u2); here v.b = -(vr1 + vr2)
                    # = lam fd and |b|^2 = 2 + 2 u1.u2, so no extra vectors are needed.
                    cos12 = dE * u2[None, :, 0] + dN * u2[None, :, 1] + dU * u2[None, :, 2]
                    p_lin = matched_power(R1, R2[None, :], cos12, lam * fd, vnorm2[None, :], sky_lin[None, :])
                    pk = np.where(use, p_lin, 0.0).max(axis=1, keepdims=True)
                    wq = np.where(use, np.maximum(p_lin / np.maximum(pk, 1e-300), W_FLOOR), 0.0)
                    okp = use.sum(axis=1) >= MIN_PASS_FRAMES
                    zp = np.where(okp, (wq * m).sum(1) / np.sqrt((wq * wq * vv).sum(1) + 1e-30), 0.0)
                    a_z[a:a + chunk] = zp
                    if self.weight == "pass":
                        a_num[a:a + chunk] = np.where(okp, _phi(zp), 0.0)
                        a_den[a:a + chunk] = okp
                        continue
                    p_num[a:a + chunk] = np.where(okp, _phi(zp), 0.0)
                    p_den[a:a + chunk] = okp
                    # weight="multi": the block part exactly as weight="blocks" below
                    u_ = use.astype(np.float64)
                    zb = ((m * u_) @ ind) / np.sqrt((vv * u_) @ ind + 1e-30)
                    cnt = ind.sum(0)[None, :]
                    full = (cnt > 0) & ((u_ @ ind) >= 0.5 * cnt)
                    a_num[a:a + chunk] = (_phi(zb) * full).sum(1)
                    a_den[a:a + chunk] = full.sum(1)
                    continue
                if self.weight == "blocks":
                    u_ = use.astype(np.float64)
                    zb = ((m * u_) @ ind) / np.sqrt((vv * u_) @ ind + 1e-30)
                    cnt = ind.sum(0)[None, :]
                    full = (cnt > 0) & ((u_ @ ind) >= 0.5 * cnt)   # blocks at least half in band
                    a_num[a:a + chunk] = (_phi(zb) * full).sum(1)
                    a_den[a:a + chunk] = full.sum(1)
                    continue
                if self.weight == "radar":
                    rho = w2[None, :] / np.maximum(R1, self.r_min) ** 2 * 6.25e14  # = 1 at 5 km / 5 km
                elif self.weight == "rx":
                    rho = np.broadcast_to(w2[None, :] * 2.5e7, R1.shape)
                else:
                    rho = np.ones_like(R1)
                rho = np.where(use, rho, 0.0).astype(np.float64)
                a_num[a:a + chunk] = (rho * m).sum(1)
                a_den[a:a + chunk] = (rho * rho * vv).sum(1)
            num += a_num
            den += a_den
            if matched and self.weight == "multi":
                p_tot += p_num
                pd_tot += p_den
            if per_aircraft:
                if self.weight == "pass":
                    per[h] = (a_num, a_den, a_z)
                elif self.weight == "multi":
                    per[h] = (a_num, a_den, p_num, p_den, a_z)
                else:
                    per[h] = (a_num, a_den)
        if self.weight == "detail":
            return np.zeros(G)
        if self.weight == "blocks":
            # Evidence in excess of what noise alone gives, summed over blocks. It is NOT divided
            # by the number of blocks of each candidate: evidence should add up, and dividing
            # would punish the true spot for also predicting lines too weak to see.
            self.n_blocks = den
            self.n_units = den
            T = (num - PHI_MEAN * den) / np.sqrt(PHI_VAR * max(float(np.median(den)), 1.0))
        elif self.weight == "pass":
            # the same standardisation as "blocks", with one unit per aircraft counted at the candidate
            self.n_units = den
            T = (num - PHI_MEAN * den) / np.sqrt(PHI_VAR * max(float(np.median(den)), 1.0))
        elif self.weight == "multi":
            self.n_units = den
            self.n_units_pass = pd_tot
            self._norm_b = float(np.sqrt(PHI_VAR * max(float(np.median(den)), 1.0)))
            self._norm_p = float(np.sqrt(PHI_VAR * max(float(np.median(pd_tot)), 1.0)))
            Tb = (num - PHI_MEAN * den) / self._norm_b
            Tp = (p_tot - PHI_MEAN * pd_tot) / self._norm_p
            T = (Tb + Tp) / np.sqrt(2.0 + 2.0 * self.rho)
            self.T_parts = (Tb, Tp)
        else:
            T = num / np.sqrt(den + 1e-30)
        return (T, per) if per_aircraft else T

    def blocks(self, tx, step=20.0):
        """Block-by-block detail for one candidate: [(hex, t_start, z, median |f|, median R1, median R2)]."""
        keep, self.weight = self.weight, "detail"
        try:
            self._detail = []
            self.score(np.asarray(tx, float)[None], step)
            return self._detail
        finally:
            self.weight = keep

    def grid(self, centre, half, step):
        e = np.arange(centre[0] - half, centre[0] + half + step / 2, step)
        n = np.arange(centre[1] - half, centre[1] + half + step / 2, step)
        E, N = np.meshgrid(e, n)
        tx = np.stack([E.ravel(), N.ravel(), np.full(E.size, self.tx_h)], axis=1)
        return e, n, self.score(tx, step).reshape(E.shape)


def peaks(e, n, M, k=5, sep=3):
    """The k highest local maxima of a map, at least `sep` cells apart. Returns [(value, e, n)]."""
    from scipy import ndimage
    mx = ndimage.maximum_filter(M, size=2 * sep + 1, mode="nearest")
    ii, jj = np.where((M == mx) & np.isfinite(M))
    order = np.argsort(M[ii, jj])[::-1][:k]
    return [(float(M[ii[o], jj[o]]), float(e[jj[o]]), float(n[ii[o]])) for o in order]


def subcell(e, n, M):
    """Peak of a map refined by a parabola through the 3 x 3 cells around the maximum."""
    i, j = np.unravel_index(np.argmax(M), M.shape)
    if i in (0, M.shape[0] - 1) or j in (0, M.shape[1] - 1):
        return float(e[j]), float(n[i]), float(M[i, j])
    de = 0.5 * (M[i, j - 1] - M[i, j + 1]) / (M[i, j - 1] - 2 * M[i, j] + M[i, j + 1] - 1e-12)
    dn = 0.5 * (M[i - 1, j] - M[i + 1, j]) / (M[i - 1, j] - 2 * M[i, j] + M[i + 1, j] - 1e-12)
    de, dn = float(np.clip(de, -0.5, 0.5)), float(np.clip(dn, -0.5, 0.5))
    return float(e[j] + de * (e[1] - e[0])), float(n[i] + dn * (n[1] - n[0])), float(M[i, j])


def _aircraft_evidence(fld, per):
    """Per-aircraft evidence at one candidate, in the units tune_clocks compares: {hex: value}.

    blocks (and the unregistered linear modes): sum phi - PHI_MEAN x blocks, as always; pass: phi(z_k) - PHI_MEAN;
    multi: the aircraft's share of T_multi (both parts divided by their normalisations, then by sqrt(2 + 2 rho))."""
    if fld.weight == "multi":
        c = np.sqrt(2.0 + 2.0 * fld.rho)
        return {h: float(((a[0] - PHI_MEAN * b[0]) / fld._norm_b + (pa[0] - PHI_MEAN * pb[0]) / fld._norm_p) / c)
                for h, (a, b, pa, pb, _) in per.items()}
    return {h: float(v[0][0] - PHI_MEAN * v[1][0]) for h, v in per.items()}


def _clock_evidence(fld, tx, dt, offsets):
    tx = np.asarray(tx, float)[None]
    ex = {}
    for d in offsets:
        fld.set_dt(dt + d)
        _, per = fld.score(tx, 20.0, per_aircraft=True)
        for h, v in _aircraft_evidence(fld, per).items():
            ex.setdefault(h, {})[d] = v
    return ex


def tune_clocks(fld, tx, dt, offsets=(-0.6, -0.4, -0.2, 0.0, 0.2, 0.4, 0.6), min_gain=6.0):
    """Per-aircraft clock offsets at one candidate spot.

    Position reports reach the aggregator through different ground stations and
    carry different delays (tenths of a second). Near a close pass the Doppler
    moves 1-2 Hz per second, so a shared clock offset cannot centre every line.
    Each aircraft takes the offset that gives it the most evidence, but only when
    that beats the shared offset by `min_gain`; otherwise it keeps 0.
    """
    ex = _clock_evidence(fld, tx, dt, offsets)
    out = {}
    for h, e in ex.items():
        best = max(e, key=e.get)
        if best != 0.0 and e[best] - e.get(0.0, 0.0) >= min_gain:
            out[h] = best
    return out


def clock_gains(fld, tx, dt, offsets=(-0.6, -0.4, -0.2, 0.0, 0.2, 0.4, 0.6)):
    """What tune_clocks would gain per aircraft at one spot, whatever min_gain is: {hex: (best offset, gain)}, gain =
    evidence at the best offset minus evidence at offset 0 (0 when 0 is the best). For the L4 calibration of min_gain."""
    ex = _clock_evidence(fld, tx, dt, offsets)
    out = {}
    for h, e in ex.items():
        best = max(e, key=e.get)
        out[h] = (float(best), float(e[best] - e.get(0.0, 0.0)) if best != 0.0 else 0.0)
    return out


def search(t, f, W, paths, rx, lam, tx_h=85.0, span=30e3, step=500.0, folded=False, weight="blocks",
           f_hi=140.0, k_peaks=4, block_s=30.0, clocks=True, verbose=False, centre=(0.0, 0.0),
           stride_wide=2, min_gain=6.0, f_lo=3.0, rho=None):
    """Wide grid, then zoom on the best few peaks while scanning the clock offset.

    Returns dict(tx, dt, score, cands, z_map, mapA, mapC, field). `cands` lists every
    zoomed peak as (score, E, N, dt), best first: the runner-up is often the mirror
    image of the transmitter across a busy flight path.

    Further options (defaults = the baseline): stride_wide (frame stride of the wide
    grid), min_gain (tune_clocks), f_lo (lower band edge), rho (weight="multi"). Per-aircraft clocks are tuned for every
    registered statistic (STATISTICS), as before for "blocks".
    """
    kw = dict(tx_h=tx_h, folded=folded, weight=weight, f_hi=f_hi, block_s=block_s, f_lo=f_lo)
    if weight == "multi":
        kw["rho"] = rho
    fa = Field(t, f, W, paths, rx, lam, stride=stride_wide, **kw)
    eA, nA, mA = fa.grid(centre, span, step)
    units_A = getattr(fa, "n_units", None)
    med = float(np.median(mA))
    spread = float(1.4826 * np.median(np.abs(mA - med))) + 1e-9
    fb = Field(t, f, W, paths, rx, lam, **kw)
    stepC = step / 25.0
    cands = []
    for val, e0, n0 in peaks(eA, nA, mA, k=k_peaks):
        top = None
        for dt in (-1.0, -0.5, 0.0, 0.5, 1.0):
            fb.set_dt(dt)
            eB, nB, mB = fb.grid((e0, n0), 1.5 * step, step / 5.0)
            if top is None or mB.max() > top[0]:
                i, j = np.unravel_index(np.argmax(mB), mB.shape)
                top = (float(mB.max()), dt, float(eB[j]), float(nB[i]))
        _, dtB, e1, n1 = top
        fine = None
        for dt in np.arange(dtB - 0.4, dtB + 0.41, 0.1):
            fb.set_dt(dt)
            eC, nC, mC = fb.grid((e1, n1), 15 * stepC, stepC)
            if fine is None or mC.max() > fine[0]:
                fine = (float(mC.max()), float(dt), eC, nC, mC)
        sC, dtC, eC, nC, mC = fine
        e2, n2, _ = subcell(eC, nC, mC)
        dt_ac = {}
        if clocks and weight in STATISTICS:
            for _ in range(2):
                dt_ac = tune_clocks(fb, (e2, n2, tx_h), dtC, min_gain=min_gain)
                fb.set_dt(dtC, dt_ac)
                eC, nC, mC = fb.grid((e2, n2), 10 * stepC, stepC)
                e2, n2, sC = subcell(eC, nC, mC)
        cands.append((sC, e2, n2, dtC, (eC, nC, mC), dt_ac))
        if verbose:
            print(f"  wide peak {val:6.1f} at E {e0:7.0f} N {n0:7.0f} -> fine {sC:6.1f} at E {e2:7.0f} N {n2:7.0f} dt {dtC:+.1f}")
    cands.sort(key=lambda c: -c[0])
    sC, e2, n2, dtC, mapC, dt_ac = cands[0]
    fb.set_dt(dtC, dt_ac)
    return dict(tx=np.array([e2, n2, tx_h]), dt=dtC, score=sC, cands=[c[:4] for c in cands],
                clocks=[c[5] for c in cands],
                z_map=float((mA.max() - med) / spread), wide_peak=float(mA.max()), wide_spread=spread,
                mapA=(eA, nA, mA), mapC=mapC, field=fb,
                units_A=None if units_A is None else np.asarray(units_A).reshape(mA.shape))


THRESHOLD = 15.0   # the largest score seen with no echoes at all is about 8 (three runs)
TIE = 0.75
CLEAR = 1.6

# Registry of the statistics the search can use. "L4" is the name of the pure-noise calibration that measured the
# values below. Its tool and its records (the 'config' files named in the entries) are not part of this package.
# Per statistic:
#   norm_mean, norm_var  what the code subtracts and divides by, per unit (fixed by the definition; for "blocks" and
#                        "pass" the moments of phi(z) for z ~ N(0, 1); "multi" combines two standardised scores)
#   null_mean, null_var  the pure-noise mean and variance per unit as measured by the L4 procedure (until measured,
#                        the assumed values and measured=False)
#   threshold_v1         rule v1's threshold for this statistic (L4 step 1: twice the largest of 30 pure-noise maxima)
#   l4                   the L4 records per method name (constants, the 30 maxima, percentiles), or None
# The "blocks" path is the frozen baseline: its code and its use of THRESHOLD etc. are unchanged; its L4 entry records
# what the procedure measures for it. Unregistered weight modes ("radar", "rx", plain) are kept as they were.
# --- registry: begin (the L4 calibration tool wrote the measured values between these markers) ---
# Written from method_blocks_l4.json, method_blocks_s1k8.json, method_pass.json, method_multi.json, method_blocks_fhi200.json.
STATISTICS = {
    'blocks': dict(description='30-s blocks per aircraft, phi(z_b) summed over blocks, standardised with PHI_MEAN and PHI_VAR (the baseline statistic)',
                unit='block', norm_mean=PHI_MEAN, norm_var=PHI_VAR, null_mean=0.5472, null_var=2.133, measured=True, threshold_v1=23.1744, frozen_threshold=THRESHOLD,
                l4={'blocks_l4': {'config': 'results/oracle/method_blocks_l4.json', 'min_gain': 12.5525, 'threshold_v1': 23.1744, 'null_ratio': 2.5341, 'loo_max': 1.2671, 'support_min': 39.1723, 'support_ratio': 0.9503, 'null_mean': 0.5472, 'null_var': 2.133, 'maxima': [7.0796, 5.1731, 6.395, 6.904, 6.2294, 5.7667, 7.1911, 5.7303, 5.818, 7.7975, 7.8272, 6.0893, 7.5022, 7.1247, 5.275, 7.2699, 11.5872, 7.8581, 8.0783, 8.1686, 5.5517, 6.5988, 8.3244, 5.6141, 7.7565, 6.9223, 5.7808, 7.0069, 6.7383, 7.5613]}, 'blocks_s1k8': {'config': 'results/oracle/method_blocks_s1k8.json', 'min_gain': 12.1234, 'threshold_v1': 23.1744, 'null_ratio': 2.5115, 'loo_max': 1.2558, 'support_min': 47.8003, 'support_ratio': 0.9334, 'null_mean': 0.567, 'null_var': 1.9946, 'maxima': [7.0796, 7.0507, 7.141, 7.597, 6.1859, 7.8278, 7.6562, 8.5069, 8.0741, 7.7975, 7.8384, 7.2113, 7.4988, 7.9779, 7.7324, 7.2699, 11.5872, 7.945, 8.0783, 8.1804, 8.6577, 7.2603, 9.0024, 6.1448, 7.7565, 7.9862, 7.6213, 7.3312, 6.9503, 8.1274]}, 'blocks_fhi200': {'config': 'results/oracle/method_blocks_fhi200.json', 'min_gain': 13.3552, 'threshold_v1': 19.7057, 'null_ratio': 2.7225, 'loo_max': 1.3612, 'support_min': 33.2384, 'support_ratio': 0.9873, 'null_mean': 0.5475, 'null_var': 2.1204, 'maxima': [6.707, 5.1023, 5.6969, 6.865, 6.6372, 5.3495, 8.4021, 6.6206, 5.6287, 7.7836, 7.5939, 7.2473, 6.5972, 5.9215, 4.5978, 7.6748, 9.8529, 8.2368, 8.3502, 7.3143, 5.3071, 6.5933, 6.9947, 5.6863, 7.0853, 8.4332, 5.6728, 8.5092, 6.2447, 8.3898]}}),
    'pass': dict(description='one matched-weight z per aircraft over its whole pass (weights: predicted relative echo power, normalised within the aircraft), phi(z_k) summed over aircraft, standardised like blocks; support is z_k',
                unit='aircraft', norm_mean=PHI_MEAN, norm_var=PHI_VAR, null_mean=0.5396, null_var=1.65, measured=True, threshold_v1=30.5239,
                l4={'pass': {'config': 'results/oracle/method_pass.json', 'min_gain': 7.0701, 'threshold_v1': 30.5239, 'null_ratio': 2.8584, 'loo_max': 1.4292, 'support_min': 13.1676, 'support_ratio': 0.9451, 'null_mean': 0.5396, 'null_var': 1.65, 'maxima': [5.3676, 4.3291, 7.3372, 8.5553, 6.5651, 6.7277, 15.2619, 7.3035, 7.224, 10.201, 6.7892, 13.163, 7.4708, 7.8294, 7.8362, 6.7056, 7.9431, 7.3033, 9.3712, 6.6135, 5.2896, 7.1052, 7.1318, 8.1707, 7.863, 7.4223, 9.9424, 6.0065, 7.0885, 7.9479]}}),
    'multi': dict(description='(T_blocks + T_pass) / sqrt(2 + 2 rho), rho the pure-noise correlation of the two',
                unit='cell', norm_mean=0.0, norm_var=1.0, null_mean=0.655, null_var=1.5029, measured=True, threshold_v1=19.5782, rho=0.4006,
                l4={'multi': {'config': 'results/oracle/method_multi.json', 'min_gain': 0.8778, 'threshold_v1': 19.5782, 'null_ratio': 2.9146, 'loo_max': 1.4573, 'support_min': 30.5548, 'support_ratio': 0.9626, 'null_mean': 0.655, 'null_var': 1.5029, 'maxima': [5.4778, 4.6384, 8.0459, 7.3379, 5.9916, 5.895, 8.6439, 7.6457, 7.4305, 9.7891, 7.4434, 7.9782, 8.2554, 8.3482, 6.21, 7.1174, 7.6537, 7.9175, 6.4193, 7.6215, 6.8904, 7.0173, 7.1149, 5.6955, 8.9034, 6.9177, 9.1318, 7.0355, 5.8714, 8.1214]}}),
}
# --- registry: end ---


def verdict(cands, threshold=THRESHOLD, tie=TIE, clear=CLEAR):
    """What to report from the list of candidates (best first).

    One flight path fits two spots equally well (the transmitter and its mirror image across the
    path), so up to two candidates can be real. A third one nearly as good means the peaks are
    side effects of bright echoes, not a fix. Returns (label, kept): "nothing", "one" or "ambiguous".
    """
    if not cands or cands[0][0] < threshold:
        return "nothing", []
    if len(cands) >= 3 and cands[0][0] < clear * cands[2][0]:
        return "nothing", []
    kept = [c for c in cands[:2] if c[0] >= tie * cands[0][0]]
    return ("one" if len(kept) == 1 else "ambiguous"), kept


def support(fld, cand, clocks=None):
    """How strongly each aircraft backs one candidate, on its own: [(z, hex)], strongest first.

    z is that aircraft's evidence at the candidate in units of its own noise spread
    (about 0 +- 1 for an aircraft that shows nothing there).
    """
    fld.set_dt(cand[3], clocks)
    _, per = fld.score(np.array([[cand[1], cand[2], fld.tx_h]]), 20.0, per_aircraft=True)
    if fld.weight == "pass":
        # the per-aircraft matched z itself (plan L1: support returns the per-aircraft z for "pass" directly)
        out = [(float(v[2][0]), h) for h, v in per.items() if v[1][0] > 0]
    elif fld.weight == "multi":
        c = np.sqrt(2.0 + 2.0 * fld.rho)
        out = []
        for h, (a, b, pa, pb, z) in per.items():
            if b[0] <= 0 and pb[0] <= 0:
                continue
            sb = (a[0] - PHI_MEAN * b[0]) / np.sqrt(PHI_VAR * b[0]) if b[0] > 0 else 0.0
            sp = z[0] if pb[0] > 0 else 0.0
            out.append((float((sb + sp) / c), h))
    else:
        out = [(float((a[0] - PHI_MEAN * b[0]) / np.sqrt(PHI_VAR * b[0])), h) for h, (a, b) in per.items() if b[0] > 0]
    return sorted(out, reverse=True)


def mask_tracks(t, f, W, paths, rx, lam, cand, clocks=None, tx_h=85.0, half_hz=2.5):
    """Blank the echoes that one found transmitter explains, so that a second one can be searched for.

    Around every aircraft's predicted Doppler track for the transmitter at `cand` (score, E, N, dt)
    the waterfall is set to the plain noise level. If the transmitter explains all echoes, what
    is left gives no peaks any more: a check that needs no outside truth.
    """
    t = np.asarray(t, float)
    f = np.asarray(f, float)
    out = np.array(W, copy=True)
    tx = np.array([cand[1], cand[2], tx_h])
    rx = np.asarray(rx, float)
    for h, p in paths.items():
        tq = t + cand[3] + (clocks.get(h, 0.0) if clocks else 0.0)
        ok = np.where(p.valid(tq))[0]
        if len(ok) == 0:
            continue
        pos, vel = p.pos(tq[ok]), p.vel(tq[ok])
        d1, d2 = pos - tx, pos - rx
        fd = -((vel * d1).sum(1) / np.linalg.norm(d1, axis=1) + (vel * d2).sum(1) / np.linalg.norm(d2, axis=1)) / lam
        # the Doppler moves during one frame near a close pass: widen the blank by the change to the next frame
        wide = half_hz + np.abs(np.gradient(fd)) if len(fd) > 1 else np.full(len(fd), half_hz)
        hit = np.abs(f[None, :] - fd[:, None]) <= wide[:, None]
        rows = out[ok]
        rows[hit] = 1.0 / LN2
        out[ok] = rows
    return out
