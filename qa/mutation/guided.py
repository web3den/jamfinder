"""Mutation-guided test generation: hand each surviving mutant to a model and ask for a test that kills it.

    python -m qa.mutation.guided jf/rules.py tests/test_rules.py          # writes qa/mutation/RESULT_rules.md

Not "write more tests", but "this exact bug gets past your tests: write the test that catches it".
The model never decides whether its test is good. The harness does, in the sandbox, for every test:
  1. the test passes on the real code          (it does not reject correct behaviour)
  2. the test fails on the mutant, by assertion (it catches the planted bug, not a crash or an import error)
  3. it imports only what tests here may import (no files, no network, no subprocess)
A test that fails a check goes back to the model once, with the pytest output. Kept tests go to
qa/mutation/generated/. The model may instead argue that a mutant cannot be told apart from the original
(an "equivalent mutant"); that claim is recorded as unverified, for a human to judge.

Careful: a kept test pins today's behaviour. If today's behaviour is wrong, the test pins a bug. That is why
the prompt tells the model to take expected values from the written rule definitions, and why a human reviews
the generated file like any other change.
"""
import argparse
import ast
import re
from pathlib import Path

from qa.core import llm
from qa.core.sandbox import ROOT, Workspace
from qa.mutation import mutate

HEADER = '''"""Tests written by a model to kill specific surviving mutants (qa/mutation/guided.py).

Each test passed on the real code and failed on its mutant, in the sandbox, before it was kept here.
Model: {model}. Review these like any other change: they pin current behaviour.
"""
import math

import numpy as np
import pytest

from jf import field, rules
'''
ALLOWED_IMPORTS = {"math", "numpy", "pytest", "jf"}

SYSTEM = """You are a careful test engineer. You write one pytest test that detects one specific planted defect
(a mutant) in a Python module.
Rules:
- The test must PASS on the original code and FAIL on the mutated code, through an assert.
- Take expected values from the rule definitions written in the module's docstring and comments, not from
  re-running the code in your head.
- Write exactly one function, named as instructed. No helper functions outside it, no fixtures, no files,
  no network. The module already has: import math; import numpy as np; import pytest; from jf import field, rules.
- If no input can make the original and the mutant behave differently, set equivalent=true, explain why in
  reason, and leave test_code empty."""

SCHEMA = {"type": "object", "additionalProperties": False, "required": ["equivalent", "reason", "test_code"],
          "properties": {"equivalent": {"type": "boolean"}, "reason": {"type": "string"},
                         "test_code": {"type": "string"}}}


def numbered(text):
    return "\n".join(f"{i:4d}  {line}" for i, line in enumerate(text.splitlines(), 1))


def prompt(m, target_src, helper_src, test_names):
    return f"""Module {m.file}:
{numbered(target_src)}

It calls field.verdict, which is:
{helper_src}

The existing tests ({len(test_names)} of them: {", ".join(test_names)}) do not detect this mutant:
  line {m.line}, in {m.function}:  {m.change}
  original: {m.before}
  mutated:  {m.after}

Write a test function named test_kills_{slug(m)} that passes on the original and fails on the mutant."""


def slug(m):
    return re.sub(r"\W+", "_", f"line{m.line}_{m.kind}_{m.id.split(':')[-1]}").strip("_")


def imports_ok(code):
    try:
        tree = ast.parse(code)
    except SyntaxError:
        return False
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            names.add((node.module or "").split(".")[0])
    return names <= ALLOWED_IMPORTS


def validate(ws, m, code, header):
    """Run the three checks in the sandbox. Returns (accepted, what to tell the model if not)."""
    if not imports_ok(code):
        return False, f"only these imports are allowed: {sorted(ALLOWED_IMPORTS)}; or the code does not parse"
    ws.write("tests/test_candidate.py", header + "\n\n" + code + "\n")
    on_real = ws.pytest("tests/test_candidate.py")
    if not on_real.ok:
        return False, "The test FAILS on the original code, so it rejects correct behaviour:\n" + on_real.output[-1500:]
    original = ws.read(m.file)
    ws.write(m.file, m.source)
    try:
        on_mutant = ws.pytest("tests/test_candidate.py")
    finally:
        ws.write(m.file, original)
    if on_mutant.returncode == 0:
        return False, "The test PASSES on the mutated code, so it does not detect the defect."
    if not any(v == "failed" for v in on_mutant.outcomes.values()):
        return False, "On the mutant the test errors instead of failing an assert:\n" + on_mutant.output[-1500:]
    return True, ""


def already_killed(ws, m, kept, header):
    """Does a test kept earlier already kill this mutant? Then no model call is needed."""
    if not kept:
        return False
    ws.write("tests/test_candidate.py", header + "\n\n" + "\n\n\n".join(kept) + "\n")
    original = ws.read(m.file)
    ws.write(m.file, m.source)
    try:
        return ws.pytest("tests/test_candidate.py").returncode != 0
    finally:
        ws.write(m.file, original)


def main(target, tests, max_mutants=40):
    meter = []
    before, _ = mutate.run(target, tests)
    cov = mutate.coverage(target, tests)
    survivors = [m for m in before if m.status == "survived"][:max_mutants]
    target_src = (ROOT / target).read_text()
    helper_src = re.search(r"def verdict\(.*?\n(?=\n\n)", (ROOT / "jf/field.py").read_text(), re.S).group(0)
    test_names = sorted(re.findall(r"^def (test_\w+)", "\n".join((ROOT / t).read_text() for t in tests), re.M))
    header = HEADER.format(model=llm.MODELS["generator"])
    kept, log = [], []
    with Workspace() as ws:
        for m in survivors:
            if already_killed(ws, m, kept, header):
                log.append((m, "killed by an earlier generated test", 0))
                continue
            user = prompt(m, target_src, helper_src, test_names)
            answer = llm.ask("generator", SYSTEM, user, SCHEMA, tag="mutation-guided", meter=meter)
            tries = 1
            if answer["equivalent"]:
                log.append((m, "model says equivalent (unverified): " + answer["reason"], tries))
                continue
            ok, feedback = validate(ws, m, answer["test_code"], header)
            if not ok:
                retry = user + "\n\nYour previous test:\n" + answer["test_code"] + "\n\nwas rejected: " + feedback
                answer = llm.ask("generator", SYSTEM, retry, SCHEMA, tag="mutation-guided", meter=meter)
                tries = 2
                ok, feedback = (False, "model says equivalent on retry: " + answer["reason"]) \
                    if answer["equivalent"] else validate(ws, m, answer["test_code"], header)
            if ok:
                kept.append(f"# kills {m.id}  ({m.function}: {m.change})\n" + answer["test_code"].strip())
                log.append((m, "new test kept", tries))
            else:
                log.append((m, "rejected: " + feedback.splitlines()[0], tries))

    out_dir = ROOT / "qa" / "mutation" / "generated"
    out_dir.mkdir(exist_ok=True)
    gen_file = out_dir / f"test_{Path(target).stem}_killers.py"
    gen_file.write_text(header + "\n\n" + "\n\n\n".join(kept) + "\n")
    rel_gen = str(gen_file.relative_to(ROOT))
    after, _ = mutate.run(target, tests, extra_tests=[rel_gen])
    report(target, tests, cov, before, after, log, rel_gen, len(kept), sum(m["recorded_usd"] for m in meter),
           len(meter))


def report(target, tests, cov, before, after, log, gen, n_kept, usd, calls):
    k0, n0, s0 = mutate.score(before)
    k1, n1, s1 = mutate.score(after)
    lines = [f"# Mutation testing of `{target}`", "",
             f"Tests: `{' '.join(tests)}`. Then the surviving mutants were handed to a model, one by one "
             f"(`qa/mutation/guided.py`).", "",
             "| | before | after |", "|---|---|---|",
             f"| Line coverage | {cov[0]:.0f}% | |",
             f"| Branch coverage | {cov[1]:.0f}% | |",
             f"| Mutants | {n0} | {n1} |",
             f"| Killed | {k0} | {k1} |",
             f"| Survived | {n0 - k0} | {n1 - k1} |",
             f"| **Mutation score** | **{s0:.0f}%** | **{s1:.0f}%** |",
             f"| Tests added | | {n_kept}, in `{gen}` |", "",
             f"Every added test passed on the real code and failed on its mutant, in the sandbox, before it was "
             f"kept. Model calls: {calls}, cost ${usd:.2f} when recorded (replays are free).", "",
             "## What happened to each survivor", "",
             "| mutant | function | planted bug | outcome | model calls |", "|---|---|---|---|---|"]
    for m, outcome, tries in log:
        lines.append(f"| `{m.id}` | `{m.function}` | `{m.change}` in `{m.after[:70]}` | {outcome[:160]} | {tries} |")
    left = [m for m in after if m.status == "survived"]
    if left:
        lines += ["", "## Still surviving", "", "| mutant | function | line after the change |", "|---|---|---|"]
        lines += [f"| `{m.id}` | `{m.function}` | `{m.after[:90]}` |" for m in left]
    out = ROOT / "qa" / "mutation" / f"RESULT_{Path(target).stem}.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines[:14]))
    print(f"\nwritten {out.relative_to(ROOT)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="mutation-guided test generation")
    ap.add_argument("target")
    ap.add_argument("tests", nargs="+")
    ap.add_argument("--max", type=int, default=40, help="at most this many survivors go to the model")
    a = ap.parse_args()
    main(a.target, a.tests, a.max)
