import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import services
from ..db import get_db
from ..models import Checklist, Conversation, Evaluation, EvaluationReview, now

router = APIRouter(prefix="/api", tags=["evaluations"])


class EvaluateIn(BaseModel):
    conversation_id: str
    checklist_id: int | None = None  # default: active checklist
    with_feedback: bool = True


class BatchIn(BaseModel):
    conversation_ids: list[str] | None = None
    group: str | None = None  # evaluate every conversation of a dataset group
    checklist_id: int | None = None
    with_feedback: bool = True


def _checklist(db, cid) -> Checklist:
    cl = db.get(Checklist, cid) if cid else services.active_checklist(db)
    if not cl:
        raise HTTPException(404, "checklist not found")
    return cl


@router.post("/evaluations")
async def evaluate_one(body: EvaluateIn, db: Session = Depends(get_db)):
    """Synchronous: runs the models and returns the full result card (takes ~20-40 s)."""
    if not db.get(Conversation, body.conversation_id):
        raise HTTPException(404, "conversation not found")
    ev = services.create_evaluation(db, body.conversation_id, _checklist(db, body.checklist_id))
    await services.run_evaluation(ev.id, body.with_feedback)
    db.expire_all()
    return services.eval_full(db.get(Evaluation, ev.id))


@router.post("/evaluations/batch", status_code=202)
async def evaluate_batch(body: BatchIn, db: Session = Depends(get_db)):
    """Async: creates pending evaluations and runs them in the background. Poll GET /api/batches/{batch_id}."""
    ids = list(body.conversation_ids or [])
    if body.group:
        ids += db.scalars(select(Conversation.id).where(Conversation.dataset_group == body.group)).all()
    ids = list(dict.fromkeys(ids))
    if not ids:
        raise HTTPException(400, "no conversations selected")
    missing = [i for i in ids if not db.get(Conversation, i)]
    if missing:
        raise HTTPException(404, f"unknown conversations: {missing[:10]}")
    cl = _checklist(db, body.checklist_id)
    batch_id = uuid.uuid4().hex[:12]
    evs = [services.create_evaluation(db, cid, cl, batch_id) for cid in ids]
    for ev in evs:
        services.spawn(services.run_evaluation(ev.id, body.with_feedback))
    return {"batch_id": batch_id, "checklist_id": cl.id, "evaluation_ids": [e.id for e in evs], "total": len(evs)}


@router.get("/batches/{batch_id}")
def batch_status(batch_id: str, db: Session = Depends(get_db)):
    evs = db.scalars(select(Evaluation).where(Evaluation.batch_id == batch_id).order_by(Evaluation.id)).all()
    if not evs:
        raise HTTPException(404, "batch not found")
    counts = {s: sum(1 for e in evs if e.status == s) for s in ("pending", "running", "done", "error")}
    return {"batch_id": batch_id, "total": len(evs), **counts, "finished": counts["pending"] + counts["running"] == 0,
            "evaluations": [services.eval_summary(e) for e in evs]}


@router.post("/evaluations/{eid}/rerun", status_code=202)
async def rerun(eid: int, db: Session = Depends(get_db)):
    ev = db.get(Evaluation, eid)
    if not ev:
        raise HTTPException(404, "evaluation not found")
    new = services.create_evaluation(db, ev.conversation_id, _checklist(db, ev.checklist_id))
    services.spawn(services.run_evaluation(new.id))
    return {"evaluation_id": new.id}


@router.get("/evaluations")
def list_evaluations(conversation_id: str | None = None, checklist_id: int | None = None, status: str | None = None,
                     batch_id: str | None = None, limit: int = 200, db: Session = Depends(get_db)):
    q = select(Evaluation).order_by(Evaluation.id.desc()).limit(limit)
    if conversation_id:
        q = q.where(Evaluation.conversation_id == conversation_id)
    if checklist_id:
        q = q.where(Evaluation.checklist_id == checklist_id)
    if status:
        q = q.where(Evaluation.status == status)
    if batch_id:
        q = q.where(Evaluation.batch_id == batch_id)
    return [services.eval_summary(e) for e in db.scalars(q)]


@router.get("/evaluations/{eid}")
def get_evaluation(eid: int, db: Session = Depends(get_db)):
    ev = db.get(Evaluation, eid)
    if not ev:
        raise HTTPException(404, "evaluation not found")
    return services.eval_full(ev)


class ReviewIn(BaseModel):
    comments: dict[str, str] | None = None  # {criterion_key: text}; empty text removes the comment
    published: bool | None = None
    reviewer: str | None = "Проверяющий"


@router.put("/evaluations/{eid}/review")
def put_review(eid: int, body: ReviewIn, db: Session = Depends(get_db)):
    """Reviewer: write comments on the AI scores and publish them to the operator (appeals open after that)."""
    ev = db.get(Evaluation, eid)
    if not ev or ev.status != "done":
        raise HTTPException(404, "finished evaluation not found")
    rv = ev.review
    if not rv:
        rv = EvaluationReview(evaluation_id=eid, comments={}, published=False)
        db.add(rv)
    if body.comments is not None:
        known = {r["key"] for r in ev.results or []}
        merged = dict(rv.comments or {})
        for k, text in body.comments.items():
            if k not in known:
                raise HTTPException(404, f"criterion {k} not in this evaluation")
            text = text.strip()
            if text:
                merged[k] = text
            else:
                merged.pop(k, None)
        rv.comments = merged
    if body.published is not None and body.published != rv.published:
        rv.published = body.published
        rv.published_at = now() if body.published else None
    rv.reviewer = body.reviewer
    db.commit()
    return {"comments": dict(rv.comments or {}), "published": bool(rv.published), "reviewer": rv.reviewer,
            "published_at": rv.published_at}


@router.get("/evaluations/{eid}/export")
def export_evaluation(eid: int, db: Session = Depends(get_db)):
    """Flat JSON for CRM (e.g. a Dynamics 365 custom entity via Web API). Not sent anywhere - export only."""
    ev = db.get(Evaluation, eid)
    if not ev or ev.status != "done":
        raise HTTPException(404, "finished evaluation not found")
    fs = ev.final_score
    return {
        "cqa_conversationid": ev.conversation_id,
        "cqa_channel": ev.conversation.channel,
        "cqa_language": ev.conversation.language,
        "cqa_operatorname": ev.operator_name,
        "cqa_checklist": ev.checklist_snapshot.get("name"),
        "cqa_totalscore": fs["total"],
        "cqa_initialscore": ev.initial_score["total"],
        "cqa_grosserror": fs["gross_error"],
        "cqa_evaluatedon": ev.finished_at,
        "cqa_criteria": [{"key": k, "answer": v["answer"], "points": v["points"], "max_points": v["max_points"]}
                         for k, v in fs["criteria"].items()],
        "cqa_feedback": (ev.feedback or {}).get("summary"),
        "cqa_improvements": [i["text"] for i in (ev.feedback or {}).get("improvements", [])],
    }
