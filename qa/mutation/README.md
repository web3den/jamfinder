# Mutation testing, and tests generated to kill the survivors

Coverage says which lines the tests ran. Mutation testing says whether the tests would notice if a line were
wrong: it plants one small bug at a time (a `>=` turned into `>`, an `and` into `or`, a constant nudged) and
runs the tests. A bug the tests let through is a surviving mutant.

    python -m qa.mutation.mutate jf/rules.py tests/test_rules.py                 # score and survivors
    python -m qa.mutation.guided jf/rules.py tests/test_rules.py                 # hand survivors to a model
    docker build -f qa/Dockerfile -t jamfinder-qa . && docker run --rm --network none jamfinder-qa

## The reporting rule: full coverage, a quarter of the bugs missed

`jf/rules.py` decides whether to report a transmitter. Its tests cover every line and every branch, yet 28 of 118
planted bugs passed them. Each survivor was then given to a model with one instruction: write the test that
catches this exact bug ([RESULT_rules.md](RESULT_rules.md)).

| | before | after |
|---|---|---|
| line coverage | 100% | 100% |
| branch coverage | 100% | 100% |
| mutation score | **76%** (90 of 118) | **98%** (116 of 118) |
| tests added | | 13, all checked in the sandbox |

The model never judges its own tests. Each one was kept only if it passed on the real code, failed on its mutant
through an assert (not a crash), and imported nothing it should not. Three first attempts were rejected and sent
back once with the pytest output. Survivors already killed by an earlier generated test cost no model call. In
all: 17 model calls, $0.09.

The 2 survivors left are equivalent mutants. Both change `len(live) > 0` to `len(live) >= 0`; with no controls the
comparison that follows is with NaN (the largest of no control scores), which is always false, so the result
cannot change. The model said so; the claim was then checked against the code, since a model's "equivalent" is
only a claim.

What the survivors were: the boundary of the support threshold (`>=` vs `>`), the sorting direction of the
support values (`reverse=True` vs `False`: condition (f) would read the weakest aircraft), the exact-half case of
a degenerate control, a missing runner-up, and five ways to break rule v2.2's chain of `and`s. Real gaps, in the
file that decides what gets reported.

A caveat that comes with this technique: a generated test pins current behaviour. If that behaviour is wrong, it
pins the bug. That is why the prompt asks for expected values from the written rule definitions, and why the
generated file is reviewed like any other change.

## The geometry: 0%, and why properties alone were not enough

`jf/geo.py` (coordinates) had no direct tests: mutation score 0% against the old geometry tests. Property tests
(`qa/properties`) raised it to 77%; the survivors were the WGS84 constants, which no self-consistency check can
catch. Differential tests against an independent library and the published constants (`qa/differential`)
raised it to 91%.

## Why a runner of our own

[mutmut](https://github.com/boxed/mutmut) is the standard tool for Python. `mutate.py` is about 250 lines so that
every step is visible, and because the other parts of this framework need two things from it: aiming at only the
lines a change touched (`qa/bugfix_loop`) and handing each survivor's diff to a model (`guided.py`). Every mutant
runs in the sandbox, several at a time. In CI it runs in a container with the network off and fails the build
below 95%.
