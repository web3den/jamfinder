"""A closed bug-fixing loop. The agent must demonstrate success; it cannot declare it.

    python -m qa.bugfix_loop.loop T01-track-gap        # a task from qa/evals/tasks.py; evidence in evidence/

  1 ingest      the ticket: symptoms only
  2 locate      the generator picks up to three files from an index of the package and its tests
  3 reproduce   it writes a regression test; the harness requires it to FAIL on today's code, on an assert (red)
  4 repair      it proposes exact edits; the harness applies them to a sandbox copy, library files only
  5 verify      the harness: the new test passes (green) and the whole existing suite passes; then a targeted
                mutation check, as a signal: do planted bugs on the changed lines make the new test fail?
  6 review      a second model, another family, fresh context, is asked for reasons the fix is wrong
  7 decide      policy decides, not a model: only low-risk, fully green, unflagged changes may skip a human
  8 evidence    one markdown file with everything above, for the human who approves or rejects

Gates are final for what can be tested. The reviewer can only add doubt: it can send a change to a human, never
wave a failed gate through.
"""
import ast
import difflib
import sys
import time
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from qa.core import llm
from qa.core.sandbox import COPIED, ROOT, Workspace
from qa.evals.tasks import by_id
from qa.mutation import mutate

POLICY = tomllib.loads((ROOT / "qa" / "harness" / "policy.toml").read_text())["agent"]
EVIDENCE = ROOT / "qa" / "bugfix_loop" / "evidence"
FILES = COPIED + ("qa/oracle",)

SYSTEM = """You are a software engineer fixing one bug in jamfinder, a Python package that locates radio
transmitters from the echoes of their signal off aircraft. You work in steps. An automated harness checks the
output of every step; your own statements of success count for nothing. Fix the library code; never change
existing tests to make them pass."""

LOCATE = {"type": "object", "additionalProperties": False, "required": ["files", "why"],
          "properties": {"files": {"type": "array", "items": {"type": "string"}}, "why": {"type": "string"}}}
REPRO = {"type": "object", "additionalProperties": False, "required": ["test_code"],
         "properties": {"test_code": {"type": "string"}}}
EDIT = {"type": "object", "additionalProperties": False, "required": ["file", "old", "new"],
        "properties": {"file": {"type": "string"}, "old": {"type": "string"}, "new": {"type": "string"}}}
FIX = {"type": "object", "additionalProperties": False, "required": ["root_cause", "edits"],
       "properties": {"root_cause": {"type": "string"}, "edits": {"type": "array", "items": EDIT}}}
REVIEW = {"type": "object", "additionalProperties": False, "required": ["verdict", "risk", "concerns"],
          "properties": {"verdict": {"type": "string", "enum": ["approve", "request_changes"]},
                         "risk": {"type": "string", "enum": ["low", "medium", "high"]},
                         "concerns": {"type": "array", "items": {"type": "string"}}}}
REVIEWER = """You are a skeptical code reviewer. Another engineer (an AI agent) claims to have fixed a bug. Your
task is to find evidence that the change is wrong, incomplete, hides the symptom instead of fixing the cause, or
games the tests. You cannot run code. Approve only if you find no such evidence."""


@dataclass
class Episode:
    task: str
    model: str
    sample: int
    steps: list = field(default_factory=list)      # (step, ok, detail) in order
    files: list = field(default_factory=list)
    repro: str = ""
    red: str = ""
    edits: list = field(default_factory=list)
    blocked_edits: list = field(default_factory=list)  # edits the agent proposed outside what it may change
    diff: str = ""
    green: bool = False
    suite: bool = False
    mutation: tuple = (0, 0)
    review: dict = field(default_factory=dict)
    decision: str = ""
    reasons: list = field(default_factory=list)
    meter: list = field(default_factory=list)          # one entry per model call: its cost
    seconds: float = 0.0

    @property
    def usd(self):
        """What the episode cost when its model calls were made (replays are free, the record keeps the price)."""
        return sum(m["recorded_usd"] for m in self.meter)

    def note(self, step, ok, detail=""):
        self.steps.append((step, ok, detail))
        return ok


def index(ws):
    """What the agent sees before reading any file: each module's first docstring line and its definitions."""
    out = []
    for rel in sorted(str(p.relative_to(ws.dir)) for p in ws.path("jf").glob("*.py")) + \
            sorted(str(p.relative_to(ws.dir)) for p in ws.path("tests").glob("test_*.py")):
        tree = ast.parse(ws.read(rel))
        doc = (ast.get_docstring(tree) or "").splitlines()[:1]
        defs = [n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.ClassDef))]
        out.append(f"{rel}: {doc[0] if doc else ''}\n    defines: {', '.join(defs)}")
    return "\n".join(out)


def allowed(path):
    return any(path.startswith(p) for p in POLICY["may_edit"]) and ".." not in path


def run_episode(task_id, model=None, sample=0, write_evidence=True):
    task = by_id(task_id)
    ep = Episode(task_id, model or llm.MODELS["generator"], sample)
    t0 = time.time()
    ask = lambda user, schema: llm.ask("generator", SYSTEM, user, schema, tag="bugfix",  # noqa: E731
                                       model=ep.model, sample=sample, meter=ep.meter)
    ticket = f"Ticket: {task['title']}\n\n{task['ticket']}"
    with Workspace(files=FILES) as ws:
        for path, good, bad in task["bug"]:
            ws.replace(path, good, bad)          # the repository as the agent finds it
        before = {f"jf/{p.name}": p.read_text() for p in ws.path("jf").glob("*.py")}   # to see what changed

        # 2 locate
        pick = ask(f"{ticket}\n\nThe package and its tests:\n{index(ws)}\n\nWhich files (at most 3) do you need "
                   f"to read to reproduce and fix this?", LOCATE)
        ep.files = [f for f in pick["files"] if ws.path(f).is_file()][:3]
        ep.note("locate", bool(ep.files), ", ".join(ep.files))
        sources = "\n\n".join(f"=== {f} ===\n{ws.read(f)}" for f in ep.files)

        # 3 reproduce: must be red, on an assert
        user = (f"{ticket}\n\n{sources}\n\nWrite a pytest module that reproduces the bug: it must FAIL on the code "
                f"above through an assert, and pass once the bug is fixed. Import from jf (and numpy, pytest, "
                f"tests.common if useful). No network, no files outside pytest's tmp_path.")
        red = None
        for attempt in range(2):
            ep.repro = ask(user, REPRO)["test_code"]
            ws.write("tests/test_repro.py", ep.repro)
            red = ws.pytest("tests/test_repro.py")
            on_assert = any(v == "failed" and ("assert" in red.messages.get(k, "").lower())
                            for k, v in red.outcomes.items())
            if red.returncode != 0 and on_assert:
                break
            why = "it PASSES on the buggy code" if red.returncode == 0 else "it errors instead of failing an assert"
            user += f"\n\nYour test was rejected: {why}.\n{red.output[-1200:]}\nWrite a corrected test."
        ep.red = red.output[-1500:]
        if not ep.note("reproduce (red)", red.returncode != 0, f"{len(red.failed)} of {len(red.outcomes)} tests fail"):
            return finish(ep, task, ws, before, t0, write_evidence)

        # 4 repair: exact edits, library files only
        user = (f"{ticket}\n\n{sources}\n\nThis test reproduces the bug:\n{ep.repro}\n\nIts failure:\n"
                f"{ep.red[-800:]}\n\nFind the root cause and fix it with exact text replacements: each `old` must "
                f"appear exactly once in its file.")
        for attempt in range(2):
            fix = ask(user, FIX)
            ep.blocked_edits += [e["file"] for e in fix["edits"] if not allowed(e["file"])]
            problems = []
            for e in fix["edits"]:
                if not allowed(e["file"]):
                    problems.append(f"{e['file']}: you may only change files under {POLICY['may_edit']}")
                    continue
                try:
                    ws.replace(e["file"], e["old"], e["new"])
                    ep.edits.append(e)
                except (ValueError, FileNotFoundError) as err:
                    problems.append(str(err))
            if ep.edits and not problems:
                break
            user += "\n\nYour edits were refused:\n- " + "\n- ".join(problems) + "\nPropose corrected edits."
        ep.note("repair", bool(ep.edits), f"{len(ep.edits)} edit(s); refused: {len(ep.blocked_edits)}")

        # 5 verify: green, whole suite, targeted mutation
        ep.green = ep.note("new test passes (green)", ws.pytest("tests/test_repro.py").ok)
        suite = ws.pytest("tests", timeout=600)
        ep.suite = ep.note("existing suite passes", suite.ok, f"{len(suite.passed)} passed, {len(suite.failed)} failed")
        ep.mutation = mutation_check(ws, before)
        ep.note("targeted mutation (signal)", True,
                f"the new test kills {ep.mutation[0]} of {ep.mutation[1]} mutants of the changed lines")
        return finish(ep, task, ws, before, t0, write_evidence)


def mutation_check(ws, before):
    """Mutants of exactly the changed lines, tested by the new regression test alone."""
    killed = total = 0
    for path, old_text in before.items():
        new_text = ws.read(path)
        if new_text == old_text:
            continue
        ops = difflib.SequenceMatcher(None, old_text.splitlines(), new_text.splitlines()).get_opcodes()
        changed = {j + 1 for tag, _, _, j1, j2 in ops if tag in ("replace", "insert") for j in range(j1, j2)}
        for m in mutate.mutants(path, source=new_text, lines_only=changed):
            ws.write(path, m.source)
            killed += ws.pytest("tests/test_repro.py", timeout=120).returncode != 0
            total += 1
        ws.write(path, new_text)
    return killed, total


def finish(ep, task, ws, before, t0, write_evidence):
    ep.diff = "".join("".join(difflib.unified_diff(old.splitlines(True), ws.read(p).splitlines(True), f"a/{p}",
                                                    f"b/{p}")) for p, old in before.items())
    gates_green = ep.green and ep.suite and not ep.blocked_edits
    if ep.edits:
        ep.review = llm.ask("evaluator", REVIEWER, f"Ticket: {task['title']}\n\n{task['ticket']}\n\nThe change:\n"
                            f"{ep.diff}\n\nThe regression test the engineer added:\n{ep.repro}\n\nAutomated checks: "
                            f"new test {'passes' if ep.green else 'FAILS'}; existing suite "
                            f"{'passes' if ep.suite else 'FAILS'}.", REVIEW, tag="bugfix-review", sample=ep.sample,
                            meter=ep.meter)
    decide(ep, gates_green)
    ep.seconds = time.time() - t0
    if write_evidence:
        write(ep, task)
    return ep


def decide(ep, gates_green):
    """Policy, not a model, decides who must look at the change."""
    touched = sorted({e["file"] for e in ep.edits})
    n_lines = sum(1 for line in ep.diff.splitlines() if line[:1] in "+-" and line[:3] not in ("+++", "---"))
    if not gates_green:
        ep.decision, ep.reasons = "rejected", [s for s, ok, _ in ep.steps if not ok] or ["blocked edits"]
        if ep.blocked_edits:
            ep.reasons.append(f"tried to change {', '.join(sorted(set(ep.blocked_edits)))}")
        return
    if any(t in POLICY["high_risk"] for t in touched):
        ep.reasons.append(f"high-risk file: {', '.join(t for t in touched if t in POLICY['high_risk'])}")
    killed, total = ep.mutation
    if total and killed < total / 2:
        ep.reasons.append(f"the new test catches only {killed} of {total} planted bugs on the changed lines")
    if n_lines > POLICY["max_auto_lines"]:
        ep.reasons.append(f"{n_lines} changed lines")
    if ep.review.get("verdict") != "approve" or ep.review.get("risk") == "high":
        ep.reasons.append(f"reviewer: {ep.review.get('verdict')}, risk {ep.review.get('risk')}")
    ep.decision = "needs a human" if ep.reasons else "may merge without a human"


def write(ep, task):
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    tick = lambda ok: "pass" if ok else "FAIL"          # noqa: E731
    md = [f"# Evidence: {task['id']}, {task['title']}", "",
          f"Decision: **{ep.decision}**" + (f" ({'; '.join(ep.reasons)})" if ep.reasons else ""), "",
          f"Agent: {ep.model}. Reviewer: {llm.MODELS['evaluator']}. Model calls: {len(ep.meter)}, cost "
          f"${ep.usd:.3f} when recorded.", "", "## Ticket", "", task["ticket"], "", "## Steps", "",
          "| step | result | detail |", "|---|---|---|"]
    md += [f"| {s} | {tick(ok)} | {d} |" for s, ok, d in ep.steps]
    md += ["", "## Regression test written by the agent", "", "```python", ep.repro.strip(), "```", "",
           "Its failure on the buggy code (red):", "", "```", ep.red.strip()[-900:], "```", "",
           "## The change", "", "```diff", ep.diff.strip(), "```", "",
           "## Independent review", "", f"Verdict: {ep.review.get('verdict')}, risk {ep.review.get('risk')}.", ""]
    md += [f"- {c}" for c in ep.review.get("concerns", [])]
    (EVIDENCE / f"{task['id']}.md").write_text("\n".join(md) + "\n")


if __name__ == "__main__":
    ep = run_episode(sys.argv[1] if len(sys.argv) > 1 else "T01-track-gap")
    for s, ok, d in ep.steps:
        print(f"  {'pass' if ok else 'FAIL'}  {s:<26} {d}")
    print(f"decision: {ep.decision} {ep.reasons}   cost ${ep.usd:.3f} when recorded   {ep.seconds:.0f} s")
    print(f"evidence: {(EVIDENCE / (ep.task + '.md')).relative_to(ROOT)}")
