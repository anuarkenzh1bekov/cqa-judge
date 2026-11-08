"""Independent check of a results.json before push (rules from the appendix "Как сдать результаты", JSON 1.0).

Checks what the exporter's own validator does not: IDs against the dataset, turn numbers inside the transcript,
final_score recomputed from the values with the official weights, team name, model mode.

    python backend/scripts/check_results.py results/dev/results.json --dataset datasets/DEV.json
    python backend/scripts/check_results.py results/prod/results.json --dataset <prod records json> --expect 10
"""
import argparse
import json
import sys
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

TEAM = "Я не отвратимость"
# criterion_id -> (weight, allowed values, max for a scale; None = yes/no)
SPEC = {
    "contact": (10, {True, False}, None),
    "discovery": (15, {True, False, None}, None),
    "identification": (20, {True, False, None}, None),
    "consultation": (20, {0, 5, 10, 15, 20, None}, 20),
    "empathy": (15, {True, False}, None),
    "dialogue": (15, {0, 4, 7, 10}, 10),
    "closure": (5, {True, False, None}, None),
    "critical": (0, {True, False}, None),
}


def round2(x: float) -> float:
    return float(Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def expected_score(crit: dict) -> float | None:
    got = total = 0.0
    for cid, (w, _, mx) in SPEC.items():
        v = crit[cid]
        if w == 0 or v is None:
            continue
        total += w
        got += w * (v / mx if mx else (1.0 if v else 0.0))
    return None if total == 0 else round2(got / total * 100)


def load_records(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    recs = data["records"] if isinstance(data, dict) and "records" in data else \
        data.get("data", {}).get("records", data) if isinstance(data, dict) else data
    return {r["conversation_id"]: r for r in recs}


def check(doc: dict, dataset: dict | None, expect: int | None) -> tuple[list[str], list[str]]:
    errors, notes = [], []
    if doc.get("schema_version") != "1.0":
        errors.append(f"schema_version = {doc.get('schema_version')!r}, нужно \"1.0\"")
    if doc.get("team_name") != TEAM:
        errors.append(f"team_name = {doc.get('team_name')!r}, нужно {TEAM!r}")
    m = doc.get("model") or {}
    if m.get("mode") not in ("local", "external_api", "hybrid") or not m.get("name"):
        errors.append(f"model = {m!r}: нужен mode local/external_api/hybrid и name")
    res = doc.get("results")
    if not isinstance(res, list):
        return errors + ["results должен быть массивом"], notes
    if expect is not None and len(res) != expect:
        errors.append(f"записей {len(res)}, нужно {expect}")
    ids = [r.get("conversation_id") for r in res]
    if len(ids) != len(set(ids)):
        errors.append("есть повторяющиеся conversation_id")
    if dataset is not None:
        missing, extra = set(dataset) - set(ids), set(ids) - set(dataset)
        if missing:
            errors.append(f"нет записей для {len(missing)} ID набора: {sorted(missing)[:5]}")
        if extra:
            errors.append(f"ID не из набора: {sorted(extra)[:5]}")
    empty_ev = 0
    for r in res:
        cid = r.get("conversation_id")
        if r.get("status") == "error":
            if r.get("criteria") != [] or r.get("score") is not None or not r.get("error"):
                errors.append(f"{cid}: error-запись должна иметь criteria=[], score=null и error")
            notes.append(f"{cid}: status=error — {r.get('error')}")
            continue
        if r.get("status") != "ok":
            errors.append(f"{cid}: status {r.get('status')!r}")
            continue
        crit = {}
        for c in r.get("criteria", []):
            k = c.get("criterion_id")
            if k in crit:
                errors.append(f"{cid}: {k} дважды")
            crit[k] = c.get("value")
            if k not in SPEC:
                errors.append(f"{cid}: неизвестный критерий {k!r}")
                continue
            v = c.get("value")
            allowed = SPEC[k][1]
            if isinstance(v, bool) != (SPEC[k][2] is None and v is not None) and v is not None:
                errors.append(f"{cid}/{k}: тип значения {v!r}")
            elif v not in allowed or (isinstance(v, bool) and SPEC[k][2] is not None):
                errors.append(f"{cid}/{k}: недопустимое значение {v!r}")
            if not isinstance(c.get("rationale"), str) or not c["rationale"].strip():
                errors.append(f"{cid}/{k}: пустой rationale")
            turns = c.get("evidence_turns")
            if not isinstance(turns, list) or not all(isinstance(t, int) and not isinstance(t, bool) for t in turns):
                errors.append(f"{cid}/{k}: evidence_turns должен быть списком целых")
                continue
            if not turns:
                empty_ev += 1
            if dataset is not None and cid in dataset:
                n = len(dataset[cid]["transcript"])
                bad = [t for t in turns if not 1 <= t <= n]
                if bad:
                    errors.append(f"{cid}/{k}: реплики {bad} вне 1..{n}")
        if set(crit) != set(SPEC):
            errors.append(f"{cid}: нужны все 8 критериев, есть {sorted(crit)}")
            continue
        sc = r.get("score") or {}
        exp = expected_score(crit)
        if sc.get("final_score") != exp:
            errors.append(f"{cid}: final_score {sc.get('final_score')} ≠ пересчёт {exp}")
        if sc.get("critical_flag") is not crit["critical"]:
            errors.append(f"{cid}: critical_flag ≠ critical")
    if empty_ev:
        notes.append(f"критериев без evidence_turns: {empty_ev} (формат это допускает, но номера реплик желательны)")
    return errors, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file")
    ap.add_argument("--dataset", help="JSON with the set's records (to check IDs and turn numbers)")
    ap.add_argument("--expect", type=int)
    a = ap.parse_args()
    raw = Path(a.file).read_bytes()
    raw.decode("utf-8")  # must be UTF-8
    doc = json.loads(raw)
    dataset = load_records(Path(a.dataset)) if a.dataset else None
    errors, notes = check(doc, dataset, a.expect)
    ok = sum(r.get("status") == "ok" for r in doc.get("results", []))
    gross = sum(bool((r.get("score") or {}).get("critical_flag")) for r in doc.get("results", []))
    print(f"{a.file}: записей {len(doc.get('results', []))}, ok {ok}, грубых ошибок {gross}, "
          f"команда {doc.get('team_name')!r}, модель {doc.get('model')}")
    for n in notes:
        print("  ·", n)
    for e in errors[:40]:
        print("  ✗", e)
    print("OK — можно пушить" if not errors else f"ОШИБОК: {len(errors)}")
    sys.exit(1 if errors else 0)


if __name__ == "__main__":
    main()
