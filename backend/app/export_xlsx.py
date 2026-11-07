"""Excel export of the analytics: one workbook, a sheet per view. Same data as /api/stats (latest finished
evaluation per conversation, final scores after appeals) plus per-dialog and per-criterion detail."""
import re
from collections import Counter
from datetime import datetime
from io import BytesIO

from openpyxl import Workbook
from openpyxl.chart import BarChart, PieChart, Reference
from openpyxl.chart.label import DataLabelList
from openpyxl.chart.legend import Legend
from openpyxl.chart.series import DataPoint
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from .models import Appeal, Evaluation

HEAD_FILL = PatternFill("solid", fgColor="164A34")
HEAD_FONT = Font(bold=True, color="FFFFFF")
RED = PatternFill("solid", fgColor="F8D7D3")
AMBER = PatternFill("solid", fgColor="FBEFC9")
GREEN = PatternFill("solid", fgColor="D6EFE1")
WRAP = Alignment(wrap_text=True, vertical="top")
MOOD = {"calm": "спокоен", "positive": "доволен", "confused": "растерян", "anxious": "волнуется",
        "irritated": "раздражён", "angry": "злится"}
AGREE = {"agree": "согласны", "minor": "соседние ступени", "disputed": "спор, перепроверено", "review": "на проверку",
         "gemini_only": "только Gemini"}
STATUS = {"open": "открыта", "confirmed": "оценка подтверждена", "changed": "оценка изменена"}


def _ans(a):
    if a in ("yes", "no", "na"):
        return {"yes": "Да", "no": "Нет", "na": "N/A"}[a]
    try:  # scale step -> a number, so Excel can sum/filter it
        f = float(a)
        return int(f) if f.is_integer() else f
    except (TypeError, ValueError):
        return a


_REF = re.compile(r"\[(\d+)\]")


def _txt(t):
    """Model explanations cite turns 0-based as [9]; the UI and this file show them as #10."""
    return _REF.sub(lambda m: f"#{int(m.group(1)) + 1}", t or "")


def _table(ws, header, rows, widths=None, wrap_cols=(), sheet_table=True):
    """sheet_table=False: a small table inside a sheet - no filter, no frozen header. (Freezing and then
    un-freezing leaves a dangling pane reference that Excel refuses to open.)"""
    ws.append(header)
    for c in ws[ws.max_row]:
        c.fill, c.font, c.alignment = HEAD_FILL, HEAD_FONT, Alignment(wrap_text=True, vertical="center")
    first = ws.max_row
    for r in rows:
        ws.append(list(r))
    if sheet_table:
        if rows:
            ws.auto_filter.ref = f"A{first}:{get_column_letter(len(header))}{ws.max_row}"
        ws.freeze_panes = ws.cell(row=first + 1, column=1)
    for i, h in enumerate(header, 1):
        w = (widths or {}).get(h) or min(45, max(10, len(str(h)) + 2))
        ws.column_dimensions[get_column_letter(i)].width = w
        if h in wrap_cols:
            for row in ws.iter_rows(min_row=first + 1, min_col=i, max_col=i):
                row[0].alignment = WRAP
    return first


def _score_colors(ws, col, first, last):
    if last <= first:
        return
    rng = f"{col}{first + 1}:{col}{last}"
    ws.conditional_formatting.add(rng, CellIsRule(operator="lessThan", formula=["50"], fill=RED))
    ws.conditional_formatting.add(rng, CellIsRule(operator="between", formula=["50", "84.99"], fill=AMBER))
    ws.conditional_formatting.add(rng, CellIsRule(operator="greaterThanOrEqual", formula=["85"], fill=GREEN))


CHART_COLORS = ["164A34", "D9A441", "5FA37E", "C0402F", "7D8883", "3E6FB0"]


def _block(ws, row, title, header, rows):
    """Writes a small data table that a chart points at. Returns (header_row, last_row)."""
    ws.cell(row, 1, title).font = Font(bold=True)
    for i, h in enumerate(header, 1):
        c = ws.cell(row + 1, i, h)
        c.fill, c.font = HEAD_FILL, HEAD_FONT
    for j, r in enumerate(rows, row + 2):
        for i, v in enumerate(r, 1):
            ws.cell(j, i, v)
    return row + 1, row + 1 + len(rows)


def _labels(val=False, pct=False):
    """Only the number on the bar (Excel otherwise prints "series; category; value")."""
    return DataLabelList(showVal=val, showPercent=pct, showSerName=False, showCatName=False, showLegendKey=False,
                         showLeaderLines=False)


def _bar(title, y_title, horizontal=False, stacked=False):
    ch = BarChart()
    ch.type = "bar" if horizontal else "col"
    ch.title, ch.y_axis.title = title, y_title
    ch.style = 10
    ch.legend = None
    ch.dataLabels = _labels(val=True)
    ch.y_axis.majorGridlines = None
    ch.x_axis.delete = False
    ch.y_axis.delete = False
    if stacked:
        ch.grouping, ch.overlap = "stacked", 100
    return ch


def _paint(ch, colors=CHART_COLORS):
    for i, s in enumerate(ch.series):
        s.graphicalProperties.solidFill = colors[i % len(colors)]
        s.graphicalProperties.line.solidFill = colors[i % len(colors)]


def _charts(wb, stats: dict, evs: list[Evaluation]):
    """Native Excel charts (they stay live: edit a number in the table and the chart follows).
    Every number comes from the same calculation as the Analytics screen - nothing is typed in by hand."""
    ws = wb.create_sheet("Графики")
    ws.column_dimensions["A"].width = 40
    for col in "BCD":
        ws.column_dimensions[col].width = 13
    anchor_col, r = "F", 1

    def place(ch, top, height=7.5, width=17):
        ch.height, ch.width = height, width
        ws.add_chart(ch, f"{anchor_col}{top}")

    # 1. score distribution
    dist = stats["score_distribution"]
    buckets = [k for k in ("0-49", "50-69", "70-84", "85-100") if k in dist] or ["85-100"]
    h, last = _block(ws, r, "Распределение итоговых баллов", ["Диапазон", "Диалогов"], [(k, dist.get(k, 0)) for k in buckets])
    ch = _bar("Сколько диалогов в каждом диапазоне баллов", "диалогов")
    ch.add_data(Reference(ws, min_col=2, min_row=h, max_row=last), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=h + 1, max_row=last))
    _paint(ch)
    pts = {"0-49": "C0402F", "50-69": "D9A441", "70-84": "9BC4A8", "85-100": "164A34"}
    for i, k in enumerate(buckets):
        dp = DataPoint(idx=i)
        dp.graphicalProperties.solidFill = pts[k]
        ch.series[0].dPt.append(dp)
    place(ch, r)
    r = max(last + 3, r + 16)

    # 2. criteria, weakest first
    crit = [c for c in stats["by_criterion"] if c["avg_score_pct"] is not None]
    # a horizontal bar chart draws the first row at the bottom: strongest first puts the weakest on top
    crit = sorted(crit, key=lambda c: -c["avg_score_pct"])
    h, last = _block(ws, r, "Средний % балла по критериям (без флагов)", ["Критерий", "Средний %"],
                     [(c["name"] or c["key"], c["avg_score_pct"]) for c in crit])
    ch = _bar("Критерии: средний % от максимального балла", None, horizontal=True)
    ch.add_data(Reference(ws, min_col=2, min_row=h, max_row=last), titles_from_data=True)
    ch.set_categories(Reference(ws, min_col=1, min_row=h + 1, max_row=last))
    ch.y_axis.scaling.min, ch.y_axis.scaling.max = 0, 100
    _paint(ch)
    place(ch, r, height=max(7.5, 1.1 * len(crit)), width=20)
    r = max(last + 3, r + int(max(7.5, 1.1 * len(crit)) * 2) + 2)

    # 3. language and channel
    for title, data in (("Средний балл по языкам", stats["by_language"]), ("Средний балл по каналам", stats["by_channel"])):
        rows = sorted(((k, v["avg_total"], v["count"]) for k, v in data.items()), key=lambda x: x[0])
        h, last = _block(ws, r, title, ["", "Средний балл", "Диалогов"], rows)
        ch = _bar(title, "балл")
        ch.add_data(Reference(ws, min_col=2, min_row=h, max_row=last), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=1, min_row=h + 1, max_row=last))
        ch.y_axis.scaling.min, ch.y_axis.scaling.max = 0, 100
        _paint(ch, ["3E6FB0"] if "язык" in title else ["5FA37E"])
        place(ch, r)
        r = max(last + 3, r + 16)

    # 4. client mood: start vs end
    order = ["calm", "positive", "confused", "anxious", "irritated", "angry"]
    start = Counter(((e.facts or {}).get("client_mood") or {}).get("start") for e in evs)
    end = Counter(((e.facts or {}).get("client_mood") or {}).get("end") for e in evs)
    with_mood = sum(1 for e in evs if (e.facts or {}).get("client_mood"))
    if with_mood:
        h, last = _block(ws, r, f"Настроение клиента (диалогов с анализом: {with_mood})", ["Настроение", "В начале", "В конце"],
                         [(MOOD[m], start.get(m, 0), end.get(m, 0)) for m in order])
        ch = _bar("Настроение клиента: в начале и в конце диалога", "диалогов")
        ch.legend = Legend()
        ch.legend.position = "b"
        ch.legend.overlay = False
        ch.add_data(Reference(ws, min_col=2, max_col=3, min_row=h, max_row=last), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=1, min_row=h + 1, max_row=last))
        _paint(ch, ["D9A441", "164A34"])
        place(ch, r)
        r = max(last + 3, r + 16)

    # 5. how often the two models agreed
    ag = stats["model_agreement"]["per_criterion_counts"]
    rows = [(AGREE.get(k, k or "—"), v) for k, v in sorted(ag.items(), key=lambda x: -x[1])]
    if rows:
        h, last = _block(ws, r, "Согласие Gemini и Jev (ответов по критериям)", ["", "Ответов"], rows)
        ch = PieChart()
        ch.title = "Насколько независимые модели согласны"
        ch.add_data(Reference(ws, min_col=2, min_row=h, max_row=last), titles_from_data=True)
        ch.set_categories(Reference(ws, min_col=1, min_row=h + 1, max_row=last))
        ch.dataLabels = _labels(pct=True)
        ch.legend = Legend()
        ch.legend.position = "r"
        for i in range(len(rows)):
            dp = DataPoint(idx=i)
            dp.graphicalProperties.solidFill = CHART_COLORS[i % len(CHART_COLORS)]
            ch.series[0].dPt.append(dp)
        place(ch, r)
    return ws


def build(stats: dict, evs: list[Evaluation], appeals: list[Appeal], filters: str) -> bytes:
    wb = Workbook()

    # --- Сводка
    ws = wb.active
    ws.title = "Сводка"
    o = stats["overview"]
    ws.append(["CQA · аналитика качества диалогов"])
    ws["A1"].font = Font(bold=True, size=14)
    ws.append([f"Выгружено {datetime.now():%d.%m.%Y %H:%M}. {filters}. Последняя оценка каждого диалога, баллы после апелляций."])
    ws.append([])
    for k, v in [("Оценено диалогов", o["evaluated_conversations"]), ("Средний балл", o["avg_total"]),
                 ("Средний балл до апелляций", o["avg_initial_total"]),
                 ("Диалогов с грубыми ошибками", o["gross_error_conversations"]),
                 ("Критериев на проверку", o["criteria_needing_review"]),
                 ("Апелляций всего", stats["appeals"].get("total", 0)),
                 ("Апелляций с изменённой оценкой", stats["appeals"].get("changed", 0)),
                 ("Стоимость оценки, всего USD", o["total_cost_usd"]), ("Стоимость одного диалога, USD", o["avg_cost_usd"]),
                 ("Среднее время оценки, с", round((o["avg_duration_ms"] or 0) / 1000, 1))]:
        ws.append([k, v])
        ws.cell(ws.max_row, 1).font = Font(bold=True)
    ws.append([])
    _table(ws, ["Распределение баллов", "Диалогов"],
           [(k, stats["score_distribution"][k]) for k in ("85-100", "70-84", "50-69", "0-49", "n/a")
            if stats["score_distribution"].get(k)], sheet_table=False)
    for title, data in (("Язык", stats["by_language"]), ("Канал", stats["by_channel"])):
        ws.append([])
        _table(ws, [title, "Диалогов", "Средний балл", "Грубые ошибки"],
               [(k, v["count"], v["avg_total"], v["gross_errors"]) for k, v in sorted(data.items())],
               sheet_table=False)
    ws.column_dimensions["A"].width = 34
    ws.column_dimensions["B"].width = 14
    ws.column_dimensions["C"].width = 14
    ws.column_dimensions["D"].width = 14

    _charts(wb, stats, evs)

    # criteria order: as in the evaluations' checklists, first seen first
    crit_order, crit_name = [], {}
    for e in evs:
        for r in e.results:
            if r["key"] not in crit_name:
                crit_order.append(r["key"])
                crit_name[r["key"]] = r["name"]

    # --- Диалоги
    ws = wb.create_sheet("Диалоги")
    header = ["Диалог", "Набор", "Канал", "Язык", "Оператор", "Итог", "До апелляций", "Грубая ошибка",
              "На проверку", *[crit_name[k] for k in crit_order], "Настроение: начало", "Настроение: конец",
              "Чек-лист", "Стоимость, USD", "Время, с", "Оценено"]
    rows = []
    for e in sorted(evs, key=lambda x: x.conversation_id):
        fc = e.final_score["criteria"]
        m = (e.facts or {}).get("client_mood") or {}
        rows.append([e.conversation_id, e.conversation.dataset_group, e.conversation.channel, e.conversation.language,
                     e.operator_name or "не указан", e.final_score["total"], (e.initial_score or {}).get("total"),
                     "ДА" if e.final_score["gross_error"] else "",
                     sum(1 for r in e.results if r.get("needs_review")) or "",
                     *[_ans(fc[k]["answer"]) if k in fc else "" for k in crit_order],
                     MOOD.get(m.get("start"), ""), MOOD.get(m.get("end"), ""),
                     (e.checklist_snapshot or {}).get("name"), e.cost_usd, round((e.duration_ms or 0) / 1000, 1),
                     e.finished_at.strftime("%d.%m.%Y %H:%M") if e.finished_at else ""])
    first = _table(ws, header, rows, widths={"Диалог": 26, "Оператор": 16, "Чек-лист": 30, "Оценено": 16})
    _score_colors(ws, "F", first, ws.max_row)
    for row in ws.iter_rows(min_row=first + 1, min_col=8, max_col=8):
        if row[0].value:
            row[0].fill, row[0].font = RED, Font(bold=True, color="9C2B1E")

    # --- Обоснования (every criterion of every dialog)
    ws = wb.create_sheet("Обоснования")
    rows = []
    for e in sorted(evs, key=lambda x: x.conversation_id):
        fc = e.final_score["criteria"]
        for r in e.results:
            f = fc.get(r["key"], {})
            rows.append([e.conversation_id, r["name"], _ans(f.get("answer", r["answer"])), f.get("points"),
                         f.get("max_points"), "изменено апелляцией" if f.get("answer", r["answer"]) != r["answer"] else "",
                         AGREE.get(r.get("agreement"), r.get("agreement")), "да" if r.get("needs_review") else "",
                         _txt(r.get("explanation")),
                         " | ".join(f"#{x['index'] + 1} {x.get('speaker')}: {x.get('text')}" for x in r.get("evidence") or [])])
    _table(ws, ["Диалог", "Критерий", "Ответ", "Баллы", "Макс.", "Апелляция", "Модели", "На проверку",
                "Обоснование", "Реплики-доказательства"], rows,
           widths={"Диалог": 26, "Критерий": 30, "Модели": 18, "Обоснование": 70, "Реплики-доказательства": 70},
           wrap_cols=("Обоснование", "Реплики-доказательства"))

    # --- Критерии
    ws = wb.create_sheet("Критерии")
    rows = []
    for c in stats["by_criterion"]:
        a, ag = c["answers"], c["model_agreement"]
        scale = ", ".join(f"{k}: {v}" for k, v in sorted(a.items()) if k not in ("yes", "no", "na"))
        rows.append([c["name"] or c["key"], c["evaluated"], c["avg_score_pct"], c["na_rate"], a.get("yes", ""),
                     a.get("no", ""), a.get("na", ""), scale, ag.get("agree", 0) + ag.get("minor", 0),
                     ag.get("disputed", ""), ag.get("review", "")])
    first = _table(ws, ["Критерий", "Оценено", "Средний % балла", "N/A, %", "Да", "Нет", "N/A", "Шкала",
                        "Модели согласны", "Спор, перепроверено", "На проверку"], rows, widths={"Критерий": 40, "Шкала": 30})
    _score_colors(ws, "C", first, ws.max_row)

    # --- Операторы
    ws = wb.create_sheet("Операторы")
    tips = {}
    for e in evs:
        for i in (e.feedback or {}).get("improvements", []):
            if i.get("criterion_key"):
                tips.setdefault(e.operator_name or "не указан", Counter())[crit_name.get(i["criterion_key"], i["criterion_key"])] += 1
    rows = [(k, v["count"], v["avg_total"], v["gross_errors"],
             "; ".join(f"{n} ({c})" for n, c in tips.get(k, Counter()).most_common(3)))
            for k, v in sorted(stats["by_operator"].items(), key=lambda x: x[1]["avg_total"] or 0)]
    first = _table(ws, ["Оператор", "Диалогов", "Средний балл", "Грубые ошибки", "Чаще всего советуют улучшить"], rows,
                   widths={"Оператор": 20, "Чаще всего советуют улучшить": 70}, wrap_cols=("Чаще всего советуют улучшить",))
    _score_colors(ws, "C", first, ws.max_row)

    # --- Грубые ошибки
    ws = wb.create_sheet("Грубые ошибки")
    rows = []
    for e in evs:
        if not e.final_score["gross_error"]:
            continue
        for r in e.results:
            if r["type"] == "flag" and e.final_score["criteria"].get(r["key"], {}).get("answer") == "yes":
                rows.append([e.conversation_id, e.operator_name or "не указан", r["name"], _txt(r.get("explanation")),
                             " | ".join(f"#{x['index'] + 1}: {x.get('text')}" for x in r.get("evidence") or [])])
    _table(ws, ["Диалог", "Оператор", "Флаг", "Обоснование", "Реплики"], rows,
           widths={"Диалог": 26, "Оператор": 16, "Флаг": 20, "Обоснование": 70, "Реплики": 70},
           wrap_cols=("Обоснование", "Реплики"))

    # --- Апелляции
    ws = wb.create_sheet("Апелляции")
    latest = {e.id for e in evs}
    rows = [[a.evaluation.conversation_id, crit_name.get(a.criterion_key, a.criterion_key), STATUS.get(a.status, a.status),
             a.author, a.comment, _ans(a.original_answer), _ans(a.new_answer) if a.new_answer else "", a.reviewer or "",
             a.reason or "", "да" if a.evaluation_id in latest else "нет, диалог переоценён",
             a.created_at.strftime("%d.%m.%Y %H:%M") if a.created_at else ""] for a in appeals]
    _table(ws, ["Диалог", "Критерий", "Статус", "Автор", "Комментарий", "Было", "Стало", "Проверяющий", "Причина решения",
                "К текущей оценке", "Создана"], rows, widths={"Диалог": 26, "Критерий": 30, "Комментарий": 50, "Причина решения": 50, "К текущей оценке": 22},
           wrap_cols=("Комментарий", "Причина решения"))

    buf = BytesIO()
    wb.save(buf)
    return buf.getvalue()
