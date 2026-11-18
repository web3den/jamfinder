"""The edge cases of jf.rules follow the written definitions. Synthetic inputs only: no file is read."""
import math

import pytest

from jf import rules


def _check(out, **expect):
    for k, v in expect.items():
        got = out[k] if k in rules.VERDICTS else out["conditions"][k]
        assert got == v, (k, got, v, out)


def _cands_from_scores(scores):
    """Only the scores enter the rules; positions are placeholders."""
    return [(s, 0.0, 0.0, 0.0) for s in scores]


# ---- edge cases of the definitions (synthetic inputs) ------------------------------------------------------

def _null(kind, best, verdict="nothing", frac=None, delta=0.0):
    row = dict(kind=kind, delta=delta, verdict=verdict, best=best)
    if frac is not None:
        row["frac"] = frac
    return row


CLEAR_ONE = _cands_from_scores([100.0, 20.0, 10.0, 9.0])          # v1 "one"
SUPPORT = [50.0, 40.0, 30.0, 5.0]                                   # (e) and (f) hold


def test_degenerate_nulls_take_no_part():
    nulls = [_null("flip", 10.0), _null("shift", 20.0, frac=0.9, delta=300.0),
             _null("shift", 500.0, "one", frac=0.3, delta=1300.0)]
    out = rules.evaluate(CLEAR_ONE, nulls, 5.0, SUPPORT)
    assert out["nulls_used"] == 2 and out["nulls_degenerate"] == 1 and out["null_best"] == 20.0
    _check(out, v1="one", v2="one", v22="one", v3="one", v31="one", a=True, a_flip=True, b=True, c=True, d=True)


def test_no_nulls_no_report_under_v3_and_v31_while_v2_falls_back_to_v1():
    out = rules.evaluate(CLEAR_ONE, [], 5.0, SUPPORT)
    assert out["null_best"] is None
    _check(out, v1="one", v2="one", v22="one", v3="nothing", v31="nothing", a=False, a_flip=False, b=False, c=False)


def test_time_shift_null_one_vetoes_v3_but_not_v31():
    nulls = [_null("flip", 10.0), _null("shift", 25.0, "one", frac=0.95, delta=600.0)]
    out = rules.evaluate(CLEAR_ONE, nulls, 5.0, SUPPORT)
    _check(out, v1="one", v2="one", v3="nothing", v31="one", v32="one", a=False, a_flip=True, b=True, c=True, d=True)


def test_flip_null_not_nothing_vetoes_v31():
    nulls = [_null("flip", 25.0, "ambiguous"), _null("shift", 10.0, delta=600.0)]
    out = rules.evaluate(CLEAR_ONE, nulls, 5.0, SUPPORT)
    _check(out, v3="nothing", v31="nothing", v32="nothing", a=False, a_flip=False, b=True)


def test_missing_flip_null_blocks_v31_only():
    nulls = [_null("shift", 10.0, delta=-600.0), _null("shift", 12.0, delta=600.0)]
    out = rules.evaluate(CLEAR_ONE, nulls, 5.0, SUPPORT)
    _check(out, v3="one", v31="nothing", v32="nothing", a=True, a_flip=False)


def test_b_c_d_boundaries():
    nulls = [_null("flip", 10.0)]
    assert rules.evaluate(_cands_from_scores([30.0, 5.0]), nulls, 5.0, SUPPORT)["conditions"]["b"]       # 30 >= 3 x 10
    assert not rules.evaluate(_cands_from_scores([29.9, 5.0]), nulls, 5.0, SUPPORT)["conditions"]["b"]
    assert not rules.evaluate(CLEAR_ONE, nulls, 10.0, SUPPORT)["conditions"]["c"]                        # residual = floor
    assert rules.evaluate(CLEAR_ONE, nulls, 9.99, SUPPORT)["conditions"]["c"]
    out = rules.evaluate(_cands_from_scores([100.0, 75.0, 10.0]), nulls, 5.0, SUPPORT)                   # mirror twin kept
    _check(out, v1="ambiguous", v2="ambiguous", v3="nothing", v31="nothing", d=False)
    assert out["kept"] == [0, 1]


def test_v2_upgrades_a_v1_nothing_v31_does_not():
    """The Ottawa pattern: v1 "nothing" by the clear test (best < 1.6 x third) with every null-floor condition met."""
    cands = _cands_from_scores([100.0, 71.0, 70.0, 66.0])
    nulls = [_null("flip", 17.0), _null("shift", 27.0, delta=-600.0)]
    out = rules.evaluate(cands, nulls, 7.0, SUPPORT)
    _check(out, v1="nothing", v2="one", v22="one", v3="one", v31="nothing", v32="one")
    assert out["kept"] == []


def test_support_in_every_stored_form_gives_the_same_e_and_f():
    forms = [[50.0, 40.0, 9.0], [(50.0, "abc"), (40.0, "def"), (9.0, "123")],
             [["AAL1", "abc", 50.0], ["AAL2", "def", 40.0], ["12345", "123", 9.0]], [["AAL1", 50.0], ["AAL2", 40.0], ["X", 9.0]]]
    outs = [rules.evaluate(CLEAR_ONE, [_null("flip", 10.0)], 5.0, s)["conditions"] for s in forms]
    assert all(o == outs[0] for o in outs) and outs[0]["e"] is False and outs[0]["f"] is True
    assert rules.evaluate(CLEAR_ONE, [_null("flip", 10.0)], 5.0, [9.0, 50.0, 40.0])["conditions"] == outs[0]  # order-free
    with pytest.raises(ValueError):
        rules.evaluate(CLEAR_ONE, [_null("flip", 10.0)], 5.0, [["a", 1.0, 2.0]])


def test_null_best_from_stored_candidates_or_best_field():
    old_style = dict(kind="shift", delta=300.0, verdict="nothing", cands=[[12.5, 0, 0, 0], [3.0, 0, 0, 0]])
    assert rules.null_score(old_style) == 12.5 and rules.null_score(_null("flip", 7.0)) == 7.0
    assert not rules.is_degenerate(old_style) and rules.is_degenerate(_null("shift", 1.0, frac=0.49))
    assert math.isnan(rules.evaluate([], [], None, [])["best"])
