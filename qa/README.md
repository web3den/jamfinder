# qa/: verifying software when writing code is cheap

When a coding agent writes the code, the hard part is no longer writing it but knowing that it is right. This
folder is a working framework for that, applied to jamfinder's real code: signal processing, geometry and a
decision rule that says when to report a transmitter.

The idea throughout: **don't control every step the AI takes; control the conditions under which its work is
accepted**. Anything that can be checked deterministically is checked by code, outside the model.

## What is here, and what it found

| idea | folder | result on this repository |
|---|---|---|
| Executable governance | [harness](harness/README.md) | Rules an agent can't talk its way past: no keys or private data in commits or prompts, no unlisted skipped tests, protected tests need a recorded human approval, import rules, a hook that vetoes an agent's forbidden edits and commands before they run. 31 tests, each guardrail shown a planted violation |
| The test oracle problem | [oracle](oracle/README.md) | Tests a model wrote from buggy code passed the bug in 3 of 4 tries and rejected the correct code in 4 of 4. From the requirement: caught it in 4 of 4, one suite with wrong expectations of its own. Physics written without the code: caught it, no false alarm |
| Mutation testing, guided by survivors | [mutation](mutation/README.md) | The reporting rule: **100% line and branch coverage, yet 28 of 118 planted bugs got through (76%)**. A model wrote one test per survivor, each checked in the sandbox: **98%**, the last 2 provably equivalent. Geometry: 0% → 77% → 91% |
| Property-based testing | [properties](properties/README.md) | 13 properties hold over thousands of generated inputs. Two don't, shrunk to the smallest case: **a louder control search can turn "nothing" into "one"** (FINDING-001); coordinates fail exactly at the poles (FINDING-002) |
| Metamorphic testing | [metamorphic](metamorphic/README.md) | Eight relations on the full pipeline where the exact answer is unknown: turn, mirror or time-shift the scene and the answer follows to the millimetre |
| Differential testing, N-version | [differential](differential/README.md) | Agrees with pymap3d, SciPy and first principles. A second rule implementation written from the definition alone exposed 2 gaps in the specification (FINDING-003, -004) |
| Generator-evaluator loop | [bugfix_loop](bugfix_loop/README.md) | Ticket → failing test (red) → fix → green + whole suite + targeted mutation → review by another model family → policy decides whether a person must look → evidence file |
| Just-in-time tests | [jit](jit/README.md) | For a proposed change: old and new run side by side on generated inputs. A harmless-looking clean-up of the rule changed behaviour twice; both found, both pinned, both sent to a person |
| Evals of the agent itself | [evals](evals/README.md) | 7 tasks with hidden acceptance tests x 2 models x 2 runs, graded by code. Today's model solved 12 of 14, a candidate 14 of 14, with overlapping intervals. Neither touched a protected test on the trap task. The reviewer model never approved a wrong fix but objected to 19 of 26 right ones: safe, and too noisy to gate alone |
| Specification-driven, design by contract | [specs](specs/README.md) | 16 requirements with IDs traced to the tests that verify them; contracts checked on every call of a full test run; a vague requirement turned into 8 questions, 4 of them open product decisions |

## Findings in the package's own code

| | found by | what | status |
|---|---|---|---|
| FINDING-001 | property-based testing | a louder control search can turn the rule's "nothing" into "one" | a question for the rule's owner (proposed REQ-GATE-005) |
| FINDING-002 | property-based testing | coordinates convert to NaN or hundreds of km off exactly at a pole | known, low priority (proposed REQ-GEO-003) |
| FINDING-003 | N-version programming | the rule's definition is silent when there is no runner-up; the code then reports a lone candidate | pinned, to be written into the definition |
| FINDING-004 | N-version programming | the docstring says controls without `frac` are real; the code also honours an older `degenerate` flag | pinned, documentation to be completed |
| 28 gaps | mutation testing | bugs in the reporting rule that its fully covering tests let through | closed by 13 generated tests; 2 equivalent |
| 1 gap | differential testing | the geometry code had no direct test; a wrong Earth model would have passed everything | closed |

Each finding is a test: the open ones are strict `xfail`s or pinned behaviour, so CI notices the day they change.

## How the model is used, safely and cheaply

All model calls go through one file, [core/llm.py](core/llm.py):

- **Recorded and replayed.** Every answer is stored in `cassettes/` under a hash of the exact request; the same
  request is answered from the record for free. CI has no key and makes no calls, and checks that every
  model-driven result reproduces exactly from the record.
- **Budgeted.** Every live call is written to `llm_ledger.jsonl`; calls stop at a hard budget (default $5).
  Everything here cost $0.74.
- **Guarded.** A prompt with a key, an IP address or an e-mail address is refused before it is sent.
- **Two families.** The generator (`gpt-5.4-mini`) writes; the evaluator (`gpt-4.1-mini`) reviews. Not
  independence, but less correlated blind spots.
- **Sandboxed.** Code a model wrote runs only in [core/sandbox.py](core/sandbox.py): a copy of the repository,
  no keys in the environment, no network beyond loopback, a timeout.
- **Never the judge of its own work.** Every acceptance in this folder is made by running code.

The key is read from `OPENAI_API_KEY` at call time and never stored. Without it, everything still runs from the
recorded answers.

## Run it

    pip install -r requirements.txt -r qa/requirements.txt
    make -f qa/Makefile gate        # governance checks
    make -f qa/Makefile test        # every test, with design-by-contract checks on
    make -f qa/Makefile mutation    # mutation score gate (95%)
    make -f qa/Makefile trace       # requirements → tests → results
    make -f qa/Makefile demos       # the model-driven parts, replayed from the record
    make -f qa/Makefile evals       # the agent's evals

CI ([.github/workflows/qa.yml](../.github/workflows/qa.yml)) runs the gate, all tests with contracts, the
traceability check, mutation testing in a container without network, and the replay check, on every push.

## Limits, stated plainly

- The evals use 7 tasks and 2 runs per model: enough to show the method, too few to rank models with confidence.
  The intervals in the result say so.
- A generated test pins current behaviour; when that behaviour is wrong, it pins the bug. Generated tests are
  reviewed like any other change.
- Agreement between two implementations is evidence, not proof: both can share a mistake.
- The sandbox is macOS `sandbox-exec` or a Linux network namespace; where neither is available it falls back to
  an empty environment only, and says so.
