"""Tests written by a model to kill specific surviving mutants (qa/mutation/guided.py).

Each test passed on the real code and failed on its mutant, in the sandbox, before it was kept here.
Model: gpt-5.4-mini. Review these like any other change: they pin current behaviour.
"""
import math

import numpy as np
import pytest

from jf import field, rules


# kills rules.py:33:2  (<module>: 10.0  ->  11.0)
def test_kills_line33_constant_2():
    from jf import rules

    cands = [(20.0, 0, 0, 0), (5.0, 0, 0, 0)]
    nulls = [{"kind": "shift", "verdict": "nothing", "best": 1.0}]
    residual = 0.5
    support = [(10.0, "a"), (10.0, "b"), (10.0, "c")]

    result = rules.evaluate(cands, nulls, residual, support)
    assert result["conditions"]["e"] is True


# kills rules.py:39:12  (<module>: 'a'  ->  'XXaXX')
def test_kills_line39_value_12():
    from jf import rules

    assert rules.CONDITIONS[0] == "a"


# kills rules.py:39:13  (<module>: 'a_flip'  ->  'XXa_flipXX')
def test_kills_line39_value_13():
    assert rules.CONDITIONS == ("a", "a_flip", "b", "c", "d", "e", "f")


# kills rules.py:52:28  (is_degenerate: <  ->  <=)
def test_kills_line52_boundary_28():
    cands = [(30.0, 0, 0, 0)]
    nulls = [{"kind": "shift", "verdict": "nothing", "best": 10.0, "frac": 0.5}]
    result = rules.evaluate(cands, nulls, residual=9.0, support=[12.0, 11.0, 10.0])

    assert result["nulls_used"] == 1
    assert result["nulls_degenerate"] == 0
    assert result["conditions"]["a"] is True
    assert result["conditions"]["b"] is True
    assert result["conditions"]["c"] is True
    assert result["v3"] == "one"


# kills rules.py:53:29  (is_degenerate: 'degenerate'  ->  'XXdegenerateXX')
def test_kills_line53_value_29():
    out = rules.evaluate(
        cands=[(20.0, 0, 0, 0)],
        nulls=[{"kind": "shift", "verdict": "one", "best": 5.0, "degenerate": True}],
        residual=0.0,
        support=[12.0, 11.0, 10.0],
    )
    assert out["nulls_used"] == 0
    assert out["nulls_degenerate"] == 1


# kills rules.py:84:44  (evaluate: 1  ->  2)
def test_kills_line84_constant_44():
    result = rules.evaluate(
        cands=[(100.0, 0, 0, 0), (80.0, 0, 0, 0)],
        nulls=[
            {"kind": "flip", "verdict": "nothing", "best": 20.0},
            {"kind": "shift", "verdict": "nothing", "best": 15.0},
        ],
        residual=10.0,
        support=[12.0, 11.0, 10.0],
    )
    assert result["v32"] == "nothing"


# kills rules.py:84:45  (evaluate: 0.0  ->  1.0)
def test_kills_line84_constant_45():
    cands = [(1.0, None, None, None)]
    nulls = [
        {"kind": "shift", "verdict": "nothing", "best": 0.2, "frac": 0.6},
        {"kind": "flip", "verdict": "nothing", "best": 0.2, "frac": 0.6},
    ]
    result = rules.evaluate(
        cands,
        nulls,
        residual=0.1,
        support=[12.0, 11.0, 10.0],
        threshold=0.5,
    )
    assert result["v3"] == "one"


# kills rules.py:89:53  (evaluate: True  ->  False)
def test_kills_line89_constant_53():
    result = rules.evaluate(
        cands=[(20.0, 0, 0, 0)],
        nulls=[],
        residual=0.0,
        support=[100.0, 1.0, 0.5],
    )
    assert result["conditions"]["f"] is False


# kills rules.py:97:82  (evaluate: >  ->  >=)
def test_kills_line97_boundary_82():
    result = rules.evaluate(
        cands=[(20.0, 0, 0, 0)],
        nulls=[],
        residual=0.0,
        support=[12.0],
    )
    assert result["conditions"]["f"] is False


# kills rules.py:97:83  (evaluate: 1  ->  2)
def test_kills_line97_constant_83():
    result = rules.evaluate(
        cands=[(20.0, 0, 0, 0)],
        nulls=[],
        residual=0.0,
        support=[20.0, 6.0],
    )
    assert result["conditions"]["f"] is True


# kills rules.py:97:86  (evaluate: >=  ->  >)
def test_kills_line97_boundary_86():
    cands = [(20.0, 0, 0, 0), (5.0, 0, 0, 0)]
    nulls = [{"kind": "shift", "verdict": "nothing", "best": 5.0}]
    residual = 4.0
    support = [("ac1", 40.0), ("ac2", 10.0), ("ac3", 10.0)]

    result = rules.evaluate(cands, nulls, residual, support)

    assert result["conditions"]["f"] is True
    assert result["v22"] == "one"


# kills rules.py:100:94  (evaluate: and  ->  or)
def test_kills_line100_logic_94():
    cands = [
        (1.0, 0, 0, 0),
        (1.0, 0, 0, 0),
    ]
    nulls = [
        {"kind": "shift", "verdict": "nothing", "best": 5.0, "frac": 1.0},
    ]
    residual = 6.0
    support = [1.0, 2.0]

    result = rules.evaluate(cands, nulls, residual, support)

    assert result["v22"] == "nothing"


# kills rules.py:100:95  (evaluate: and  ->  or)
def test_kills_line100_logic_95():
    cands = [(10.0, 0, 0, 0), (6.0, 0, 0, 0)]
    nulls = [
        {"kind": "shift", "verdict": "one", "best": 1.0, "frac": 0.9},
    ]
    residual = 0.5
    support = [("ac1", 12.0), ("ac2", 11.0), ("ac3", 10.0)]

    result = rules.evaluate(cands, nulls, residual, support)

    assert result["v1"] == "nothing"
    assert result["conditions"] == {"a": False, "a_flip": False, "b": True, "c": True, "d": True, "e": True, "f": True}
    assert result["v22"] == "nothing"
