# Specification-driven development: requirements, traceability, contracts

When implementation is cheap, the precision of the specification decides the quality of the result. This
folder turns "what correct means" into things a machine can check.

    python -m qa.specs.trace                                   # requirements -> tests -> results
    python -m pytest -p qa.specs.contracts tests qa/metamorphic   # contracts checked on every call
    python -m qa.specs.spec_review                             # a vague requirement -> open questions

## Requirements with IDs (`requirements.toml`)

Each requirement has an ID, a source, a verification method (test, analysis or inspection, as in avionics
verification), the functions that implement it, and the tests or checks that verify it. Requirements raised
by QA and not yet accepted by the owner are marked `proposed`.

## Traceability (`trace.py`, [TRACEABILITY.md](TRACEABILITY.md))

`trace.py` runs every linked test and check and reports each requirement as VERIFIED, OPEN (a known, documented
failure), FAILED or NOT VERIFIED (nothing linked, or a linked test missing). It also lists tests that verify no
requirement: either they test internals, or a requirement was never written down. CI fails if an accepted
requirement is not verified.

Today: 16 requirements; the 14 accepted ones are VERIFIED by 44 tests and 2 static checks; the 2 proposed ones
(FINDING-001 and -002) are OPEN. 58 of the 102 tests verify no written requirement, mostly tests of internals,
which is itself worth a look: a test nobody can trace to a requirement is either missing its requirement or
testing an accident of the implementation.

The just-in-time tests (`qa/jit`) use the same file in the other direction: a change to a function that
implements a requirement is rated riskier.

## Design by contract (`contracts.py`)

Preconditions, postconditions and invariants of the key functions, checked on every call during a test run, deep
inside the pipeline as well as in the tests. Examples: no echo shifts more than 2 x speed / wavelength; the
whitened waterfall keeps its shape and stays finite and non-negative; `verdict` keeps exactly one candidate when
it says "one"; rule v3.2 says "one" exactly when its four conditions hold. Outside such a run nothing is wrapped,
so the library pays nothing.

One full run (`tests` and `qa`): 14,356 calls checked against 5 contracts, none broken.

| contract | calls checked |
|---|---|
| `tracks.doppler_pv`: finite, \|shift\| <= 2 \|v\| / λ, matching shapes, λ > 0 | 2,149 |
| `geo.Frame.to_enu`: finite, three coordinates per point | 1,706 |
| `scatter.whiten`: same shape, finite, non-negative | 14 |
| `field.verdict`: sorted input, known label, "one" keeps exactly one candidate | 5,250 |
| `rules.evaluate`: v3.2 matches its conditions, every verdict a known label | 5,237 |

## Specification review (`spec_review.py`, [SPEC_REVIEW.md](SPEC_REVIEW.md))

The vague requirement *"Report the transmitter's location when the evidence is strong enough"* went to one model,
which listed the 8 questions it leaves open, each with a testable criterion. A second model mapped each question
to the written requirements that settle it. Four are settled (what "strong enough" means, minimum evidence,
handling of bad position reports, operating conditions). Four are open product decisions: the form of the
report (point, area or both), the accuracy promised, the latency, and whether a report is updated as evidence
grows. Asking is the model's job; answering is a person's. The mapping is a suggestion, and lenient in places:
linking "duplicate or conflicting position reports" to the rule on degenerate control searches is a stretch.
