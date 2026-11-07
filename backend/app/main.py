import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import update

from . import services
from .config import ROOT, settings
from .db import Base, SessionLocal, engine
from .llm import jev
from .models import Evaluation
from .routers import ai_text, appeals, checklists, conversations, evaluations, reports, stats

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

for r in (conversations, checklists, evaluations, appeals, stats, reports, ai_text):
    app.include_router(r.router)


@app.middleware("http")
async def revalidate_static(request, call_next):
    """The UI files change with every deploy: make the browser re-check them (cheap 304 via ETag) instead of
    running stale JS from its heuristic cache - otherwise new buttons silently don't show up after an update."""
    resp = await call_next(request)
    if not request.url.path.startswith("/api/"):
        resp.headers["Cache-Control"] = "no-cache"
    return resp


@app.get("/api/health")
def health():
    return {"status": "ok", "gemini_model": settings.gemini_model, "jev_enabled": jev.enabled(),
            "jev_model": settings.jev_model if jev.enabled() else None}


# The frontend (web/) is served from the same origin: http://localhost:8000/
WEB_DIR = ROOT / "web"


def _versioned_index() -> str:
    """index.html with ?v=<mtime> on every local script and stylesheet: after an update the browser must fetch the new
    files, not run a cached copy (Cache-Control alone is not enough for subresources in every browser)."""
    html = (WEB_DIR / "index.html").read_text(encoding="utf-8")

    def stamp(m):
        f = WEB_DIR / m.group(2)
        return f'{m.group(1)}="{m.group(2)}?v={int(f.stat().st_mtime)}"' if f.is_file() else m.group(0)

    return re.sub(r'(src|href)="((?:js|css)/[^"?]+)"', stamp, html)


if WEB_DIR.is_dir():
    @app.get("/", include_in_schema=False)
    @app.get("/index.html", include_in_schema=False)
    def index():
        return HTMLResponse(_versioned_index())

    app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
