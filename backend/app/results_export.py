"""Submission file for the organizers: results.json, schema 1.0 (see the appendix "Как сдать результаты").

Built from the latest evaluation of every conversation in a dataset group, using FINAL answers (after appeals).
"""
import re

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Conversation, Evaluation
from .scoring import round2

TEAM_NAME = "Я не отвратимость"  # as registered with the organizers

# our checklist keys -> criterion_id of the submission format (the format fixes eight criteria)
CRITERION_IDS = {
    "c01_contact": "contact", "c02_needs": "discovery", "c03_identification": "identification",
    "c04_consultation": "consultation", "c05_empathy": "empathy", "c06_management": "dialogue",
    "c07_closing": "closure", "c08_gross": "critical",
}
BOOL = "bool"
ALLOWED = {  # criterion_id -> (allowed values, kind); kind "bool" means true/false/null, otherwise numbers
    "contact": ({True, False}, BOOL), "discovery": ({True, False, None}, BOOL),
    "identification": ({True, False, None}, BOOL), "consultation": ({0, 5, 10, 15, 20, None}, "num"),
    "empathy": ({True, False}, BOOL), "dialogue": ({0, 4, 7, 10}, "num"),
    "closure": ({True, False, None}, BOOL), "critical": ({True, False}, BOOL),
}


def submission_ready(criteria: list[dict]) -> tuple[bool, str]:
    """The organizers' format fixes eight criteria with the PDF's weights and scales. A checklist that differs can
    still be used in the product, but its evaluations cannot go into results.json."""
    from .checklist import DEFAULT_CHECKLIST
    by_key = {c["key"]: c for c in criteria}
    if set(by_key) != set(CRITERION_IDS):
        return False, "нужны ровно 8 критериев чек-листа из PDF"
    for d in DEFAULT_CHECKLIST["criteria"]:
        c = by_key[d["key"]]
        if c["type"] != d["type"] or float(c["weight"]) != float(d["weight"]) or \
                bool(c.get("na_allowed")) != bool(d.get("na_allowed")):
            return False, f"«{d['name']}»: тип, вес или N/A отличаются от PDF"
        if d["type"] == "scale" and sorted(float(s["value"]) for s in c["scale"]) != \
                sorted(float(s["value"]) for s in d["scale"]):
            return False, f"«{d['name']}»: ступени шкалы отличаются от PDF"
    return True, "подходит для сдачи результатов"


def _value(answer: str):
    if answer == "na":
        return None
    if answer in ("yes", "no"):
        return answer == "yes"
    n = float(answer)
    return int(n) if n == int(n) else n


def _turns(row: dict) -> list[int]:
    """Turn numbers are 1-based over the original transcript array."""
    ev = [e["index"] + 1 for e in row.get("evidence") or []]
    if not ev and row.get("checked_range"):
        ev = sorted({row["checked_range"][0] + 1, row["checked_range"][1] + 1})
    return ev


def _rationale(text) -> str:
    """Explanations cite turns as [N] counted from 0; the submission counts from 1, like evidence_turns."""
    def shift(m):
        return "[" + re.sub(r"\d+", lambda d: str(int(d.group()) + 1), m.group(1)) + "]"
    return re.sub(r"\[(\d+(?:\s*[,–-]\s*\d+)*)\]", shift, " ".join(str(text).split()))


def _error(cid: str, msg: str) -> dict:
    return {"conversation_id": cid, "status": "error", "criteria": [], "score": None, "error": msg}


def _record(ev: Evaluation) -> dict:
    rows = {r["key"]: r for r in ev.results or []}
    crit = []
    for key, cid in CRITERION_IDS.items():
        fc = (ev.final_score or {}).get("criteria", {}).get(key)
        if key not in rows or fc is None:
            return _error(ev.conversation_id, f"В оценке нет критерия {key}: использован другой чек-лист")
        value = _value(fc["answer"])
        turns = _turns(rows[key])
        if cid == "critical" and value is False and not turns:
            # A negative finding covers the operator's contributions across the transcript.
            turns = [n for n, turn in enumerate(ev.conversation.transcript, 1)
                     if turn["speaker"] == "operator"]
        crit.append({"criterion_id": cid, "value": value,
                     "rationale": _rationale(rows[key]["explanation"]), "evidence_turns": turns})
    fs = ev.final_score
    return {"conversation_id": ev.conversation_id, "status": "ok", "criteria": crit,
            "score": {"final_score": None if fs["total"] is None else round2(fs["total"]),
                      "critical_flag": bool(fs["gross_error"])}}


def build(db: Session, group: str, team_name: str = TEAM_NAME) -> dict:
    cids = db.scalars(select(Conversation.id).where(Conversation.dataset_group == group)
                      .order_by(Conversation.id)).all()
    latest: dict[str, Evaluation] = {}
    for ev in db.scalars(select(Evaluation).where(Evaluation.conversation_id.in_(cids)).order_by(Evaluation.id)):
        latest[ev.conversation_id] = ev
    results, models = [], []
    for cid in cids:
        ev = latest.get(cid)
        if ev is None:
            results.append(_error(cid, "Диалог не оценён"))
        elif ev.status == "done":
            results.append(_record(ev))
            models += [m for m in (ev.models or {}).values() if m]
        else:
            results.append(_error(cid, ev.error or "Оценка не завершена"))
    return {"schema_version": "1.0", "team_name": team_name,
            "model": {"mode": "external_api", "name": " + ".join(dict.fromkeys(models)) or "unknown"},
            "results": results}


def _value_ok(cid: str, v) -> bool:
    allowed, kind = ALLOWED[cid]
    if v is None:
        return None in allowed
    if kind == BOOL:
        return isinstance(v, bool)
    return not isinstance(v, bool) and v in allowed


def validate(doc: dict, expect: int | None = None) -> list[str]:
    """Problems that would break the organizers' parser; empty list = fine to push."""
    bad, seen = [], set()
    res = doc.get("results", [])
    if expect is not None and len(res) != expect:
        bad.append(f"ожидалось {expect} записей, найдено {len(res)}")
    for r in res:
        cid = r.get("conversation_id")
        if cid in seen:
            bad.append(f"{cid}: ID повторяется")
        seen.add(cid)
        if r.get("status") == "error":
            if r.get("criteria") or r.get("score") is not None or not r.get("error"):
                bad.append(f"{cid}: для error нужны пустой criteria, score=null и текст error")
            continue
        ids = [c.get("criterion_id") for c in r.get("criteria", [])]
        if sorted(ids) != sorted(ALLOWED):
            bad.append(f"{cid}: нужны все 8 критериев ровно по разу, есть {ids}")
            continue
        for c in r["criteria"]:
            if not _value_ok(c["criterion_id"], c["value"]):
                bad.append(f"{cid}/{c['criterion_id']}: недопустимое значение {c['value']!r}")
            if not c.get("rationale") or not isinstance(c.get("evidence_turns"), list):
                bad.append(f"{cid}/{c['criterion_id']}: нужны rationale и evidence_turns")
        crit = next(c for c in r["criteria"] if c["criterion_id"] == "critical")
        if (r.get("score") or {}).get("critical_flag") != crit["value"]:
            bad.append(f"{cid}: critical_flag не совпадает со значением critical")
    return bad
