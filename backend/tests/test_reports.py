"""Calibration from appeals, checklist version comparison, report export, confidence."""
import io

import pytest
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app import prompts
from app.checklist import DEFAULT_CHECKLIST
from app.main import app
from tests.conftest import CRIT, TRANSCRIPT


@pytest.fixture
def client(fake):
    with TestClient(app) as c:
        yield c


def upload(c, cid, group="TEST"):
    c.post("/api/conversations", json={"group": group, "records": [
        {"conversation_id": cid, "channel": "agent chat", "language": "RU", "transcript": TRANSCRIPT}]})


def publish(c, eid):
    c.put(f"/api/evaluations/{eid}/review", json={"published": True})


def appeal_and_change(c, eid, key, new, reason):
    publish(c, eid)
    ap = c.post(f"/api/evaluations/{eid}/appeals", json={"criterion_key": key, "comment": "не согласен"}).json()
    return c.post(f"/api/appeals/{ap['id']}/decision",
                  json={"decision": "change", "new_answer": new, "reason": reason, "reviewer": "QA"}).json()


def test_prompt_contains_corrections():
    conv = {"id": "x", "channel": "agent chat", "language": "RU", "transcript": TRANSCRIPT}
    ex = {"c07_closing": ["ИИ ответил «Нет», проверяющий исправил на «Да». Причина: попрощался."]}
    assert "ПОПРАВКИ ПРОВЕРЯЮЩИХ" in prompts.build_eval_prompt(CRIT, conv, True, ex)
    assert "ПОПРАВКИ ПРОВЕРЯЮЩИХ" not in prompts.build_eval_prompt(CRIT, conv, True, None)


def test_changed_appeal_becomes_example_for_next_evaluation(client, fake, monkeypatch):
    seen = []
    orig = fake.generate_json

    async def spy(prompt, schema, **kw):
        seen.append(prompt)
        return await orig(prompt, schema, **kw)

    from app.llm import gemini
    monkeypatch.setattr(gemini, "generate_json", spy)
    upload(client, "cal-1")
    upload(client, "cal-2")
    fake.gemini_answers["c07_closing"] = fake.jev_answers["c07_closing"] = "no"
    ev1 = client.post("/api/evaluations", json={"conversation_id": "cal-1"}).json()
    appeal_and_change(client, ev1["id"], "c07_closing", "yes", "Оператор попрощался в последней реплике")

    seen.clear()
    ev2 = client.post("/api/evaluations", json={"conversation_id": "cal-2"}).json()
    assert any("Оператор попрощался в последней реплике" in p for p in seen)
    assert ev2["status"] == "done"
    # the conversation's own correction is not fed back into its re-evaluation
    seen.clear()
    client.post("/api/evaluations", json={"conversation_id": "cal-1"})
    assert not any("Оператор попрощался в последней реплике" in p for p in seen)

    cal = client.get("/api/calibration").json()
    # the test DB is shared with other tests, so only lower bounds are checked
    assert cal["overall"]["changed"] >= 1 and cal["overall"]["decided"] >= cal["overall"]["changed"]
    assert cal["learning"]["examples_available"] >= 1 and cal["learning"]["evaluations_using_examples"] >= 1
    row = next(r for r in cal["by_criterion"] if r["key"] == "c07_closing")
    assert row["decided"] >= 1 and row["changed"] >= 1 and row["agreement_pct"] < 100 and cal["trend"][0]["n"] == 1


def test_confidence_flags_disagreement(client, fake):
    upload(client, "conf-1", "CONF")
    ok = client.post("/api/evaluations", json={"conversation_id": "conf-1"}).json()
    assert ok["confidence"] == {"level": "high", "flagged": 0, "total": 7}
    fake.jev_answers["c05_empathy"] = "no"
    fake.jev_prob = 0.3  # low-confidence disagreement -> "needs review"
    bad = client.post("/api/evaluations", json={"conversation_id": "conf-1"}).json()
    assert bad["confidence"]["level"] == "medium" and bad["confidence"]["flagged"] >= 1
    ov = client.get("/api/stats?group=CONF").json()["overview"]
    assert ov["needs_human_conversations"] == 1 and ov["confident_conversations"] == 0


def test_checklist_compare(client, fake):
    upload(client, "cmp-1")
    upload(client, "cmp-2")
    a = client.get("/api/checklists/active").json()
    for cid in ("cmp-1", "cmp-2"):
        client.post("/api/evaluations", json={"conversation_id": cid, "checklist_id": a["id"]})
    body = {**DEFAULT_CHECKLIST, "name": "v2"}
    body["criteria"] = [{**c, "weight": 5} if c["key"] == "c05_empathy" else c for c in DEFAULT_CHECKLIST["criteria"]]
    b = client.post("/api/checklists", json=body).json()

    pre = client.get(f"/api/checklist-compare?a={a['id']}&b={b['id']}").json()
    assert pre["rows"] == [] and set(pre["missing_b"]) >= {"cmp-1", "cmp-2"}

    fake.gemini_answers["c05_empathy"] = fake.jev_answers["c05_empathy"] = "no"
    client.post("/api/evaluations", json={"conversation_id": "cmp-1", "checklist_id": b["id"]})
    res = client.get(f"/api/checklist-compare?a={a['id']}&b={b['id']}").json()
    assert res["summary"]["compared"] == 1 and res["rows"][0]["conversation_id"] == "cmp-1"
    assert res["rows"][0]["delta"] < 0 and res["rows"][0]["changed"][0]["key"] == "c05_empathy"
    assert res["answer_flips"][0]["count"] == 1 and "cmp-2" in res["missing_b"]
    diff = {d["key"]: d for d in res["criteria_diff"]}
    assert diff["c05_empathy"]["kind"] == "changed" and "weight" in diff["c05_empathy"]["fields"]
    assert client.get("/api/checklist-compare?a=999&b=1").status_code == 404


def test_export_xlsx_and_csv(client, fake):
    upload(client, "exp-1", "EXP")
    ev = client.post("/api/evaluations", json={"conversation_id": "exp-1"}).json()
    r = client.get("/api/export?format=xlsx&group=EXP")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    wb = load_workbook(io.BytesIO(r.content))
    assert wb.sheetnames == ["Сводка", "Диалоги", "Критерии", "Операторы"]
    dialogs = list(wb["Диалоги"].iter_rows(values_only=True))
    assert len(dialogs) == 2 and dialogs[1][0] == "exp-1" and dialogs[1][5] == ev["final_total"]
    c = client.get("/api/export?format=csv&group=EXP")
    assert c.content.startswith(b"\xef\xbb\xbf") and "exp-1" in c.content.decode("utf-8")
    assert client.get("/api/export?format=pdf").status_code == 422
