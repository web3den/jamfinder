"""Design by contract, switched on for a whole test run:

    python -m pytest -p qa.specs.contracts tests qa/metamorphic

A contract states what must be true when a function is called (precondition), what must be true of its result
(postcondition), and what must stay true throughout (invariant). Here the contracts of the key functions are
checked on EVERY call that the test suite makes, deep inside the pipeline as well as in the tests themselves.
A broken contract stops the test that caused it, with the contract's name. Outside such a run nothing is
wrapped, so the library pays nothing for it.
"""
import functools
from collections import Counter
from dataclasses import dataclass, field

import numpy as np

from jf import field as jf_field
from jf import geo, rules, scatter, tracks

VERDICTS = {"one", "nothing", "ambiguous"}


class ContractViolation(AssertionError):
    pass


@dataclass
class Contract:
    owner: object                    # the module or class that holds the function
    name: str
    pre: list = field(default_factory=list)     # (description, check(*args, **kw) -> bool)
    post: list = field(default_factory=list)    # (description, check(result, *args, **kw) -> bool)


def _doppler_bound(f, p, v, tx, rx, lam):
    """Each path leg shortens at most at the aircraft's speed: |shift| <= 2 |v| / lambda."""
    return bool(np.all(np.abs(f) <= 2 * np.linalg.norm(v, axis=-1) / lam + 1e-6))


def _evaluate_consistent(out, *a, **k):
    c = out["conditions"]
    return out["v32"] == ("one" if c["a_flip"] and c["b"] and c["c"] and c["d"] else "nothing")


CONTRACTS = [
    Contract(tracks, "doppler_pv",
             pre=[("wavelength is positive", lambda p, v, tx, rx, lam: lam > 0),
                  ("positions and velocities have matching shapes", lambda p, v, *a: np.shape(p) == np.shape(v))],
             post=[("finite", lambda f, *a: bool(np.all(np.isfinite(f)))),
                   ("|shift| <= 2 |v| / wavelength", _doppler_bound)]),
    Contract(geo.Frame, "to_enu",
             post=[("finite", lambda e, *a: bool(np.all(np.isfinite(e)))),
                   ("three coordinates per point", lambda e, *a: np.shape(e)[-1] == 3)]),
    Contract(scatter, "whiten",
             pre=[("one frequency per spectrum column", lambda S, f, *a, **k: np.shape(S)[-1] == np.size(f))],
             post=[("same shape as the input", lambda out, S, *a, **k: out[0].shape == np.shape(S)),
                   ("non-negative and finite", lambda out, *a, **k: bool(np.all(np.isfinite(out[0]) & (out[0] >= 0))))]),
    Contract(jf_field, "verdict",
             pre=[("candidates sorted best first",
                   lambda cands, *a, **k: all(x[0] >= y[0] for x, y in zip(cands, cands[1:])))],
             post=[("a known label", lambda out, *a, **k: out[0] in VERDICTS),
                   ("'one' keeps exactly one candidate", lambda out, *a, **k: (out[0] == "one") == (len(out[1]) == 1)),
                   ("kept candidates come from the top two", lambda out, cands, *a, **k: len(out[1]) <= 2)]),
    Contract(rules, "evaluate",
             post=[("v3.2 is 'one' exactly when a', b, c and d hold", _evaluate_consistent),
                   ("every verdict is a known label", lambda out, *a, **k: all(out[v] in VERDICTS
                                                                                for v in rules.VERDICTS))]),
]

CALLS, BROKEN = Counter(), Counter()


def _wrap(contract, fn):
    label = f"{getattr(contract.owner, '__name__', contract.owner)}.{contract.name}"

    @functools.wraps(fn)
    def checked(*args, **kw):
        CALLS[label] += 1
        call_args = args[1:] if isinstance(contract.owner, type) else args      # methods: leave out self
        for what, ok in contract.pre:
            if not ok(*call_args, **kw):
                BROKEN[label] += 1
                raise ContractViolation(f"{label}: precondition broken: {what}")
        result = fn(*args, **kw)
        for what, ok in contract.post:
            if not ok(result, *call_args, **kw):
                BROKEN[label] += 1
                raise ContractViolation(f"{label}: postcondition broken: {what}")
        return result
    return checked


def pytest_configure(config):
    for c in CONTRACTS:
        setattr(c.owner, c.name, _wrap(c, getattr(c.owner, c.name)))


def pytest_terminal_summary(terminalreporter):
    tr = terminalreporter
    tr.section("design-by-contract checks")
    for c in CONTRACTS:
        label = f"{getattr(c.owner, '__name__', c.owner)}.{c.name}"
        tr.write_line(f"  {label:<28} {CALLS[label]:>8} calls checked   {BROKEN[label]} broken   "
                      f"({len(c.pre)} pre, {len(c.post)} post)")
