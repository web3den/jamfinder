"""The reporting rule, written twice: jf/rules.py and a second version a model wrote from the definition alone
(nversion_generated.py, reviewed before it was committed). See NVERSION.md for how they were compared.

Where the definition is unambiguous, both versions must agree on every input. Where it was not, the disagreement
was a finding, and the code's current choice is pinned here so that any change to it is deliberate.
"""
from hypothesis import given, settings

from jf import rules
from qa.differential.nversion_generated import rule_v32
from qa.properties.strategies import rule_input


# Inputs the definition settles: every control carries frac, the flip control is a real one, there is a runner-up.
# (Outside these, see FINDING-003 and FINDING-004 below.)
UNAMBIGUOUS = rule_input(min_cands=2, forms=("frac",), real_flip=True)


@given(UNAMBIGUOUS)
@settings(max_examples=2000)
def test_both_versions_agree_where_the_definition_is_clear(x):
    real = rules.evaluate(x["cands"], x["nulls"], x["residual"], x["support"])
    second = rule_v32(x["cands"], x["nulls"], x["residual"])
    assert {k: real["conditions"][k] for k in ("a_flip", "b", "c", "d")} == {k: second[k] for k in ("a_flip", "b", "c", "d")}
    assert real["v32"] == second["v32"]


FLIP = dict(kind="flip", best=1.0, verdict="nothing", frac=1.0)


def test_finding_003_a_single_candidate_counts_as_having_no_runner_up():
    """The definition says 'the runner-up < 0.75 x best' and is silent when there is no runner-up. The code takes
    a missing runner-up as 0, so one candidate alone can be reported; the second version refused it."""
    out = rules.evaluate([(3.0, 0, 0, 0)], [FLIP], 0.0, [])
    assert out["conditions"]["d"] is True and out["v32"] == "one"


def test_finding_004_the_old_degenerate_flag_still_counts():
    """The docstring says a control without frac counts as non-degenerate; the code also honours the older
    'degenerate' flag. The second version, following the text, kept such a control."""
    flagged = dict(kind="flip", best=1.0, verdict="nothing", degenerate=True)
    assert rules.is_degenerate(flagged) is True
    assert rules.evaluate([(100.0, 0, 0, 0)], [flagged], 0.0, [])["nulls_used"] == 0
