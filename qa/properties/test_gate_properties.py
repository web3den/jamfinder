"""Property-based tests of the reporting rule (jf/rules.py): rules that must hold for every input, not for five.

Hypothesis generates thousands of rule inputs (candidate scores, control-search scores, residuals, per-aircraft
support), looks for one that breaks a property, and shrinks it to the simplest failing case.
The scoring rule here is v3.2 ("v32"): report "one" if the flip control says nothing, the best spot beats the
controls by the ratio, the residual stays below the controls, and the runner-up is clearly weaker.

FINDING-001 (strict xfail below): a stronger control search can turn "nothing" into "one". See README.md.
"""
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st

from jf import rules
from qa.properties.strategies import quiet, rule_input, score


def v32(x):
    return rules.evaluate(x["cands"], x["nulls"], x["residual"], x["support"])["v32"]


def live(x):
    return [i for i, n in enumerate(x["nulls"]) if not rules.is_degenerate(n)]


# ---- properties that hold ----------------------------------------------------------------------------------------

@given(rule_input())
@settings(max_examples=500)
def test_the_verdict_is_exactly_its_written_conditions(x):
    """Contract: v3.2 says "one" if and only if conditions a', b, c and d all hold."""
    out = rules.evaluate(x["cands"], x["nulls"], x["residual"], x["support"])
    c = out["conditions"]
    assert (out["v32"] == "one") == (c["a_flip"] and c["b"] and c["c"] and c["d"])
    assert out["v32"] in ("one", "nothing") and out["v1"] in ("one", "nothing", "ambiguous")


@given(rule_input(), st.integers(-20, 20))
@settings(max_examples=500)
def test_the_unit_of_the_scores_does_not_matter(x, power):
    """Every condition of v3.2 is a ratio, so scaling all scores together cannot change the verdict.
    Scaling by a power of two is exact in floating point, so rounding cannot fake a failure."""
    k = 2.0 ** power
    y = dict(x, cands=[(s * k, *rest) for s, *rest in x["cands"]], residual=x["residual"] * k,
             nulls=[dict(n, best=n["best"] * k) for n in x["nulls"]])
    assert v32(y) == v32(x)


@given(rule_input(), st.randoms(use_true_random=False))
@settings(max_examples=300)
def test_the_order_of_the_control_searches_does_not_matter(x, rnd):
    y = dict(x, nulls=x["nulls"][:])
    rnd.shuffle(y["nulls"])
    assert v32(y) == v32(x)


@given(rule_input(), score, st.sampled_from(["one", "nothing", "ambiguous"]), st.floats(0.0, 0.499))
@settings(max_examples=300)
def test_a_degenerate_control_has_no_say(x, best, verdict, frac):
    """A control that kept under half of the aircraft time is not a control; whatever it says changes nothing."""
    y = dict(x, nulls=x["nulls"] + [dict(kind="shift", best=best, verdict=verdict, frac=frac)])
    assert v32(y) == v32(x)


@given(rule_input(), st.floats(0.0, 1000.0))
@settings(max_examples=500)
def test_a_stronger_best_spot_never_lowers_confidence(x, extra):
    y = dict(x, cands=[(x["cands"][0][0] + extra, 0.0, 0.0, 0.0)] + x["cands"][1:])
    assert not (v32(x) == "one" and v32(y) == "nothing")


# ---- a property that does not hold: FINDING-001 ----------------------------------------------------------------

@pytest.mark.xfail(strict=True, reason="FINDING-001: condition (c) compares the residual with the controls, "
                                       "so a stronger control can satisfy it; see qa/properties/README.md")
@given(rule_input(), quiet, st.data())
@settings(max_examples=1000)
def test_more_evidence_against_never_raises_confidence(x, louder, data):
    """A control search finds a spurious spot where none can be real. If one control finds a LOUDER spurious
    spot (still too weak to count as a find of its own), there is more evidence of false spots, so the rule
    should never become more willing to report."""
    idx = live(x)
    assume(idx)
    i = data.draw(st.sampled_from(idx))
    assume(louder > x["nulls"][i]["best"])
    y = dict(x, nulls=[dict(n, best=louder, verdict="nothing") if j == i else n for j, n in enumerate(x["nulls"])])
    assume(x["nulls"][i]["verdict"] == "nothing")
    assert not (v32(x) == "nothing" and v32(y) == "one"), (
        f"control {i} rose from {x['nulls'][i]['best']:.3g} to {louder:.3g} and the verdict went "
        f"from nothing to one (residual {x['residual']:.3g}, best {x['cands'][0][0]:.3g})")
