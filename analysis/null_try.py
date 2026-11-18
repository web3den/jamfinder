#!/usr/bin/env python3
"""What does the search report when the aircraft tracks do not belong to the echoes?

The recording is real and full of echoes, but the tracks are moved in time (or the waterfall is
mirrored in frequency), so no spot can explain the echoes. Every peak found this way is false.
This is the honest test of the reporting rule: bright echoes from aircraft whose track we do not
have (no transponder, or not in the feed) look exactly like this.

usage: null_try.py name iq_prefix adsb rx_lat rx_lon freq [rx_e= rx_n= shifts=-600,-300,300,600 flip=1
                   noise=0 mode=field|blind out=]"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jf import blind, field, geo, scatter, tracks  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


class Shifted:
    """An aircraft track played back `delta` seconds early or late."""

    def __init__(self, p, delta):
        self.p, self.delta = p, float(delta)
        self.flight, self.actype = p.flight, p.actype

    def valid(self, t):
        return self.p.valid(np.asarray(t, float) + self.delta)

    def pos(self, t):
        return self.p.pos(np.asarray(t, float) + self.delta)

    def vel(self, t):
        return self.p.vel(np.asarray(t, float) + self.delta)


name, prefix, adsb = sys.argv[1:4]
rx_lat, rx_lon, freq = map(float, sys.argv[4:7])
opt = dict(a.split("=", 1) for a in sys.argv[7:])
tx_h = float(opt.get("tx_h", 85))
lam = tracks.C / freq
fr = geo.Frame(rx_lat, rx_lon, 0.0)
rx = np.array([float(opt.get("rx_e", 0)), float(opt.get("rx_n", 0)), float(opt.get("rx_h", 45))])
paths, off = tracks.load_paths(adsb, fr, ground_h=float(opt.get("ground_h", 73)),
                               max_gap=float(opt.get("max_gap", 12.0)))   # max_gap=30 for 20-s position feeds
bb = scatter.baseband(prefix, cache=os.path.join(ROOT, "results", f"{name}_bb.npz"))
mode = opt.get("mode", "field")
db = float(opt.get("noise", 0))
base = scatter.waterfall(bb)
if mode == "blind":
    wf = scatter.waterfall_blind(bb, add_noise_db=db, floor_dbc_hz=base["n0_dbc_hz"])
    t, f, W = wf["t"], wf["f"], wf["W"]
else:
    wf = base if db == 0 else scatter.waterfall(bb, add_noise_db=db, floor_dbc_hz=base["n0_dbc_hz"])
    t, f = wf["t"], wf["f"]
    W, _ = scatter.whiten(wf["S"], f)
out = opt.get("out", os.path.join(ROOT, "results", f"{name}_null.jsonl"))
cases = [("flip", 0.0)] if int(opt.get("flip", 1)) else []
cases += [("shift", float(v)) for v in opt.get("shifts", "-600,-300,300,600").split(",") if v]
print(f"{name}: {len(paths)} aircraft, {t[-1] - t[0]:.0f} s, mode {mode}, {db:.0f} dB weaker", flush=True)
for kind, delta in cases:
    t1 = time.time()
    if kind == "flip":
        assert abs(f[0] + f[-1]) < 1e-6, "frequency axis must be symmetric"
        W2, use = W[:, ::-1], paths
    else:
        W2, use = W, {h: Shifted(p, delta) for h, p in paths.items()}
    if mode == "blind":
        r = blind.search(t, f, W2, use, rx, lam, tx_h=tx_h)
        sup = []
    else:
        r = field.search(t, f, W2, use, rx, lam, tx_h=tx_h)
        sup = [[round(z, 1) for z, h in field.support(r["field"], c, k)[:4]] for c, k in zip(r["cands"], r["clocks"])]
    label, kept = field.verdict(r["cands"])
    row = dict(name=name, mode=mode, kind=kind, delta=delta, noise=db, verdict=label,
               cands=[[float(v) for v in c] for c in r["cands"]], support=sup)
    with open(out, "a") as fo:
        fo.write(json.dumps(row) + "\n")
    print(f"{kind:5s} {delta:+6.0f} s: " + "  ".join(f"[{c[0]:.1f}]" for c in r["cands"]) + f"   -> {label}"
          + ("   support of best: " + " ".join(f"{z:.0f}" for z in sup[0]) if sup else "") + f"   [{time.time() - t1:.0f} s]",
          flush=True)
