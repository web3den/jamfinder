"""Just-in-time tests: tests made for one code change, at the moment it is proposed.

    python -m qa.jit.run --demo           # a plausible "clean-up" of jf/rules.py, built in (writes RESULT.md)
    python -m qa.jit.run --base HEAD      # the working tree's changes against the last commit

A static suite tests what someone once thought of. This looks at the change itself and treats it as possibly
wrong until shown otherwise:
  1 what changed      which functions differ between the old and the new version (by syntax tree, not text)
  2 how risky         policy: is the file high-risk, does the change touch comparisons or constants, which
                      requirements trace to the function (qa/specs/requirements.toml)
  3 does behaviour    old and new run side by side on thousands of generated inputs; Hypothesis searches for an
    differ?           input where they disagree and shrinks it to the smallest one
  4 catching test     for each difference, a model writes a readable test that pins the OLD behaviour. The harness
                      keeps it only if it passes on the old code and fails on the new one
  5 who decides       a behaviour change in a high-risk function goes to a human with the smallest example:
                      "intended or not?" No difference, low risk: no human needed
"""
import argparse
import ast
import math
import subprocess
import sys
import tomllib
import types

import numpy as np
from hypothesis import HealthCheck, find, settings
from hypothesis import strategies as st
from hypothesis.errors import NoSuchExample

from qa.core import llm
from qa.core.sandbox import COPIED, ROOT, Workspace
from qa.properties.strategies import null_row, rule_input, score

POLICY = tomllib.loads((ROOT / "qa" / "harness" / "policy.toml").read_text())["agent"]
SPECS = ROOT / "qa" / "specs" / "requirements.toml"

# A plausible "simplification" of jf/rules.py, as a coding agent might propose it. Each edit looks harmless.
DEMO = [
    ("jf/rules.py",
     '''    if row.get("frac") is not None:
        return float(row["frac"]) < degenerate_frac
    return bool(row.get("degenerate", False))''',
     '''    return float(row.get("frac", 1.0)) < degenerate_frac'''),
    ("jf/rules.py", "d = bool(cands) and second < runner_up * best", "d = bool(cands) and second / best < runner_up"),
    ("jf/rules.py", '''    """Best score of one null run: `best` (sim_v3_check rows, sweep rows) or the first candidate's score
    (null_try rows)."""''', '''    """Best score of one control run: its `best` field, or else its first candidate's score."""'''),
]


def _plain(x):
    """Outputs made comparable: NaN equals NaN, arrays become tuples."""
    if isinstance(x, dict):
        return {k: _plain(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return tuple(_plain(v) for v in x)
    if isinstance(x, np.ndarray):
        return tuple(np.round(x, 9).ravel().tolist())
    if isinstance(x, float):
        return "nan" if math.isnan(x) else round(x, 9)
    return x


def outcome(invoke, module, x, raw=False):
    """What one version does with one input: ("returns", value) or ("raises", exception name)."""
    try:
        value = invoke(module, x)
        return ("returns", value if raw else _plain(value))
    except Exception as e:                       # a crash is a behaviour too
        return ("raises", type(e).__name__)


# Which functions can be exercised automatically: an input generator and how to call one version with an input.
REGISTRY = {
    "jf/rules.py:evaluate": (rule_input(), lambda m, x: m.evaluate(x["cands"], x["nulls"], x["residual"], x["support"])),
    "jf/rules.py:is_degenerate": (null_row("shift"), lambda m, x: m.is_degenerate(x)),
    "jf/rules.py:null_score": (null_row("shift"), lambda m, x: m.null_score(x)),
    "jf/field.py:verdict": (st.lists(score, max_size=5).map(lambda s: [(v, 0, 0, 0) for v in sorted(s)[::-1]]),
                            lambda m, x: m.verdict(x)),
}


def load(path, source, tag):
    """Import one version of a module from its source, under its own name, inside the jf package."""
    name = f"jf._jit_{tag}_{path.split('/')[-1][:-3]}"
    mod = types.ModuleType(name)
    mod.__package__ = "jf"
    exec(compile(source, f"{tag}:{path}", "exec"), mod.__dict__)
    return mod


def functions(source):
    tree = ast.parse(source)
    out = {}
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            out[node.name] = ast.get_source_segment(source, node)
    return out


def changed(old_src, new_src):
    """Functions whose code differs, ignoring docstrings and formatting."""
    def body(src):
        tree = ast.parse(src)
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)) and ast.get_docstring(node):
                node.body = node.body[1:] or [ast.Pass()]
        return {n.name: ast.dump(n) for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))}
    old, new = body(old_src), body(new_src)
    text_old, text_new = functions(old_src), functions(new_src)
    code = sorted(n for n in new if old.get(n) != new[n])
    docs_only = sorted(n for n in new if old.get(n) == new[n] and text_old.get(n) != text_new.get(n))
    return code, docs_only


def touches_thresholds(old_fn, new_fn):
    kinds = lambda src: sorted(type(n).__name__ for n in ast.walk(ast.parse(src))           # noqa: E731
                               if isinstance(n, (ast.Compare, ast.Constant, ast.BinOp)))
    return kinds(old_fn) != kinds(new_fn) or old_fn.count("<") != new_fn.count("<")


def requirements_of(path, name):
    if not SPECS.exists():
        return []
    reqs = tomllib.loads(SPECS.read_text()).get("requirement", [])
    return [r["id"] for r in reqs if f"{path}:{name}" in r.get("implemented_by", [])]


def behaviour_diff(key, old_mod, new_mod):
    """The smallest generated input on which the two versions disagree, or None after 3000 tries."""
    strategy, invoke = REGISTRY[key]
    try:
        x = find(strategy, lambda x: outcome(invoke, old_mod, x) != outcome(invoke, new_mod, x),
                 settings=settings(max_examples=3000, database=None, derandomize=True,
                                   suppress_health_check=list(HealthCheck)))
    except NoSuchExample:
        return None
    return x, outcome(invoke, old_mod, x, raw=True), outcome(invoke, new_mod, x, raw=True)


CATCH = {"type": "object", "additionalProperties": False, "required": ["what_changed", "question", "test_code"],
         "properties": {"what_changed": {"type": "string"}, "question": {"type": "string"},
                        "test_code": {"type": "string"}}}
SYSTEM = """You write one pytest test that catches a behaviour change between two versions of a function. The test
must pass on the OLD version and fail on the NEW one. It imports the module the normal way (e.g. `from jf import
rules`), uses the given smallest input literally, and asserts the old output. Also say in one or two plain
sentences what changed, and ask the change's author one yes/no question about whether it was intended."""


def catching_test(key, old_fn, new_fn, x, out_old, out_new, old_src, new_src):
    path, name = key.split(":")
    user = (f"Module {path}, function {name}.\n\nOLD:\n{old_fn}\n\nNEW:\n{new_fn}\n\n"
            f"Smallest input where they differ: {x!r}\nOLD gives: {out_old!r}\nNEW gives: {out_new!r}\n\n"
            f"Name the test test_jit_{name}_keeps_old_behaviour.")
    with Workspace(files=COPIED) as ws:
        for attempt in range(2):
            ans = llm.ask("generator", SYSTEM, user, CATCH, tag="jit")
            ws.write("tests/test_jit.py", ans["test_code"])
            ws.write(path, old_src)
            on_old = ws.pytest("tests/test_jit.py")
            ws.write(path, new_src)
            on_new = ws.pytest("tests/test_jit.py")
            ans["kept"] = on_old.ok and on_new.returncode != 0 and bool(on_new.failed)
            if ans["kept"]:
                break
            why = "it fails on the OLD version" if not on_old.ok else "it passes on the NEW version"
            user += f"\n\nYour test was rejected: {why}.\n{(on_old if not on_old.ok else on_new).output[-1200:]}"
    return ans


def analyse(path, old_src, new_src):
    code, docs_only = changed(old_src, new_src)
    old_mod, new_mod = load(path, old_src, "old"), load(path, new_src, "new")
    old_fns, new_fns = functions(old_src), functions(new_src)
    rows = []
    for name in code:
        key = f"{path}:{name}"
        risk, why = 0, []
        if path in POLICY["high_risk"]:
            risk, why = risk + 3, why + ["high-risk file"]
        if touches_thresholds(old_fns.get(name, ""), new_fns[name]):
            risk, why = risk + 1, why + ["comparisons, constants or arithmetic changed"]
        reqs = requirements_of(path, name)
        if reqs:
            risk, why = risk + 1, why + [f"traces to {', '.join(reqs)}"]
        diff = behaviour_diff(key, old_mod, new_mod) if key in REGISTRY else None
        row = dict(key=key, generator=key in REGISTRY, diff=diff, catch=None, reqs=reqs)
        if diff:
            risk, why = risk + 2, why + ["behaviour differs"]
            row["catch"] = catching_test(key, old_fns[name], new_fns[name], *diff, old_src, new_src)
        row.update(risk=risk, why=why, level="high" if risk >= 5 else "medium" if risk >= 3 else "low")
        row["decision"] = ("a human confirms the behaviour change is intended" if diff and row["level"] == "high"
                           else "reviewer" if row["level"] != "low" or not row["generator"] else "no human needed")
        rows.append(row)
    return rows, docs_only


def report(path, rows, docs_only, title):
    md = [f"# Just-in-time tests: {title}", "", f"File: `{path}`. Changed functions: {len(rows)}"
          + (f"; documentation only: {', '.join(docs_only)} (no behaviour to test)." if docs_only else "."), "",
          "| function | risk | why | behaviour | decision |", "|---|---|---|---|---|"]
    for r in rows:
        beh = ("no generator: cannot check automatically" if not r["generator"] else
               "same on 3000 generated inputs" if not r["diff"] else "DIFFERS")
        md.append(f"| `{r['key'].split(':')[1]}` | {r['level']} ({r['risk']}) | {'; '.join(r['why'])} | {beh} | "
                  f"{r['decision']} |")
    for r in rows:
        if not r["diff"]:
            continue
        x, a, b = r["diff"]
        md += ["", f"## `{r['key']}`", "", f"Smallest input found where old and new disagree: `{x!r}`", "",
               f"- old: `{a!r}`"[:400], f"- new: `{b!r}`"[:400], "", f"What changed: {r['catch']['what_changed']}", "",
               f"Question for the author: **{r['catch']['question']}**", "",
               f"Catching test ({'kept: passes on old, fails on new' if r['catch']['kept'] else 'REJECTED by the harness'}):",
               "", "```python", r["catch"]["test_code"].strip(), "```"]
    out = ROOT / "qa" / "jit" / "RESULT.md"
    out.write_text("\n".join(md) + "\n")
    print("\n".join(md[:4 + len(rows) + 2]))
    print(f"\nwritten {out.relative_to(ROOT)}")


def main():
    ap = argparse.ArgumentParser(description="just-in-time tests for a change")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--base", default="HEAD")
    a = ap.parse_args()
    if a.demo:
        path = DEMO[0][0]
        old_src = (ROOT / path).read_text()
        new_src = old_src
        for _, old, new in DEMO:
            assert new_src.count(old) == 1
            new_src = new_src.replace(old, new)
        rows, docs = analyse(path, old_src, new_src)
        report(path, rows, docs, "a 'clean-up' of the reporting rule (built-in demo)")
        return
    names = subprocess.run(["git", "diff", "--name-only", a.base, "--", "jf"], cwd=ROOT, capture_output=True,
                           text=True).stdout.split()
    for path in names:
        old_src = subprocess.run(["git", "show", f"{a.base}:{path}"], cwd=ROOT, capture_output=True, text=True).stdout
        new_src = (ROOT / path).read_text()
        rows, docs = analyse(path, old_src, new_src)
        report(path, rows, docs, f"changes to {path} since {a.base}")
    if not names:
        print(f"no changes under jf/ since {a.base}")


if __name__ == "__main__":
    sys.exit(main())
