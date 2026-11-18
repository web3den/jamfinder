#!/usr/bin/env python3
"""Plant a made-up transmitter among real aircraft tracks and see whether the search finds it.

usage: sim_run.py name adsb rx_lat rx_lon freq spots [key=value ...]
  name    names the real recording whose start time and length are copied (results/<name>_bb.npz)
  spots   "E,N;E,N;..." metres east/north of the receiver, or "lat,lon;..." when ll=1
  keys    power=0,-10,-20 (dB relative to 10 W)   seeds=1   rx_e= rx_n= rx_h=45 tx_h=85 ground_h=73
          direct=1 (0: no direct signal)   cn0= (direct C/N0, default from distance and obstruction)
          obstruction=39.1  latency=0.5  pos_sigma=10  fade=6  plateau=8  k=174.5  am=0  out=results/sim_<name>.jsonl
          only=hex,hex  (only these aircraft scatter and are searched)   clocks=1  span=30000
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jf import blind, field, geo, scatter, tracks  # noqa: E402
from sim import synth  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
name, adsb = sys.argv[1:3]
rx_lat, rx_lon, freq = map(float, sys.argv[3:6])
spots_arg = sys.argv[6]
opt = dict(a.split("=", 1) for a in sys.argv[7:])
tx_h = float(opt.get("tx_h", 85))
lam = tracks.C / freq
fr = geo.Frame(rx_lat, rx_lon, 0.0)
rx = np.array([float(opt.get("rx_e", 0)), float(opt.get("rx_n", 0)), float(opt.get("rx_h", 45))])
paths, off = tracks.load_paths(adsb, fr, ground_h=float(opt.get("ground_h", 73)),
                               max_gap=float(opt.get("max_gap", 12.0)))   # max_gap=30 for 20-s position feeds
if "only" in opt:
    keep = set(opt["only"].split(","))
    paths = {h: p for h, p in paths.items() if h in keep or (p.flight or "") in keep}
real = np.load(os.path.join(ROOT, "results", f"{name}_bb.npz"))
t0, dur = float(real["t0"]), len(real["y"]) / float(real["fs"])
scene = synth.Scene(paths, rx, lam, t0, dur)
spots = []
for s in spots_arg.split(";"):
    a, b = map(float, s.split(","))
    spots.append(fr.to_enu(a, b, tx_h)[:2] if int(opt.get("ll", 0)) else (a, b))
out = opt.get("out", os.path.join(ROOT, "results", f"sim_{name}.jsonl"))
kw = dict(obstruction_db=float(opt.get("obstruction", 39.1)), latency=(0.0, float(opt.get("latency", 0.5))),
          pos_sigma=float(opt.get("pos_sigma", 10)), fade_db=float(opt.get("fade", 6)), k_db=float(opt.get("k", synth.K_DB)),
          plateau_deg=float(opt.get("plateau", 8)), am_rms=float(opt.get("am", 0)),
          direct=bool(int(opt.get("direct", 1))))
if "cn0" in opt:
    kw["direct_cn0_db"] = float(opt["cn0"])
print(f"{len(paths)} aircraft, {dur:.0f} s, receiver at E {rx[0]:.0f} N {rx[1]:.0f}", flush=True)
for e, n in spots:
    tx = np.array([e, n, tx_h])
    for pw in [float(v) for v in opt.get("power", "0").split(",")]:
        for seed in range(int(opt.get("seeds", 1))):
            t1 = time.time()
            bb, truth = scene.synth(tx, power_db=pw, seed=seed, **kw)
            if kw["direct"]:
                wf = scatter.waterfall(bb)
                W, _ = scatter.whiten(wf["S"], wf["f"])
                r = field.search(wf["t"], wf["f"], W, paths, rx, lam, tx_h=tx_h, span=float(opt.get("span", 30e3)),
                                 clocks=bool(int(opt.get("clocks", 1))))
                cn0, dt, note = -wf["n0_dbc_hz"], r["dt"], f"direct C/N0 {-wf['n0_dbc_hz']:.0f}"
            else:   # the receiver hears no direct signal: echoes only, unknown frequency path
                wf = scatter.waterfall_blind(bb, has_carrier=False)
                r = blind.search(wf["t"], wf["f"], wf["W"], paths, rx, lam, tx_h=tx_h, span=float(opt.get("span", 30e3)))
                tm, f0 = r["paths"][0]
                off = float(np.sqrt(np.mean((f0 - np.interp(tm, *truth["f0"])) ** 2)))
                cn0, dt, note = None, r["cands"][0][3], f"no direct signal, path off {off:.2f} Hz"
            errs = [float(np.hypot(c[1] - e, c[2] - n)) for c in r["cands"]]
            label, kept = field.verdict(r["cands"])
            row = dict(spot=[float(e), float(n)], power_db=pw, seed=seed, cn0=cn0,
                       direct_cn0=truth["direct_cn0_db"], cands=[[float(v) for v in c] for c in r["cands"]],
                       errs=errs, z_map=r["z_map"], dt=dt, verdict=label)
            with open(out, "a") as fo:
                fo.write(json.dumps(row) + "\n")
            print(f"spot E {e:7.0f} N {n:7.0f}  {pw:+4.0f} dB  seed {seed}  {note}: " +
                  "  ".join(f"[{c[0]:.1f}: {er:.0f} m]" for c, er in zip(r["cands"], errs)) +
                  f"   -> {label}   dt {dt:+.1f}  [{time.time() - t1:.0f} s]", flush=True)
