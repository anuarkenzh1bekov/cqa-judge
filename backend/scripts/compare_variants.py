"""Speed vs quality: compare pipeline variants on the same dialogs.

There is no ground truth for DEV, so "quality did not drop" is measured as agreement with the current (baseline)
pipeline, against the baseline's own run-to-run noise (baseline vs a second baseline run):
  * answer agreement per criterion (same answer for the same criterion),
  * mean absolute difference of the total score,
  * time and cost per evaluation.
A variant is fine when its agreement with the baseline is about as high as the baseline's agreement with itself.

Usage (from backend/):  python scripts/compare_variants.py --n 8 --seed 11
"""
import argparse
import asyncio
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from app import pipeline  # noqa: E402
from app.checklist import DEFAULT_CHECKLIST, ChecklistIn  # noqa: E402
from app.config import settings  # noqa: E402
from app.services import fetch_dataset  # noqa: E402
from eval_sample import stratified_sample  # noqa: E402

# name -> (with_feedback, gemini_thinking)
VARIANTS = {
    "A  текущий (с рекомендациями)": (True, ""),
    "A2 текущий, повтор": (True, ""),
    "B  без рекомендаций в основном запросе": (False, ""),
    "C  B + thinking=low": (False, "low"),
}


async def run_variant(sample, criteria, with_feedback, thinking):
    settings.gemini_thinking = thinking

    async def one(rec):
        conv = {"id": rec["conversation_id"], "channel": rec["channel"], "language": rec["language"],
                "transcript": rec["transcript"]}
        return rec["conversation_id"], await pipeline.evaluate(conv, criteria, with_feedback=with_feedback)

    return dict(await asyncio.gather(*(one(r) for r in sample)))


def answers(out):
    return {r["key"]: r["answer"] for r in out["results"]}


def compare(base, other):
    same = tot = 0
    diffs = []
    for cid, b in base.items():
        a, o = answers(b), answers(other[cid])
        for k in a:
            tot += 1
            same += a[k] == o.get(k)
        if b["score"]["total"] is not None and other[cid]["score"]["total"] is not None:
            diffs.append(abs(b["score"]["total"] - other[cid]["score"]["total"]))
    return same / tot * 100, statistics.mean(diffs) if diffs else 0.0, max(diffs) if diffs else 0.0


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=8)
    ap.add_argument("--seed", type=int, default=11)
    ap.add_argument("--only", default="", help="comma list of variant letters to run, e.g. A,A2,B")
    args = ap.parse_args()
    criteria = ChecklistIn(**DEFAULT_CHECKLIST).criteria
    sample = stratified_sample(await fetch_dataset("DEV"), args.n, args.seed)
    print(f"{len(sample)} dialogs:", [r["conversation_id"] for r in sample], flush=True)
    wanted = {x.strip() for x in args.only.split(",") if x.strip()}
    outs = {}
    for name, (fb, th) in VARIANTS.items():
        if wanted and name.split()[0] not in wanted:
            continue
        res = await run_variant(sample, criteria, fb, th)
        outs[name] = res
        d = [o["duration_ms"] / 1000 for o in res.values()]
        c = [o["cost_usd"] for o in res.values()]
        print(f"{name:42} время {statistics.mean(d):5.1f} с (макс {max(d):.0f}) · ${statistics.mean(c):.4f}", flush=True)
    base = outs.get("A  текущий (с рекомендациями)")
    print("\nСогласие ответов с вариантом A (по критериям) · средняя / макс. разница итога")
    for name, res in outs.items():
        if res is base:
            continue
        pct, mean_d, max_d = compare(base, res)
        print(f"{name:42} {pct:5.1f}%  Δитога {mean_d:.2f} / {max_d:.2f}")
    Path(__file__).resolve().parents[1].joinpath("reports", "compare_variants.json").write_text(
        json.dumps({n: {cid: {"answers": answers(o), "total": o["score"]["total"], "ms": o["duration_ms"],
                              "cost": o["cost_usd"]} for cid, o in r.items()} for n, r in outs.items()},
                   ensure_ascii=False, indent=1), encoding="utf-8")


asyncio.run(main())
