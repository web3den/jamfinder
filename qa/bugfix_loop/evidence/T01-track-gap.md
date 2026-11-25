# Evidence: T01-track-gap, 20-second position feeds give empty tracks even with max_gap=30

Decision: **needs a human** (the new test catches only 0 of 3 planted bugs on the changed lines; reviewer: request_changes, risk medium)

Agent: gpt-5.4-mini. Reviewer: gpt-4.1-mini. Model calls: 4, cost $0.013 when recorded.

## Ticket

Tracks built from a position feed with one report every 20 seconds come back almost entirely invalid (Path.valid is False nearly everywhere), even when I pass max_gap=30 to tracks.load_paths. Feeds with a report every 2 seconds are fine. Expected: with max_gap=30 a 20-second feed gives a fully valid track; with max_gap below 20 it should not.

## Steps

| step | result | detail |
|---|---|---|
| locate | pass | jf/tracks.py, tests/test_track_gaps.py |
| reproduce (red) | pass | 1 of 1 tests fail |
| repair | pass | 1 edit(s); refused: 0 |
| new test passes (green) | pass |  |
| existing suite passes | pass | 46 passed, 0 failed |
| targeted mutation (signal) | pass | the new test kills 0 of 3 mutants of the changed lines |

## Regression test written by the agent

```python
import gzip
import json

import numpy as np

from jf import geo, tracks


LAT0, LON0 = 46.0, -94.0
SPEED, ALT, DUR = 230.0, 10000.0, 400.0


def _write_feed(path, cadence_s):
    frame = geo.Frame(LAT0, LON0, 0.0)
    t0 = 1.7e9
    with gzip.open(path, "wt") as f:
        for k in range(int(DUR / cadence_s) + 1):
            t = t0 + k * cadence_s
            e = -SPEED * DUR / 2 + SPEED * k * cadence_s
            lat, lon, _ = frame.to_geo(np.array([e, 0.0, ALT]))
            ac = dict(
                hex="abc123",
                type="adsb_icao",
                flight="TEST1",
                t="B738",
                category="A3",
                alt_baro=32000,
                alt_geom=int(round(ALT / geo.FT)),
                gs=SPEED / geo.KT,
                track=90.0,
                geom_rate=0,
                baro_rate=0,
                lat=float(lat),
                lon=float(lon),
                nic=8,
                rc=186,
                seen_pos=0.1,
                seen=0.1,
            )
            f.write(json.dumps(dict(t0=t, t1=t + 0.2, now=int(t * 1000), ac=[ac])) + "\n")
    return frame


def test_max_gap_controls_validity_for_twenty_second_feeds(tmp_path):
    fn = str(tmp_path / "feed20.jsonl.gz")
    frame = _write_feed(fn, 20.0)

    paths, _ = tracks.load_paths(fn, frame, ground_h=0.0, max_gap=30.0)
    p = paths["abc123"]

    tc = np.arange(p.t0, p.t1, 1.0)
    valid_fraction = float(p.valid(tc).mean())

    assert valid_fraction > 0.95
```

Its failure on the buggy code (red):

```
F                                                                        [100%]
=================================== FAILURES ===================================
____________ test_max_gap_controls_validity_for_twenty_second_feeds ____________
tests/test_repro.py:54: in test_max_gap_controls_validity_for_twenty_second_feeds
    assert valid_fraction > 0.95
E   assert 0.0 > 0.95
=========================== short test summary info ============================
FAILED tests/test_repro.py::test_max_gap_controls_validity_for_twenty_second_feeds
1 failed
```

## The change

```diff
--- a/jf/tracks.py
+++ b/jf/tracks.py
@@ -162,7 +162,7 @@
         t = np.asarray(t, float)
         i = np.clip(np.searchsorted(self.tp, t), 1, len(self.tp) - 1)
         gap = self.tp[i] - self.tp[i - 1]
-        return (t >= self.t0) & (t <= self.t1) & (gap <= 12.0)
+        return (t >= self.t0) & (t <= self.t1) & (gap <= self.max_gap)
 
     def pos(self, t):
         return self.sp(np.clip(np.asarray(t, float), self.t0, self.t1))
```

## Independent review

Verdict: request_changes, risk medium.

- The fix changes the allowed gap threshold from a hardcoded value of 12.0 to self.max_gap, which seems correct, but the source of self.max_gap is unclear and not verified in the provided diff or test.
- The test checks that valid_fraction > 0.95 with max_gap=30 and a 20-second feed but does not test the behavior with max_gap below 20, which the ticket states is an important expected case.
- The test only samples validity at 1-second intervals but the feed positions are 20 seconds apart; this coarse sampling may not fully verify gap handling or intermittent invalidity.
- No test verifies that paths remain invalid when max_gap is below the feed interval, so it is unclear if the fix truly respects max_gap as intended.
- The patch modifies a single method without showing if self.max_gap is properly initialized for the Tracks or Path class, raising suspicion about completeness of the fix.
