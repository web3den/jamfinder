#!/usr/bin/env python3
"""Does the whole verdict (rule v3) pass on a planted transmitter among real aircraft tracks?

sim_run.py only asks whether the search finds the planted spot (rule v1). This script applies rule v3
(definitions in jf/rules.py): "one" only if every wrong-track null is "nothing" (a), the best
is at least 3 times the largest null (b), the blanking residual is below the largest null (c) and the
runner-up is below 0.75 of the best (d). Corridor traffic can lift the time-shift nulls: aircraft
following each other on one route make a shifted track land near a real echo (Brainerd, +300 s null
46.7 with support 130/53). So the whole verdict, not just the search, is checked on the simulation
before any real recording. Simulated scores are trusted to about 5 dB (see sim/synth.py).

usage: sim_v3_check.py name adsb rx_lat rx_lon freq_hz tx_lat tx_lon [key=value ...]
  name     the real recording whose start and length are copied (results/<name>_bb.npz; without a recording,
           tools/make_stub_bb.py writes a stand-in from a positions file)
  keys     power=0,-7  seeds=1  rx_h=45  tx_h=85  ground_h=73  max_gap=12 (30 for 20-s feeds)
           shifts=-600,-300,300,600  flip=1  obstruction=39.1  latency=0.5  pos_sigma=10  fade=6
           out=results/simv3_<name>.jsonl
A null whose shifted tracks keep less than half of their aircraft-seconds inside the recording is
degenerate and does not count (v3's condition (a))."""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jf import field, geo, scatter, tracks  # noqa: E402
from sim import synth  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


class Shifted:
    """An aircraft track played back `delta` seconds early or late (as in analysis/null_try.py)."""

    def __init__(self, p, delta):
        self.p, self.delta = p, float(delta)
        self.flight, self.actype = p.flight, p.actype

    def valid(self, t):
        return self.p.valid(np.asarray(t, float) + self.delta)

    def pos(self, t):
        return self.p.pos(np.asarray(t, float) + self.delta)

    def vel(self, t):
        return self.p.vel(np.asarray(t, float) + self.delta)


def main():
    name, adsb = sys.argv[1:3]
    rx_lat, rx_lon, freq, tx_lat, tx_lon = map(float, sys.argv[3:8])
    opt = dict(a.split("=", 1) for a in sys.argv[8:])
    tx_h = float(opt.get("tx_h", 85))
    lam = tracks.C / freq
    fr = geo.Frame(rx_lat, rx_lon, 0.0)
    rx = np.array([float(opt.get("rx_e", 0)), float(opt.get("rx_n", 0)), float(opt.get("rx_h", 45))])
    paths, _ = tracks.load_paths(adsb, fr, ground_h=float(opt.get("ground_h", 73)), max_gap=float(opt.get("max_gap", 12.0)))
    real = np.load(os.path.join(ROOT, "results", f"{name}_bb.npz"))
    t0, dur = float(real["t0"]), len(real["y"]) / float(real["fs"])
    scene = synth.Scene(paths, rx, lam, t0, dur)
    tx = np.array(fr.to_enu(tx_lat, tx_lon, tx_h), float)
    tx[2] = tx_h
    kw = dict(obstruction_db=float(opt.get("obstruction", 39.1)), latency=(0.0, float(opt.get("latency", 0.5))),
              pos_sigma=float(opt.get("pos_sigma", 10)), fade_db=float(opt.get("fade", 6)))
    shifts = [float(v) for v in opt.get("shifts", "-600,-300,300,600").split(",") if v]
    nulls = ([("flip", 0.0)] if int(opt.get("flip", 1)) else []) + [("shift", d) for d in shifts]
    out = opt.get("out", os.path.join(ROOT, "results", f"simv3_{name}.jsonl"))
    label = lambda h: (paths[h].flight or h).strip()
    print(f"{len(paths)} aircraft, {dur:.0f} s, receiver at E {rx[0]:.0f} N {rx[1]:.0f}, planted at E {tx[0]:.0f} N {tx[1]:.0f}; "
          f"nulls {[k if k == 'flip' else f'{d:+.0f}' for k, d in nulls]}", flush=True)
    for pw in [float(v) for v in opt.get("power", "0,-7").split(",")]:
        for seed in range(int(opt.get("seeds", 1))):
            t1 = time.time()
            bb, truth = scene.synth(tx, power_db=pw, seed=seed, **kw)
            wf = scatter.waterfall(bb)
            W, _ = scatter.whiten(wf["S"], wf["f"])
            t, f = wf["t"], wf["f"]
            r = field.search(t, f, W, paths, rx, lam, tx_h=tx_h)
            c, ck = r["cands"][0], r["clocks"][0]
            err = float(np.hypot(c[1] - tx[0], c[2] - tx[1]))
            v1, _ = field.verdict(r["cands"])
            sup = field.support(r["field"], c, ck)
            print(f"\n{pw:+.0f} dB seed {seed}: direct C/N0 {-wf['n0_dbc_hz']:.0f}; search best {c[0]:.1f} at {err:.0f} m, "
                  f"second {r['cands'][1][0]:.1f}, v1 {v1}; support " + ", ".join(f"{label(h)} {z:.0f}" for z, h in sup[:5])
                  + f"  [{time.time() - t1:.0f} s]", flush=True)
            # how many aircraft-seconds the unshifted tracks have inside the recording
            base_valid = sum(int(p.valid(t).sum()) for p in paths.values())
            rows = []
            for kind, delta in nulls:
                t2 = time.time()
                if kind == "flip":
                    assert abs(f[0] + f[-1]) < 1e-6, "frequency axis must be symmetric"
                    W2, use, frac = W[:, ::-1], paths, 1.0
                else:
                    use = {h: Shifted(p, delta) for h, p in paths.items()}
                    W2 = W
                    frac = sum(int(p.valid(t).sum()) for p in use.values()) / max(base_valid, 1)
                rn = field.search(t, f, W2, use, rx, lam, tx_h=tx_h)
                vn, _ = field.verdict(rn["cands"])
                sn = field.support(rn["field"], rn["cands"][0], rn["clocks"][0])
                rows.append(dict(kind=kind, delta=delta, best=float(rn["cands"][0][0]), verdict=vn, frac=float(frac),
                                 degenerate=bool(frac < 0.5), support=[round(float(z), 1) for z, _ in sn[:3]]))
                print(f"   null {kind:5s} {delta:+6.0f} s: best {rn['cands'][0][0]:6.1f} -> {vn:9s} "
                      f"(tracks inside {100 * frac:3.0f} %{', degenerate' if frac < 0.5 else ''}); support "
                      + " ".join(f"{z:.0f}" for z, _ in sn[:3]) + f"  [{time.time() - t2:.0f} s]", flush=True)
            t2 = time.time()
            Wb = field.mask_tracks(t, f, W, paths, rx, lam, c, ck, tx_h=tx_h)
            rb = field.search(t, f, Wb, paths, rx, lam, tx_h=tx_h)
            residual = float(rb["cands"][0][0])
            print(f"   blanking residual {residual:.1f}  [{time.time() - t2:.0f} s]", flush=True)
            live = [q for q in rows if not q["degenerate"]]
            largest = max(q["best"] for q in live) if live else float("nan")
            a = all(q["verdict"] == "nothing" for q in live)
            b = c[0] >= 3.0 * largest
            cc = residual < largest
            d = r["cands"][1][0] < field.TIE * c[0]
            v3 = "one" if (a and b and cc and d) else "nothing"
            print(f"   (a) nulls all nothing {a}  (b) {c[0]:.1f} >= 3 x {largest:.1f} {b}  (c) residual {residual:.1f} < {largest:.1f} {cc}  "
                  f"(d) second {r['cands'][1][0]:.1f} < 0.75 x best {d}  ->  v1 {v1}, v3 {v3}; planted spot {err:.0f} m from the best", flush=True)
            row = dict(name=name, power_db=pw, seed=seed, direct_cn0=truth["direct_cn0_db"], cn0=float(-wf["n0_dbc_hz"]),
                       best=float(c[0]), err_m=err, second=float(r["cands"][1][0]), dt=float(c[3]),
                       support=[[label(h), round(float(z), 1)] for z, h in sup[:6]], nulls=rows, residual=residual,
                       conditions=dict(a=bool(a), b=bool(b), c=bool(cc), d=bool(d)), v1=v1, v3=v3)
            with open(out, "a") as fo:
                fo.write(json.dumps(row) + "\n")


if __name__ == "__main__":
    main()
