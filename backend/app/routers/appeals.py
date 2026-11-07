from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import pipeline, scoring, services
from ..db import get_db
from ..models import Appeal, Evaluation

router = APIRouter(prefix="/api", tags=["appeals"])


class AppealIn(BaseModel):
    criterion_key: str
    comment: str
    author: str | None = None


class DecisionIn(BaseModel):
    decision: Literal["confirm", "change"]
    new_answer: str | None = None
    reason: str
    reviewer: str | None = None

    @model_validator(mode="after")
    def _need_answer(self):
        if self.decision == "change" and self.new_answer is None:
            raise ValueError("new_answer is required when decision=change")
        return self


def _crit(ev: Evaluation, key: str):
    c = next((c for c in services.criteria_of(ev.checklist_snapshot) if c.key == key), None)
    if not c:
        raise HTTPException(404, f"criterion {key} not in this evaluation's checklist")
    return c


@router.post("/evaluations/{eid}/appeals", status_code=201)
def create_appeal(eid: int, body: AppealIn, db: Session = Depends(get_db)):
    ev = db.get(Evaluation, eid)
    if not ev or ev.status != "done":
        raise HTTPException(404, "finished evaluation not found")
    _crit(ev, body.criterion_key)
    if not (ev.review and ev.review.published):
        raise HTTPException(409, "the evaluation has not been reviewed yet: appeals open after the reviewer publishes it")
    if any(a.criterion_key == body.criterion_key and a.status == "open" for a in ev.appeals):
        raise HTTPException(409, "there is already an open appeal for this criterion")
    current = services.final_answers(ev)[body.criterion_key]
    ap = Appeal(evaluation_id=eid, criterion_key=body.criterion_key, comment=body.comment, author=body.author,
                original_answer=current)
    db.add(ap)
    db.commit()
    return services.appeal_dict(ap, with_context=True)


@router.get("/appeals")
def list_appeals(status: str | None = None, evaluation_id: int | None = None, db: Session = Depends(get_db)):
    q = select(Appeal).order_by(Appeal.id.desc())
    if status:
        q = q.where(Appeal.status == status)
    if evaluation_id:
        q = q.where(Appeal.evaluation_id == evaluation_id)
    return [services.appeal_dict(a, with_context=True) for a in db.scalars(q)]


@router.get("/appeals/{aid}")
def get_appeal(aid: int, db: Session = Depends(get_db)):
    ap = db.get(Appeal, aid)
    if not ap:
        raise HTTPException(404, "appeal not found")
    return services.appeal_dict(ap, with_context=True)


@router.post("/appeals/{aid}/ai-review")
async def ai_review(aid: int, db: Session = Depends(get_db)):
    """Optional AI second look for the reviewer. Advisory only - the human decides."""
    ap = db.get(Appeal, aid)
    if not ap:
        raise HTTPException(404, "appeal not found")
    ev = ap.evaluation
    c = _crit(ev, ap.criterion_key)
    row = next(r for r in ev.results if r["key"] == ap.criterion_key)
    current = {"answer": ap.original_answer, "explanation": row.get("explanation")}
    try:
        ap.ai_review = await pipeline.review_appeal(c, services.conv_dict(ev.conversation), current, ap.comment)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"AI review failed: {e}") from e
    db.commit()
    return services.appeal_dict(ap, with_context=True)


@router.post("/appeals/{aid}/decision")
def decide(aid: int, body: DecisionIn, db: Session = Depends(get_db)):
    ap = db.get(Appeal, aid)
    if not ap:
        raise HTTPException(404, "appeal not found")
    if ap.status != "open":
        raise HTTPException(409, "appeal already decided")
    ev = ap.evaluation
    if body.decision == "change":
        try:
            new = scoring.validate_answer(_crit(ev, ap.criterion_key), body.new_answer)
        except ValueError as e:
            raise HTTPException(422, str(e)) from e
        ap.status, ap.new_answer = ("changed", new) if new != ap.original_answer else ("confirmed", None)
    else:
        ap.status = "confirmed"
    ap.reason, ap.reviewer, ap.decided_at = body.reason, body.reviewer, datetime.now(timezone.utc)
    services.recompute_final(ev)
    db.commit()
    return {"appeal": services.appeal_dict(ap, with_context=True),
            "initial_total": ev.initial_score["total"], "final_total": ev.final_score["total"],
            "final_score": ev.final_score}
