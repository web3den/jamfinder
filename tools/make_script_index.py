#!/usr/bin/env python3
"""Write docs/script_index.md: one line per script, taken from its docstring or leading comment.

usage: make_script_index.py            (run from anywhere; writes docs/script_index.md next to this repository's README)
Stdlib only.
"""
import ast
import os
import re

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
FOLDERS = (("jf", "The method"), ("sim", "The simulator"), ("examples", "Examples"),
           ("tools", "Recording, repair, screening and run scripts"),
           ("analysis", "The pipeline steps, pictures, and simulations on real aircraft tracks"), ("tests", "Tests"))


def first_sentence(text, limit=220):
    para = re.split(r"\n\s*\n", text.strip(), maxsplit=1)[0]
    para = " ".join(para.split())
    para = re.split(r"\s+usage:", para, maxsplit=1, flags=re.I)[0]
    m = re.search(r"(?<=[a-z0-9)\"'`])[.:](?= [A-Z0-9(]|$)", para)
    s = para[: m.start() + 1] if m else para
    s = s.rstrip(":").rstrip()
    if len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0] + " ..."
    return s.replace("|", "/")


def describe(path):
    src = open(path, encoding="utf-8").read()
    if path.endswith(".py"):
        try:
            doc = ast.get_docstring(ast.parse(src))
        except SyntaxError:
            doc = None
        if doc:
            return first_sentence(doc)
    lines = [ln[1:].strip() for ln in src.split("\n")[:12] if ln.startswith("#") and not ln.startswith("#!")]
    return first_sentence(" ".join(lines)) if lines else ""


def main():
    out = ["# Script index", "",
           "One line per file, taken from the file's own docstring or leading comment. Regenerate with",
           "`python tools/make_script_index.py`. Usage lines and details are at the top of each file.", ""]
    for folder, title in FOLDERS:
        d = os.path.join(ROOT, folder)
        if not os.path.isdir(d):
            continue
        names = sorted(f for f in os.listdir(d) if f.endswith((".py", ".sh")) and f != "__init__.py")
        out += [f"## `{folder}/`: {title.lower()}", "", "| File | What it does |", "|---|---|"]
        out += [f"| `{folder}/{f}` | {describe(os.path.join(d, f))} |" for f in names]
        out.append("")
    dst = os.path.join(ROOT, "docs", "script_index.md")
    with open(dst, "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print(f"wrote {os.path.normpath(dst)}: {sum(1 for ln in out if ln.startswith('| `'))} files")


if __name__ == "__main__":
    main()
