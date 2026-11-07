"""Evaluation pipeline.

  Gemini (full analysis: facts, answer, explanation, evidence)  ┐ in parallel,
  Jev    (independent answer + calibrated probability)          ┘ independent of each other
      -> merge per criterion (agree / minor / disputed -> Gemini adjudication / review)
      -> evidence validation against the transcript
      -> deterministic scoring (scoring.compute)
"""
import asyncio
import contextlib
import time

from . import prompts, scoring
from .checklist import Criterion
from .config import settings
from .llm import gemini, jev

_sem: asyncio.Semaphore | None = None


def sem() -> asyncio.Semaphore:
    global _sem
    if _sem is None:
        _sem = asyncio.Semaphore(settings.max_concurrency)
    return _sem


def _make_validator(criteria: list[Criterion], n_turns: int, key="criteria"):
    def validate(data):
        block = data[key] if key else data
        for c in criteria:
            scoring.validate_answer(c, block[c.key]["answer"])
    return validate


def _enrich_evidence(idx_list, transcript) -> tuple[list[dict], list[int]]:
    ok, bad = [], []
    for i in dict.fromkeys(idx_list or []):
        if isinstance(i, int) and 0 <= i < len(transcript):
            t = transcript[i]
            ok.append({"index": i, "timestamp": t.get("timestamp"), "speaker": t.get("speaker"), "text": t.get("text")})
        else:
            bad.append(i)
    return ok, bad


def _clean_range(r, n):
    if not r or len(r) < 2:
        return None
    a, b = max(0, min(r[0], r[1])), min(n - 1, max(r[0], r[1]))
    return [a, b] if a <= b else None


def _scale_distance(c: Criterion, a: str, b: str) -> int | None:
    if c.type != "scale" or "na" in (a, b):
        return None
    order = [scoring.fmt_num(s.value) for s in c.scale]
    return abs(order.index(a) - order.index(b))


async def _run_jev(criteria, conv):
    if not jev.enabled():
        return None, None, "disabled"
    try:
        answers, usage = await jev.ask(prompts.jev_state(conv), prompts.jev_questions(criteria))
        return answers, usage, None
    except Exception as e:  # noqa: BLE001 - Jev is optional; never fail the evaluation because of it
        return None, None, str(e)


async def evaluate(conv: dict, criteria: list[Criterion], with_feedback: bool = True, use_sem: bool = True) -> dict:
    transcript = conv["transcript"]
    n = len(transcript)

    async with (sem() if use_sem else contextlib.nullcontext()):
        t_start = time.perf_counter()  # model time only, not time spent queued for a slot
        g_task = gemini.generate_json(
            prompts.build_eval_prompt(criteria, conv, with_feedback),
            prompts.build_eval_schema(criteria, with_feedback),
            system=prompts.SYSTEM_PROMPT,
            validate=_make_validator(criteria, n),
        )
        (g, g_usage), (j_answers, j_usage, j_err) = await asyncio.gather(g_task, _run_jev(criteria, conv))

        results, disputes = [], []
        for c in criteria:
            gc = g["criteria"][c.key]
            g_ans = scoring.validate_answer(c, gc["answer"])
            row = {
                "key": c.key, "name": c.name, "section": c.section, "type": c.type, "weight": c.weight,
                "gemini": {"answer": g_ans, "explanation": gc["explanation"], "analysis": gc.get("analysis"),
                           "confidence": gc.get("confidence")},
                "jev": None, "agreement": "gemini_only", "adjudicated": False, "adjudication": None,
                "answer": g_ans, "explanation": gc["explanation"], "confidence": gc.get("confidence"),
                "_evidence_idx": gc.get("evidence") or [], "_range": gc.get("checked_range"),
            }
            if j_answers and c.key in j_answers:
                ja = j_answers[c.key]
                j_ans = scoring.normalize_answer(ja.get("choice"))
                probs = ja.get("probabilities") or {}
                j_prob = float(probs.get(ja.get("choice"), ja.get("confidence") or 0))
                row["jev"] = {"answer": j_ans, "probability": round(j_prob, 3),
                              "confidence": ja.get("confidence"), "probabilities": probs}
                if j_ans == g_ans:
                    row["agreement"] = "agree"
                elif _scale_distance(c, g_ans, j_ans) == 1:
                    row["agreement"] = "minor"  # adjacent scale steps: keep Gemini, no flag
                elif j_prob >= settings.jev_adjudicate_threshold:
                    row["agreement"] = "disputed"
                    disputes.append({"criterion": c, "first_answer": g_ans, "first_explanation": gc["explanation"],
                                     "alt_answer": j_ans, "alt_prob": j_prob})
                else:
                    row["agreement"] = "review"
            results.append(row)

        adj_usage = None
        if disputes:
            dc = [d["criterion"] for d in disputes]
            try:
                adj, adj_usage = await gemini.generate_json(
                    prompts.build_adjudication_prompt(dc, conv, disputes),
                    prompts.build_adjudication_schema(dc),
                    system=prompts.SYSTEM_PROMPT,
                    validate=_make_validator(dc, n, key=None),
                )
                by_key = {r["key"]: r for r in results}
                for c in dc:
                    a = adj[c.key]
                    row = by_key[c.key]
                    new = scoring.validate_answer(c, a["answer"])
                    row["adjudicated"] = True
                    row["adjudication"] = {"answer": new, "explanation": a["explanation"],
                                           "changed": new != row["answer"]}
                    row.update(answer=new, explanation=a["explanation"], confidence=a.get("confidence"),
                               _evidence_idx=a.get("evidence") or row["_evidence_idx"],
                               _range=a.get("checked_range") or row["_range"])
            except gemini.LLMError as e:
                for d in disputes:
                    next(r for r in results if r["key"] == d["criterion"].key)["adjudication"] = {"error": str(e)}

    # Evidence validation + review flags
    for row in results:
        ev, bad = _enrich_evidence(row.pop("_evidence_idx"), transcript)
        row["evidence"] = ev
        row["checked_range"] = _clean_range(row.pop("_range"), n)
        reasons = []
        if row["agreement"] in ("disputed", "review"):
            reasons.append("models_disagree")
        if row["confidence"] == "low":
            reasons.append("low_confidence")
        if bad:
            reasons.append("invalid_evidence_dropped")
        if not ev and not row["checked_range"] and row["type"] != "flag":
            reasons.append("no_evidence")
        row["needs_review"] = bool(reasons)
        row["review_reasons"] = reasons

    score = scoring.compute(criteria, {r["key"]: r["answer"] for r in results})
    for row in results:
        row.update({k: score["criteria"][row["key"]][k] for k in ("points", "max_points", "applicable")})

    feedback = g.get("feedback")
    if feedback:
        for item in feedback.get("strengths", []) + feedback.get("improvements", []):
            t = item.get("turn")
            item["timestamp"] = transcript[t]["timestamp"] if isinstance(t, int) and 0 <= t < n else None

    usage = {"gemini": _sum_usage(g_usage, adj_usage), "jev": j_usage, "jev_error": j_err}
    cost = gemini.cost_usd(usage["gemini"]) + (jev.cost_usd(j_usage) if j_usage else 0.0)
    return {
        "facts": g["facts"],
        "results": results,
        "score": score,
        "feedback": feedback,
        "operator_name": (g["facts"].get("operator_name") or None),
        "models": {"gemini": settings.gemini_model, "jev": (j_usage or {}).get("model") if j_usage else None},
        "usage": usage,
        "cost_usd": round(cost, 6),
        "duration_ms": int((time.perf_counter() - t_start) * 1000),
    }


def _sum_usage(a: dict, b: dict | None) -> dict:
    if not b:
        return a
    return {k: a.get(k, 0) + b.get(k, 0) for k in set(a) | set(b)}


async def review_appeal(c: Criterion, conv: dict, current: dict, comment: str) -> dict:
    """AI second look for the human reviewer (does not change the score)."""
    data, usage = await gemini.generate_json(
        prompts.build_appeal_review_prompt(c, conv, current, comment),
        prompts.appeal_review_schema(c),
        system=prompts.SYSTEM_PROMPT,
        validate=lambda d: scoring.validate_answer(c, d["answer"]),
    )
    ev, _ = _enrich_evidence(data.get("evidence"), conv["transcript"])
    return {"suggested_answer": scoring.normalize_answer(data["answer"]), "appeal_justified": data["appeal_justified"],
            "explanation": data["explanation"], "evidence": ev, "confidence": data.get("confidence"),
            "cost_usd": round(gemini.cost_usd(usage), 6)}
