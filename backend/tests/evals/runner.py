"""LLM eval runner: prints intent and entity accuracy per language.

uv run python -m tests.evals.runner            # provider from LLM_PROVIDER (mock by default)
"""
import asyncio
from collections import defaultdict
from pathlib import Path

import yaml

from app.core.exceptions import ProviderUnavailable
from app.providers.llm import IntentContext, LLMProvider, get_llm
from app.tools.registry import ALLOWLIST
from app.utils.numbers import parse_amount_to_paise
from app.utils.text import normalize_name

CASES = Path(__file__).with_name("utterances.yaml")


def load() -> dict:
    return yaml.safe_load(CASES.read_text(encoding="utf-8"))


def _entities_match(expected: dict, ent: dict) -> tuple[bool, list[str]]:
    problems = []
    for k, v in expected.items():
        if k == "customer_name":
            if normalize_name(ent.get("customer_name") or "") != normalize_name(v):
                problems.append(f"customer_name {ent.get('customer_name')!r} != {v!r}")
        elif k == "amount":
            got = parse_amount_to_paise(ent.get("amount_phrase"))
            if got != v:
                problems.append(f"amount {got} != {v}")
        elif k == "date":
            d = ent.get("date") or {}
            for dk, dv in v.items():
                if d.get(dk) != dv:
                    problems.append(f"date.{dk} {d.get(dk)!r} != {dv!r}")
        elif ent.get(k) != v:
            problems.append(f"{k} {ent.get(k)!r} != {v!r}")
    return not problems, problems


async def _extract_paced(llm: LLMProvider, text: str, ctx: IntentContext):  # type: ignore[no-untyped-def]
    """Real providers on free tiers rate-limit or blip; wait and retry instead of scoring a failure."""
    for attempt in range(6):
        try:
            return await llm.extract_intent(text, ctx)
        except ProviderUnavailable as e:
            transient = "rate limit" in e.message.lower() or "unreachable" in e.message.lower()
            if not transient or attempt == 5:
                raise
            await asyncio.sleep(float(e.details.get("retry_after") or 30))
    raise AssertionError("unreachable")


async def run(provider: LLMProvider | None = None, verbose: bool = True) -> dict:
    llm = provider or get_llm()
    data = load()
    stats: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "intent": 0, "entities": 0})
    failures = []
    for case in data["cases"]:
        ctx = IntentContext(language=case["lang"], timezone="Asia/Kolkata", today_iso="2026-10-19",
                            allowed_intents=sorted(ALLOWLIST))
        intent = await _extract_paced(llm, case["text"], ctx)
        ent = intent.entities.model_dump()
        ok_type = intent.type == case["type"]
        ok_ent, problems = _entities_match(case.get("entities") or {}, ent)
        if ok_type and "missing" in case and sorted(case["missing"]) != sorted(intent.missing_fields):
            ok_ent = False
            problems.append(f"missing {intent.missing_fields} != {case['missing']}")
        for bucket in (case["lang"], "all"):
            stats[bucket]["n"] += 1
            stats[bucket]["intent"] += int(ok_type)
            stats[bucket]["entities"] += int(ok_type and ok_ent)
        if not (ok_type and ok_ent):
            failures.append({"text": case["text"], "expected": case["type"], "got": intent.type,
                             "problems": problems})
    scores = {lang: {"n": s["n"], "intent": s["intent"] / s["n"], "entities": s["entities"] / s["n"]}
              for lang, s in stats.items()}
    if verbose:
        print(f"\nLLM provider: {llm.name}")
        print(f"{'language':<10}{'cases':>7}{'intent':>10}{'entities':>10}")
        for lang in sorted(scores, key=lambda x: (x == "all", x)):
            s = scores[lang]
            print(f"{lang:<10}{s['n']:>7}{s['intent']:>10.0%}{s['entities']:>10.0%}")
        for f in failures:
            print(f"  FAIL: {f['text']!r}: expected {f['expected']}, got {f['got']} {f['problems']}")
    return {"provider": llm.name, "scores": scores, "failures": failures, "targets": data["targets"]}


if __name__ == "__main__":
    result = asyncio.run(run())
    key = "mock" if result["provider"] == "mock" else "real"
    target = result["targets"][key]
    overall = result["scores"]["all"]
    passed = overall["intent"] >= target["intent"] and overall["entities"] >= target["entities"]
    print(f"\nTargets ({key}): intent >= {target['intent']:.0%}, entities >= {target['entities']:.0%} -> "
          f"{'PASS' if passed else 'FAIL'}")
    raise SystemExit(0 if passed else 1)
