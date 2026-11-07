"""Shared logic between routers: running evaluations, recomputing final scores, serialization."""
import asyncio
import json
import logging
from datetime import datetime, timezone

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import pipeline, scoring
from .checklist import DEFAULT_CHECKLIST, ChecklistIn, Criterion
from .config import ROOT, settings
from .db import SessionLocal
from .models import Appeal, Checklist, Conversation, Evaluation

log = logging.getLogger(__name__)
_tasks: set[asyncio.Task] = set()


# ---------- checklists ----------

def seed_default_checklist(db: Session):
    if db.scalar(select(Checklist.id).limit(1)) is None:
        cl = ChecklistIn(**DEFAULT_CHECKLIST)
        db.add(Checklist(name=cl.name, description=cl.description, is_active=True,
                         criteria=[c.model_dump() for c in cl.criteria]))
        db.commit()


def seed_conversations(db: Session, group: str = "DEV") -> int:
    """Empty database -> load the saved dataset copy (dialogs only, no scores: evaluation still runs live)."""
    if db.scalar(select(Conversation.id).limit(1)) is not None:
        return 0
    path = DATASETS_DIR / f"{group}.json"
    if not path.is_file():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    ids = upsert_conversations(db, data["records"] if isinstance(data, dict) else data, group)
    log.info("seeded %d conversations from %s", len(ids), path)
    return len(ids)


def active_checklist(db: Session) -> Checklist:
    cl = db.scalar(select(Checklist).where(Checklist.is_active).order_by(Checklist.id.desc()))
    if cl is None:
        cl = db.scalar(select(Checklist).order_by(Checklist.id.desc()))
    return cl


def criteria_of(snapshot_or_list) -> list[Criterion]:
    items = snapshot_or_list["criteria"] if isinstance(snapshot_or_list, dict) else snapshot_or_list
    return [Criterion(**c) for c in items]


# ---------- dataset ----------

DATASETS_DIR = ROOT / "datasets"


async def fetch_dataset(group_id: str) -> list[dict]:
    """Organizers' API first; if it is unavailable, fall back to the saved copy datasets/<group>.json."""
    return (await fetch_dataset_with_source(group_id))[0]


async def fetch_dataset_with_source(group_id: str) -> tuple[list[dict], str]:
    try:
        return await fetch_dataset_api(group_id), "api"
    except Exception as e:  # noqa: BLE001
        path = DATASETS_DIR / f"{group_id}.json"
        if not path.is_file() or not path.resolve().is_relative_to(DATASETS_DIR.resolve()):
            raise
        log.warning("dataset API failed (%s), using %s", e, path)
        data = json.loads(path.read_text(encoding="utf-8"))
        return data["records"] if isinstance(data, dict) else data, "file"


async def fetch_dataset_api(group_id: str) -> list[dict]:
    if not settings.dataset_api_url:
        raise RuntimeError("DATASET_API_URL is not set")
    sep = "&" if "?" in settings.dataset_api_url else "?"
    async with httpx.AsyncClient(timeout=120) as http:
        r = await http.get(f"{settings.dataset_api_url}{sep}group_id={group_id}")
    r.raise_for_status()
    data = r.json()
    if not data.get("isSuccess"):
        raise RuntimeError(f"Dataset API error: {data.get('error')}")
    return data["data"]["records"]


def upsert_conversations(db: Session, records: list[dict], group: str | None) -> list[str]:
    ids = []
    for rec in records:
        cid = rec["conversation_id"]
        conv = db.get(Conversation, cid) or Conversation(id=cid)
        conv.dataset_group = group or conv.dataset_group
        conv.channel = rec.get("channel") or "agent chat"
        conv.language = (rec.get("language") or "RU").upper()
        conv.audio_url = rec.get("audio_url") or (conv.audio_url if rec.get("has_audio") else None)
        conv.transcript = rec["transcript"]
        db.add(conv)
        ids.append(cid)
    db.commit()
    return ids


def conv_dict(conv: Conversation) -> dict:
    return {"id": conv.id, "channel": conv.channel, "language": conv.language, "transcript": conv.transcript}


# ---------- evaluation ----------

def create_evaluation(db: Session, conversation_id: str, checklist: Checklist, batch_id: str | None = None) -> Evaluation:
    ev = Evaluation(conversation_id=conversation_id, checklist_id=checklist.id, batch_id=batch_id, status="pending",
                    checklist_snapshot={"id": checklist.id, "name": checklist.name, "criteria": checklist.criteria})
    db.add(ev)
    db.commit()
    return ev


ANSWER_LABEL = {"yes": "Да", "no": "Нет", "na": "N/A"}


def calibration_examples(db: Session, criteria: list[Criterion], exclude_conversation: str | None = None) -> dict[str, list[str]]:
    """Corrections that reviewers made through appeals (decision 'changed'), newest first, per criterion.
    They are fed into the prompt so the judge learns how people read the rules. The conversation being
    evaluated is excluded: its own corrections would just leak the answer."""
    if not settings.calibration_enabled or settings.calibration_examples <= 0:
        return {}
    keys = {c.key for c in criteria}
    q = (select(Appeal).join(Evaluation).where(Appeal.status == "changed", Appeal.criterion_key.in_(keys))
         .order_by(Appeal.decided_at.desc(), Appeal.id.desc()))
    out: dict[str, list[str]] = {}
    for ap in db.scalars(q):
        items = out.setdefault(ap.criterion_key, [])
        if len(items) >= settings.calibration_examples or not (ap.reason or "").strip():
            continue
        if exclude_conversation and ap.evaluation.conversation_id == exclude_conversation:
            continue
        lab = lambda a: ANSWER_LABEL.get(a, a)  # noqa: E731
        row = next((r for r in ap.evaluation.results or [] if r["key"] == ap.criterion_key), None)
        quote = ""
        if row and row.get("evidence"):
            quote = " Реплика: «" + " ".join(str(row["evidence"][0]["text"]).split())[:140] + "»."
        items.append(f"ИИ ответил «{lab(ap.original_answer)}», проверяющий исправил на «{lab(ap.new_answer)}». "
                     f"Причина: {ap.reason.strip()[:240]}.{quote}")
    return {k: v for k, v in out.items() if v}


async def run_evaluation(eval_id: int, with_feedback: bool = True) -> None:
    """Always calls the models - no caching by conversation_id (results must come from real analysis)."""
    with SessionLocal() as db:
        ev = db.get(Evaluation, eval_id)
        conv = conv_dict(ev.conversation)
        criteria = criteria_of(ev.checklist_snapshot)
        examples = calibration_examples(db, criteria, exclude_conversation=ev.conversation_id)
    try:
        async with pipeline.sem():  # status becomes "running" only once a concurrency slot is free
            with SessionLocal() as db:
                db.get(Evaluation, eval_id).status = "running"
                db.commit()
            out = await pipeline.evaluate(conv, criteria, with_feedback=with_feedback, use_sem=False,
                                          examples=examples)
    except Exception as e:  # noqa: BLE001
        log.exception("evaluation %s failed", eval_id)
        with SessionLocal() as db:
            ev = db.get(Evaluation, eval_id)
            ev.status, ev.error, ev.finished_at = "error", str(e)[:2000], datetime.now(timezone.utc)
            db.commit()
        return
    with SessionLocal() as db:
        ev = db.get(Evaluation, eval_id)
        ev.facts, ev.results, ev.feedback = out["facts"], out["results"], out["feedback"]
        ev.initial_score = ev.final_score = out["score"]
        ev.operator_name, ev.models = out["operator_name"], out["models"]
        ev.usage = {**out["usage"], "calibration_examples": out.get("calibration_examples", 0)}
        ev.cost_usd, ev.duration_ms = out["cost_usd"], out["duration_ms"]
        ev.status, ev.error, ev.finished_at = "done", None, datetime.now(timezone.utc)
        db.commit()


def spawn(coro) -> None:
    t = asyncio.create_task(coro)
    _tasks.add(t)
    t.add_done_callback(_tasks.discard)


# ---------- appeals / final score ----------

def final_answers(ev: Evaluation) -> dict[str, str]:
    answers = {r["key"]: r["answer"] for r in ev.results}
    for ap in ev.appeals:
        if ap.status == "changed" and ap.new_answer is not None:
            answers[ap.criterion_key] = ap.new_answer
    return answers


def recompute_final(ev: Evaluation) -> None:
    ev.final_score = scoring.compute(criteria_of(ev.checklist_snapshot), final_answers(ev))


# ---------- serialization ----------

def confidence_of(ev: Evaluation) -> dict:
    """How sure the AI is about this evaluation: criteria flagged for a human look (models disagree, low confidence,
    no evidence). Flags are those raised at evaluation time, before any human review."""
    rows = [r for r in (ev.results or []) if r.get("type") != "flag"]
    flagged = sum(1 for r in rows if r.get("needs_review"))
    level = "high" if flagged == 0 else "medium" if flagged <= 2 else "low"
    return {"level": level, "flagged": flagged, "total": len(rows)}


def eval_summary(ev: Evaluation) -> dict:
    fs, isc = ev.final_score or {}, ev.initial_score or {}
    return {
        "id": ev.id, "conversation_id": ev.conversation_id, "checklist_id": ev.checklist_id,
        "checklist_name": (ev.checklist_snapshot or {}).get("name"), "batch_id": ev.batch_id, "status": ev.status,
        "error": ev.error, "initial_total": isc.get("total"), "final_total": fs.get("total"),
        "gross_error": fs.get("gross_error"), "operator_name": ev.operator_name,
        "needs_review": sum(1 for r in (ev.results or []) if r.get("needs_review")),
        "confidence": confidence_of(ev) if ev.results else None,
        "open_appeals": sum(1 for a in ev.appeals if a.status == "open"),
        "cost_usd": ev.cost_usd, "duration_ms": ev.duration_ms,
        "created_at": ev.created_at, "finished_at": ev.finished_at,
    }


def appeal_dict(ap: Appeal, with_context: bool = False) -> dict:
    d = {
        "id": ap.id, "evaluation_id": ap.evaluation_id, "criterion_key": ap.criterion_key, "comment": ap.comment,
        "author": ap.author, "status": ap.status, "original_answer": ap.original_answer, "new_answer": ap.new_answer,
        "reviewer": ap.reviewer, "reason": ap.reason, "ai_review": ap.ai_review,
        "created_at": ap.created_at, "decided_at": ap.decided_at,
    }
    if with_context:
        ev = ap.evaluation
        row = next((r for r in ev.results if r["key"] == ap.criterion_key), None)
        d["conversation_id"] = ev.conversation_id
        d["criterion_result"] = row
        idx = [e["index"] for e in (row or {}).get("evidence", [])] + list((row or {}).get("checked_range") or [])
        tr = ev.conversation.transcript
        if idx:
            lo, hi = max(0, min(idx) - 2), min(len(tr) - 1, max(idx) + 2)
        else:
            lo, hi = 0, len(tr) - 1
        d["fragment"] = [{"index": i, **tr[i]} for i in range(lo, hi + 1)]
        d["initial_total"] = (ev.initial_score or {}).get("total")
        d["final_total"] = (ev.final_score or {}).get("total")
    return d


def review_dict(ev: Evaluation) -> dict:
    r = ev.review
    return {"comments": dict(r.comments or {}) if r else {}, "published": bool(r and r.published),
            "reviewer": r.reviewer if r else None, "published_at": r.published_at if r else None}


def eval_full(ev: Evaluation) -> dict:
    d = eval_summary(ev)
    fs = ev.final_score or {}
    final_crit = fs.get("criteria", {})
    results = []
    for r in ev.results or []:
        r = dict(r)
        fc = final_crit.get(r["key"], {})
        r["final_answer"], r["final_points"], r["final_max_points"] = fc.get("answer"), fc.get("points"), fc.get("max_points")
        r["appeals"] = [appeal_dict(a) for a in ev.appeals if a.criterion_key == r["key"]]
        results.append(r)
    conv = ev.conversation
    d.update({
        "conversation": {"id": conv.id, "channel": conv.channel, "language": conv.language,
                         "audio_url": conv.audio_url, "has_audio": bool(conv.audio_url),
                         "transcript": [{"index": i, **t} for i, t in enumerate(conv.transcript)]},
        "facts": ev.facts, "results": results, "initial_score": ev.initial_score, "final_score": ev.final_score,
        "feedback": ev.feedback, "models": ev.models, "usage": ev.usage,
        "appeals": [appeal_dict(a) for a in ev.appeals],
        "review": review_dict(ev),
        "checklist": ev.checklist_snapshot,
    })
    return d
