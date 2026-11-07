from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from .. import prompts, services
from ..checklist import DEFAULT_CHECKLIST, ChecklistIn
from ..db import get_db
from ..llm import gemini
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


class SuggestIn(BaseModel):
    brief: str = Field(min_length=3, max_length=2000)  # what the user wants to check, in their own words
    existing: list[str] = []  # names of criteria already in the checklist (avoid duplicates)
    sections: list[str] = []


_SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "section": {"type": "string"},
        "description": {"type": "string"},
        "type": {"type": "string", "enum": ["binary", "scale"]},
        "weight": {"type": "number"},
        "na_allowed": {"type": "boolean"},
        "na_condition": {"type": "string"},
        "scale": {"type": "array", "items": {"type": "object", "properties": {
            "value": {"type": "number"}, "description": {"type": "string"}},
            "required": ["value", "description"]}},
        "guidance": {"type": "string"},
    },
    "required": ["name", "section", "description", "type", "weight", "na_allowed", "na_condition", "scale", "guidance"],
}

_SUGGEST_SYSTEM = (
    "Ты помогаешь методологу составлять чек-лист качества диалогов службы поддержки брокера. "
    "По описанию на человеческом языке составь ОДИН критерий. Пиши по-русски, коротко и проверяемо по тексту диалога. "
    "name: короткое название (2-5 слов). description: для binary - одно утверждение, на которое можно ответить «Да» или «Нет» "
    "(«Да» = требование выполнено); для scale - что оценивается. type: binary, если достаточно да/нет; scale - если нужна градация. "
    "Для scale дай 3-5 ступеней по убыванию (value - числа, высшая = полный балл, низшая 0), у каждой description с наблюдаемым признаком. "
    "Для binary scale = []. weight: от 5 до 20. na_allowed: true только если критерий бывает неприменим, тогда заполни na_condition, иначе пустая строка. "
    "section: выбери из имеющихся секций, если подходит, иначе придумай короткую. "
    "guidance: 1-2 предложения о пограничных случаях, иначе пустая строка. Критерий должен проверять ровно то, что просит пользователь, ничего не подменяй и не добавляй от себя; "
    "существующие критерии нужны только чтобы не дублировать их."
)


@router.post("/suggest-criterion")
async def suggest_criterion(body: SuggestIn):
    """Draft one criterion from a free-text brief (the editor's "AI help" button). Nothing is saved."""
    existing = "; ".join(body.existing) or "нет"
    sections = "; ".join(body.sections) or "нет"
    prompt = (f"Запрос методолога (составь критерий именно про это):\n«{body.brief.strip()}»\n\n"
              f"Уже есть критерии (не дублировать): {existing}\n"
              f"Имеющиеся секции: {sections}")
    try:
        data, usage = await gemini.generate_json(prompt, _SUGGEST_SCHEMA, system=_SUGGEST_SYSTEM)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Не удалось получить ответ модели: {e}") from e
    scale = data.get("scale") or []
    if data["type"] == "scale" and len(scale) < 2:
        data["type"], scale = "binary", []
    if data["type"] == "binary":
        scale = []
    na_cond = (data.get("na_condition") or "").strip()
    return {"criterion": {
        "section": data.get("section") or None, "name": data["name"].strip(), "description": data["description"].strip(),
        "type": data["type"], "weight": max(0, min(100, data.get("weight") or 10)),
        "na_allowed": bool(data.get("na_allowed")) and bool(na_cond), "na_condition": na_cond or None,
        "scale": sorted(scale, key=lambda s: -s["value"]) or None,
        "guidance": (data.get("guidance") or "").strip() or None},
        "cost_usd": round(gemini.cost_usd(usage), 5)}


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
