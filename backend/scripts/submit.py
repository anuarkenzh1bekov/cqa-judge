"""One command for the submission hour: load the set -> evaluate -> retry failures -> results.json -> strict check.

Works through the running server (Docker), so the evaluations land in the same database as the UI.

    python backend/scripts/submit.py --group <group_id from the organizers> --expect 10
    python backend/scripts/submit.py --file prod.json --group PROD --expect 10      # if the set comes as a file
    python backend/scripts/submit.py --group DEV --set dev --expect 65 --no-eval   # rebuild the file only

Then:  git add results && git commit -m "PROD results" && git push
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from check_results import check  # noqa: E402


class Api:
    def __init__(self, base):
        self.base = base.rstrip("/")

    def call(self, method, path, body=None, timeout=300):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=None if body is None else json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise SystemExit(f"{method} {path}: HTTP {e.code} {e.read().decode(errors='replace')[:500]}") from e


def records_from_file(path: Path) -> list[dict]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, dict):
        data = data.get("records") or (data.get("data") or {}).get("records") or [data]
    return data


def evaluate(api: Api, ids: list[str], label: str) -> dict:
    b = api.call("POST", "/api/evaluations/batch", {"conversation_ids": ids})
    t0, last = time.time(), None
    while True:
        s = api.call("GET", f"/api/batches/{b['batch_id']}")
        line = f"  {label}: готово {s['done']}/{s['total']}, ошибок {s['error']}, в работе {s['running'] + s['pending']}"
        if line != last:
            print(line, f"({time.time() - t0:.0f} с)", flush=True)
            last = line
        if s["finished"]:
            return s
        if time.time() - t0 > 20 * 60:
            raise SystemExit("оценка идёт дольше 20 минут — проверьте сервер (docker compose logs)")
        time.sleep(3)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--group", required=True, help="group_id набора (из API организаторов) или имя набора для --file")
    ap.add_argument("--file", help="JSON с записями набора, если его выдали файлом")
    ap.add_argument("--set", default="prod", choices=["dev", "prod"])
    ap.add_argument("--expect", type=int, help="сколько записей должно быть (prod: 10)")
    ap.add_argument("--api", default="http://localhost:8000")
    ap.add_argument("--no-eval", action="store_true", help="не оценивать, только собрать файл из готовых оценок")
    ap.add_argument("--out", help="куда записать (по умолчанию results/<set>/results.json)")
    a = ap.parse_args()
    api = Api(a.api)
    t_all = time.time()
    print("сервер:", api.call("GET", "/api/health"))

    # 1. the set
    if a.file:
        recs = records_from_file(Path(a.file))
        ids = api.call("POST", "/api/conversations", {"records": recs, "group": a.group})["conversation_ids"]
        print(f"1. набор из файла {a.file}: {len(ids)} диалогов → группа {a.group}")
    else:
        r = api.call("POST", "/api/datasets/import", {"group_id": a.group})
        ids = r["conversation_ids"]
        print(f"1. набор {a.group}: {len(ids)} диалогов, источник: {r.get('source')}")
        if r.get("source") != "api":
            print("   ! набор взят не из API организаторов — проверьте, что это нужный набор")
    if a.expect is not None and len(ids) != a.expect:
        print(f"   ! ожидалось {a.expect} диалогов, получено {len(ids)}")

    # 2. evaluate, then retry the failed ones once
    if not a.no_eval:
        s = evaluate(api, ids, "2. оценка")
        failed = [e["conversation_id"] for e in s["evaluations"] if e["status"] == "error"]
        if failed:
            print(f"   повтор для {len(failed)}: {failed}")
            evaluate(api, failed, "   повтор")

    # 3. the file
    q = f"/api/results?group={urllib.request.quote(a.group)}" + (f"&expect={a.expect}" if a.expect else "")
    doc = api.call("GET", q)
    doc.pop("problems", None)  # the server's own check; the strict one runs below
    dataset = {cid: api.call("GET", f"/api/conversations/{urllib.request.quote(cid)}") for cid in ids}
    errors, notes = check(doc, dataset, a.expect)
    out = Path(a.out) if a.out else ROOT / "results" / a.set / "results.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    ok = sum(r["status"] == "ok" for r in doc["results"])
    print(f"3. записано {out}: {len(doc['results'])} записей, ok {ok}, error {len(doc['results']) - ok}")
    for r in doc["results"]:
        sc = r.get("score") or {}
        print(f"   {r['conversation_id']:28} {r['status']:5} {sc.get('final_score')!s:>6}"
              f"{'  ГРУБАЯ ОШИБКА' if sc.get('critical_flag') else ''}{'  ' + r['error'] if r.get('error') else ''}")
    for n in notes:
        print("   ·", n)
    for e in errors:
        print("   ✗", e)
    print(f"всего {time.time() - t_all:.0f} с.", "Проверка пройдена. Дальше: git add results && git commit && git push"
          if not errors else "ЕСТЬ ОШИБКИ — исправьте до push")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
