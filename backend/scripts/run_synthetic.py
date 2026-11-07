"""Run the hand-written edge-case dialogs (eval/synthetic.json) through a running server and compare with our labels.

Usage: python backend/scripts/run_synthetic.py [--api http://localhost:8000] [--only s02,s04]
The dialogs are uploaded as dataset group "SYNTH" (visible in the UI), then evaluated through the normal API.
"""
import argparse
import asyncio
import json
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[2]


async def run(api: str, only: list[str]):
    data = json.loads((ROOT / "eval" / "synthetic.json").read_text(encoding="utf-8"))
    recs = [r for r in data["records"] if not only or any(r["conversation_id"].startswith(o) for o in only)]
    async with httpx.AsyncClient(base_url=api, timeout=300) as c:
        (await c.post("/api/conversations", json={"records": recs, "group": "SYNTH"})).raise_for_status()

        async def one(r):
            resp = await c.post("/api/evaluations", json={"conversation_id": r["conversation_id"]})
            resp.raise_for_status()
            return r["conversation_id"], resp.json()

        out = await asyncio.gather(*(one(r) for r in recs))

    total = hit = 0
    lines = []
    for cid, ev in out:
        exp = data["expected"][cid]["answers"]
        got = {r["key"]: r for r in ev["results"]}
        bad = []
        for k, want in exp.items():
            ok_set = want if isinstance(want, list) else [want]
            a = got[k]["answer"]
            total += 1
            if a in ok_set:
                hit += 1
            else:
                bad.append(f"  {k}: got {a}, want {'/'.join(ok_set)} [{got[k].get('agreement')}] — {got[k].get('explanation', '')[:220]}")
        fs = ev["final_score"]
        lines.append(f"{'OK ' if not bad else 'XX '}{cid}: {fs['total']}{' GROSS' if fs['gross_error'] else ''}"
                     f"  ({ev['duration_ms'] / 1000:.0f}s, ${ev['cost_usd']:.4f})")
        lines += bad
    print("\n".join(lines))
    print(f"\nCriteria matched: {hit}/{total} ({hit / total:.0%})")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--api", default="http://localhost:8000")
    p.add_argument("--only", default="")
    a = p.parse_args()
    asyncio.run(run(a.api, [s for s in a.only.split(",") if s]))
