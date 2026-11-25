# The test oracle problem

A test oracle is whatever decides that an output is correct. If a model writes an implementation and then the
tests for it, both come from the same understanding. When that understanding is wrong, the tests confirm the
mistake: they show internal consistency, not correctness. This is a common-mode failure.

    python -m qa.oracle.run                  # re-runs the experiment (recorded model answers replay for free)
    python -m pytest qa/oracle               # the independent oracle accepts the real code, rejects the bug

## The experiment

One function, the bistatic Doppler shift of an echo, with one planted mistake: the sign of the transmitter leg
(`subject.py`). The same model was asked for tests three ways, four times each, and every suite ran against the
wrong code and the right code in the sandbox. Full table: [RESULT.md](RESULT.md).

| who wrote the expected values | passes the WRONG code | rejects the RIGHT code |
|---|---|---|
| A: the model, shown the (wrong) code: "write tests for this function" | 3 of 4 suites, 6/6 tests each | 4 of 4 suites |
| B: the model, shown only the one-sentence requirement | 0 of 4 suites | 1 of 4 suites (2 wrong expectations) |
| C: physics written down without the code (`independent_oracle.py`) | no: 0 of 4 checks pass | no: 4 of 4 checks pass |

Tests written from the code passed the bug and would have rejected the correct code. The fourth suite of A
did notice something, but still rejected the right code too.

The independent oracle (C) takes its expected values from places the code cannot influence:

- first principles: the shift is minus the rate of change of the path length over the wavelength;
- a textbook limit: with transmitter and receiver in one place it must become radar's -2 v·u / λ;
- symmetry: the path is as long one way as the other, so transmitter and receiver may swap;
- a hand calculation: one geometry worked out on paper.

Requirements-derived tests (B) did much better than code-derived ones, but not perfectly: one of the four suites
had two wrong expectations of its own. Expected values need a source independent of the implementation, and
someone who checks them.

Files: `subject.py`, `independent_oracle.py`, `run.py`, `RESULT.md`, `test_oracle.py`.
