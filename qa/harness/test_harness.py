"""The guardrails are code, so they get tests too. Each check is shown a planted violation and must catch it
(a negative control), and the real repository must pass (the positive control).

Fake secrets are assembled at run time, so this file itself never contains one.
"""
import json
import subprocess
import sys

import pytest

from qa.core import llm
from qa.core.guard import FORBIDDEN_FILES, find_leaks
from qa.core.sandbox import Workspace
from qa.harness import gate

FAKE_KEY = "sk-" + "proj-" + "Q7" * 20
FAKE_GH = "gh" + "p_" + "x9" * 18
FAKE_IP = ".".join(["10", "20", "30", "40"])


# ---- secrets ---------------------------------------------------------------------------------------------------

@pytest.mark.parametrize("text, kind", [
    (f"OPENAI_API_KEY={FAKE_KEY}", "OpenAI key"),
    (f"token: {FAKE_GH}", "GitHub token"),
    (f"server at {FAKE_IP} port 5555", "IP address"),
    ("contact " + "jane.doe" + "@" + "corp.io", "e-mail address"),
    ("-----BEGIN RSA " + "PRIVATE KEY-----", "private key block"),
])
def test_leaks_are_found(text, kind):
    assert [leak.kind for leak in find_leaks(text)] == [kind]


@pytest.mark.parametrize("text", ["loopback 127.0.0.1", "docs range 192.0.2.10", "numpy 2.5.4", "a@example.com",
                                  "task-1234567890abcdefghijklmnop", '"code": "x = 1\\n@pytest.mark.slow"'])
def test_harmless_text_is_not_flagged(text):
    assert find_leaks(text) == []


@pytest.mark.parametrize("path", [".env", "config/.env.local", "keys/server.pem", "home/.codex/auth.json"])
def test_key_files_are_refused_by_name(path):
    assert FORBIDDEN_FILES.search(path)


def test_a_prompt_with_a_key_is_never_sent():
    with pytest.raises(llm.EgressBlocked):
        llm.ask("generator", system="You write tests.", user=f"use this key: {FAKE_KEY}", tag="never-sent")


def test_spending_stops_at_the_budget(monkeypatch):
    monkeypatch.setattr(llm, "spent", lambda: llm.BUDGET_USD + 0.01)
    monkeypatch.setenv("OPENAI_API_KEY", "placeholder-not-a-key")
    with pytest.raises(llm.BudgetExceeded):
        llm.ask("generator", system="x", user="a prompt with no recorded answer", tag="never-sent")


# ---- skips, protected tests, architecture ----------------------------------------------------------------------

def test_unlisted_and_lenient_skips_are_seen():
    source = ("import pytest\n"
              "@pytest.mark.skip(reason='flaky')\ndef test_a(): assert 1\n"
              "@pytest.mark.xfail(reason='later')\ndef test_b(): assert 0\n"
              "def test_c():\n    pytest.skip('not today')\n")
    assert gate.skip_markers(source) == [("test_a", "skip", False), ("test_b", "xfail", False),
                                         ("test_c", "pytest.skip", False)]


def test_a_weakened_test_is_detected():
    before = "def test_gate():\n    assert f(1) == 'one'\n    assert f(0) == 'nothing'\n"
    after = "def test_gate():\n    assert f(1) == 'one'\n"
    assert gate.assertion_counts(before) == {"test_gate": 2}
    assert gate.assertion_counts(after) == {"test_gate": 1}


def test_forbidden_imports_are_seen():
    assert gate.imported_modules("import socket\nfrom urllib import request\nfrom . import geo\n") == {"socket",
                                                                                                     "urllib"}


def test_the_repository_passes_its_own_gate():
    assert gate.run(quick=True) == 0


# ---- the coding-agent hook -------------------------------------------------------------------------------------

def hook(tool, **tool_input):
    payload = json.dumps({"tool_name": tool, "tool_input": tool_input})
    p = subprocess.run([sys.executable, str(gate.ROOT / "qa" / "harness" / "claude_hook.py")], input=payload,
                       capture_output=True, text=True)
    return p.returncode, p.stderr.strip()


@pytest.mark.parametrize("tool, tool_input", [
    ("Edit", {"file_path": "tests/test_rules.py"}),
    ("Write", {"file_path": "qa/harness/policy.toml"}),
    ("Bash", {"command": "git commit --no-verify -m wip"}),
    ("Bash", {"command": "pytest -k 'not test_b_c_d_boundaries'"}),
    ("Bash", {"command": "cat ~/.codex/auth.json"}),
    ("Bash", {"command": "sed -i '' 's/== \"one\"/!= \"one\"/' tests/test_rules.py"}),
    ("Bash", {"command": "git push --force origin main"}),
])
def test_the_hook_blocks(tool, tool_input):
    code, reason = hook(tool, **tool_input)
    assert code == 2 and reason


@pytest.mark.parametrize("tool, tool_input", [
    ("Edit", {"file_path": "jf/rules.py"}),
    ("Write", {"file_path": "tests/test_new_behaviour.py"}),
    ("Bash", {"command": "python -m pytest -q tests/test_rules.py"}),
])
def test_the_hook_allows_normal_work(tool, tool_input):
    assert hook(tool, **tool_input) == (0, "")


# ---- the sandbox -----------------------------------------------------------------------------------------------

PROBE = '''
import os, socket
def test_no_key_in_the_environment():
    assert not [k for k in os.environ if "KEY" in k or "TOKEN" in k]
def test_no_network():
    s = socket.socket()
    s.settimeout(3)
    try:
        s.connect(("192.0.2.1", 443))
        reached = True
    except OSError as e:
        reached = e.errno not in (1, 13)        # 1, 13: refused by the sandbox, not by a timeout
    assert not reached
'''


def test_model_written_code_runs_without_keys_or_network():
    with Workspace() as ws:
        ws.write("tests/test_probe.py", PROBE)
        res = ws.pytest("tests/test_probe.py")
    assert "tests.test_probe::test_no_key_in_the_environment" in res.passed
    if res.isolation != "empty environment only":
        assert "tests.test_probe::test_no_network" in res.passed
