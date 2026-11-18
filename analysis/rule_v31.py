#!/usr/bin/env python3
"""Rules v3, v3.1 and v3.2 from a finished pipeline run — no search of its own.

Reads results/<name>_rules.json (candidates, support, residual, conditions) and results/<name>_null.jsonl
(the wrong-track nulls), works out which time-shift nulls are degenerate (shifted tracks keeping less than
half of the aircraft-seconds inside the recording — they do not count), and prints the verdicts as
jf/rules.py defines them:
  v3   = "one" iff (a) every non-degenerate null "nothing" under v1, (b) best >= 3 x largest null best,
         (c) blanking residual < largest null best, (d) second < 0.75 x best
  v3.1 = "one" iff v1 "one" and (a') the flip null "nothing" under v1 and (b) and (c) and (d)
  v3.2 = "one" iff (a') and (b) and (c) and (d), with no v1 requirement: the final rule
usage: rule_v31.py name adsb rx_lat rx_lon [ground_h=73 max_gap=12 rules= nulls= out=]"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jf import geo, tracks  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
name, adsb = sys.argv[1:3]
rx_lat, rx_lon = map(float, sys.argv[3:5])
opt = dict(a.split("=", 1) for a in sys.argv[5:])
rules = json.load(open(opt.get("rules", os.path.join(ROOT, "results", f"{name}_rules.json"))))
nulls_fn = opt.get("nulls", os.path.join(ROOT, "results", f"{name}_null.jsonl"))
nulls = [json.loads(l) for l in open(nulls_fn)] if os.path.exists(nulls_fn) else []
bb = np.load(os.path.join(ROOT, "results", f"{name}_bb.npz"))
t0, dur = float(bb["t0"]), len(bb["y"]) / float(bb["fs"])
t = np.arange(t0, t0 + dur, 1.0)
fr = geo.Frame(rx_lat, rx_lon, 0.0)
paths, _ = tracks.load_paths(adsb, fr, ground_h=float(opt.get("ground_h", 73)), max_gap=float(opt.get("max_gap", 12.0)))
base = sum(int(p.valid(t).sum()) for p in paths.values())

rows = []
for n in nulls:
    if n["kind"] == "flip":
        frac = 1.0
    elif "frac" in n:              # wrong-time-tracks nulls (analysis/null_wrongtime.py) carry their own fraction
        frac = float(n["frac"])
    else:
        frac = sum(int(p.valid(t + n["delta"]).sum()) for p in paths.values()) / max(base, 1)
    rows.append(dict(kind=n["kind"], delta=n["delta"], verdict=n["verdict"], best=float(n["cands"][0][0]), frac=frac, degenerate=frac < 0.5))
live = [r for r in rows if not r["degenerate"]]
cands = rules["cands"]
best, second = cands[0][0], (cands[1][0] if len(cands) > 1 else 0.0)
v1 = rules["v1"]
largest = max((r["best"] for r in live), default=float("nan"))
flips = [r for r in live if r["kind"] == "flip"]
a = bool(live) and all(r["verdict"] == "nothing" for r in live)
a1 = bool(flips) and all(r["verdict"] == "nothing" for r in flips)
b = bool(live) and best >= 3 * largest
c = bool(live) and rules["residual"] < largest
d = second < 0.75 * best
v3 = "one" if (a and b and c and d) else "nothing"
v31 = "one" if (v1 == "one" and a1 and b and c and d) else "nothing"
v32 = "one" if (a1 and b and c and d) else "nothing"     # v3 with the flip-only veto, no v1 requirement
print(f"{name}: {len(paths)} aircraft with a track, {dur:.0f} s; v1 {v1}, v2 {rules['v2']}, v2.2 {rules['v22']}")
for r in rows:
    # frac = aircraft-seconds of the shifted tracks inside the recording / the unshifted amount; it can exceed 1 when
    # position files run longer than the recording (shifted tracks enter from outside). Degenerate = below 0.5.
    print(f"  null {r['kind']:5s} {r['delta']:+6.0f} s: best {r['best']:6.1f} -> {r['verdict']:9s} aircraft-seconds inside, shifted/unshifted {r['frac']:.2f}" + ("  (degenerate, not counted)" if r["degenerate"] else ""))
print(f"  (a) all live nulls nothing: {a}   (a') flip nothing: {a1}   (b) {best:.1f} >= 3 x {largest:.1f}: {b}   (c) residual {rules['residual']:.1f} < {largest:.1f}: {c}   (d) second {second:.1f} < 0.75 x best: {d}")
print(f"  v3: {v3}   v3.1: {v31}   v3.2: {v32}   best spot {rules['best']['lat']:.5f}, {rules['best']['lon']:.5f} (E {rules['best']['e']:.0f} N {rules['best']['n']:.0f}); support " +
      ", ".join(f"{s[0]} {s[2]:.0f}" for s in rules["support"][:6]))
out = opt.get("out", os.path.join(ROOT, "results", f"{name}_rules_v31.json"))
json.dump(dict(name=name, v1=v1, v2=rules["v2"], v22=rules["v22"], v3=v3, v31=v31, v32=v32, conditions=dict(a=a, a1=a1, b=b, c=c, d=d),
               largest_null=largest, nulls=rows, best=rules["best"], second=second, residual=rules["residual"]), open(out, "w"), indent=1)
print("written", out)
