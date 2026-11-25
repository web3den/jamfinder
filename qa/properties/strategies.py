"""Input generators shared by the property tests and the just-in-time tests: what a valid input of the reporting
rule looks like. Kept apart from the tests so both use one definition of "a valid input"."""
from hypothesis import strategies as st

from jf import field

score = st.floats(0.0, 1000.0, allow_nan=False)
quiet = st.floats(0.0, field.THRESHOLD * 0.99)          # a control score below its own v1 threshold


@st.composite
def null_row(draw, kind, forms=("frac", "flag", "none"), min_frac=0.0):
    """One control search, as the pipeline stores it. Older result files mark degenerate controls with a
    "degenerate" flag instead of "frac"; both forms occur."""
    best = draw(score)
    verdict = "nothing" if best < field.THRESHOLD else draw(st.sampled_from(["one", "ambiguous", "nothing"]))
    row = dict(kind=kind, best=best, verdict=verdict)
    form = draw(st.sampled_from(forms))
    if form == "frac":
        row["frac"] = draw(st.floats(min_frac, 1.0))
    elif form == "flag":
        row["degenerate"] = draw(st.booleans())
    return row


@st.composite
def rule_input(draw, min_cands=1, forms=("frac", "flag", "none"), real_flip=False):
    """One complete input of rules.evaluate, consistent the way the pipeline makes it:
    candidates sorted best first, each control's v1 label agrees with its score.

    min_cands   at least this many candidates
    forms       how controls may mark themselves degenerate ("frac", the old "flag", or not at all)
    real_flip   the flip control is never degenerate
    """
    cands = sorted(draw(st.lists(score, min_size=min_cands, max_size=5)), reverse=True)
    kinds = ["flip"] + draw(st.lists(st.just("shift"), max_size=4))
    nulls = [draw(null_row(k, forms, 0.5 if (real_flip and k == "flip") else 0.0)) for k in kinds]
    return dict(cands=[(s, 0.0, 0.0, 0.0) for s in cands], nulls=nulls,
                residual=draw(score), support=draw(st.lists(st.floats(-5.0, 500.0), max_size=8)))
