# A closed bug-fixing loop: generator, evaluator, gates

The agent must demonstrate success; it cannot declare it.

    python -m qa.bugfix_loop.loop T01-track-gap      # any task id from qa/evals/tasks.py

| step | who | what has to be true to go on |
|---|---|---|
| 1 ingest | | a ticket that describes symptoms only |
| 2 locate | generator model | picks up to 3 files from an index of the package and its tests |
| 3 reproduce | generator model, checked by the harness | its new test FAILS on today's code, on an assert (red). One retry with the output |
| 4 repair | generator model, checked by the harness | exact edits, each matching its file exactly once, library files only. Edits to tests, CI or the harness are refused and recorded |
| 5 verify | the harness | the new test passes (green); the whole existing suite passes; a targeted mutation check of the changed lines, as a signal |
| 6 review | evaluator model, another family, fresh context | asked for reasons the fix is wrong, incomplete, or games the tests. It cannot run code |
| 7 decide | policy (`qa/harness/policy.toml`), not a model | failed gate: rejected. Otherwise a person looks if the file is high-risk, the change is large, the new test catches few planted bugs, or the reviewer objects |
| 8 evidence | | one markdown file with ticket, test, red output, diff, review and decision ([example](evidence/T01-track-gap.md)) |

The gates are final for what can be tested; the reviewer can only add doubt. It can send a change to a person,
never wave a failed gate through.

## One run, T01

The task is modelled on a bug this project really had: position feeds that report every 20 s gave empty tracks.
The planted bug makes `Path.valid` ignore `max_gap`. The agent
read `jf/tracks.py` and the existing track-gap tests, wrote a test that failed on the bug (`assert 0.0 > 0.95`),
and fixed the root cause in one line: `Path.valid` compared gaps with a hard-coded 12 s instead of
`self.max_gap`. New test green; the existing suite (45 tests) green.

The decision was still "needs a human", for two good reasons. The reviewer pointed out that the ticket asked for
two behaviours (valid at `max_gap=30`, invalid below 20 s) and the new test checks only the first. And the
targeted mutation check agreed: planted bugs on the changed line (`<=` to `<`, `>=` to `>`) do not make the new
test fail. A correct fix with a weak test is a case for a person, not for an automatic merge.

How well this loop does across many tasks and two models is measured in [qa/evals](../evals/README.md).
