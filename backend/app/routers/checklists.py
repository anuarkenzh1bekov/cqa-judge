from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import prompts, services
from ..checklist import DEFAULT_CHECKLIST, ChecklistIn
from ..db import get_db
from ..models import Checklist, Conversation

router = APIRouter(prefix="/api/checklists", tags=["checklists"])


def _out(cl: Checklist) -> dict:
    return {"id": cl.id, "name": cl.name, "description": cl.description, "is_active": cl.is_active,
            "criteria": cl.criteria, "total_weight": sum(c["weight"] for c in cl.criteria),
            "created_at": cl.created_at, "updated_at": cl.updated_at}


def _get(db, cid) -> Checklist:
    cl = db.get(Checklist, cid)
    if not cl:
        raise HTTPException(404, "checklist not found")
    return cl


@router.get("")
def list_checklists(db: Session = Depends(get_db)):
    return [_out(c) for c in db.scalars(select(Checklist).order_by(Checklist.id))]


@router.get("/active")
def get_active(db: Session = Depends(get_db)):
    return _out(services.active_checklist(db))


@router.get("/default-template")
def default_template():
    """The checklist from the PDF - handy for 'reset to default' in the editor."""
    return DEFAULT_CHECKLIST


@router.get("/{cid}")
def get_checklist(cid: int, db: Session = Depends(get_db)):
    return _out(_get(db, cid))


@router.post("", status_code=201)
def create_checklist(body: ChecklistIn, activate: bool = False, db: Session = Depends(get_db)):
    cl = Checklist(name=body.name, description=body.description, criteria=[c.model_dump() for c in body.criteria])
    db.add(cl)
    db.flush()
    if activate:
        db.execute(update(Checklist).values(is_active=False))
        cl.is_active = True
    db.commit()
    return _out(cl)


@router.put("/{cid}")
def update_checklist(cid: int, body: ChecklistIn, db: Session = Depends(get_db)):
    """Edit in place. Past evaluations are unaffected: each stores the checklist snapshot it used."""
    cl = _get(db, cid)
    cl.name, cl.description = body.name, body.description
    cl.criteria = [c.model_dump() for c in body.criteria]
    db.commit()
    return _out(cl)


@router.post("/{cid}/activate")
def activate(cid: int, db: Session = Depends(get_db)):
    cl = _get(db, cid)
    db.execute(update(Checklist).values(is_active=False))
    cl.is_active = True
    db.commit()
    return _out(cl)


@router.post("/{cid}/duplicate", status_code=201)
def duplicate(cid: int, db: Session = Depends(get_db)):
    src = _get(db, cid)
    cl = Checklist(name=f"{src.name} (копия)", description=src.description, criteria=src.criteria)
    db.add(cl)
    db.commit()
    return _out(cl)


@router.delete("/{cid}")
def delete_checklist(cid: int, db: Session = Depends(get_db)):
    cl = _get(db, cid)
    if cl.is_active:
        raise HTTPException(400, "cannot delete the active checklist")
    db.delete(cl)
    db.commit()
    return {"deleted": cid}


@router.get("/{cid}/prompt-preview")
def prompt_preview(cid: int, conversation_id: str | None = None, db: Session = Depends(get_db)):
    """Shows the exact prompt sent to the model - transparency: the system applies the configured criteria."""
    cl = _get(db, cid)
    crit = services.criteria_of(cl.criteria)
    conv = db.get(Conversation, conversation_id) if conversation_id else None
    conv_d = services.conv_dict(conv) if conv else {"id": "<id>", "channel": "<channel>", "language": "<lang>",
                                                    "transcript": []}
    return {"prompt": prompts.build_eval_prompt(crit, conv_d), "json_schema": prompts.build_eval_schema(crit),
            "jev_questions": prompts.jev_questions(crit)}
