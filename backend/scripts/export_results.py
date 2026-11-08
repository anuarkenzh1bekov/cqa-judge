"""Write the submission file results/<dev|prod>/results.json straight from the database (no server needed).

    python scripts/export_results.py --group DEV --set dev  [--team "Название"] [--expect 65]
    python scripts/export_results.py --group <prod group_id> --set prod --expect 10

Validates the file; exits with code 1 and does not write it if there are problems unless --force is given.
Then: git add results && git commit && git push.
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import results_export  # noqa: E402
from app.db import SessionLocal  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True, help="dataset group_id of the conversations (DEV, ...)")
    ap.add_argument("--set", required=True, choices=["dev", "prod"], help="target folder under results/")
    ap.add_argument("--team", default=results_export.TEAM_NAME)
    ap.add_argument("--expect", type=int, help="expected number of records (prod: 10)")
    ap.add_argument("--force", action="store_true", help="write even if validation fails")
    a = ap.parse_args()
    with SessionLocal() as db:
        doc = results_export.build(db, a.group, a.team)
    problems = results_export.validate(doc, a.expect)
    ok = sum(r["status"] == "ok" for r in doc["results"])
    print(f"{len(doc['results'])} записей: ok {ok}, error {len(doc['results']) - ok}; модель: {doc['model']['name']}")
    for p in problems[:30]:
        print("  !", p)
    if problems and not a.force:
        print("Файл не записан. Исправьте или запустите с --force.")
        sys.exit(1)
    out = ROOT / "results" / a.set / "results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("записано:", out.relative_to(ROOT))


if __name__ == "__main__":
    main()
