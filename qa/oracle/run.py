"""The test oracle experiment: who should decide what the right answer is?

    python -m qa.oracle.run            # writes qa/oracle/RESULT.md (recorded model answers replay for free)

One function, the bistatic Doppler shift, with one planted mistake (qa/oracle/subject.py). Three ways to get
tests for it:
  A  tests from the code          the model sees the (wrong) implementation: "write tests for this function"
  B  tests from the requirement   the model sees only the one-sentence requirement and the signature
  C  independent oracle           physics written down without the code: qa/oracle/independent_oracle.py
Every test suite is then run twice, in the sandbox: against the wrong code and against the right code.

The failure mode this measures is a common-mode failure: when the implementation and its tests come from the
same understanding, the tests confirm the misunderstanding. Passing tests then prove internal consistency only.
"""
from qa.core import llm
from qa.core.sandbox import ROOT, Workspace
from qa.oracle import independent_oracle, subject

SAMPLES = 4
SYSTEM = "You are a senior test engineer. You write pytest test modules. Reply with the module source only."
SCHEMA = {"type": "object", "additionalProperties": False, "required": ["test_code"],
          "properties": {"test_code": {"type": "string"}}}
IMPORT = "from subject_under_test import bistatic_doppler"

ARMS = {
    "A": ("tests from the code",
          f"Here is a function from our codebase:\n\n{subject.BUGGY_SOURCE}\n"
          f"Write a pytest test module for it, 5 to 8 tests with concrete expected values. "
          f"Import it with: {IMPORT}"),
    "B": ("tests from the requirement",
          f"Requirement: {subject.REQUIREMENT}\n\nSignature: bistatic_doppler(p, v, tx, rx, lam) -> float\n\n"
          f"The implementation is not available to you. Write a pytest test module, 5 to 8 tests, with expected "
          f"values you derive yourself from the physics. Import it with: {IMPORT}"),
}


def run_suite(ws, code, implementation):
    ws.write("subject_under_test.py", implementation)
    ws.write("test_suite.py", code)
    res = ws.pytest("test_suite.py", timeout=120)
    return len(res.passed), len(res.outcomes)


def classify(wrong, right):
    (pw, nw), (pr, nr) = wrong, right
    if nw == 0 or nr == 0:
        return "broken"
    if pw < nw:
        return "caught the bug" if pr == nr else "caught it, but also rejects the right code"
    return "common-mode: passes the bug, rejects the right code" if pr < nr else "too weak: passes both"


def main():
    meter, rows = [], []
    with Workspace() as ws:
        for arm, (name, user) in ARMS.items():
            for k in range(SAMPLES):
                code = llm.ask("generator", SYSTEM, user, SCHEMA, tag="oracle", sample=k, meter=meter)["test_code"]
                wrong = run_suite(ws, code, subject.BUGGY_SOURCE)
                right = run_suite(ws, code, subject.CORRECT_SOURCE)
                rows.append((arm, name, k, wrong, right, classify(wrong, right)))
    c_wrong = independent_oracle.judge(_buggy())
    c_right = independent_oracle.judge(subject.bistatic_doppler_correct)
    report(rows, c_wrong, c_right, sum(m["recorded_usd"] for m in meter))


def _buggy():
    scope = {}
    exec(subject.BUGGY_SOURCE, scope)
    return scope["bistatic_doppler"]


def report(rows, c_wrong, c_right, usd):
    n = len(independent_oracle.CHECKS)
    failed = lambda msgs: len({m.split(":")[0] for m in msgs})     # noqa: E731  (one label per check)
    lines = ["# Test oracle experiment: tests from the code against tests from the requirement", "",
             "The function: bistatic Doppler shift of an echo. The planted mistake: the sign of the transmitter "
             "leg (`qa/oracle/subject.py`). Each suite ran against the wrong code and against the right code, "
             "in the sandbox.", "",
             "| arm | sample | passed on the WRONG code | passed on the RIGHT code | verdict |", "|---|---|---|---|---|"]
    for arm, name, k, (pw, nw), (pr, nr), verdict in rows:
        lines.append(f"| {arm}: {name} | {k + 1} | {pw}/{nw} | {pr}/{nr} | {verdict} |")
    lines.append(f"| C: independent oracle | | {n - failed(c_wrong)}/{n} checks | {n - failed(c_right)}/{n} checks "
                 f"| {'caught the bug' if c_wrong and not c_right else 'see below'} |")
    lines += ["", "Totals:", ""]
    for arm in ARMS:
        verdicts = [r[5] for r in rows if r[0] == arm]
        lines.append(f"- **{arm}, {ARMS[arm][0]}:** " + "; ".join(f"{v}: {verdicts.count(v)}"
                                                                 for v in dict.fromkeys(verdicts)))
    lines += [f"- **C, independent oracle:** caught the bug in {len(c_wrong)} ways; on the right code "
              f"{'no complaint' if not c_right else c_right}.", "",
              "What the independent oracle reported on the wrong code:", ""]
    lines += [f"- {m}" for m in c_wrong]
    lines += ["", f"Model: {llm.MODELS['generator']}, {SAMPLES} samples per arm. Model cost: ${usd:.2f} when "
              "recorded (replays are free)."]
    out = ROOT / "qa" / "oracle" / "RESULT.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
