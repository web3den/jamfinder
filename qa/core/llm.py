"""The only door to a language model in this repository. Four rules are enforced here, in code:

  1. Budget.     Every live call is written to qa/llm_ledger.jsonl with its tokens and its estimated cost.
                 A call that would start once the ledger has reached BUDGET_USD is refused.
  2. Egress.     A prompt that contains a key, an IP address or an e-mail address is refused before it is sent
                 (qa/core/guard.py).
  3. Replay.     Every answer is stored in qa/cassettes/ under a hash of the exact request. The same request is
                 answered from the cassette for free, so demos rerun at no cost and CI needs no key.
  4. The key.    It is read from the OPENAI_API_KEY environment variable at call time, never stored, never logged.

    from qa.core import llm
    out = llm.ask("generator", system="...", user="...", schema=SCHEMA, tag="mutation")   # -> dict

Roles and models. Different roles use different model generations on purpose: a reviewer from another family
is less likely to share the writer's blind spots (it is not independence, only less correlation).
"""
import hashlib
import json
import os
import threading
import time
from pathlib import Path

from qa.core.guard import find_leaks

ROOT = Path(__file__).resolve().parents[2]
LEDGER = ROOT / "qa" / "llm_ledger.jsonl"
CASSETTES = ROOT / "qa" / "cassettes"

MODELS = {
    "generator": "gpt-5.4-mini",    # writes code and tests: the "coding agent"
    "evaluator": "gpt-4.1-mini",    # reviews, judges, looks for reasons to reject
}
# US dollars per million tokens (input, output), from the provider's price list, November 2026.
PRICES = {
    "gpt-5.4-mini": (0.75, 4.50),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-6.1-terra": (1.00, 5.00),
    "gpt-5-mini": (0.25, 2.00),
}
BUDGET_USD = float(os.environ.get("QA_LLM_BUDGET_USD", "5.00"))   # for everything in qa/, all runs together


class BudgetExceeded(RuntimeError):
    pass


class EgressBlocked(RuntimeError):
    pass


class NoCassette(RuntimeError):
    pass


def spent():
    """Dollars spent so far, from the ledger of live calls."""
    if not LEDGER.exists():
        return 0.0
    return sum(json.loads(line)["usd"] for line in LEDGER.read_text().splitlines() if line.strip())


def _key(model, system, user, schema, effort, sample):
    blob = json.dumps([model, system, user, schema, effort, sample], sort_keys=True)
    return hashlib.sha256(blob.encode()).hexdigest()[:20]


_LOCK = threading.Lock()


def _log(row):
    with _LOCK, LEDGER.open("a") as fo:
        fo.write(json.dumps(row) + "\n")


def ask(role, system, user, schema=None, tag="misc", effort="low", sample=0, model=None, meter=None):
    """One model call. Returns the parsed JSON object when `schema` is given, else the text.

    sample   different values give independent answers to the same prompt (used for repeated eval runs)
    meter    a list; the call's cost in dollars is appended to it (0 for a replay)
    """
    model = model or MODELS[role]
    leaks = find_leaks(system + "\n" + user)
    if leaks:
        raise EgressBlocked("prompt not sent, it contains: " + ", ".join(f"{x.kind} '{x.masked()}'" for x in leaks))

    key = _key(model, system, user, schema, effort, sample)
    cassette = CASSETTES / tag / f"{key}.json"
    if cassette.exists() and os.environ.get("QA_LLM") != "live":
        rec = json.loads(cassette.read_text())                    # replayed: free, and not written to the ledger
        if os.environ.get("QA_CASSETTE_LOG"):                     # which recordings a run used (to prune stale ones)
            with _LOCK, open(os.environ["QA_CASSETTE_LOG"], "a") as fo:
                fo.write(str(cassette.relative_to(ROOT)) + "\n")
        if meter is not None:
            meter.append(dict(usd=0.0, recorded_usd=rec["usd"]))
        return rec["output"]
    if os.environ.get("QA_LLM") == "replay" or not os.environ.get("OPENAI_API_KEY"):
        raise NoCassette(f"no recorded answer for {tag}/{key} and live calls are off (set OPENAI_API_KEY)")
    if spent() >= BUDGET_USD:
        raise BudgetExceeded(f"ledger shows ${spent():.2f} spent of the ${BUDGET_USD:.2f} budget")

    from openai import OpenAI
    request = dict(model=model, input=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    if schema is not None:
        request["text"] = {"format": {"type": "json_schema", "name": "answer", "schema": schema, "strict": True}}
    if not model.startswith("gpt-4"):
        request["reasoning"] = {"effort": effort}
    t = time.time()
    resp = OpenAI().responses.create(**request)
    text = resp.output_text
    output = json.loads(text) if schema is not None else text
    p_in, p_out = PRICES.get(model, (10.0, 50.0))       # unknown model: assume an expensive one
    usd = (resp.usage.input_tokens * p_in + resp.usage.output_tokens * p_out) / 1e6
    rec = dict(tag=tag, role=role, model=model, effort=effort, sample=sample, system=system, user=user,
               schema=schema, output=output, tokens_in=resp.usage.input_tokens,
               tokens_out=resp.usage.output_tokens, usd=round(usd, 6), seconds=round(time.time() - t, 1))
    if meter is not None:
        meter.append(dict(usd=rec["usd"], recorded_usd=rec["usd"]))
    cassette.parent.mkdir(parents=True, exist_ok=True)
    cassette.write_text(json.dumps(rec, indent=1))
    _log(dict(time=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), tag=tag, role=role, model=model, key=key,
              tokens_in=rec["tokens_in"], tokens_out=rec["tokens_out"], usd=rec["usd"]))
    return output
