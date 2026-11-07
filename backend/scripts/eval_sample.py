"""Evaluation run on a random (stratified) sample of a dataset with the REAL models.

There is no ground truth for DEV, so the report measures what can be measured without it:
  * validity     - every answer allowed by the checklist, evidence points to real turns, N/A only where allowed;
  * consistency  - answers agree with the model's own extracted facts (e.g. no identification needed -> N/A);
  * stability    - the same dialog evaluated twice gives the same answers (--runs 2);
  * agreement    - how often Gemini and Jev agree, how often the re-check changed the answer;
  * accuracy     - ONLY if a hand-labelled gold file is given (--gold), per-criterion accuracy and total-score MAE.

Usage (from backend/):
  python scripts/eval_sample.py --n 12 --runs 2 --seed 7
  python scripts/eval_sample.py --make-gold-template eval/gold.json --n 15   # blank labels to fill by hand
  python scripts/eval_sample.py --gold eval/gold.json                         # compare with hand labels
"""
import argparse
import asyncio
import json
import random
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import pipeline, scoring  # noqa: E402
from app.checklist import DEFAULT_CHECKLIST, ChecklistIn  # noqa: E402
from app.services import fetch_dataset  # noqa: E402

REPORTS = Path(__file__).resolve().parents[1] / "reports"


def stratified_sample(records, n, seed):
    """Keep the language/channel mix of the dataset (calls are rare, so at least one if present)."""
    rng = random.Random(seed)
    groups = defaultdict(list)
    for r in records:
        groups[(r["language"], r["channel"])].append(r)
    total = len(records)
    picked = []
    for _key, items in sorted(groups.items()):
        k = max(1, round(n * len(items) / total))
        picked += rng.sample(items, min(k, len(items)))
    rng.shuffle(picked)
    return picked[:max(n, len(groups))]


def validity_issues(out, criteria, n_turns):
    issues = []
    crit = {c.key: c for c in criteria}
    for r in out["results"]:
        c = crit[r["key"]]
        if r["answer"] not in c.allowed_answers():
            issues.append(f"{r['key']}: answer {r['answer']} not allowed")
        if r["answer"] == "na" and not c.na_allowed:
            issues.append(f"{r['key']}: N/A not allowed")
        for e in r["evidence"]:
            if not 0 <= e["index"] < n_turns:
                issues.append(f"{r['key']}: evidence out of range")
        if "invalid_evidence_dropped" in r["review_reasons"]:
            issues.append(f"{r['key']}: model cited non-existent turns (dropped)")
    t = out["score"]["total"]
    if t is not None and not 0 <= t <= 100:
        issues.append(f"total {t} out of range")
    return issues


def consistency_warnings(out):
    """Heuristic: final answers should agree with the facts the model itself extracted."""
    f, a = out["facts"], {r["key"]: r["answer"] for r in out["results"]}
    w = []
    if "c03_identification" in a:
        if not f.get("identity_required") and a["c03_identification"] != "na":
            w.append("identity not required by facts, but c03 is not N/A")
        if f.get("identity_required") and a["c03_identification"] == "na":
            w.append("identity required by facts, but c03 is N/A")
    if "c07_closing" in a and f.get("ending") in ("client_left", "connection_lost") and a["c07_closing"] == "no":
        w.append(f"ending={f['ending']} but c07 is 'no' (expected N/A unless operator could close)")
    if "c04_consultation" in a and not f.get("request_formulated") and a["c04_consultation"] != "na":
        w.append("request not formulated, but c04 is not N/A")
    return w


async def evaluate_sample(sample, criteria, runs):
    """Dialogs run in parallel (bounded by MAX_CONCURRENCY inside the pipeline); runs of one dialog are independent."""
    done = 0

    async def one(rec):
        nonlocal done
        conv = {"id": rec["conversation_id"], "channel": rec["channel"], "language": rec["language"],
                "transcript": rec["transcript"]}
        outs = list(await asyncio.gather(*(pipeline.evaluate(conv, criteria) for _ in range(runs))))
        done += 1
        print(f"[{done}/{len(sample)}] {rec['conversation_id']:10} totals={[o['score']['total'] for o in outs]}",
              flush=True)
        return rec["conversation_id"], {"rec": rec, "outs": outs}

    pairs = await asyncio.gather(*(one(r) for r in sample))
    order = {r["conversation_id"]: i for i, r in enumerate(sample)}
    return dict(sorted(pairs, key=lambda p: order[p[0]]))


def build_report(results, criteria, runs, gold, args, elapsed):
    lines, data = [], {"args": vars(args), "dialogs": {}}
    keys = [c.key for c in criteria]
    names = {c.key: c.name for c in criteria}
    n = len(results)
    val_issues, cons_warn = [], []
    stab = defaultdict(lambda: [0, 0])  # key -> [same, compared]
    tot_spread = []
    agree = Counter()
    adj_changed = 0
    answers = defaultdict(Counter)
    cost = dur = 0.0
    gold_hits = defaultdict(lambda: [0, 0])
    gold_mae = []

    for cid, item in results.items():
        outs, n_turns = item["outs"], len(item["rec"]["transcript"])
        first = outs[0]
        for o in outs:
            val_issues += [f"{cid}: {x}" for x in validity_issues(o, criteria, n_turns)]
            cost += o["cost_usd"]
            dur += o["duration_ms"]
        cons_warn += [f"{cid}: {x}" for x in consistency_warnings(first)]
        for r in first["results"]:
            agree[r["agreement"]] += 1
            answers[r["key"]][r["answer"]] += 1
            if (r.get("adjudication") or {}).get("changed"):
                adj_changed += 1
        if runs > 1:
            a0 = {r["key"]: r["answer"] for r in outs[0]["results"]}
            for o in outs[1:]:
                for r in o["results"]:
                    stab[r["key"]][1] += 1
                    stab[r["key"]][0] += r["answer"] == a0[r["key"]]
            ts = [o["score"]["total"] for o in outs if o["score"]["total"] is not None]
            if len(ts) > 1:
                tot_spread.append(max(ts) - min(ts))
        if gold and cid in gold:
            g = gold[cid]
            for k, v in g.get("answers", {}).items():
                if v in (None, "") or k not in keys:
                    continue
                pred = next(r["answer"] for r in first["results"] if r["key"] == k)
                gold_hits[k][1] += 1
                gold_hits[k][0] += scoring.normalize_answer(v) == pred
            if g.get("total") is not None and first["score"]["total"] is not None:
                gold_mae.append(abs(float(g["total"]) - first["score"]["total"]))
        data["dialogs"][cid] = {
            "language": item["rec"]["language"], "channel": item["rec"]["channel"],
            "runs": [{"total": o["score"]["total"], "gross_error": o["score"]["gross_error"],
                      "answers": {r["key"]: r["answer"] for r in o["results"]},
                      "agreement": {r["key"]: r["agreement"] for r in o["results"]},
                      "explanations": {r["key"]: r["explanation"] for r in o["results"]}} for o in outs],
            "facts": first["facts"],
        }

    evals = n * runs
    lines += [f"# Прогон на случайной выборке — {datetime.now():%Y-%m-%d %H:%M}", "",
              f"Набор: `{args.group}` · выборка: {n} диалогов (seed {args.seed}, стратифицирована по языку и каналу) · "
              f"прогонов на диалог: {runs} · оценок всего: {evals}", "",
              f"Время: {elapsed:.0f} с · стоимость: ${cost:.3f} (≈ ${cost / max(1, evals):.4f} за оценку) · "
              f"среднее время одной оценки: {dur / max(1, evals) / 1000:.1f} с", "",
              "Эталонных оценок для DEV нет, поэтому точность здесь не измеряется — "
              "только корректность, согласованность и стабильность.", ""]

    mix = Counter((it["rec"]["language"], it["rec"]["channel"]) for it in results.values())
    lines += ["## Выборка", "", " · ".join(f"{lang} {ch}: {k}" for (lang, ch), k in sorted(mix.items())), ""]

    lines += ["## Корректность", "",
              f"- Нарушений формата (недопустимый ответ, N/A где запрещён, ссылка на несуществующую реплику): "
              f"**{len(val_issues)}**"] + [f"  - {x}" for x in val_issues[:20]] + [""]
    lines += [f"- Расхождений с собственными фактами модели (эвристика правил N/A): **{len(cons_warn)}**"] \
        + [f"  - {x}" for x in cons_warn[:20]] + [""]

    if runs > 1:
        overall = sum(s for s, _ in stab.values()) / max(1, sum(t for _, t in stab.values()))
        lines += ["## Стабильность (тот же диалог, повторная оценка)", "",
                  f"Совпадение ответов по критериям: **{overall:.0%}** · разброс итога: среднее "
                  f"{statistics.mean(tot_spread) if tot_spread else 0:.2f}, максимум "
                  f"{max(tot_spread) if tot_spread else 0:.2f} балла", "",
                  "| Критерий | Совпадение |", "|---|---|"]
        lines += [f"| {names[k]} | {stab[k][0]}/{stab[k][1]} |" for k in keys if stab[k][1]]
        lines += [""]

    total_rows = sum(agree.values()) or 1
    lines += ["## Gemini и Jev", "",
              " · ".join(f"{k}: {v} ({v / total_rows:.0%})" for k, v in agree.most_common()),
              f"· ответ изменён после перепроверки: {adj_changed}", ""]

    lines += ["## Распределение ответов (первый прогон)", "", "| Критерий | Ответы |", "|---|---|"]
    lines += [f"| {names[k]} | {', '.join(f'{a}: {c}' for a, c in answers[k].most_common())} |" for k in keys]
    lines += [""]

    if gold:
        lines += ["## Сравнение с ручной разметкой", ""]
        if gold_hits:
            acc = sum(h for h, _ in gold_hits.values()) / max(1, sum(t for _, t in gold_hits.values()))
            lines += [f"Точность по критериям: **{acc:.0%}**" +
                      (f" · MAE итогового балла: **{statistics.mean(gold_mae):.2f}**" if gold_mae else ""), "",
                      "| Критерий | Верно |", "|---|---|"]
            lines += [f"| {names[k]} | {gold_hits[k][0]}/{gold_hits[k][1]} |" for k in keys if gold_hits[k][1]]
        else:
            lines += ["В файле разметки нет заполненных ответов для диалогов выборки."]
        lines += [""]

    lines += ["## Диалоги", "", "| Диалог | Язык | Канал | Итог | Грубая | Спорные критерии |", "|---|---|---|---|---|---|"]
    for cid, item in results.items():
        o = item["outs"][0]
        disputed = [r["key"] for r in o["results"] if r["needs_review"]]
        tot = " / ".join(str(x["score"]["total"]) for x in item["outs"])
        lines += [f"| {cid} | {item['rec']['language']} | {item['rec']['channel']} | {tot} | "
                  f"{'да' if o['score']['gross_error'] else ''} | {', '.join(disputed)} |"]
    data["summary"] = {"validity_issues": val_issues, "consistency_warnings": cons_warn,
                       "agreement": dict(agree), "cost_usd": cost}
    return "\n".join(lines) + "\n", data


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--group", default="DEV")
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--runs", type=int, default=2)
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--gold", help="JSON with hand labels: {conversation_id: {answers: {key: answer}, total}}")
    ap.add_argument("--make-gold-template", metavar="PATH", help="write a blank labelling file for the sample and exit")
    args = ap.parse_args()
    args.seed = args.seed if args.seed is not None else random.randrange(10_000)

    records = asyncio.run(fetch_dataset(args.group))
    criteria = ChecklistIn(**DEFAULT_CHECKLIST).criteria
    gold = json.loads(Path(args.gold).read_text(encoding="utf-8")) if args.gold else None
    if gold:
        sample = [r for r in records if r["conversation_id"] in gold]
    else:
        sample = stratified_sample(records, args.n, args.seed)

    if args.make_gold_template:
        tpl = {r["conversation_id"]: {"answers": {c.key: None for c in criteria}, "total": None,
                                      "note": f"{r['language']} {r['channel']}; allowed: "
                                              + "; ".join(f"{c.key}={'/'.join(c.allowed_answers())}"
                                                          for c in criteria)}
               for r in sample}
        Path(args.make_gold_template).parent.mkdir(parents=True, exist_ok=True)
        Path(args.make_gold_template).write_text(json.dumps(tpl, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Template with {len(tpl)} dialogs written to {args.make_gold_template}")
        return

    print(f"Sample of {len(sample)} from {len(records)} (seed {args.seed}), runs={args.runs}")
    t0 = time.time()
    results = asyncio.run(evaluate_sample(sample, criteria, args.runs))
    md, data = build_report(results, criteria, args.runs, gold, args, time.time() - t0)
    REPORTS.mkdir(exist_ok=True)
    stem = f"eval_{args.group}_{datetime.now():%Y%m%d_%H%M%S}"
    (REPORTS / f"{stem}.md").write_text(md, encoding="utf-8")
    (REPORTS / f"{stem}.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str),
                                          encoding="utf-8")
    print(md)
    print(f"Report: {REPORTS / (stem + '.md')}")


if __name__ == "__main__":
    main()
