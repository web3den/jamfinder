# Just-in-time tests: a 'clean-up' of the reporting rule (built-in demo)

File: `jf/rules.py`. Changed functions: 2; documentation only: null_score (no behaviour to test).

| function | risk | why | behaviour | decision |
|---|---|---|---|---|
| `evaluate` | high (6) | high-risk file; traces to REQ-GATE-001, REQ-GATE-002, REQ-GATE-003, REQ-GATE-004, REQ-GATE-005; behaviour differs | DIFFERS | a human confirms the behaviour change is intended |
| `is_degenerate` | high (7) | high-risk file; comparisons, constants or arithmetic changed; traces to REQ-GATE-003; behaviour differs | DIFFERS | a human confirms the behaviour change is intended |

## `jf/rules.py:evaluate`

Smallest input found where old and new disagree: `{'cands': [(0.0, 0.0, 0.0, 0.0)], 'nulls': [{'kind': 'flip', 'best': 0.0, 'verdict': 'nothing', 'frac': 0.0}], 'residual': 0.0, 'support': []}`

- old: `('returns', {'v1': 'nothing', 'v2': 'nothing', 'v22': 'nothing', 'v3': 'nothing', 'v31': 'nothing', 'v32': 'nothing', 'kept': [], 'conditions': {'a': False, 'a_flip': False, 'b': False, 'c': False, 'd': False, 'e': False, 'f': False}, 'best': 0.0, 'second': 0.0, 'null_best': None, 'nulls_used': 0, 'nulls_degenerate': 1})`
- new: `('raises', 'ZeroDivisionError')`

What changed: `evaluate()` now divides by `best` when computing rule `d`, so an input with `best == 0.0` raises `ZeroDivisionError` instead of returning the old all-`nothing` result. This changes the behavior for the smallest case where there is one zero-scored candidate and one flip null.

Question for the author: **Was changing rule `d` to use `second / best < runner_up` with `best == 0.0` intended?**

Catching test (kept: passes on old, fails on new):

```python
import pytest

from jf import rules


def test_jit_evaluate_keeps_old_behaviour():
    assert rules.evaluate(
        cands=[(0.0, 0.0, 0.0, 0.0)],
        nulls=[{'kind': 'flip', 'best': 0.0, 'verdict': 'nothing', 'frac': 0.0}],
        residual=0.0,
        support=[],
    ) == {
        'v1': 'nothing',
        'v2': 'nothing',
        'v22': 'nothing',
        'v3': 'nothing',
        'v31': 'nothing',
        'v32': 'nothing',
        'kept': [],
        'conditions': {'a': False, 'a_flip': False, 'b': False, 'c': False, 'd': False, 'e': False, 'f': False},
        'best': 0.0,
        'second': 0.0,
        'null_best': None,
        'nulls_used': 0,
        'nulls_degenerate': 1,
    }
```

## `jf/rules.py:is_degenerate`

Smallest input found where old and new disagree: `{'kind': 'shift', 'best': 0.0, 'verdict': 'nothing', 'degenerate': True}`

- old: `('returns', True)`
- new: `('returns', False)`

What changed: `is_degenerate` used to fall back to the `degenerate` field when `frac` was missing; the new version ignores `degenerate` and treats missing `frac` as `1.0`, which changes this case from `True` to `False`.

Question for the author: **Was it intended to stop honoring `row['degenerate']` when `frac` is absent?**

Catching test (kept: passes on old, fails on new):

```python
from jf import rules


def test_jit_is_degenerate_keeps_old_behaviour():
    row = {'kind': 'shift', 'best': 0.0, 'verdict': 'nothing', 'degenerate': True}
    assert rules.is_degenerate(row) is True
```
