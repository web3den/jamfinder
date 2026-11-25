# The harness: executable governance

Instruction files (CLAUDE.md, AGENTS.md) are advisory: an agent can misread or skip them. Anything that can be
stated as a deterministic rule is enforced here instead, outside the model, where it cannot be argued with.

| an instruction would say | enforced by | where |
|---|---|---|
| don't commit keys or private data | secret, IP and e-mail scan of every file git would commit | `gate.py`, pre-commit, CI |
| don't skip tests | every skip/xfail must be listed in `policy.toml` with a reason; every xfail must be strict | `gate.py` |
| don't weaken existing tests | protected tests are fingerprinted; a change needs a recorded human approval, and an approval with fewer assertions is refused | `gate.py approve` |
| keep the architecture | import rules: the core library is offline and self-contained; only `qa/core/llm.py` may talk to a model | `gate.py` |
| don't let the suite shrink | the collected test count may not fall below the recorded minimum | `gate.py` |
| don't edit acceptance criteria, don't bypass checks | the coding agent's edits and shell commands are vetoed before they run | `claude_hook.py` |
| don't let model-written code touch anything | it runs in a sandbox: no keys, no network beyond loopback, no writes outside a copy | `qa/core/sandbox.py` |
| don't leak secrets to a model; don't overspend | prompts are scanned before sending; a hard budget stops calls | `qa/core/llm.py` |
| only small, low-risk agent changes skip a human | what an agent may edit, and which files always need a person | `policy.toml [agent]` |

    python -m qa.harness.gate                        # all checks (CI runs this)
    git config core.hooksPath .githooks              # once per clone: the same checks before every commit
    python -m qa.harness.gate approve tests/test_rules.py --reason "why this change to a protected test is right"
    python -m pytest qa/harness                      # the guardrails' own tests

## The coding-agent hook

`.claude/settings.json` wires `claude_hook.py` into Claude Code as a PreToolUse hook. Before any edit or shell
command it receives the planned call as JSON and can veto it (exit code 2, with the reason sent back to the
agent). It blocks edits to protected tests, to this folder, to CI and to the spending ledger, and commands that
skip the gate (`--no-verify`), force-push, hide tests (`--deselect`, `-k "not ..."`), change protected files
through the shell, or read keys. Normal work (editing the library, adding new tests, running pytest) passes.

## The guardrails are tested too

`test_harness.py` shows every check a planted violation and requires it to be caught (a negative control), and
requires the real repository to pass (the positive control). This paid off while building: an early sandbox rule
meant to allow loopback connections also let traffic out to the internet. The sandbox's own test failed, and the
rule was narrowed to loopback only.

Files: `policy.toml` (the rules), `gate.py`, `claude_hook.py`, `protected.json` (fingerprints),
`approvals.jsonl` (who approved what, when, why), `test_harness.py`.
