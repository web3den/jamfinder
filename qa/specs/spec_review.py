"""Specification review: turn a vague product requirement into questions, and check which ones are answered.

    python -m qa.specs.spec_review         # writes qa/specs/SPEC_REVIEW.md

When code is cheap to write, the precision of the requirement decides the quality of the result. A model is good
at asking the awkward questions; deciding the answers stays with people. Two steps:
  1 a model reads a one-line product requirement and lists what it leaves open, each with a testable criterion
  2 a second model maps every question to the written requirements (qa/specs/requirements.toml) that answer it;
    what nothing answers is an open product decision, listed for a person
"""
import tomllib

from qa.core import llm
from qa.core.sandbox import ROOT

VAGUE = "Report the transmitter's location when the evidence is strong enough."

ASK = {"type": "object", "additionalProperties": False, "required": ["questions"],
       "properties": {"questions": {"type": "array", "items": {
           "type": "object", "additionalProperties": False, "required": ["question", "why", "testable_criterion"],
           "properties": {"question": {"type": "string"}, "why": {"type": "string"},
                          "testable_criterion": {"type": "string"}}}}}}
MAP = {"type": "object", "additionalProperties": False, "required": ["answers"],
       "properties": {"answers": {"type": "array", "items": {
           "type": "object", "additionalProperties": False, "required": ["question", "answered_by", "note"],
           "properties": {"question": {"type": "string"},
                          "answered_by": {"type": "array", "items": {"type": "string"}},
                          "note": {"type": "string"}}}}}}


def main():
    reqs = tomllib.loads((ROOT / "qa" / "specs" / "requirements.toml").read_text())["requirement"]
    asked = llm.ask("generator", "You are a product-minded test engineer reviewing requirements before any code is "
                    "written. You find what a requirement leaves undefined.",
                    f"Product requirement for a system that locates a radio transmitter from aircraft echoes, using one "
                    f"receiver and aircraft position reports:\n\n  \"{VAGUE}\"\n\nList the 8 most important questions "
                    f"this leaves open. For each: why it matters, and an acceptance criterion that would make it "
                    f"testable.", ASK, tag="spec-review")["questions"]
    written = "\n".join(f"{r['id']}: {r['text']}" for r in reqs)
    mapped = llm.ask("evaluator", "You check requirement coverage. Be strict: a requirement answers a question only "
                     "if it settles it, not if it is merely related.",
                     f"Written requirements:\n{written}\n\nQuestions:\n" +
                     "\n".join(f"- {q['question']}" for q in asked) +
                     "\n\nFor every question, list the requirement IDs that answer it (empty if none) and a short note.",
                     MAP, tag="spec-review")["answers"]
    by_q = {a["question"]: a for a in mapped}
    md = ["# Specification review", "", f"Vague requirement: *\"{VAGUE}\"*", "",
          f"Questions raised by {llm.MODELS['generator']}; mapped to `qa/specs/requirements.toml` by "
          f"{llm.MODELS['evaluator']}. A person decides the open ones.", "",
          "| # | question | testable criterion | answered by |", "|---|---|---|---|"]
    open_q = 0
    for i, q in enumerate(asked, 1):
        a = by_q.get(q["question"], {"answered_by": [], "note": ""})
        ids = ", ".join(a["answered_by"]) or "**open: a product decision**"
        open_q += not a["answered_by"]
        md.append(f"| {i} | {q['question']} | {q['testable_criterion']} | {ids} |")
    md += ["", f"{len(asked) - open_q} of {len(asked)} questions are settled by a written requirement; {open_q} are "
               "open.", "", "Why each question matters:", ""]
    md += [f"{i}. {q['why']}" for i, q in enumerate(asked, 1)]
    (ROOT / "qa" / "specs" / "SPEC_REVIEW.md").write_text("\n".join(md) + "\n")
    print("\n".join(md[:7 + len(asked) + 2]))


if __name__ == "__main__":
    main()
