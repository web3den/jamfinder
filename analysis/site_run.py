#!/usr/bin/env python3
"""Search at a site where we do not know where the transmitter is.

1. Ordinary search with the receiver at its listed position. The verdict comes from this run.
2. If something was found: fit the receiver position together with the transmitter position
   (a listed receiver position is often only roughly right), and search once more.
Prints spots as east/north of the listed receiver position and as latitude/longitude, and which
aircraft carry the evidence. Writes results/<name>_fix.json. Nothing in here uses a "true" position.

usage: site_run.py name iq_prefix adsb rx_lat rx_lon freq [rx_h=45 tx_h=85 ground_h=73 car_lo= car_hi=
                   t_max= (only the first so many seconds)  rxfit=1 (2: also when nothing was found)
                   rx_half=1000 rx_step=50 span=30000
                   rx_e=0 rx_n=0 cache=1 out=]
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jf import field, geo, iq, scatter, tracks  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


def load_bb(prefix, opt, cache=None):
    """Baseband from a finished capture or from one still being written (uses what the minute-by-minute
    checkpoint covers). The carrier is looked for between car_lo and car_hi (Hz from the centre) if given."""
    if cache and os.path.exists(cache):
        return dict(np.load(cache))
    x, fs, meta = iq.load(prefix)
    x = x[:int(meta["nsamp"])]
    t0, true_rate = iq.sample_clock(meta, len(x))
    if "t_max" in opt:
        x = x[:int(float(opt["t_max"]) * fs)]
    lo, hi = opt.get("car_lo"), opt.get("car_hi")
    fc = iq.find_carrier(x, fs, float(lo), float(hi)) if lo is not None else iq.find_carrier(x, fs)
    y, fs2 = iq.to_baseband(x, fs, fc)
    bb = dict(y=y, fs=np.float64(fs2), t0=np.float64(t0), scale=np.float64(fs / true_rate), carrier_hz=np.float64(fc))
    if cache and not meta.get("partial") and "t_max" not in opt:
        np.savez(cache, **bb)
    return bb


def show(fr, cands, tx_h):
    out = []
    for c in cands:
        la, lo, _ = fr.to_geo(np.array([c[1], c[2], tx_h]))
        out.append(dict(score=float(c[0]), e=float(c[1]), n=float(c[2]), dt=float(c[3]), lat=float(la), lon=float(lo)))
        print(f"   score {c[0]:7.1f}   E {c[1]:8.0f}  N {c[2]:8.0f}   {la:.5f}, {lo:.5f}   dt {c[3]:+.1f}")
    return out


if __name__ == "__main__":
    name, prefix, adsb = sys.argv[1:4]
    rx_lat, rx_lon, freq = map(float, sys.argv[4:7])
    opt = dict(a.split("=", 1) for a in sys.argv[7:])
    tx_h, rx_h = float(opt.get("tx_h", 85)), float(opt.get("rx_h", 45))
    span = float(opt.get("span", 30e3))
    lam = tracks.C / freq
    fr = geo.Frame(rx_lat, rx_lon, 0.0)
    rx = np.array([float(opt.get("rx_e", 0)), float(opt.get("rx_n", 0)), rx_h])
    paths, off = tracks.load_paths(adsb, fr, ground_h=float(opt.get("ground_h", 73)),
                                   max_gap=float(opt.get("max_gap", 12.0)))   # max_gap=30 for 20-s position feeds
    cache = os.path.join(ROOT, "results", f"{name}_bb.npz") if int(opt.get("cache", 1)) else None
    bb = load_bb(prefix, opt, cache)
    wf = scatter.waterfall(bb)
    t, f = wf["t"], wf["f"]
    W, _ = scatter.whiten(wf["S"], f)
    n_in = sum(1 for p in paths.values() if p.valid(t).sum() > 20)
    print(f"{name}: {t[-1] - t[0]:.0f} s, carrier at {float(bb['carrier_hz']):+.1f} Hz, direct C/N0 {-wf['n0_dbc_hz']:.1f} dB-Hz, "
          f"{n_in} aircraft with a track during the recording", flush=True)
    t1 = time.time()
    r = field.search(t, f, W, paths, rx, lam, tx_h=tx_h, span=span, verbose=True)
    label, kept = field.verdict(r["cands"])
    print(f"1. receiver at its listed position: -> {label}   (wide map z {r['z_map']:.1f}, {time.time() - t1:.0f} s)")
    res = dict(name=name, written=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), args=sys.argv[1:],
               seconds=float(t[-1] - t[0]), cn0=float(-wf["n0_dbc_hz"]), aircraft=n_in,
               listed=dict(verdict=label, z_map=r["z_map"], cands=show(fr, r["cands"], tx_h)))
    sup = field.support(r["field"], r["cands"][0], r["clocks"][0])
    print("   aircraft behind the best spot: " + ", ".join(
        f"{(paths[h].flight or h).strip()} {z:.1f}" for z, h in sup[:8]))
    res["listed"]["support"] = [[(paths[h].flight or h).strip(), h, z] for z, h in sup[:12]]
    rxfit = int(opt.get("rxfit", 1))          # 2: fit the receiver even when the first search reports nothing
    if rxfit and (label != "nothing" or rxfit >= 2):
        half, step = float(opt.get("rx_half", 1000)), float(opt.get("rx_step", 50))
        x = np.array([r["cands"][0][1], r["cands"][0][2], tx_h])
        rxf, rr = rx.copy(), r
        for k in range(3):
            F = rr["field"]                       # clocks and delay as the last search left them
            es = np.arange(rxf[0] - half, rxf[0] + half + 1, step)
            ns = np.arange(rxf[1] - half, rxf[1] + half + 1, step)
            M = np.array([[F.score(x[None], 20.0, rx=np.array([e, n, rx_h]))[0] for e in es] for n in ns])
            e_b, n_b, top = field.subcell(es, ns, M)
            rxf = np.array([e_b, n_b, rx_h])
            rr = field.search(t, f, W, paths, rxf, lam, tx_h=tx_h, span=1500.0, step=100.0, k_peaks=2, centre=(x[0], x[1]))
            x = np.array([rr["cands"][0][1], rr["cands"][0][2], tx_h])
            print(f"   round {k + 1}: receiver E {rxf[0]:+7.0f} N {rxf[1]:+7.0f} (evidence {top:.1f}) -> "
                  f"transmitter E {x[0]:.0f} N {x[1]:.0f}, score {rr['cands'][0][0]:.1f}", flush=True)
            half, step = max(half / 4, 100.0), max(step / 2.5, 10.0)
        r2 = field.search(t, f, W, paths, rxf, lam, tx_h=tx_h, span=span, verbose=True)
        label2, _ = field.verdict(r2["cands"])
        la, lo, _ = fr.to_geo(rxf)
        print(f"2. receiver fitted at E {rxf[0]:+.0f} N {rxf[1]:+.0f} ({la:.5f}, {lo:.5f}): -> {label2}   (wide map z {r2['z_map']:.1f})")
        res["fitted"] = dict(rx_e=float(rxf[0]), rx_n=float(rxf[1]), rx_lat=float(la), rx_lon=float(lo), verdict=label2,
                             z_map=r2["z_map"], cands=show(fr, r2["cands"], tx_h))
        sup = field.support(r2["field"], r2["cands"][0], r2["clocks"][0])
        res["fitted"]["support"] = [[(paths[h].flight or h).strip(), h, z] for z, h in sup[:12]]
        res["fitted"]["clocks"] = r2["clocks"][0]
        print("   aircraft behind the best spot: " + ", ".join(
            f"{(paths[h].flight or h).strip()} {z:.1f}" for z, h in sup[:8]))
    out = opt.get("out", os.path.join(ROOT, "results", f"{name}_fix.json"))
    with open(out, "w") as g:
        json.dump(res, g, indent=1)
    print("written", out)
