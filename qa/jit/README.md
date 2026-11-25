# Just-in-time tests

A regression suite tests what someone once thought of. Just-in-time testing makes tests for one change, at the
moment it is proposed, and treats the change as possibly wrong until shown otherwise.

    python -m qa.jit.run --demo          # a built-in "clean-up" of jf/rules.py (writes RESULT.md)
    python -m qa.jit.run --base HEAD     # your working tree's changes to jf/ against the last commit

The steps:

1. **What changed:** functions whose syntax tree differs; a docstring-only edit is recognised as such.
2. **How risky:** the file's risk class (`qa/harness/policy.toml`), whether comparisons, constants or arithmetic
   changed, and which requirements trace to the function (`qa/specs/requirements.toml`).
3. **Does behaviour differ:** the old and the new version are imported side by side and run on thousands of
   generated inputs. Hypothesis searches for an input where they disagree and shrinks it.
4. **Catching test:** for each difference, a model writes a readable test that pins the old behaviour. It is kept
   only if it passes on the old code and fails on the new.
5. **Who decides:** a behaviour change in a high-risk function goes to a person with the smallest example and
   one question, "intended or not?". No difference and low risk: no person needed.

## The demo

A plausible clean-up of the reporting rule, three edits that each look harmless
([RESULT.md](RESULT.md)):

| edit | found |
|---|---|
| `is_degenerate` shortened to `float(row.get("frac", 1.0)) < degenerate_frac` | behaviour differs: an old result row flagged `degenerate: true` now counts as a real control |
| condition (d) rewritten as `second / best < runner_up` | behaviour differs: a best score of 0 now raises `ZeroDivisionError` |
| a docstring reworded | documentation only, nothing to test |

Both behaviour changes got a catching test that passed on the old code and failed on the new, and both went to
a person, because the reporting rule is a high-risk file. The original test suite passes with both changes in
place; of the tests added by mutation-guided generation (`qa/mutation`), one catches the first, none the second.
Neither change looks like a behaviour change when read.

Functions without an input generator are reported as "cannot check automatically"; adding a generator to
`REGISTRY` in `run.py` brings them in.
