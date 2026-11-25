"""Run code that a model wrote, where it can do no harm.

    with Workspace() as ws:                          # a fresh copy of jf/, sim/, tests/ in a temporary folder
        ws.write("tests/test_generated.py", code)     # add or replace files in the copy only
        result = ws.pytest("tests/test_generated.py")
        result.passed, result.failed, result.outcomes  # outcomes: {test id: "passed" | "failed" | "error"}

What the code inside cannot do:
  - see any key: the environment is emptied (no OPENAI_API_KEY, no tokens), HOME points into the copy;
  - reach the network (only this machine's loopback, for tests with a fake local server), write outside the copy,
    or read key folders (macOS: sandbox-exec; Linux: a network namespace via unshare when the kernel allows it);
  - run forever: every run has a timeout.
The real repository is never touched.
"""
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
COPIED = ("jf", "sim", "tests", "tools", "examples", "qa/__init__.py", "qa/conftest.py", "qa/core")
HOME = Path.home()
SECRET_PLACES = [HOME / p for p in (".codex", ".ssh", ".aws", ".config", ".netrc", ".git-credentials", ".docker",
                                    ".claude", "Library/Keychains")]


@dataclass
class Result:
    returncode: int
    output: str
    outcomes: dict = field(default_factory=dict)     # test id -> "passed" | "failed" | "error" | "skipped"
    messages: dict = field(default_factory=dict)     # test id -> first line of the failure
    isolation: str = ""

    @property
    def passed(self):
        return [k for k, v in self.outcomes.items() if v == "passed"]

    @property
    def failed(self):
        return [k for k, v in self.outcomes.items() if v in ("failed", "error")]

    @property
    def ok(self):
        return self.returncode == 0 and bool(self.outcomes)


def stable(output, workdir):
    """Test output without what changes from run to run (timings, the temporary folder's name), so that a prompt
    built from it is the same every time and a recorded model answer can be replayed."""
    output = output.replace(str(workdir), "<repo>").replace(str(workdir).replace("/private", "", 1), "<repo>")
    output = re.sub(r" in \d+\.\d+s( \(\d+:\d+:\d+\))?", "", output)
    return re.sub(r"0x[0-9a-f]{6,}", "0x...", output)


def _macos_profile(workdir):
    deny_read = " ".join(f'(subpath "{p}")' for p in SECRET_PLACES)
    return ("(version 1)(allow default)(deny network*)"
            '(allow network-outbound (remote ip "localhost:*"))'      # loopback only: a broader rule such as
            '(allow network-bind (local ip "localhost:*"))'           # (allow network* (local ip ...)) lets
            '(allow network-inbound (local ip "localhost:*"))'        # outside traffic through (the test caught it)
            "(deny file-write*)"
            f'(allow file-write* (subpath "{workdir}") (subpath "/private/var/folders") (subpath "/dev"))'
            f"(deny file-read* {deny_read})")


def _linux_netns_works():
    try:
        return subprocess.run(["unshare", "-rn", "true"], capture_output=True, timeout=10).returncode == 0
    except (OSError, subprocess.SubprocessError):
        return False


class Workspace:
    def __init__(self, files=COPIED, keep=False):
        self.files, self.keep = files, keep

    def __enter__(self):
        self.dir = Path(tempfile.mkdtemp(prefix="qa-ws-")).resolve()
        for rel in self.files:
            src, dst = ROOT / rel, self.dir / rel
            if src.is_dir():
                shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
            elif src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)
        return self

    def __exit__(self, *exc):
        if not self.keep:
            shutil.rmtree(self.dir, ignore_errors=True)

    def path(self, rel):
        return self.dir / rel

    def read(self, rel):
        return (self.dir / rel).read_text()

    def write(self, rel, text):
        p = self.dir / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)

    def replace(self, rel, old, new):
        """Change exactly one occurrence of `old` in a copied file. Anything else is refused, so an edit can
        never land somewhere unintended."""
        text = self.read(rel)
        n = text.count(old)
        if n != 1:
            raise ValueError(f"{rel}: the text to replace occurs {n} times, not once")
        self.write(rel, text.replace(old, new))

    def run(self, args, timeout=300):
        """Run a command inside the copy, isolated. Returns (returncode, output, isolation used)."""
        env = {"PATH": "/usr/bin:/bin", "HOME": str(self.dir), "PYTHONDONTWRITEBYTECODE": "1",
               "PYTHONHASHSEED": "0", "QA_DETERMINISTIC": "1", "NUMBA_CACHE_DIR": str(self.dir / ".numba"), "MPLBACKEND": "Agg",
               "LANG": "C.UTF-8"}
        cmd = [sys.executable, *args]
        if platform.system() == "Darwin":
            cmd, isolation = ["sandbox-exec", "-p", _macos_profile(self.dir), *cmd], "sandbox-exec"
        elif _linux_netns_works():               # a new network namespace starts with loopback down: bring it up
            up = 'ip link set lo up 2>/dev/null; exec "$0" "$@"'
            cmd, isolation = ["unshare", "-rn", "sh", "-c", up, *cmd], "network namespace"
        else:
            isolation = "empty environment only"
        try:
            p = subprocess.run(cmd, cwd=self.dir, env=env, capture_output=True, text=True, timeout=timeout)
            return p.returncode, stable(p.stdout + p.stderr, self.dir), isolation
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or b"").decode(errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or "")
            return -9, stable(out, self.dir) + f"\nTIMEOUT after {timeout} s", isolation

    def pytest(self, *targets, timeout=300, extra=()):
        """Run pytest on the copy and read the per-test outcomes from its JUnit report."""
        report = self.dir / ".junit.xml"
        report.unlink(missing_ok=True)
        code, out, isolation = self.run(["-m", "pytest", "-q", "-p", "no:cacheprovider", "--tb=short",
                                         f"--junitxml={report}", *extra, *targets], timeout=timeout)
        res = Result(code, out, isolation=isolation)
        if report.exists():
            for case in ET.parse(report).getroot().iter("testcase"):
                tid = f"{case.get('classname')}::{case.get('name')}"
                kids = {c.tag: c for c in case}
                if "failure" in kids or "error" in kids:
                    bad = kids.get("failure", kids.get("error"))
                    res.outcomes[tid] = "failed" if "failure" in kids else "error"
                    res.messages[tid] = (bad.get("message") or "").splitlines()[0][:300] if bad.get("message") else ""
                elif "skipped" in kids:
                    res.outcomes[tid] = "skipped"
                else:
                    res.outcomes[tid] = "passed"
        return res
