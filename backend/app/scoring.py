"""Deterministic scoring - no LLM here.

Order (checklist PDF p.2):
 1. applicability (N/A only where allowed),
 2. yes = full weight, no = 0; scale level picked from the allowed steps,
 3. scale -> points proportional to weight (top step = full weight),
 4. drop N/A criteria and redistribute their weight proportionally (max stays 100),
 5. round total to 2 decimals; no applicable weighted criteria -> total is None; gross errors flagged separately.
"""
from decimal import ROUND_HALF_UP, Decimal

from .checklist import Criterion, fmt_num


def round2(x: float) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def normalize_answer(answer) -> str:
    a = str(answer).strip().lower()
    aliases = {"да": "yes", "нет": "no", "n/a": "na", "н/д": "na", "true": "yes", "false": "no", "иә": "yes",
               "жоқ": "no"}
    a = aliases.get(a, a)
    try:
        return fmt_num(float(a))
    except ValueError:
        return a


def validate_answer(c: Criterion, answer) -> str:
    answer = normalize_answer(answer)
    if answer not in c.allowed_answers():
        raise ValueError(f"{c.key}: {answer!r} not in {c.allowed_answers()}")
    return answer


def raw_points(c: Criterion, answer: str) -> float | None:
    """Points before N/A redistribution; None when N/A or a flag criterion."""
    if answer == "na" or c.type == "flag":
        return None
    if c.type == "binary":
        if answer not in ("yes", "no"):
            raise ValueError(f"{c.key}: invalid answer {answer!r}")
        return float(c.weight) if answer == "yes" else 0.0
    levels = {fmt_num(s.value): s.value for s in c.scale}
    if answer not in levels:
        raise ValueError(f"{c.key}: {answer!r} is not a scale step {list(levels)}")
    return levels[answer] / max(levels.values()) * c.weight


def compute(criteria: list[Criterion], answers: dict[str, str]) -> dict:
    """answers: criterion key -> answer. Returns the score block stored on the evaluation."""
    rows = [(c, answers[c.key], raw_points(c, answers[c.key])) for c in criteria]

    def summarize(subset):
        applicable = [(c, p) for c, _, p in subset if p is not None and c.weight > 0]
        w = sum(c.weight for c, _ in applicable)
        if w == 0:
            return None, 0.0, 0.0
        earned = sum(p for _, p in applicable)
        return earned / w * 100, earned, w

    total, _, applicable_weight = summarize(rows)
    nominal = sum(c.weight for c in criteria if c.type != "flag")

    per = {}
    for c, a, p in rows:
        if p is None or c.weight == 0:
            per[c.key] = {"answer": a, "applicable": a != "na" and c.type != "flag" and c.weight > 0,
                          "points": None, "max_points": None, "weight": c.weight, "raw_points": None}
        else:
            # Points on the 100-point scale after N/A redistribution.
            per[c.key] = {"answer": a, "applicable": True,
                          "points": round2(p / applicable_weight * 100),
                          "max_points": round2(c.weight / applicable_weight * 100),
                          "weight": c.weight, "raw_points": round2(p)}

    sections = {}
    for sec in dict.fromkeys(c.section for c in criteria if c.section and c.type != "flag"):
        s_total, s_earned, s_w = summarize([r for r in rows if r[0].section == sec])
        sections[sec] = {"score_pct": round2(s_total) if s_total is not None else None,
                         "earned_raw": round2(s_earned), "applicable_weight": round2(s_w)}

    gross = [c.key for c, a, _ in rows if c.type == "flag" and a == "yes"]
    return {
        "total": round2(total) if total is not None else None,
        "max": 100,
        "gross_error": bool(gross),
        "gross_error_criteria": gross,
        "applicable_weight": round2(applicable_weight),
        "nominal_weight": round2(nominal),
        "criteria": per,
        "sections": sections,
    }
