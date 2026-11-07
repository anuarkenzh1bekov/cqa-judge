import html
import re

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import services
from ..db import get_db
from ..llm import gemini
from ..models import Conversation, Evaluation
from ..prompts import format_transcript

router = APIRouter(prefix="/api", tags=["conversations"])


class ImportIn(BaseModel):
    group_id: str = "DEV"


class Turn(BaseModel):
    timestamp: str
    speaker: str
    text: str


class ConversationIn(BaseModel):
    conversation_id: str
    channel: str = "agent chat"
    language: str = "RU"
    transcript: list[Turn] = Field(min_length=1)
    audio_url: str | None = None


class UploadIn(BaseModel):
    records: list[ConversationIn] = Field(min_length=1)
    group: str | None = "UPLOAD"


@router.post("/datasets/import")
async def import_dataset(body: ImportIn, db: Session = Depends(get_db)):
    """Fetch a dataset from the organizers' API by group_id (server-side, so no CORS) and store it."""
    try:
        records, source = await services.fetch_dataset_with_source(body.group_id)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(502, f"Dataset fetch failed: {e}") from e
    ids = services.upsert_conversations(db, records, body.group_id)
    return {"group_id": body.group_id, "imported": len(ids), "conversation_ids": ids, "source": source}


@router.post("/conversations")
def upload_conversations(body: UploadIn, db: Session = Depends(get_db)):
    """Upload transcripts in the same format as the organizers' API records."""
    ids = services.upsert_conversations(db, [r.model_dump() for r in body.records], body.group)
    return {"imported": len(ids), "conversation_ids": ids}


@router.get("/conversations")
def list_conversations(group: str | None = None, language: str | None = None, channel: str | None = None,
                       db: Session = Depends(get_db)):
    q = select(Conversation).order_by(Conversation.id)
    if group:
        q = q.where(Conversation.dataset_group == group)
    if language:
        q = q.where(Conversation.language == language.upper())
    if channel:
        q = q.where(Conversation.channel == channel)
    convs = db.scalars(q).all()
    latest_ids = dict(db.execute(select(Evaluation.conversation_id, func.max(Evaluation.id))
                                 .group_by(Evaluation.conversation_id)).all())
    evs = {e.id: e for e in db.scalars(select(Evaluation).where(Evaluation.id.in_(latest_ids.values())))}
    out = []
    for c in convs:
        ev = evs.get(latest_ids.get(c.id))
        out.append({
            "id": c.id, "group": c.dataset_group, "channel": c.channel, "language": c.language,
            "has_audio": bool(c.audio_url), "turns": len(c.transcript),
            "preview": next((t["text"][:140] for t in c.transcript if t.get("speaker") == "client"), ""),
            "latest_evaluation": services.eval_summary(ev) if ev else None,
        })
    return out


@router.get("/conversations/{cid}")
def get_conversation(cid: str, db: Session = Depends(get_db)):
    c = db.get(Conversation, cid)
    if not c:
        raise HTTPException(404, "conversation not found")
    evs = db.scalars(select(Evaluation).where(Evaluation.conversation_id == cid).order_by(Evaluation.id.desc())).all()
    return {"id": c.id, "group": c.dataset_group, "channel": c.channel, "language": c.language,
            "audio_url": c.audio_url, "has_audio": bool(c.audio_url),
            "transcript": [{"index": i, **t} for i, t in enumerate(c.transcript)],
            "evaluations": [services.eval_summary(e) for e in evs]}


_SRC_RE = re.compile(r"""<source[^>]+src=["']([^"']+)["']""", re.I)


async def _resolve_audio(http: httpx.AsyncClient, url: str) -> str:
    """The organizers' audio_url is an HTML player page whose <source> holds a short-lived (1 h) signed mp3 link.
    Resolve it on every request so the link is always fresh."""
    r = await http.get(url)
    if r.status_code != 200:
        raise HTTPException(502, f"audio page returned {r.status_code}")
    if r.headers.get("content-type", "").startswith("audio/"):
        return url
    m = _SRC_RE.search(r.text)
    if not m:
        raise HTTPException(502, "no audio source found on the player page")
    return html.unescape(m.group(1))


_SUMMARY_CACHE: dict[str, dict] = {}
_SUMMARY_SCHEMA = {"type": "object", "properties": {
    "summary": {"type": "string"},
    "mood": {"type": "string", "enum": ["positive", "neutral", "negative"]}},
    "required": ["summary", "mood"]}
_SUMMARY_SYSTEM = (
    "Ты кратко пересказываешь диалог клиента со службой поддержки брокера. Напиши 1-2 предложения по-русски "
    "(не больше 220 символов): с чем обратился клиент, что ответили и чем закончилось. Только факты из диалога, "
    "без оценок качества работы оператора, без цитат и без номеров реплик. Если клиент заметно недоволен или раздражён, скажи это в тексте. "
    "mood: настроение клиента к концу диалога: positive (доволен, благодарит), neutral (спокоен, деловой тон), negative (недоволен, раздражён, жалуется). "
)


@router.get("/conversations/{cid}/summary")
async def conversation_summary(cid: str, db: Session = Depends(get_db)):
    """One-two sentence retelling of what the dialog was about (shown above the transcript). Cached in memory."""
    conv = db.get(Conversation, cid)
    if not conv:
        raise HTTPException(404, "conversation not found")
    if cid not in _SUMMARY_CACHE:
        try:
            data, _ = await gemini.generate_json(format_transcript(conv.transcript), _SUMMARY_SCHEMA, system=_SUMMARY_SYSTEM)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(502, f"Не удалось получить краткое содержание: {e}") from e
        _SUMMARY_CACHE[cid] = {"summary": " ".join(str(data.get("summary", "")).split()),
                               "mood": data.get("mood", "neutral")}
    return _SUMMARY_CACHE[cid]


@router.get("/conversations/{cid}/audio")
async def conversation_audio(cid: str, request: Request, db: Session = Depends(get_db)):
    """Streams the call recording (mp3). Supports Range, so <audio> can seek to a transcript timestamp."""
    c = db.get(Conversation, cid)
    if not c or not c.audio_url:
        raise HTTPException(404, "no audio for this conversation")
    http = httpx.AsyncClient(timeout=120, follow_redirects=True)
    try:
        src = await _resolve_audio(http, c.audio_url)
        headers = {"Range": request.headers["range"]} if "range" in request.headers else {}
        resp = await http.send(http.build_request("GET", src, headers=headers), stream=True)
    except Exception:
        await http.aclose()
        raise
    if resp.status_code not in (200, 206):
        await resp.aclose()
        await http.aclose()
        raise HTTPException(502, f"audio upstream returned {resp.status_code}")

    async def body():
        try:
            async for chunk in resp.aiter_bytes():
                yield chunk
        finally:
            await resp.aclose()
            await http.aclose()

    keep = ("content-length", "content-range", "accept-ranges")
    out_headers = {k: v for k, v in resp.headers.items() if k.lower() in keep}
    out_headers.setdefault("accept-ranges", "bytes")
    return StreamingResponse(body(), status_code=resp.status_code, headers=out_headers,
                             media_type=resp.headers.get("content-type", "audio/mpeg"))
