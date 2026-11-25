# Mutation testing of `jf/rules.py`

Tests: `tests/test_rules.py`. Then the surviving mutants were handed to a model, one by one (`qa/mutation/guided.py`).

| | before | after |
|---|---|---|
| Line coverage | 100% | |
| Branch coverage | 100% | |
| Mutants | 118 | 118 |
| Killed | 90 | 116 |
| Survived | 28 | 2 |
| **Mutation score** | **76%** | **98%** |
| Tests added | | 13, in `qa/mutation/generated/test_rules_killers.py` |

Every added test passed on the real code and failed on its mutant, in the sandbox, before it was kept. Model calls: 17, cost $0.09 when recorded (replays are free).

## What happened to each survivor

| mutant | function | planted bug | outcome | model calls |
|---|---|---|---|---|
| `rules.py:33:2` | `<module>` | `10.0  ->  11.0` in `SUPPORT_MIN = 11.0      # (e): support threshold per aircraft` | new test kept | 1 |
| `rules.py:39:12` | `<module>` | `'a'  ->  'XXaXX'` in `CONDITIONS = ('XXaXX', "a_flip", "b", "c", "d", "e", "f")` | new test kept | 1 |
| `rules.py:39:13` | `<module>` | `'a_flip'  ->  'XXa_flipXX'` in `CONDITIONS = ("a", 'XXa_flipXX', "b", "c", "d", "e", "f")` | new test kept | 1 |
| `rules.py:39:14` | `<module>` | `'b'  ->  'XXbXX'` in `CONDITIONS = ("a", "a_flip", 'XXbXX', "c", "d", "e", "f")` | killed by an earlier generated test | 0 |
| `rules.py:39:15` | `<module>` | `'c'  ->  'XXcXX'` in `CONDITIONS = ("a", "a_flip", "b", 'XXcXX', "d", "e", "f")` | killed by an earlier generated test | 0 |
| `rules.py:39:16` | `<module>` | `'d'  ->  'XXdXX'` in `CONDITIONS = ("a", "a_flip", "b", "c", 'XXdXX', "e", "f")` | killed by an earlier generated test | 0 |
| `rules.py:39:17` | `<module>` | `'e'  ->  'XXeXX'` in `CONDITIONS = ("a", "a_flip", "b", "c", "d", 'XXeXX', "f")` | killed by an earlier generated test | 0 |
| `rules.py:39:18` | `<module>` | `'f'  ->  'XXfXX'` in `CONDITIONS = ("a", "a_flip", "b", "c", "d", "e", 'XXfXX')` | killed by an earlier generated test | 0 |
| `rules.py:52:28` | `is_degenerate` | `<  ->  <=` in `return float(row["frac"]) <= degenerate_frac` | new test kept | 2 |
| `rules.py:53:29` | `is_degenerate` | `'degenerate'  ->  'XXdegenerateXX'` in `return bool(row.get('XXdegenerateXX', False))` | new test kept | 1 |
| `rules.py:84:43` | `evaluate` | `>  ->  >=` in `second = float(cands[1][0]) if len(cands) >= 1 else 0.0` | killed by an earlier generated test | 0 |
| `rules.py:84:44` | `evaluate` | `1  ->  2` in `second = float(cands[1][0]) if len(cands) > 2 else 0.0` | new test kept | 1 |
| `rules.py:84:45` | `evaluate` | `0.0  ->  1.0` in `second = float(cands[1][0]) if len(cands) > 1 else 1.0` | new test kept | 1 |
| `rules.py:89:53` | `evaluate` | `True  ->  False` in `z = sorted((_z(s) for s in support), reverse=False)` | new test kept | 2 |
| `rules.py:91:55` | `evaluate` | `0  ->  1` in `a = len(live) > 1 and all(n["verdict"] == "nothing" for n in live)` | killed by an earlier generated test | 0 |
| `rules.py:93:66` | `evaluate` | `>  ->  >=` in `b = len(live) >= 0 and bool(cands) and best >= null_ratio * null_best` | model says equivalent (unverified): This mutation is not observable. When there are no non-degenerate nulls, `live` is empty, so the original sets `b` false bec | 1 |
| `rules.py:94:72` | `evaluate` | `>  ->  >=` in `c = len(live) >= 0 and residual < null_best` | model says equivalent (unverified): The mutation changes `len(live) > 0` to `len(live) >= 0` in condition `c`. Since `len(live)` is never negative, the only cas | 1 |
| `rules.py:96:80` | `evaluate` | `>=  ->  >` in `e = sum(1 for v in z if v > support_min) >= support_count` | killed by an earlier generated test | 0 |
| `rules.py:97:82` | `evaluate` | `>  ->  >=` in `f = len(z) >= 1 and z[1] >= support_ratio * z[0]` | new test kept | 1 |
| `rules.py:97:83` | `evaluate` | `1  ->  2` in `f = len(z) > 2 and z[1] >= support_ratio * z[0]` | new test kept | 1 |
| `rules.py:97:86` | `evaluate` | `>=  ->  >` in `f = len(z) > 1 and z[1] > support_ratio * z[0]` | new test kept | 1 |
| `rules.py:97:87` | `evaluate` | `*  ->  /` in `f = len(z) > 1 and z[1] >= support_ratio / z[0]` | killed by an earlier generated test | 0 |
| `rules.py:97:88` | `evaluate` | `0  ->  1` in `f = len(z) > 1 and z[1] >= support_ratio * z[1]` | killed by an earlier generated test | 0 |
| `rules.py:100:94` | `evaluate` | `and  ->  or` in `v22 = "one" if (a or b and c and d and e and f) else v1` | new test kept | 1 |
| `rules.py:100:95` | `evaluate` | `and  ->  or` in `v22 = "one" if (a and b or c and d and e and f) else v1` | new test kept | 1 |
| `rules.py:100:96` | `evaluate` | `and  ->  or` in `v22 = "one" if (a and b and c or d and e and f) else v1` | killed by an earlier generated test | 0 |
| `rules.py:100:97` | `evaluate` | `and  ->  or` in `v22 = "one" if (a and b and c and d or e and f) else v1` | killed by an earlier generated test | 0 |
| `rules.py:100:98` | `evaluate` | `and  ->  or` in `v22 = "one" if (a and b and c and d and e or f) else v1` | killed by an earlier generated test | 0 |

## Still surviving

| mutant | function | line after the change |
|---|---|---|
| `rules.py:93:66` | `evaluate` | `b = len(live) >= 0 and bool(cands) and best >= null_ratio * null_best` |
| `rules.py:94:72` | `evaluate` | `c = len(live) >= 0 and residual < null_best` |
