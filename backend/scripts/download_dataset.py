"""Download a dataset from the organizers' API into datasets/<GROUP>.json.

Signed audio links (audio_url) point to real customer call recordings, so they are NOT written to the repo copy:
they are replaced with null and `has_audio: true` is kept. The player still works when the set is imported through
the API (the backend then stores the live link). Transcripts are saved unchanged, with original timestamps.

Usage (from backend/):  python scripts/download_dataset.py --group DEV
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services import DATASETS_DIR, fetch_dataset_api  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", default="DEV")
    args = ap.parse_args()
    records = asyncio.run(fetch_dataset_api(args.group))
    for r in records:
        r["has_audio"] = bool(r.get("audio_url"))
        r["audio_url"] = None
    DATASETS_DIR.mkdir(exist_ok=True)
    out = DATASETS_DIR / f"{args.group}.json"
    out.write_text(json.dumps({"dataset_group_id": args.group, "total_records": len(records), "records": records},
                              ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{out}: {len(records)} records, audio links removed from {sum(r['has_audio'] for r in records)}")


if __name__ == "__main__":
    main()
