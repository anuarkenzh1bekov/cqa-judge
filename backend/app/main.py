import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import update

from . import services
from .config import ROOT, settings
from .db import Base, SessionLocal, engine
from .llm import jev
from .models import Evaluation
from .routers import appeals, checklists, conversations, evaluations, reports, stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        services.seed_default_checklist(db)
        # evaluations run inside this process: after a restart nothing is working on pending/running ones
        db.execute(update(Evaluation).where(Evaluation.status.in_(("pending", "running")))
                   .values(status="error", error="Прервано перезапуском сервера"))
        db.commit()
        if settings.seed_dataset:
            services.seed_conversations(db, settings.seed_dataset)
    yield


app = FastAPI(title="CQA Judge API", version="0.1.0", lifespan=lifespan,
              description="Conversation Quality Analytics: checklist-based evaluation of operator dialogs "
                          "(Gemini + Jev), appeals and analytics.")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
                   allow_methods=["*"], allow_headers=["*"])

for r in (conversations, checklists, evaluations, appeals, stats, reports):
    app.include_router(r.router)


@app.get("/api/health")
def health():
    return {"status": "ok", "gemini_model": settings.gemini_model, "jev_enabled": jev.enabled(),
            "jev_model": settings.jev_model if jev.enabled() else None}


# The frontend (web/) is served from the same origin: http://localhost:8000/
WEB_DIR = ROOT / "web"
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
