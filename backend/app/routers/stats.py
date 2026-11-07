"""Admin analytics. Built on the latest finished evaluation per conversation, using FINAL scores (after appeals)."""
from collections import Counter, defaultdict
from statistics import mean

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import export_xlsx, services
from ..db import get_db
from ..models import Appeal, Checklist, Conversation, Evaluation
from ..scoring import round2

router = APIRouter(prefix="/api", tags=["stats"])


def _latest(db: Session, checklist_id: int | None, group: str | None) -> list[Evaluation]:
    q = select(func.max(Evaluation.id)).where(Evaluation.status == "done").group_by(Evaluation.conversation_id)
    if checklist_id:
        q = q.where(Evaluation.checklist_id == checklist_id)
    if group:
        q = q.join(Conversation).where(Conversation.dataset_group == group)
    ids = db.scalars(q).all()
    return db.scalars(select(Evaluation).where(Evaluation.id.in_(ids))).all() if ids else []


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return round2(mean(xs)) if xs else None


def _group(evs, keyfn):
    g = defaultdict(list)
    for e in evs:
        g[keyfn(e)].append(e)
    return {k: {"count": len(v), "avg_total": _avg(e.final_score["total"] for e in v),
                "gross_errors": sum(e.final_score["gross_error"] for e in v)} for k, v in g.items()}


def _criteria_stats(evs):
    acc = {}
    for e in evs:
        names = {r["key"]: r["name"] for r in e.results}
        agree = {r["key"]: r.get("agreement") for r in e.results}
        for key, v in e.final_score["criteria"].items():
            s = acc.setdefault(key, {"key": key, "name": names.get(key), "n": 0, "na": 0, "answers": Counter(),
                                     "pct": [], "agreement": Counter()})
            s["n"] += 1
            s["answers"][v["answer"]] += 1
            s["agreement"][agree.get(key)] += 1
            if v["answer"] == "na":
                s["na"] += 1
            if v.get("max_points"):
                s["pct"].append(v["points"] / v["max_points"] * 100)
    out = []
    for s in acc.values():
        out.append({"key": s["key"], "name": s["name"], "evaluated": s["n"],
                    "na_rate": round2(s["na"] / s["n"] * 100) if s["n"] else None,
                    "avg_score_pct": _avg(s["pct"]), "answers": dict(s["answers"]),
                    "model_agreement": dict(s["agreement"])})
    return sorted(out, key=lambda x: (x["avg_score_pct"] is None, x["avg_score_pct"] or 0))


@router.get("/stats")
def stats(checklist_id: int | None = None, group: str | None = None, db: Session = Depends(get_db)):
    evs = [e for e in _latest(db, checklist_id, group) if e.final_score]
    totals = [e.final_score["total"] for e in evs]
    buckets = Counter()
    for t in totals:
        if t is None:
            buckets["n/a"] += 1
        else:
            buckets["0-49" if t < 50 else "50-69" if t < 70 else "70-84" if t < 85 else "85-100"] += 1
    appeals = db.scalars(select(Appeal)).all()
    agreement = Counter(r.get("agreement") for e in evs for r in e.results)
    adj_changed = sum(1 for e in evs for r in e.results if (r.get("adjudication") or {}).get("changed"))
    return {
        "overview": {
            "evaluated_conversations": len(evs),
            "avg_total": _avg(totals),
            "avg_initial_total": _avg(e.initial_score["total"] for e in evs),
            "gross_error_conversations": sum(e.final_score["gross_error"] for e in evs),
            "criteria_needing_review": sum(1 for e in evs for r in e.results if r.get("needs_review")),
            "confident_conversations": sum(1 for e in evs if not services.confidence_of(e)["flagged"]),
            "needs_human_conversations": sum(1 for e in evs if services.confidence_of(e)["flagged"]),
            "total_cost_usd": round(sum(e.cost_usd or 0 for e in evs), 4),
            "avg_cost_usd": round(mean([e.cost_usd or 0 for e in evs]), 5) if evs else None,
            "avg_duration_ms": int(mean([e.duration_ms or 0 for e in evs])) if evs else None,
        },
        "score_distribution": dict(buckets),
        "by_language": _group(evs, lambda e: e.conversation.language),
        "by_channel": _group(evs, lambda e: e.conversation.channel),
        "by_operator": _group(evs, lambda e: e.operator_name or "не указан"),
        "by_criterion": _criteria_stats(evs),
        "model_agreement": {"per_criterion_counts": dict(agreement), "adjudication_changed_answer": adj_changed},
        "appeals": {"total": len(appeals), **Counter(a.status for a in appeals),
                    "change_rate_pct": round2(sum(a.status == "changed" for a in appeals)
                                              / max(1, sum(a.status != "open" for a in appeals)) * 100)},
        "lowest": sorted(({"evaluation_id": e.id, "conversation_id": e.conversation_id,
                           "total": e.final_score["total"], "gross_error": e.final_score["gross_error"]}
                          for e in evs if e.final_score["total"] is not None), key=lambda x: x["total"])[:10],
        "gross_errors": [{"evaluation_id": e.id, "conversation_id": e.conversation_id,
                          "explanation": next((r["explanation"] for r in e.results if r["type"] == "flag"), None)}
                         for e in evs if e.final_score["gross_error"]],
    }


@router.get("/operators")
def operators(checklist_id: int | None = None, db: Session = Depends(get_db)):
    evs = _latest(db, checklist_id, None)
    names = sorted({e.operator_name or "не указан" for e in evs})
    return [{"operator": n, **_group([e for e in evs if (e.operator_name or "не указан") == n], lambda e: 0)[0]}
            for n in names]


@router.get("/operators/{name}")
def operator_profile(name: str, checklist_id: int | None = None, db: Session = Depends(get_db)):
    """Operator card: scores, weakest criteria and the collected improvement advice."""
    evs = [e for e in _latest(db, checklist_id, None) if (e.operator_name or "не указан") == name]
    if not evs:
        raise HTTPException(404, "operator not found")
    improvements = []
    for e in evs:
        for i in (e.feedback or {}).get("improvements", []):
            improvements.append({**i, "evaluation_id": e.id, "conversation_id": e.conversation_id})
    by_crit = Counter(i.get("criterion_key") for i in improvements if i.get("criterion_key"))
    return {
        "operator": name,
        "evaluations": [services.eval_summary(e) for e in evs],
        "avg_total": _avg(e.final_score["total"] for e in evs),
        "criteria": _criteria_stats(evs),
        "improvements": improvements,
        "most_frequent_improvement_areas": by_crit.most_common(),
    }


@router.get("/export/stats.xlsx")
def export_stats(checklist_id: int | None = None, group: str | None = None, db: Session = Depends(get_db)):
    """Everything from the Analytics screen as an Excel workbook, plus per-dialog and per-criterion detail."""
    evs = [e for e in _latest(db, checklist_id, group) if e.final_score]
    # all appeals (as counted on the Analytics screen); the sheet marks those made on an older evaluation
    q = select(Appeal).join(Evaluation).order_by(Appeal.id)
    if checklist_id:
        q = q.where(Evaluation.checklist_id == checklist_id)
    if group:
        q = q.join(Conversation, Evaluation.conversation_id == Conversation.id).where(Conversation.dataset_group == group)
    appeals = db.scalars(q).all()
    cl = db.get(Checklist, checklist_id) if checklist_id else None
    filters = f"Набор: {group or 'все'}; чек-лист: {cl.name if cl else 'все версии'}"
    data = export_xlsx.build(stats(checklist_id, group, db), evs, appeals, filters)
    name = f"cqa-stats-{group or 'all'}-{datetime.now():%Y%m%d-%H%M}.xlsx"
    return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})
