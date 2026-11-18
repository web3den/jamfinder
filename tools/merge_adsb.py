#!/usr/bin/env python3
"""Merge several position-snapshot files (readsb-style lines, possibly with a truncated tail) into one, in time order.
usage: merge_adsb.py out.jsonl.gz in1.jsonl.gz [in2 ...]"""
import gzip, json, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jf import tracks
out, ins = sys.argv[1], sys.argv[2:]
rows = []
for fn in ins:
    if os.path.exists(fn) and os.path.getsize(fn) > 0:
        n = 0
        for r in tracks.read_lines(fn):
            rows.append(r); n += 1
        print(f"{fn}: {n} snapshots")
rows.sort(key=lambda r: r["t0"])
with gzip.open(out, "wt") as f:
    for r in rows:
        f.write(json.dumps(r, separators=(",", ":")) + "\n")
print(f"{out}: {len(rows)} snapshots, {sum(1 for r in rows for a in r['ac'] if 'lat' in a)} positions")
