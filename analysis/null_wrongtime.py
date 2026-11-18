#!/usr/bin/env python3
"""Wrong-time-tracks null: search a recording with the aircraft tracks of ANOTHER recording of the same site.

The time-shift nulls of analysis/null_try.py are lifted on airway traffic — a track shifted by minutes lands on
the real echo of the aircraft behind it (Brainerd 2026-11-15, Hot Springs simulation, Genoa: +600 s null
"one" at 63.4 from one aircraft). Tracks from another hour or day of the same site cannot do that: an aircraft
would have to pass the same place at the same clock time to the second. Rule v3.2
counts this null in the standard set whenever such tracks exist. Output rows have the format of null_try.py
(kind "wrongtime", delta = seconds added to recording time to look up the other tracks, source file, frac =
aircraft-seconds of the other tracks inside the recording / the recording's own tracks' aircraft-seconds).

usage: null_wrongtime.py name iq_prefix adsb_own adsb_other rx_lat rx_lon freq [rx_e= rx_n= rx_h=45 tx_h=85 ground_h=73
                         max_gap=12 offset=auto|<seconds> out=results/<name>_null_wrongtime.jsonl]
offset=auto aligns the other file's first position snapshot with the start of the recording."""
import json
import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jf import field, geo, scatter, tracks  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")


class Shifted:
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
    name, prefix, adsb_own, adsb_other = sys.argv[1:5]
    rx_lat, rx_lon, freq = map(float, sys.argv[5:8])
    opt = dict(a.split("=", 1) for a in sys.argv[8:] if "=" in a)
    tx_h = float(opt.get("tx_h", 85))
    lam = tracks.C / freq
    fr = geo.Frame(rx_lat, rx_lon, 0.0)
    rx = np.array([float(opt.get("rx_e", 0)), float(opt.get("rx_n", 0)), float(opt.get("rx_h", 45))])
    gh, mg = float(opt.get("ground_h", 73)), float(opt.get("max_gap", 12.0))
    own, _ = tracks.load_paths(adsb_own, fr, ground_h=gh, max_gap=mg)
    other, _ = tracks.load_paths(adsb_other, fr, ground_h=gh, max_gap=mg)
    bb = scatter.baseband(prefix, cache=os.path.join(ROOT, "results", f"{name}_bb.npz"))
    wf = scatter.waterfall(bb)
    t, f = wf["t"], wf["f"]
    W, _ = scatter.whiten(wf["S"], f)
    if opt.get("offset", "auto") == "auto":
        first = min(r["t0"] for r in tracks.read_lines(adsb_other))
        delta = float(first - t[0])
    else:
        delta = float(opt["offset"])
    use = {h: Shifted(p, delta) for h, p in other.items()}
    grid = np.arange(t[0], t[-1], 1.0)
    base = sum(int(p.valid(grid).sum()) for p in own.values())
    inside = sum(int(p.valid(grid).sum()) for p in use.values())
    frac = inside / max(base, 1)
    print(f"{name}: own tracks {len(own)} aircraft ({base} aircraft-seconds); other tracks {len(other)} aircraft from {os.path.basename(adsb_other)} "
          f"shifted by {delta:+.0f} s -> {inside} aircraft-seconds inside the recording (frac {frac:.2f})", flush=True)
    t1 = time.time()
    r = field.search(t, f, W, use, rx, lam, tx_h=tx_h)
    label, kept = field.verdict(r["cands"])
    sup = [[round(z, 1) for z, h in field.support(r["field"], c, k)[:4]] for c, k in zip(r["cands"], r["clocks"])]
    row = dict(name=name, mode="field", kind="wrongtime", delta=delta, source=adsb_other, noise=0.0, verdict=label,
               cands=[[float(v) for v in c] for c in r["cands"]], support=sup, frac=frac, degenerate=frac < 0.5)
    out = opt.get("out", os.path.join(ROOT, "results", f"{name}_null_wrongtime.jsonl"))
    with open(out, "a") as fo:
        fo.write(json.dumps(row) + "\n")
    print(f"wrongtime {delta:+6.0f} s: " + "  ".join(f"[{c[0]:.1f}]" for c in r["cands"]) + f"   -> {label}   support of best: "
          + " ".join(f"{z:.0f}" for z in sup[0]) + f"   [{time.time() - t1:.0f} s]", flush=True)
    print("written", out)


if __name__ == "__main__":
    main()
