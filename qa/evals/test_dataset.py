"""The golden dataset is itself tested: every hidden acceptance test must fail on its task's bug and pass once the
bug is undone. An eval built on an unsound task measures nothing."""
import pytest

from qa.core.sandbox import COPIED, Workspace
from qa.evals.tasks import TASKS


@pytest.mark.parametrize("task", TASKS, ids=[t["id"] for t in TASKS])
def test_hidden_test_fails_on_the_bug_and_passes_on_the_fix(task):
    with Workspace(files=COPIED + ("qa/oracle",)) as ws:
        ws.write("tests/test_hidden.py", task["hidden_test"])
        assert ws.pytest("tests/test_hidden.py").ok, "the hidden test must pass on the real code"
        for path, good, bad in task["bug"]:
            ws.replace(path, good, bad)
        on_bug = ws.pytest("tests/test_hidden.py")
        assert on_bug.returncode != 0 and on_bug.failed, "the hidden test must fail on the bug"
