"""Mutation testing in one readable file: plant small bugs in the code, one at a time, and see if the tests notice.

    python -m qa.mutation.mutate jf/rules.py tests/test_rules.py            # score and survivors
    python -m qa.mutation.mutate jf/rules.py tests/test_rules.py --function evaluate

A mutant is the original file with one small change, the kind a person or a model makes by accident:
    best >= null_ratio * null_best   ->   best > null_ratio * null_best     (boundary)
    a and b and c and d               ->   a or b and c and d                 (logic)
    second < runner_up * best         ->   second < runner_up / best          (arithmetic)
    NULL_RATIO = 3.0                  ->   NULL_RATIO = 4.0                   (constant)
    return "one"                      ->   return "XXoneXX"                   (value)
The tests "kill" a mutant when at least one of them fails. A mutant that survives is a bug the tests would let
through. Mutation score = killed / all mutants. Line coverage only says which lines ran; this says whether a
wrong line would be caught.

Why not mutmut? mutmut is the standard tool for Python and works on this repository too. This runner is
written out so every step is visible, it can aim at one function (the bug-fix loop and the just-in-time tests
mutate only what a change touched), and it hands each survivor, with its diff, to the test generator.
"""
import argparse
import ast
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from pathlib import Path
from queue import Queue

from qa.core.sandbox import COPIED, ROOT, Workspace

COMPARE_SWAP = {ast.Lt: (ast.LtE, "<", "<="), ast.LtE: (ast.Lt, "<=", "<"), ast.Gt: (ast.GtE, ">", ">="),
                ast.GtE: (ast.Gt, ">=", ">"), ast.Eq: (ast.NotEq, "==", "!="), ast.NotEq: (ast.Eq, "!=", "=="),
                ast.In: (ast.NotIn, "in", "not in"), ast.NotIn: (ast.In, "not in", "in"),
                ast.Is: (ast.IsNot, "is", "is not"), ast.IsNot: (ast.Is, "is not", "is")}
BINOP_SWAP = {ast.Add: ("+", "-"), ast.Sub: ("-", "+"), ast.Mult: ("*", "/"), ast.Div: ("/", "*"),
              ast.FloorDiv: ("//", "/"), ast.Pow: ("**", "*"), ast.Mod: ("%", "*")}
BOOL_SWAP = {ast.And: ("and", "or"), ast.Or: ("or", "and")}


@dataclass
class Mutant:
    id: str              # file:line:n, stable while the file does not change
    file: str
    line: int
    function: str
    kind: str            # boundary, negation, logic, arithmetic, constant, value
    change: str          # e.g. ">=  ->  >"
    before: str          # the original line
    after: str           # the mutated line
    status: str = ""     # killed, survived, timeout
    killed_by: str = ""
    source: str = field(default="", repr=False)


def _functions(tree):
    """Map every node to the name of the function (or class.method) it sits in."""
    owner = {}

    def visit(node, name):
        for child in ast.iter_child_nodes(node):
            inner = name
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                inner = f"{name}.{child.name}" if name and not name.startswith("<") else child.name
            elif isinstance(child, ast.ClassDef):
                inner = child.name
            owner[child] = inner
            visit(child, inner)
    visit(tree, "<module>")
    return owner


def _docstrings(tree):
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.ClassDef, ast.AsyncFunctionDef)) and node.body:
            first = node.body[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant):
                out.add(first.value)
    return out


def sites(source, tree):
    """Every place one small change can be made: (start byte, end byte, replacement, kind, label, node)."""
    data = source.encode()
    starts = [0] + [m.end() for m in re.finditer(b"\n", data)]
    in_fstrings = {x for n in ast.walk(tree) if isinstance(n, ast.JoinedStr) for x in ast.walk(n)}
    skip = _docstrings(tree) | in_fstrings

    def off(line, col):
        return starts[line - 1] + col

    def gap(a, b):
        """Byte range between the end of node a and the start of node b (where an operator sits)."""
        return off(a.end_lineno, a.end_col_offset), off(b.lineno, b.col_offset)

    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare):
            left = node.left
            for op, right in zip(node.ops, node.comparators):
                if type(op) in COMPARE_SWAP:
                    _, old, new = COMPARE_SWAP[type(op)]
                    a, b = gap(left, right)
                    m = re.search(rb"(?<![<>=!])" + re.escape(old.encode()) + rb"(?![<>=])", data[a:b])
                    if m:
                        kind = "boundary" if old in ("<", "<=", ">", ">=") else "negation"
                        found.append((a + m.start(), a + m.end(), new, kind, f"{old}  ->  {new}", node))
                left = right
        elif isinstance(node, ast.BinOp) and type(node.op) in BINOP_SWAP:
            old, new = BINOP_SWAP[type(node.op)]
            a, b = gap(node.left, node.right)
            m = re.search(rb"(?<![*/])" + re.escape(old.encode()) + rb"(?![*/=])", data[a:b])
            if m:
                found.append((a + m.start(), a + m.end(), new, "arithmetic", f"{old}  ->  {new}", node))
        elif isinstance(node, ast.BoolOp):
            old, new = BOOL_SWAP[type(node.op)]
            for x, y in zip(node.values, node.values[1:]):
                a, b = gap(x, y)
                m = re.search(rb"\b" + old.encode() + rb"\b", data[a:b])
                if m:
                    found.append((a + m.start(), a + m.end(), new, "logic", f"{old}  ->  {new}", node))
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            a, b = off(node.lineno, node.col_offset), off(node.operand.lineno, node.operand.col_offset)
            found.append((a, b, "", "negation", "not x  ->  x", node))
        elif isinstance(node, ast.Constant) and node not in skip:
            a, b = off(node.lineno, node.col_offset), off(node.end_lineno, node.end_col_offset)
            v = node.value
            if isinstance(v, bool):
                found.append((a, b, str(not v), "constant", f"{v}  ->  {not v}", node))
            elif isinstance(v, (int, float)):
                found.append((a, b, repr(v + 1), "constant", f"{v!r}  ->  {v + 1!r}", node))
            elif isinstance(v, str) and v and len(v) < 40:
                found.append((a, b, repr("XX" + v + "XX"), "value", f"{v!r}  ->  'XX{v}XX'", node))
    return found


def mutants(path, function=None, source=None, lines_only=None):
    """All mutants of one file (optionally of one function, or of some lines), each a complete changed copy.

    source       the file's text, if not the one in the repository (the bug-fix loop mutates a patched copy)
    lines_only   a set of line numbers: only mutants on these lines
    """
    source = source if source is not None else (ROOT / path).read_text()
    data = source.encode()
    tree = ast.parse(source)
    owner = _functions(tree)
    lines = source.splitlines()
    out = []
    for i, (a, b, new, kind, label, node) in enumerate(sorted(sites(source, tree), key=lambda s: s[0])):
        fn = owner.get(node, "<module>")
        if function and fn != function and not fn.startswith(function + "."):
            continue
        text = (data[:a] + new.encode() + data[b:]).decode()
        try:
            compile(text, path, "exec")
        except SyntaxError:
            continue
        line = source.encode()[:a].count(b"\n") + 1
        if lines_only is not None and line not in lines_only:
            continue
        after = text.splitlines()[line - 1]
        out.append(Mutant(id=f"{Path(path).name}:{line}:{i}", file=path, line=line, function=fn, kind=kind,
                          change=label, before=lines[line - 1].strip(), after=after.strip(), source=text))
    return out


def run(path, tests, function=None, workers=None, extra_tests=()):
    """Run the tests against every mutant. Returns (mutants with status, baseline seconds)."""
    tests = list(tests) + list(extra_tests)
    workers = workers or max(1, (os.cpu_count() or 2) - 1)
    pool = Queue()
    spaces = [Workspace(files=COPIED + tuple(tests)).__enter__() for _ in range(workers)]
    for ws in spaces:
        pool.put(ws)
    try:
        t = time.time()
        base = spaces[0].pytest(*tests)
        baseline = time.time() - t
        if not base.ok:
            raise RuntimeError("the tests fail on the unchanged code, so mutation results would mean nothing:\n"
                               + base.output[-2000:])
        todo = mutants(path, function)
        original = (ROOT / path).read_text()

        def one(m):
            ws = pool.get()
            try:
                ws.write(path, m.source)
                res = ws.pytest(*tests, extra=["-x"], timeout=max(30, 10 * baseline))
                if res.returncode == -9:
                    m.status = "timeout"
                elif res.returncode == 0:
                    m.status = "survived"
                else:
                    m.status, m.killed_by = "killed", (res.failed[0] if res.failed else "collection error")
            finally:
                ws.write(path, original)
                pool.put(ws)
            return m

        with ThreadPoolExecutor(workers) as ex:
            done = list(ex.map(one, todo))
    finally:
        for ws in spaces:
            ws.__exit__(None, None, None)
    return done, baseline


def coverage(path, tests):
    """Line and branch coverage of one file by the given tests (coverage.py), in percent."""
    with Workspace(files=COPIED + tuple(tests)) as ws:
        ws.run(["-m", "coverage", "run", "--branch", f"--include={path}", "-m", "pytest", "-q",
                "-p", "no:cacheprovider", *tests])
        code, out, _ = ws.run(["-m", "coverage", "json", "-o", "cov.json"])
        data = json.loads(ws.read("cov.json"))["totals"]
    lines = 100.0 * data["covered_lines"] / max(1, data["num_statements"])
    branches = 100.0 * data["covered_branches"] / max(1, data["num_branches"])
    return lines, branches


def score(ms):
    killed = sum(1 for m in ms if m.status in ("killed", "timeout"))
    return killed, len(ms), 100.0 * killed / max(1, len(ms))


def summary(path, tests, ms, cov=None):
    killed, total, pct = score(ms)
    out = [f"target {path}   tests {' '.join(tests)}"]
    if cov:
        out.append(f"line coverage {cov[0]:.0f}%   branch coverage {cov[1]:.0f}%")
    out.append(f"mutants {total}   killed {killed}   survived {total - killed}   mutation score {pct:.0f}%")
    for m in ms:
        if m.status == "survived":
            out.append(f"  survived  {m.id:<18} {m.function:<14} {m.change:<22} {m.after}")
    return "\n".join(out)


def save(ms, out_json):
    Path(out_json).write_text(json.dumps([{k: v for k, v in asdict(m).items() if k != "source"} for m in ms],
                                         indent=1) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="mutation testing of one file")
    ap.add_argument("target")
    ap.add_argument("tests", nargs="+")
    ap.add_argument("--function")
    ap.add_argument("--json", help="write every mutant and its status here")
    ap.add_argument("--min-score", type=float, help="exit with an error below this mutation score (a CI gate)")
    a = ap.parse_args()
    ms, _ = run(a.target, a.tests, a.function)
    print(summary(a.target, a.tests, ms, coverage(a.target, a.tests)))
    if a.json:
        save(ms, a.json)
    if a.min_score is not None and score(ms)[2] < a.min_score:
        raise SystemExit(f"mutation score {score(ms)[2]:.0f}% is below the required {a.min_score:.0f}%")
