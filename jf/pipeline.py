"""The whole fix as two calls: blind grid search, then least squares on measured lines."""
import numpy as np

from . import locate, ridge, scatter


def blind_search(t, f, W, paths, rx, lam, tx_h=85.0, span=30e3, step=500.0, folded=False, verbose=False):
    """Coarse grid, fine grid with a clock scan, simplex polish. Returns dict."""
    df = float(f[1] - f[0])
    scA = scatter.score_matrix(W, blur_bins=int(round(2.0 / df)))
    pr = locate.Problem(t, f, scA, paths, rx, lam, tx_h=tx_h, folded=folded)
    eA, nA, mA = pr.grid((-span, span), (-span, span), step)
    i, j = np.unravel_index(np.argmax(mA), mA.shape)
    pk = np.array([eA[j], nA[i]])
    scB = scatter.score_matrix(W, blur_bins=int(round(0.5 / df)))
    prB = locate.Problem(t, f, scB, paths, rx, lam, tx_h=tx_h, folded=folded)
    best = None
    for dt in np.arange(-2.0, 2.01, 0.5):
        prB.set_dt(dt)
        eB, nB, mB = prB.grid((pk[0] - 3000, pk[0] + 3000), (pk[1] - 3000, pk[1] + 3000), 100.0)
        if best is None or mB.max() > best[0]:
            i, j = np.unravel_index(np.argmax(mB), mB.shape)
            best = (float(mB.max()), float(dt), eB[j], nB[i], eB, nB, mB)
    _, dtB, e0, n0, eB, nB, mB = best
    prB.set_dt(dtB)
    tx, dt, _, sc = prB.refine([e0, n0], fit_dt=True, fit_rx=False)
    z = (mA.max() - np.median(mA)) / (1.4826 * np.median(np.abs(mA - np.median(mA))) + 1e-9)
    if verbose:
        print(f"  grid peak E {pk[0]:.0f} N {pk[1]:.0f} (z {z:.1f}); fine E {tx[0]:.0f} N {tx[1]:.0f} dt {dt:+.2f}")
    return dict(tx=tx, dt=float(dt), score=float(sc), peak_z=float(z), mapA=(eA, nA, mA), mapB=(eB, nB, mB), n_ac=len(pr.ac))


def precise_fix(t, f, W, paths, rx, lam, tx0, dt0=0.0, tx_h=85.0, fit_rx=True, rx_prior=0.0, fit_dt_ac=False,
                min_db=9.0, folded=False, min_points=12, verbose=False):
    """Measure the lines near the current guess, solve, repeat with a tighter window."""
    tx = np.array([tx0[0], tx0[1], tx_h], float)
    rx0 = np.asarray(rx, float)
    rxe, dt, dt_ac = rx0.copy(), dt0, None
    fit = res = meas = None
    for half in (5.0, 3.0, 2.0, 2.0):
        meas = ridge.extract(t, f, W, paths, tx, rxe, lam, dt=dt, dt_ac=dt_ac, half_hz=half, min_db=min_db, folded=folded)
        meas = [m for m in meas if len(m["f"]) >= min_points]
        if not meas:
            return None
        fit = ridge.Fit(meas, paths, lam, tx_h, rx0, fit_rx=fit_rx, fit_dt=True, fit_dt_ac=fit_dt_ac,
                        rx_prior=rx_prior, folded=folded)
        x0 = fit.x0(tx, dt)
        if fit_rx:
            x0[2:4] = rxe[:2]
        res = fit.solve(x0)
        txn, rxe, dt, dta = fit.unpack(res.x)
        dt_ac = {m["hex"]: float(d) for m, d in zip(meas, dta)} if fit_dt_ac else None
        if verbose:
            n = sum(len(m["f"]) for m in meas)
            print(f"  window ±{half:.0f} Hz: {len(meas)} aircraft, {n} points -> tx E {txn[0]:.0f} N {txn[1]:.0f}  "
                  f"rx E {rxe[0]:.0f} N {rxe[1]:.0f}  dt {dt:+.2f} s")
        tx = txn
    return dict(tx=tx, rx=rxe, dt=float(dt), fit=fit, res=res, meas=meas,
                n_points=int(sum(len(m["f"]) for m in meas)), n_ac=len(meas))


def jackknife(fix, min_points=40):
    """Leave one aircraft out at a time. Returns (shifts[k, 2], names)."""
    fit, res, meas = fix["fit"], fix["res"], fix["meas"]
    if fit.fit_dt_ac:
        raise NotImplementedError
    out, names = [], []
    for k, m in enumerate(meas):
        if len(m["f"]) < min_points:
            continue
        keep = [i != k for i in range(len(meas))]
        r2 = fit.solve(res.x, keep=keep)
        out.append(fit.unpack(r2.x)[0][:2] - fix["tx"][:2])
        names.append(m["hex"])
    return np.array(out).reshape(-1, 2), names
