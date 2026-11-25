# Differential testing

The same input through this code and through an independent implementation; any disagreement is investigated.
Agreement is evidence, not proof (both can share a mistake). Disagreement always means something.

    python -m pytest qa/differential
    python -m qa.differential.nversion        # re-runs the N-version comparison below (writes NVERSION.md)

## Against reference implementations (`test_reference_implementations.py`)

| this code | independent reference | agreement |
|---|---|---|
| `jf/geo.py` coordinates | [pymap3d](https://github.com/geospace-code/pymap3d), a separate geodesy library | 1 µm, 300 generated points per function |
| `jf/iq.py` spectrogram | `scipy.signal.stft` | relative 1e-4, two window settings |
| `jf/tracks.py` Doppler | the path-length derivative, written here from first principles | 1e-6 Hz |
| WGS84, foot, knot constants | their published definitions | exact |

What it found. The geometry code had no direct tests; its mutation score against the old tests was 0%. The
property tests lifted that to 77%, and the survivors were the Earth model's constants: a wrong ellipsoid is
perfectly self-consistent, so no property can see it. Only an independent reference can. With these tests the
score is 91%; the last 5 mutants change the starting guess or the count of an iteration that converges anyway.

One disagreement was the reference's fault: Hypothesis found a fast aircraft 220 m from the transmitter where a
1-ms finite-difference step was itself off by 1e-4 Hz. The step is now 10 µs. A disagreement says "look", not
"the code is wrong".

## N-version programming (`nversion.py`, `NVERSION.md`)

A model wrote a second implementation of the reporting rule from its written definition only, never seeing
`jf/rules.py`. The two were compared on generated inputs, inside the sandbox; Hypothesis shrank every
disagreement. Each one was a finding about the definition, not the code:

| disagreement | smallest case | what it showed |
|---|---|---|
| condition (d) with one candidate | one candidate of score 1 | the definition says "the runner-up < 0.75 x best" and is silent when there is none. The code counts a missing runner-up as 0, so a lone candidate can be reported. **FINDING-003** |
| (b), (c): a control marked `degenerate: true` without `frac` | best 0, flagged flip control | the docstring says a control without `frac` is a real one; the code also honours the older `degenerate` flag. The documentation is incomplete. **FINDING-004** |
| (a'): a flip control with `frac` 0 | a degenerate flip control | the summary given to the model said "degenerate nulls take no part" without listing (a'); the docstring in the code lists it. A summary lost a clause. |

`test_nversion.py` keeps this honest: where the definition is unambiguous, both versions must agree on 2000
generated inputs; where it was not, the code's current choice is pinned with the finding's name, so changing it
takes a decision.

## Files

- `test_reference_implementations.py`: the reference comparisons
- `nversion.py`: writes `nversion_generated.py` (the second version) and `NVERSION.md`
- `test_nversion.py`: agreement where the definition is clear; FINDING-003 and -004 pinned
