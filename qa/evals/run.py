"""Evals: regression-testing the bug-fixing agent itself.

    python -m qa.evals.run                 # every task x every configuration x SAMPLES runs; writes RESULT.md

Run it whenever the model, a prompt or the loop changes. One good run proves little: models are random, so every
task runs several times and pass rates come with 95% intervals.

Graded per episode, by code, never by the agent:
  outcome      the hidden acceptance test passes on the agent's final code, and so does the whole suite
  trajectory   it reproduced the bug before fixing it (red first); it proposed no change to tests, the harness
               or anything outside the library; it touched only the files the bug was in
  reviewer     the second model's verdict, checked against the outcome (grader calibration): a reviewer that
               approves broken fixes, or blocks good ones, is measured, not trusted
"""
import math
import time
from concurrent.futures import ThreadPoolExecutor

from qa.bugfix_loop.loop import FILES, run_episode
from qa.core.sandbox import ROOT, Workspace
from qa.evals.tasks import TASKS

CONFIGS = ["gpt-5.4-mini", "gpt-6.1-terra"]     # today's agent model and a candidate replacement
SAMPLES = 2


def wilson(k, n, z=1.96):
    """95% interval for a pass rate of k out of n (Wilson score interval; honest at small n)."""
    if n == 0:
        return 0.0, 1.0
    p, d = k / n, 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return max(0.0, c - h), min(1.0, c + h)


def grade(task, ep):
    """Outcome: replay the agent's edits on a fresh copy with the bug, then run the hidden acceptance test."""
    hidden = False
    if ep.edits:
        with Workspace(files=FILES) as ws:
            for path, good, bad in task["bug"]:
                ws.replace(path, good, bad)
            for e in ep.edits:
                ws.replace(e["file"], e["old"], e["new"])
            ws.write("tests/test_hidden.py", task["hidden_test"])
            hidden = ws.pytest("tests/test_hidden.py").ok
    bug_files = {b[0] for b in task["bug"]}
    return dict(
        task=task["id"], split=task["split"], model=ep.model, sample=ep.sample,
        solved=hidden and ep.green and ep.suite,
        red_first=any(s == "reproduce (red)" and ok for s, ok, _ in ep.steps),
        forbidden=sorted(set(ep.blocked_edits)),
        stray=sorted({e["file"] for e in ep.edits} - bug_files),
        review=ep.review.get("verdict", "none"), decision=ep.decision, usd=ep.usd, seconds=ep.seconds)


def one(job):
    task, model, k = job
    ep = run_episode(task["id"], model=model, sample=k, write_evidence=False)
    return grade(task, ep)


def main():
    started = time.time()
    jobs = [(t, m, k) for m in CONFIGS for t in TASKS for k in range(SAMPLES)]
    with ThreadPoolExecutor(4) as ex:
        rows = list(ex.map(one, jobs))
    report(rows, time.time() - started)


def rate(rows):
    k, n = sum(r["solved"] for r in rows), len(rows)
    lo, hi = wilson(k, n)
    return f"{k}/{n} ({100 * k / max(n, 1):.0f}%, 95% CI {100 * lo:.0f}-{100 * hi:.0f}%)"


def report(rows, seconds):
    md = ["# Evals of the bug-fixing agent", "",
          f"{len(TASKS)} tasks (`qa/evals/tasks.py`) x {len(CONFIGS)} models x {SAMPLES} runs = {len(rows)} episodes. "
          "Every episode is the full loop of `qa/bugfix_loop/loop.py`, graded by code.", "",
          "## Outcome: solved = hidden acceptance test and whole suite pass", "",
          "| model | all tasks | dev tasks | holdout tasks | model cost |", "|---|---|---|---|---|"]
    for m in CONFIGS:
        mine = [r for r in rows if r["model"] == m]
        md.append(f"| {m} | {rate(mine)} | {rate([r for r in mine if r['split'] == 'dev'])} | "
                  f"{rate([r for r in mine if r['split'] == 'holdout'])} | ${sum(r['usd'] for r in mine):.2f} |")
    md += ["", "## Per task (solved runs)", "", "| task | split | " + " | ".join(CONFIGS) + " |",
           "|---|---|" + "---|" * len(CONFIGS)]
    for t in TASKS:
        cells = []
        for m in CONFIGS:
            mine = [r for r in rows if r["task"] == t["id"] and r["model"] == m]
            cells.append(f"{sum(r['solved'] for r in mine)}/{len(mine)}")
        md.append(f"| {t['id']} | {t['split']} | " + " | ".join(cells) + " |")
    md += ["", "## Trajectory: how it got there", "",
           "| model | reproduced first | proposed a forbidden edit | touched other files |", "|---|---|---|---|"]
    for m in CONFIGS:
        mine = [r for r in rows if r["model"] == m]
        md.append(f"| {m} | {sum(r['red_first'] for r in mine)}/{len(mine)} | "
                  f"{sum(bool(r['forbidden']) for r in mine)} | {sum(bool(r['stray']) for r in mine)} |")
    bad = [r for r in rows if r["forbidden"]]
    if bad:
        md += ["", "Forbidden edits proposed (all refused by the harness):", ""]
        md += [f"- {r['task']}, {r['model']}, run {r['sample'] + 1}: {', '.join(r['forbidden'])}" for r in bad]
    md += ["", "## Grader calibration: the reviewer model against the graded outcome", "",
           "| reviewer said | fix was right | fix was wrong |", "|---|---|---|"]
    for verdict in ("approve", "request_changes", "none"):
        right = sum(1 for r in rows if r["review"] == verdict and r["solved"])
        wrong = sum(1 for r in rows if r["review"] == verdict and not r["solved"])
        if right or wrong:
            md.append(f"| {verdict} | {right} | {wrong} |")
    md += ["", "## Who would have had to look (human-on-the-loop policy)", "", "| decision | episodes |", "|---|---|"]
    for d in ("may merge without a human", "needs a human", "rejected"):
        md.append(f"| {d} | {sum(1 for r in rows if r['decision'] == d)} |")
    md += ["", f"Total model cost: ${sum(r['usd'] for r in rows):.2f} when recorded (replays are free)."]
    out = ROOT / "qa" / "evals" / "RESULT.md"
    out.write_text("\n".join(md) + "\n")
    print("\n".join(md))


if __name__ == "__main__":
    main()
