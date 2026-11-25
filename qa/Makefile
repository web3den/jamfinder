# Shortcuts for the verification framework. Run from the repository root:  make -f qa/Makefile <target>
PY ?= .venv/bin/python

gate:          ## the governance gate: keys, skips, protected tests, imports, test count
	$(PY) -m qa.harness.gate
test:          ## every test, with design-by-contract checks on every call
	$(PY) -m pytest -q -p qa.specs.contracts tests qa
trace:         ## requirements -> tests -> results, into qa/specs/TRACEABILITY.md
	$(PY) -m qa.specs.trace
mutation:      ## mutation score of the reporting rule; fails below 95%
	$(PY) -m qa.mutation.mutate jf/rules.py tests/test_rules.py qa/mutation/generated/test_rules_killers.py --min-score 95
demos:         ## the model-driven demos (recorded answers replay for free; new ones need OPENAI_API_KEY)
	$(PY) -m qa.oracle.run
	$(PY) -m qa.mutation.guided jf/rules.py tests/test_rules.py
	$(PY) -m qa.differential.nversion
	$(PY) -m qa.specs.spec_review
	$(PY) -m qa.jit.run --demo
	$(PY) -m qa.bugfix_loop.loop T01-track-gap
evals:         ## the bug-fixing agent's evals: 7 tasks x 2 models x 2 runs
	$(PY) -m qa.evals.run
spend:         ## dollars spent on model calls so far
	@$(PY) -c "from qa.core import llm; print(f'\$${llm.spent():.2f} of \$${llm.BUDGET_USD:.2f}')"

.PHONY: gate test trace mutation demos evals spend
