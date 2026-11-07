from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def now():
    return datetime.now(timezone.utc)


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[str] = mapped_column(String, primary_key=True)  # conversation_id
    dataset_group: Mapped[str | None] = mapped_column(String, index=True)
    channel: Mapped[str] = mapped_column(String)  # "agent chat" | "voice call"
    language: Mapped[str] = mapped_column(String)  # RU | KZ | EN
    audio_url: Mapped[str | None] = mapped_column(Text)
    transcript: Mapped[list] = mapped_column(JSON)  # [{timestamp, speaker, text}] — original, untouched
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)


class Checklist(Base):
    __tablename__ = "checklists"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String)
    description: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    criteria: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)


class Evaluation(Base):
    __tablename__ = "evaluations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)
    checklist_id: Mapped[int] = mapped_column(ForeignKey("checklists.id"))
    checklist_snapshot: Mapped[dict] = mapped_column(JSON)  # criteria as they were when evaluated
    batch_id: Mapped[str | None] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String, default="pending")  # pending|running|done|error
    error: Mapped[str | None] = mapped_column(Text)

    facts: Mapped[dict | None] = mapped_column(JSON)
    results: Mapped[list | None] = mapped_column(JSON)  # per-criterion results (see pipeline)
    initial_score: Mapped[dict | None] = mapped_column(JSON)  # score block before appeals
    final_score: Mapped[dict | None] = mapped_column(JSON)  # score block after reviewer decisions
    feedback: Mapped[dict | None] = mapped_column(JSON)
    operator_name: Mapped[str | None] = mapped_column(String, index=True)

    models: Mapped[dict | None] = mapped_column(JSON)
    usage: Mapped[dict | None] = mapped_column(JSON)
    cost_usd: Mapped[float | None] = mapped_column(Float)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    conversation: Mapped[Conversation] = relationship()
    appeals: Mapped[list["Appeal"]] = relationship(back_populates="evaluation", order_by="Appeal.id")


class Appeal(Base):
    __tablename__ = "appeals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    evaluation_id: Mapped[int] = mapped_column(ForeignKey("evaluations.id"), index=True)
    criterion_key: Mapped[str] = mapped_column(String)
    comment: Mapped[str] = mapped_column(Text)
    author: Mapped[str | None] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default="open")  # open|confirmed|changed
    original_answer: Mapped[str] = mapped_column(String)
    new_answer: Mapped[str | None] = mapped_column(String)
    reviewer: Mapped[str | None] = mapped_column(String)
    reason: Mapped[str | None] = mapped_column(Text)
    ai_review: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    evaluation: Mapped[Evaluation] = relationship(back_populates="appeals")
