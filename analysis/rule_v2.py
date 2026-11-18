#!/usr/bin/env python3
"""Apply the reporting rules v1, v2 and v2.2 to a site, as defined in jf/rules.py, and print the verdicts.

Inputs: the cached baseband results/<name>_bb.npz (written by site_run.py), the aircraft file, and the wrong-track
null runs results/<name>_null.jsonl (written by null_try.py). The search is run again here with the receiver at
the given position, then the best spot's predicted lines are blanked and the search is run once more (the
"explains all echoes" test).

usage: rule_v2.py name adsb rx_lat rx_lon freq [rx_e= rx_n= rx_h=45 tx_h=85 ground_h=73 nulls=results/<name>_null.jsonl out=]

v1:   score >= 15; with three or more candidates the best must be >= 1.6 x the third; keep candidates >= 0.75 x best.
v2:   (a) every null "nothing" under v1; (b) best >= 3 x the largest null best score; (c) after blanking the best
      spot's lines the largest remaining score is below the largest null best score; (d) no other candidate >= 0.75 x best.
v2.2: v2 plus (e) at least three aircraft with support >= 10 and (f) second-strongest support >= 0.25 x strongest.
"""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jf import field, geo, scatter, tracks  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
name, adsb = sys.argv[1:3]
rx_lat, rx_lon, freq = map(float, sys.argv[3:6])
opt = dict(a.split("=", 1) for a in sys.argv[6:])
tx_h = float(opt.get("tx_h", 85))
lam = tracks.C / freq
fr = geo.Frame(rx_lat, rx_lon, 0.0)
rx = np.array([float(opt.get("rx_e", 0)), float(opt.get("rx_n", 0)), float(opt.get("rx_h", 45))])
paths, _ = tracks.load_paths(adsb, fr, ground_h=float(opt.get("ground_h", 73)),
                             max_gap=float(opt.get("max_gap", 12.0)))   # max_gap=30 for 20-s position feeds
bb = dict(np.load(os.path.join(ROOT, "results", f"{name}_bb.npz")))
wf = scatter.waterfall(bb)
t, f = wf["t"], wf["f"]
W, _ = scatter.whiten(wf["S"], f)
nulls_fn = opt.get("nulls", os.path.join(ROOT, "results", f"{name}_null.jsonl"))
nulls = [json.loads(l) for l in open(nulls_fn)] if os.path.exists(nulls_fn) else []

t1 = time.time()
r = field.search(t, f, W, paths, rx, lam, tx_h=tx_h, span=30e3)
v1, kept = field.verdict(r["cands"])
best = r["cands"][0]
sup = field.support(r["field"], best, r["clocks"][0])
z = [s for s, h in sup]
W2 = field.mask_tracks(t, f, W, paths, rx, lam, best, r["clocks"][0], tx_h=tx_h)
r2 = field.search(t, f, W2, paths, rx, lam, tx_h=tx_h, span=30e3)
la, lo, _ = fr.to_geo(np.array([best[1], best[2], tx_h]))

null_best = max((n["cands"][0][0] for n in nulls), default=float("nan"))
null_v1_ok = all(n["verdict"] == "nothing" for n in nulls) and len(nulls) > 0
second = r["cands"][1][0] if len(r["cands"]) > 1 else 0.0
a = null_v1_ok
b = bool(len(nulls)) and best[0] >= 3 * null_best
c = bool(len(nulls)) and r2["cands"][0][0] < null_best
d = second < 0.75 * best[0]
e = sum(1 for v in z if v >= 10) >= 3
f_ = len(z) > 1 and z[1] >= 0.25 * z[0]
v2 = "one" if (a and b and c and d) else v1
v22 = "one" if (a and b and c and d and e and f_) else v1

print(f"{name}: {len(paths)} aircraft, {t[-1] - t[0]:.0f} s  [{time.time() - t1:.0f} s]")
print("candidates: " + "  ".join(f"[{c_[0]:.1f} @ E {c_[1]:.0f} N {c_[2]:.0f}]" for c_ in r["cands"]))
print(f"best spot: E {best[1]:.0f} N {best[2]:.0f} = {la:.5f}, {lo:.5f}; support " + ", ".join(f"{(paths[h].flight or h).strip()} {s:.0f}" for s, h in sup[:8]))
print(f"nulls: {len(nulls)} runs, all 'nothing' under v1: {null_v1_ok}, largest best score {null_best:.1f}")
print(f"after blanking the best spot's lines: largest remaining {r2['cands'][0][0]:.1f} (map z {r2['z_map']:.1f})")
print(f"v1: {v1}   v2: {v2}  [(a) nulls {a}, (b) {best[0]:.1f} >= 3 x {null_best:.1f}: {b}, (c) residual {r2['cands'][0][0]:.1f} < {null_best:.1f}: {c}, (d) second {second:.1f} < 0.75 x best: {d}]")
print(f"v2.2: {v22}  [(e) >= 3 aircraft with support >= 10: {e} ({sum(1 for v in z if v >= 10)}), (f) second/first support {z[1] / z[0] if len(z) > 1 and z[0] > 0 else 0:.2f} >= 0.25: {f_}]")
out = opt.get("out", os.path.join(ROOT, "results", f"{name}_rules.json"))
json.dump(dict(name=name, written=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), args=sys.argv[1:],
               cands=[[float(v) for v in c_] for c_ in r["cands"]], best=dict(e=float(best[1]), n=float(best[2]), lat=float(la), lon=float(lo), score=float(best[0])),
               support=[[(paths[h].flight or h).strip(), h, s] for s, h in sup[:12]], null_best=null_best, null_runs=len(nulls),
               residual=float(r2["cands"][0][0]), residual_zmap=r2["z_map"], v1=v1, v2=v2, v22=v22,
               conditions=dict(a=a, b=b, c=c, d=d, e=e, f=f_)), open(out, "w"), indent=1)
print("written", out)
