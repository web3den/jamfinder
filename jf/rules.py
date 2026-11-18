"""The reporting rules v1, v2, v2.2, v3, v3.1 and v3.2 as one pure function.

Nothing here searches or reads files: the inputs are what a run already produced (the candidates of the
search, the wrong-track null runs, the blanking residual and the per-aircraft support at the best spot).
Definitions, as computed in analysis/rule_v2.py, analysis/rule_v31.py and analysis/sim_v3_check.py:

  v1    field.verdict(cands): best >= 15; with three or more candidates the best must be >= 1.6 x the
        third; keep the top two that reach 0.75 x best -> "one", "ambiguous" or "nothing".
  (a)   every non-degenerate null is "nothing" under v1 (and there is at least one such null);
  (a')  the spectrum-flip null is "nothing" under v1 (key "a_flip"; no flip null -> false);
  (b)   best >= 3 x the largest best score over the non-degenerate nulls;
  (c)   the blanking residual (largest score after blanking the best spot's lines) < that largest null best;
  (d)   the runner-up < 0.75 x best;
  (e)   at least 3 aircraft with support >= 10 at the best spot;
  (f)   second-strongest support >= 0.25 x the strongest.
  v2    "one" if a, b, c, d, else v1                      (2026-11-14, about 15:00 UTC)
  v2.2  "one" if a, b, c, d, e, f, else v1                (2026-11-14, about 17:15 UTC)
  v3    "one" if and only if a, b, c, d                   (2026-11-15 21:24 UTC, clarified 21:40 UTC)
  v3.1  "one" if and only if v1 == "one" and a', b, c, d   (2026-11-15 23:33 UTC)
  v3.2  "one" if and only if a', b, c, d                   (2026-11-16 02:05 UTC; the final rule)

A null is degenerate when its shifted tracks keep less than half of the aircraft-seconds inside the
recording (its row carries frac < 0.5, as analysis/sim_v3_check.py records it). A row without frac (the
null files written before 2026-11-15) counts as non-degenerate. Degenerate nulls take no part in (a), (a'),
(b) or (c). Without any non-degenerate null, (a), (b) and (c) are false, as in analysis/rule_v2.py.
"""
import math

from . import field

NULL_RATIO = 3.0        # (b): best >= NULL_RATIO x largest null best
RUNNER_UP = 0.75        # (d): runner-up < RUNNER_UP x best
SUPPORT_MIN = 10.0      # (e): support threshold per aircraft
SUPPORT_COUNT = 3       # (e): how many aircraft must reach it
SUPPORT_RATIO = 0.25    # (f): second-strongest >= SUPPORT_RATIO x strongest
DEGENERATE_FRAC = 0.5   # a null keeping less than this share of the aircraft-seconds is not a null

VERDICTS = ("v1", "v2", "v22", "v3", "v31", "v32")
CONDITIONS = ("a", "a_flip", "b", "c", "d", "e", "f")


def null_score(row):
    """Best score of one null run: `best` (sim_v3_check rows, sweep rows) or the first candidate's score
    (null_try rows)."""
    if row.get("best") is not None:
        return float(row["best"])
    return float(row["cands"][0][0])


def is_degenerate(row, degenerate_frac=DEGENERATE_FRAC):
    if row.get("frac") is not None:
        return float(row["frac"]) < degenerate_frac
    return bool(row.get("degenerate", False))


def _z(item):
    """One support entry -> its z. Accepts a number, (z, hex) as field.support returns it, or the lists
    stored in result files ([flight, hex, z] or [flight, z])."""
    if isinstance(item, (int, float)) and not isinstance(item, bool):
        return float(item)
    nums = [v for v in item if isinstance(v, (int, float)) and not isinstance(v, bool)]
    if len(nums) != 1:
        raise ValueError(f"cannot read a support value from {item!r}")
    return float(nums[0])


def evaluate(cands, nulls, residual, support, threshold=field.THRESHOLD, tie=field.TIE, clear=field.CLEAR,
             null_ratio=NULL_RATIO, runner_up=RUNNER_UP, support_min=SUPPORT_MIN, support_count=SUPPORT_COUNT,
             support_ratio=SUPPORT_RATIO, degenerate_frac=DEGENERATE_FRAC):
    """Conditions a-f and the verdicts of every rule for one run.

    cands     the search's candidates, best first: [(score, E, N, dt), ...] (only the scores are used)
    nulls     the null runs: dicts with "kind" ("flip" or "shift"), "verdict" (their v1 label, computed by the
              run with the same v1 constants), the best score as "best" or as cands[0][0], and optionally "frac"
    residual  the largest score after blanking the best spot's predicted lines
    support   per-aircraft support at the best spot (see _z for the accepted forms)

    Returns dict(v1, v2, v22, v3, v31, kept, conditions, best, second, null_best, nulls_used, nulls_degenerate).
    """
    cands = [tuple(c) for c in cands]
    v1, kept = field.verdict(cands, threshold=threshold, tie=tie, clear=clear)
    kept_idx = list(range(len(kept)))      # verdict keeps a prefix of the (sorted) candidates
    best = float(cands[0][0]) if cands else float("nan")
    second = float(cands[1][0]) if len(cands) > 1 else 0.0
    live = [n for n in nulls if not is_degenerate(n, degenerate_frac)]
    flips = [n for n in live if n.get("kind") == "flip"]
    null_best = max((null_score(n) for n in live), default=float("nan"))
    residual = float("nan") if residual is None else float(residual)
    z = sorted((_z(s) for s in support), reverse=True)

    a = len(live) > 0 and all(n["verdict"] == "nothing" for n in live)
    a_flip = len(flips) > 0 and all(n["verdict"] == "nothing" for n in flips)
    b = len(live) > 0 and bool(cands) and best >= null_ratio * null_best
    c = len(live) > 0 and residual < null_best
    d = bool(cands) and second < runner_up * best
    e = sum(1 for v in z if v >= support_min) >= support_count
    f = len(z) > 1 and z[1] >= support_ratio * z[0]

    v2 = "one" if (a and b and c and d) else v1
    v22 = "one" if (a and b and c and d and e and f) else v1
    v3 = "one" if (a and b and c and d) else "nothing"
    v31 = "one" if (v1 == "one" and a_flip and b and c and d) else "nothing"
    # v3.2: v3 with the flip-only veto and no v1 requirement. The final rule
    v32 = "one" if (a_flip and b and c and d) else "nothing"
    return dict(v1=v1, v2=v2, v22=v22, v3=v3, v31=v31, v32=v32, kept=kept_idx,
                conditions=dict(a=bool(a), a_flip=bool(a_flip), b=bool(b), c=bool(c), d=bool(d), e=bool(e), f=bool(f)),
                best=best, second=second, null_best=None if math.isnan(null_best) else float(null_best),
                nulls_used=len(live), nulls_degenerate=len(nulls) - len(live))
