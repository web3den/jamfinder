#!/usr/bin/env python3
"""A Claude Code PreToolUse hook: it runs before every edit or shell command of a coding agent and can veto it.

Wired up in .claude/settings.json. Claude Code sends the planned tool call as JSON on stdin; exit code 2 blocks
the call and the message on stderr goes back to the agent. Standard library only, Python 3.9 or newer.

What it blocks, and why the agent cannot argue its way past it:
  - edits to protected tests, to the harness itself, to CI and to the spending ledger
    (an agent may add tests; changing acceptance criteria needs a human: python -m qa.harness.gate approve ...)
  - shell commands that skip the gate (--no-verify), rewrite history (push --force), hide tests from pytest
    (--deselect, -k "not ...", --ignore), touch protected files through the shell, or read keys
"""
import fnmatch
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
GUARDED = ["qa/harness/*", ".github/workflows/*", ".githooks/*", ".claude/settings.json", "qa/llm_ledger.jsonl"]
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")

BASH_RULES = [
    (r"--no-verify", "skips the pre-commit gate"),
    (r"git\s+push\b.*\s(--force|-f)\b", "rewrites published history"),
    (r"pytest\b.*(--deselect|--ignore|-k\s*['\"]?\s*not\b)", "hides tests from the run"),
    (r"(\.codex/auth\.json|printenv|\$\{?OPENAI_API_KEY|\benv\s*$|\benv\s*\|)", "reads secrets"),
    (r"(curl|wget)\b[^|]*\|\s*(sh|bash|zsh|python)", "runs code straight from the internet"),
]


def protected_files():
    """The [protected] list of qa/harness/policy.toml, read without tomllib (Python 3.9 has none)."""
    text = open(os.path.join(ROOT, "qa", "harness", "policy.toml")).read()
    block = re.search(r"\[protected\]\s*files\s*=\s*\[(.*?)\]", text, re.S)
    return re.findall(r'"([^"]+)"', block.group(1)) if block else []


def relative(path):
    path = os.path.abspath(os.path.join(ROOT, path))
    return os.path.relpath(path, ROOT)


def verdict(call):
    """None if the call may run, else the reason it may not."""
    tool, args = call.get("tool_name", ""), call.get("tool_input", {}) or {}
    guarded = protected_files() + GUARDED
    if tool in EDIT_TOOLS:
        rel = relative(args.get("file_path") or args.get("notebook_path") or "")
        if any(fnmatch.fnmatch(rel, g) for g in guarded):
            return (f"{rel} is protected. Add a new test instead, or ask a human to change it and record the "
                    f"approval with: python -m qa.harness.gate approve {rel} --reason ...")
    if tool == "Bash":
        cmd = args.get("command", "")
        for pattern, why in BASH_RULES:
            if re.search(pattern, cmd):
                return f"blocked: this command {why}"
        writes = re.search(r"(sed\s+-i|>\s*|\btee\b|\bmv\b|\brm\b|\bgit\s+checkout\s+--)", cmd)
        touched = [g for g in guarded if "*" not in g and g in cmd]
        if writes and touched:
            return f"blocked: this command changes protected files ({', '.join(touched)})"
    return None


def main():
    reason = verdict(json.load(sys.stdin))
    if reason:
        print(reason, file=sys.stderr)
        sys.exit(2)
    sys.exit(0)


if __name__ == "__main__":
    main()
