"""Calibration against human decisions, checklist-version comparison and the management report (Excel / CSV)."""
import csv
import io
from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .. import results_export, services
from ..config import settings
from ..db import get_db
from ..models import Appeal, Checklist, Evaluation
from ..scoring import round2
from .stats import _avg, _criteria_stats, _group, _latest

router = APIRouter(prefix="/api", tags=["reports"])


def _pct(part: int, whole: int) -> float | None:
    return round2(part / whole * 100) if whole else None


# ---------- calibration ----------

@router.get("/calibration")
def calibration(db: Session = Depends(get_db)):
    """How well the AI judge agrees with people. Humans only see the disputed cases, so this is the agreement on
    appealed criteria, not overall accuracy: it shows where the judge is weakest and whether it improves."""
    appeals = db.scalars(select(Appeal).order_by(Appeal.decided_at, Appeal.id)).all()
    decided = [a for a in appeals if a.status in ("confirmed", "changed")]
    evs = _latest(db, None, None)

    names: dict[str, str] = {}
    evaluated = Counter()
    for e in evs:
        for r in e.results or []:
            if r.get("type") == "flag":
                continue
            names[r["key"]] = r["name"]
            evaluated[r["key"]] += 1

    per = defaultdict(lambda: {"appealed": 0, "decided": 0, "changed": 0})
    agreement_kind = defaultdict(lambda: {"decided": 0, "changed": 0})
    for a in appeals:
        s = per[a.criterion_key]
        s["appealed"] += 1
        names.setdefault(a.criterion_key, a.criterion_key)
        if a.status in ("confirmed", "changed"):
            s["decided"] += 1
            s["changed"] += a.status == "changed"
            row = next((r for r in a.evaluation.results or [] if r["key"] == a.criterion_key), None)
            k = agreement_kind[(row or {}).get("agreement") or "gemini_only"]
            k["decided"] += 1
            k["changed"] += a.status == "changed"

    by_criterion = []
    for key, s in per.items():
        by_criterion.append({"key": key, "name": names.get(key, key), "evaluated": evaluated.get(key, 0),
                             **s, "confirmed": s["decided"] - s["changed"],
                             "agreement_pct": _pct(s["decided"] - s["changed"], s["decided"]),
                             "appeal_rate_pct": _pct(s["appealed"], evaluated.get(key, 0))})
    by_criterion.sort(key=lambda x: (x["agreement_pct"] is None, x["agreement_pct"] or 0))

    trend, confirmed = [], 0
    for i, a in enumerate(decided, 1):
        confirmed += a.status == "confirmed"
        trend.append({"n": i, "agreement_pct": _pct(confirmed, i), "decided_at": a.decided_at})

    examples = db.scalar(select(func.count()).select_from(Appeal).where(
        Appeal.status == "changed", Appeal.reason.is_not(None), Appeal.reason != "")) or 0
    used = sum(1 for e in evs if (e.usage or {}).get("calibration_examples"))
    changed = sum(a.status == "changed" for a in decided)
    return {
        "learning": {"enabled": settings.calibration_enabled, "per_criterion": settings.calibration_examples,
                     "examples_available": examples, "evaluations_using_examples": used},
        "overall": {"appealed": len(appeals), "decided": len(decided), "changed": changed,
                    "confirmed": len(decided) - changed, "agreement_pct": _pct(len(decided) - changed, len(decided))},
        "by_criterion": by_criterion,
        "by_model_agreement": [{"agreement": k, **v, "changed_pct": _pct(v["changed"], v["decided"])}
                               for k, v in sorted(agreement_kind.items())],
        "trend": trend,
    }


# ---------- checklist versions ----------

def _latest_by_conv(db: Session, checklist_id: int) -> dict[str, Evaluation]:
    ids = db.scalars(select(func.max(Evaluation.id)).where(Evaluation.status == "done",
                                                            Evaluation.checklist_id == checklist_id)
                     .group_by(Evaluation.conversation_id)).all()
    evs = db.scalars(select(Evaluation).where(Evaluation.id.in_(ids))).all() if ids else []
    return {e.conversation_id: e for e in evs}


def _crit_diff(ca: list[dict], cb: list[dict]) -> list[dict]:
    ma, mb = {c["key"]: c for c in ca}, {c["key"]: c for c in cb}
    out = []
    for k in dict.fromkeys([*ma, *mb]):
        if k not in mb:
            out.append({"key": k, "name": ma[k]["name"], "kind": "removed"})
        elif k not in ma:
            out.append({"key": k, "name": mb[k]["name"], "kind": "added"})
        elif ma[k] != mb[k]:
            fields = [f for f in ("weight", "description", "scale", "type", "na_allowed", "na_condition", "guidance",
                                  "name") if ma[k].get(f) != mb[k].get(f)]
            out.append({"key": k, "name": mb[k]["name"], "kind": "changed", "fields": fields})
    return out


@router.get("/checklist-compare")
def compare_checklists(a: int, b: int, db: Session = Depends(get_db)):
    """Same conversations scored by two checklist versions (AI scores before appeals): who moves and why."""
    cla, clb = db.get(Checklist, a), db.get(Checklist, b)
    if not cla or not clb:
        raise HTTPException(404, "checklist not found")
    ea, eb = _latest_by_conv(db, a), _latest_by_conv(db, b)
    both = [c for c in ea if c in eb]
    rows, flips = [], Counter()
    for cid in both:
        x, y = ea[cid], eb[cid]
        ta, tb = (x.initial_score or {}).get("total"), (y.initial_score or {}).get("total")
        ra, rb = {r["key"]: r for r in x.results}, {r["key"]: r for r in y.results}
        changed = []
        for k in rb:
            if k in ra and ra[k]["answer"] != rb[k]["answer"]:
                flips[k] += 1
                changed.append({"key": k, "name": rb[k]["name"], "a": ra[k]["answer"], "b": rb[k]["answer"]})
        rows.append({"conversation_id": cid, "operator_name": y.operator_name or x.operator_name, "total_a": ta,
                     "total_b": tb, "delta": round2(tb - ta) if ta is not None and tb is not None else None,
                     "evaluation_a": x.id, "evaluation_b": y.id, "changed": changed})
    rows.sort(key=lambda r: -abs(r["delta"] or 0))
    deltas = [r["delta"] for r in rows if r["delta"] is not None]
    names = {r["key"]: r["name"] for e in eb.values() for r in e.results}
    return {
        "a": {"id": cla.id, "name": cla.name}, "b": {"id": clb.id, "name": clb.name},
        "criteria_diff": _crit_diff(cla.criteria, clb.criteria),
        "summary": {"compared": len(rows), "avg_a": _avg(r["total_a"] for r in rows),
                    "avg_b": _avg(r["total_b"] for r in rows),
                    "avg_delta": round2(mean(deltas)) if deltas else None,
                    "avg_abs_delta": round2(mean(abs(d) for d in deltas)) if deltas else None,
                    "moved_up": sum(d > 0 for d in deltas), "moved_down": sum(d < 0 for d in deltas),
                    "unchanged": sum(d == 0 for d in deltas)},
        "answer_flips": [{"key": k, "name": names.get(k, k), "count": n} for k, n in flips.most_common()],
        "rows": rows,
        # evaluated with `a` but not yet with `b`: the interface runs them to fill the comparison
        "missing_b": [c for c in ea if c not in eb],
    }


# ---------- management report ----------

_CONF = {"high": "высокая", "medium": "средняя", "low": "низкая"}


def _safe(v):
    """Spreadsheet formula injection guard for text that comes from models or operators."""
    return "'" + v if isinstance(v, str) and v[:1] in ("=", "+", "-", "@", "\t", "\r") else v


def _report_data(db: Session, checklist_id: int | None, group: str | None) -> dict:
    evs = [e for e in _latest(db, checklist_id, group) if e.final_score]
    evs.sort(key=lambda e: (e.conversation.dataset_group or "", e.conversation_id))
    open_appeals = Counter()
    for a in db.scalars(select(Appeal)):
        open_appeals[a.evaluation_id] += a.status == "open"
    rows = []
    for e in evs:
        conf = services.confidence_of(e)
        rows.append([e.conversation_id, e.conversation.dataset_group or "", e.conversation.language,
                     e.conversation.channel, e.operator_name or "не указан", e.final_score["total"],
                     e.initial_score["total"], "да" if e.final_score["gross_error"] else "нет", conf["flagged"],
                     _CONF[conf["level"]], len(e.appeals), open_appeals[e.id],
                     (e.feedback or {}).get("summary") or ""])
    return {"evs": evs, "dialog_rows": rows}


DIALOG_HEAD = ["Диалог", "Набор", "Язык", "Канал", "Оператор", "Итог", "До апелляций", "Грубая ошибка",
               "Критериев на проверку", "Уверенность ИИ", "Апелляций", "Открытых апелляций", "Сводка по оператору"]


@router.get("/export")
def export_report(format: str = Query("xlsx", pattern="^(xlsx|csv)$"), checklist_id: int | None = None,
                  group: str | None = None, db: Session = Depends(get_db)):
    """Report for managers: summary, conversations, criteria, operators. `csv` returns the conversations sheet only."""
    data = _report_data(db, checklist_id, group)
    evs, rows = data["evs"], data["dialog_rows"]
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
    if format == "csv":
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(DIALOG_HEAD)
        w.writerows([[_safe(c) for c in r] for r in rows])
        return Response(("﻿" + buf.getvalue()).encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="cqa-report-{stamp}.csv"'})

    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    head_font, head_fill = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="2F5D50")

    def sheet(ws, head, body, widths):
        ws.append(head)
        for cell in ws[1]:
            cell.font, cell.fill = head_font, head_fill
            cell.alignment = Alignment(vertical="center", wrap_text=True)
        for r in body:
            ws.append([_safe(c) for c in r])
        for i, wd in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = wd
        ws.freeze_panes = "A2"

    totals = [e.final_score["total"] for e in evs if e.final_score["total"] is not None]
    appeals = db.scalars(select(Appeal)).all()
    decided = [a for a in appeals if a.status != "open"]
    flagged = sum(1 for e in evs if services.confidence_of(e)["flagged"])
    ws = wb.active
    ws.title = "Сводка"
    summary = [
        ("Отчёт сформирован", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")),
        ("Набор", group or "все"),
        ("Оценено диалогов", len(evs)),
        ("Средний итог (после апелляций)", _avg(totals)),
        ("Средний итог до апелляций", _avg(e.initial_score["total"] for e in evs)),
        ("Диалогов с грубыми ошибками", sum(e.final_score["gross_error"] for e in evs)),
        ("Оценены уверенно (ИИ не просит проверки)", f"{len(evs) - flagged} из {len(evs)}"),
        ("Диалогов, где нужен взгляд человека", flagged),
        ("Апелляций", len(appeals)),
        ("Из них изменено", sum(a.status == "changed" for a in decided)),
        ("Согласие проверяющих с ИИ по спорным, %", _pct(sum(a.status == "confirmed" for a in decided), len(decided))),
        ("Стоимость оценки, USD", round(sum(e.cost_usd or 0 for e in evs), 4)),
    ]
    sheet(ws, ["Показатель", "Значение"], summary, [48, 28])
    sheet(wb.create_sheet("Диалоги"), DIALOG_HEAD, rows, [22, 10, 8, 14, 20, 9, 13, 14, 14, 14, 11, 12, 70])
    crit = [[c["name"] or c["key"], c["evaluated"], c["avg_score_pct"], c["na_rate"],
             c["answers"].get("yes", 0), c["answers"].get("no", 0), c["answers"].get("na", 0)]
            for c in _criteria_stats(evs)]
    sheet(wb.create_sheet("Критерии"), ["Критерий", "Оценок", "Средний % балла", "N/A, %", "Да", "Нет", "N/A"], crit,
          [40, 10, 16, 10, 8, 8, 8])
    ops = [[k, v["count"], v["avg_total"], v["gross_errors"]] for k, v in
           sorted(_group(evs, lambda e: e.operator_name or "не указан").items(),
                  key=lambda kv: kv[1]["avg_total"] if kv[1]["avg_total"] is not None else 999)]
    sheet(wb.create_sheet("Операторы"), ["Оператор", "Диалогов", "Средний балл", "Грубые ошибки"], ops, [28, 10, 14, 14])

    out = io.BytesIO()
    wb.save(out)
    return Response(out.getvalue(),
                    media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    headers={"Content-Disposition": f'attachment; filename="cqa-report-{stamp}.xlsx"'})


@router.get("/results")
def submission_results(group: str, team_name: str = results_export.TEAM_NAME, expect: int | None = None,
                       db: Session = Depends(get_db)):
    """results.json for the organizers (schema 1.0): `results` plus `problems` found by the validator."""
    doc = results_export.build(db, group, team_name)
    return {**doc, "problems": results_export.validate(doc, expect)}
