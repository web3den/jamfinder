#!/usr/bin/env python3
"""Write a stub baseband cache that only carries a start time and a length, for simulations on a position capture
that has no recording (analysis/sim_v3_check.py reads results/<name>_bb.npz for t0 and len(y)/fs and nothing else).

usage: make_stub_bb.py <adsb.jsonl.gz> <out .npz> [start_unix] [seconds]
Default start = the capture's first snapshot, seconds = capture length."""
import sys

import numpy as np

sys.path.insert(0, __import__("os").path.join(__import__("os").path.dirname(__file__), ".."))
from jf import tracks  # noqa: E402

adsb, out = sys.argv[1:3]
rows = list(tracks.read_lines(adsb))
first, last = min(r["t0"] for r in rows), max(r["t0"] for r in rows)
start = float(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3] else float(first)
dur = float(sys.argv[4]) if len(sys.argv) > 4 else float(last - first)
np.savez(out, y=np.zeros(int(round(dur)), dtype=np.complex64), fs=1.0, t0=start, scale=1.0, carrier_hz=0.0)
print(f"{out}: t0 {start:.0f} ({dur:.0f} s) from {len(rows)} snapshots {first:.0f}..{last:.0f}")
