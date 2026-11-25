"""Executable governance: the rules in qa/harness/policy.toml as checks that pass or fail.

    python -m qa.harness.gate                     # every check; exit code 1 if any fails (this is what CI runs)
    python -m qa.harness.gate --staged            # only what is about to be committed (the pre-commit hook)
    python -m qa.harness.gate approve tests/test_rules.py --reason "why the change is right"

  secrets        no key, token, IP address or e-mail address in any file git would commit; no .env or key files
  skips          every skip or xfail is listed in the policy with a reason, and every xfail is strict
  protected      protected tests are unchanged since their last recorded approval
  architecture   no forbidden imports (core library offline and self-contained, one door to a model)
  test count     the suite still collects at least the recorded number of tests
"""
import argparse
import ast
import fnmatch
import hashlib
import json
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from qa.core.guard import FORBIDDEN_FILES, find_leaks

ROOT = Path(__file__).resolve().parents[2]
POLICY = ROOT / "qa" / "harness" / "policy.toml"
MANIFEST = ROOT / "qa" / "harness" / "protected.json"
APPROVALS = ROOT / "qa" / "harness" / "approvals.jsonl"


def git_files(staged=False):
    """Paths git would commit: staged ones, or tracked plus new files that are not ignored."""
    if staged:
        cmd = ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"]
        return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout.split()
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    new = subprocess.run(["git", "ls-files", "--others", "--exclude-standard"], cwd=ROOT,
                         capture_output=True, text=True).stdout.split()
    return sorted(set(tracked) | set(new))


def read(rel, staged=False):
    if staged:
        p = subprocess.run(["git", "show", f":{rel}"], cwd=ROOT, capture_output=True)
        data = p.stdout
    else:
        path = ROOT / rel
        data = path.read_bytes() if path.is_file() else b""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return None                                    # images and other binary files


# ---- the checks: each returns a list of problems (empty = pass) ----------------------------------------------

def check_secrets(files, staged=False):
    problems = []
    for rel in files:
        if FORBIDDEN_FILES.search(rel):
            problems.append(f"{rel}: this kind of file must never be committed")
            continue
        text = read(rel, staged)
        for leak in find_leaks(text) if text else []:
            problems.append(f"{rel}:{leak.line}: {leak.kind} '{leak.masked()}'")
    return problems


def _is_test_file(rel):
    name = Path(rel).name
    return rel.endswith(".py") and (rel.startswith("tests/") or name.startswith("test_"))


def skip_markers(source):
    """(test name, marker, strict) for every skip/xfail decorator or call in a test module."""
    found = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for dec in node.decorator_list:
                call = dec if isinstance(dec, ast.Call) else None
                name = ast.unparse(call.func if call else dec)
                if name.endswith(("mark.skip", "mark.skipif", "mark.xfail")):
                    strict = any(k.arg == "strict" and getattr(k.value, "value", False) is True
                                 for k in (call.keywords if call else []))
                    found.append((node.name, name.split(".")[-1], strict))
            for inner in ast.walk(node):
                if isinstance(inner, ast.Call) and ast.unparse(inner.func) in ("pytest.skip", "pytest.xfail",
                                                                               "pytest.importorskip"):
                    found.append((node.name, ast.unparse(inner.func), False))
        if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "pytestmark" for t in node.targets):
            found.append(("<whole module>", "pytestmark", False))
    return found


def check_skips(files, policy, staged=False):
    allowed = policy.get("skips", {})
    problems = []
    for rel in filter(_is_test_file, files):
        text = read(rel, staged)
        if not text:
            continue
        for test, marker, strict in skip_markers(text):
            key = f"{rel}::{test}"
            if key not in allowed:
                problems.append(f"{key}: '{marker}' without an entry in policy.toml [skips]")
            elif marker == "xfail" and not strict:
                problems.append(f"{key}: xfail must be strict=True, or a fix (or a new bug) goes unnoticed")
    return problems


def assertion_counts(source):
    """Per test function: how many assertions it makes (assert statements and assert-like calls)."""
    counts = {}
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            n = 0
            for inner in ast.walk(node):
                if isinstance(inner, ast.Assert):
                    n += 1
                elif isinstance(inner, ast.Call):
                    fn = ast.unparse(inner.func)
                    if "assert" in fn.split(".")[-1].lower() or fn in ("pytest.raises", "_check"):
                        n += 1
            counts[node.name] = n
    return counts


def fingerprint(rel):
    text = (ROOT / rel).read_text()
    return dict(sha256=hashlib.sha256(text.encode()).hexdigest(), asserts=assertion_counts(text))


def check_protected(policy):
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    problems = []
    for rel in policy["protected"]["files"]:
        if not (ROOT / rel).exists():
            problems.append(f"{rel}: protected test file is missing")
            continue
        now, then = fingerprint(rel), manifest.get(rel)
        if then is None:
            problems.append(f"{rel}: not approved yet (run: python -m qa.harness.gate approve {rel} --reason ...)")
        elif now["sha256"] != then["sha256"]:
            weaker = [f"{t} {then['asserts'][t]}->{now['asserts'].get(t, 0)}" for t in then["asserts"]
                      if now["asserts"].get(t, 0) < then["asserts"][t]]
            note = f"; fewer assertions in: {', '.join(weaker)}" if weaker else ""
            problems.append(f"{rel}: changed since its last approval{note}")
    return problems


def imported_modules(source):
    names = set()
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            names |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names.add(node.module.split(".")[0])
    return names


def check_architecture(files, policy, staged=False):
    problems = []
    for rule in policy.get("architecture", []):
        for rel in files:
            if not rel.endswith(".py") or not fnmatch.fnmatch(rel, rule["files"]) or rel in rule.get("except", []):
                continue
            text = read(rel, staged)
            bad = sorted(imported_modules(text) & set(rule["forbid"])) if text else []
            if bad:
                problems.append(f"{rel}: imports {', '.join(bad)}; rule: {rule['rule']}")
    return problems


def check_test_count(policy):
    p = subprocess.run([sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider"],
                       cwd=ROOT, capture_output=True, text=True)
    n = sum(1 for line in p.stdout.splitlines() if "::" in line)
    minimum = policy["test_count"]["minimum"]
    return [] if n >= minimum else [f"only {n} tests collected, the policy requires at least {minimum}"]


# ---- running them --------------------------------------------------------------------------------------------

def run(staged=False, quick=False):
    policy = tomllib.loads(POLICY.read_text())
    files = git_files(staged)
    results = {
        "secrets": check_secrets(files, staged),
        "skips": check_skips(files, policy, staged),
        "protected": check_protected(policy),
        "architecture": check_architecture(files, policy, staged),
    }
    if not (staged or quick):
        results["test count"] = check_test_count(policy)
    width = max(map(len, results))
    print(f"governance gate: {len(files)} files {'staged' if staged else 'in the repository'}")
    for name, problems in results.items():
        print(f"  {name:<{width}}  {'PASS' if not problems else 'FAIL'}")
        for p in problems:
            print(f"  {'':<{width}}    - {p}")
    return 0 if not any(results.values()) else 1


def approve(rel, reason, allow_fewer=False):
    """Record a human's approval of a changed protected test: new fingerprint plus who, when and why."""
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    now, then = fingerprint(rel), manifest.get(rel)
    if then and not allow_fewer:
        fewer = [t for t in then["asserts"] if now["asserts"].get(t, 0) < then["asserts"][t]]
        if fewer:
            sys.exit(f"refused: fewer assertions in {', '.join(fewer)}; pass --allow-fewer-asserts if that is intended")
    who = subprocess.run(["git", "config", "user.name"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    manifest[rel] = now
    MANIFEST.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    with APPROVALS.open("a") as fo:
        fo.write(json.dumps(dict(time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), file=rel,
                                 by=who or "unknown", reason=reason, sha256=now["sha256"][:12])) + "\n")
    print(f"approved {rel} ({now['sha256'][:12]})")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", nargs="?", default="check", choices=["check", "approve"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--reason")
    ap.add_argument("--staged", action="store_true")
    ap.add_argument("--quick", action="store_true", help="skip the test count (it imports the whole suite)")
    ap.add_argument("--allow-fewer-asserts", action="store_true")
    a = ap.parse_args()
    if a.command == "approve":
        if not (a.file and a.reason):
            sys.exit("approve needs a file and --reason")
        approve(a.file, a.reason, a.allow_fewer_asserts)
    else:
        sys.exit(run(a.staged, a.quick))
