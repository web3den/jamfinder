"""Aircraft tracks from readsb-style JSON snapshots, and predicted Doppler.

Positions say where the aircraft is; the reported velocity (ground speed,
track, vertical rate) is what sets the Doppler. Both go into one smooth fit.
"""
import gzip
import json
from collections import defaultdict

import numpy as np
from scipy.interpolate import BSpline

from . import geo

C = 299792458.0


def _num(v):
    return float(v) if isinstance(v, (int, float)) else np.nan


def _coarse(a):
    """1.0 when the report is not the aircraft's own GPS broadcast (multilateration, TIS-B, ...)."""
    return 0.0 if str(a.get("type", "")).startswith(("adsb", "adsr")) else 1.0


def read_lines(path):
    """Yield parsed JSON lines; stops quietly at a truncated tail (file still being written)."""
    with gzip.open(path, "rt") as f:
        while True:
            try:
                line = f.readline()
            except (EOFError, OSError):
                return
            if not line:
                return
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                return


def load_snapshots(path, vel_age=0.3):
    """Read a record_adsb.py file. Returns {hex: track dict}."""
    pos = defaultdict(dict)   # hex -> {(lat, lon): row}
    vel = defaultdict(list)
    info = {}
    for r in read_lines(path):
        now = r["now"] / 1000.0 if r["now"] > 1e11 else float(r["now"])
        for a in r.get("ac", []):
            h = a.get("hex")
            if h is None:
                continue
            ground = a.get("alt_baro") == "ground"
            if "lat" in a and "seen_pos" in a:
                key = (round(a["lat"], 6), round(a["lon"], 6))
                tp = now - a["seen_pos"]
                old = pos[h].get(key)
                if old is None or tp < old[0]:
                    pos[h][key] = (tp, a["lat"], a["lon"], _num(a.get("alt_geom")),
                                   np.nan if ground else _num(a.get("alt_baro")), float(ground), _coarse(a))
            if "gs" in a and ("track" in a or ground):
                trk = a.get("track", a.get("true_heading", np.nan))
                vr = 0.0 if ground else _num(a.get("geom_rate", a.get("baro_rate", np.nan)))
                if a.get("seen", 0.0) < 3.0 and np.isfinite(_num(trk)):
                    vel[h].append((now - vel_age, a["gs"] * geo.KT, float(trk),
                                   (0.0 if np.isnan(vr) else vr) * geo.FT / 60.0, _coarse(a)))
            info[h] = ((a.get("flight") or "").strip(), a.get("t", "?"), a.get("type", "?"))
    out = {}
    for h, d in pos.items():
        p = np.array(sorted(d.values()), dtype=float)
        v = np.array(vel.get(h, []), dtype=float).reshape(-1, 5)
        out[h] = dict(tp=p[:, 0], lat=p[:, 1], lon=p[:, 2], alt_geom=p[:, 3] * geo.FT,
                      alt_baro=p[:, 4] * geo.FT, ground=p[:, 5], p_coarse=p[:, 6],
                      tv=v[:, 0], gs=v[:, 1], track=v[:, 2], vrate=v[:, 3], v_coarse=v[:, 4],
                      flight=info[h][0], actype=info[h][1], src=info[h][2])
    return out


def baro_offset(tracks):
    """Median (geometric - barometric) height in metres over all aircraft that report both."""
    d = np.concatenate([tr["alt_geom"] - tr["alt_baro"] for tr in tracks.values()] or [np.zeros(0)])
    d = d[np.isfinite(d)]
    return float(np.median(d)) if len(d) else 0.0


class Path:
    """Smooth 3-D path of one aircraft in a local east-north-up frame.

    Cubic B-spline per axis, fitted to positions and to reported velocities
    at the same time, with a weak pull toward straight flight.
    """

    def __init__(self, tr, frame, ground_h=0.0, baro_off=0.0, knot_s=4.0,
                 sig_p=(25.0, 150.0), sig_v=(1.0, 5.0), max_gap=12.0):
        self.flight, self.actype, self.src = tr["flight"], tr["actype"], tr["src"]
        tp = tr["tp"]
        self.n = len(tp)
        self.ok = False
        if self.n < 5 or tp[-1] - tp[0] < 8.0:
            return
        alt = np.where(np.isfinite(tr["alt_geom"]), tr["alt_geom"], tr["alt_baro"] + baro_off)
        alt = np.where(tr["ground"] > 0, ground_h, alt)
        good = np.isfinite(alt)
        if good.sum() < 5:
            return
        tp, alt = tp[good], alt[good]
        P = frame.to_enu(tr["lat"][good], tr["lon"][good], alt)
        sp = np.where(tr["p_coarse"][good] > 0, sig_p[1], sig_p[0])
        self.tp = tp
        self.t0, self.t1 = float(tp[0]), float(tp[-1])
        self.max_gap = max_gap
        self.coarse = float(np.mean(tr["p_coarse"][good]))
        tv, gs = tr["tv"], tr["gs"]
        m = (tv >= self.t0) & (tv <= self.t1)
        if m.sum() >= 5:
            # throw out wild speed reports (they do happen on multilateration)
            pad = np.pad(gs[m], 4, mode="edge")
            med = np.median(np.lib.stride_tricks.sliding_window_view(pad, 9), axis=1)
            keep = np.abs(gs[m] - med) < np.maximum(12.0, 0.08 * med)
            idx = np.where(m)[0][keep]
        else:
            idx = np.where(m)[0]
        tv = tv[idx]
        th = np.radians(tr["track"][idx])
        V = np.stack([tr["gs"][idx] * np.sin(th), tr["gs"][idx] * np.cos(th), tr["vrate"][idx]], axis=1)
        sv = np.where(tr["v_coarse"][idx] > 0, sig_v[1], sig_v[0])
        # ENU axes turn slowly with distance from the origin; over 100 km that is under 1 degree.
        k = 3
        n_int = max(1, int(np.ceil((self.t1 - self.t0) / knot_s)))
        inner = np.linspace(self.t0, self.t1, n_int + 1)
        kn = np.r_[[self.t0] * k, inner, [self.t1] * k]
        nb = len(kn) - k - 1
        Bp = BSpline.design_matrix(tp, kn, k).toarray()
        basis = BSpline(kn, np.eye(nb), k)
        Bv = basis.derivative()(tv) if len(tv) else np.zeros((0, nb))
        D2 = np.diff(np.eye(nb), 2, axis=0) / (inner[1] - inner[0]) ** 2 / 3.0 if nb > 2 else np.zeros((0, nb))
        # pass 0 uses positions only, to find and drop velocity reports that contradict the path
        wp, wv = 1.0 / sp, np.zeros(len(tv))
        coef = None
        for it in range(4):
            A = np.vstack([Bp * wp[:, None], Bv * wv[:, None], D2])
            b = np.vstack([P * wp[:, None], V * wv[:, None], np.zeros((len(D2), 3))])
            coef, *_ = np.linalg.lstsq(A, b, rcond=None)
            rp = np.linalg.norm(Bp @ coef - P, axis=1) / sp
            dv = np.linalg.norm(Bv @ coef - V, axis=1) if len(tv) else np.zeros(0)
            wp = np.where(rp > 2.5, 2.5 / np.maximum(rp, 1e-9), 1.0) / sp
            if it == 0:
                bad_v = dv > np.maximum(20.0, 12.0 * sv)
            rv = dv / sv
            wv = np.where(bad_v, 0.0, np.where(rv > 2.5, 2.5 / np.maximum(rv, 1e-9), 1.0) / sv)
        self.n_bad_v = int(bad_v.sum()) if len(tv) else 0
        self.sp = BSpline(kn, coef, k)
        self.sv = self.sp.derivative()
        self.res_p = float(np.sqrt(np.mean(np.sum((Bp @ coef - P) ** 2, axis=1))))
        gv = ~bad_v if len(tv) else np.zeros(0, bool)
        self.res_v = float(np.sqrt(np.mean(np.sum((Bv[gv] @ coef - V[gv]) ** 2, axis=1)))) if gv.any() else np.nan
        self.ok = True

    def valid(self, t):
        """True where t lies inside the track and close enough to real position reports."""
        t = np.asarray(t, float)
        i = np.clip(np.searchsorted(self.tp, t), 1, len(self.tp) - 1)
        gap = self.tp[i] - self.tp[i - 1]
        return (t >= self.t0) & (t <= self.t1) & (gap <= self.max_gap)

    def pos(self, t):
        return self.sp(np.clip(np.asarray(t, float), self.t0, self.t1))

    def vel(self, t):
        return self.sv(np.clip(np.asarray(t, float), self.t0, self.t1))

    def doppler(self, t, tx, rx, lam):
        """Shift of the aircraft-scattered copy relative to the direct signal (Hz).

        tx may be one point (3,) or many (G, 3); the result is (T,) or (G, T).
        """
        p, v = self.pos(t), self.vel(t)
        return doppler_pv(p, v, tx, rx, lam)

    def ranges(self, t, tx, rx):
        p = self.pos(t)
        return np.linalg.norm(p - tx, axis=-1), np.linalg.norm(p - rx, axis=-1)


def doppler_pv(p, v, tx, rx, lam):
    tx = np.asarray(tx, float)
    u_rx = p - rx
    u_rx = u_rx / np.linalg.norm(u_rx, axis=-1, keepdims=True)
    f_rx = np.sum(v * u_rx, axis=-1)
    d = p - tx[:, None, :] if tx.ndim > 1 else p - tx
    r = np.linalg.norm(d, axis=-1)
    f_tx = np.einsum("...tk,tk->...t", d, v) / r
    return -(f_rx + f_tx) / lam


def load_paths(path, frame, ground_h=0.0, **kw):
    trs = load_snapshots(path)
    off = baro_offset(trs)
    out = {}
    for h, tr in trs.items():
        p = Path(tr, frame, ground_h=ground_h, baro_off=off, **kw)
        if p.ok:
            out[h] = p
    return out, off
