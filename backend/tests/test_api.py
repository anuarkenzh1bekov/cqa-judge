"""End-to-end API flow with fake models: upload -> evaluate -> appeal -> decision -> stats; checklist edits."""
import pytest
from fastapi.testclient import TestClient

from app.checklist import DEFAULT_CHECKLIST
from app.main import app
from tests.conftest import TRANSCRIPT


@pytest.fixture
def client(fake):
    with TestClient(app) as c:
        yield c


def upload(c, cid):
    r = c.post("/api/conversations", json={"group": "TEST", "records": [
        {"conversation_id": cid, "channel": "agent chat", "language": "RU", "transcript": TRANSCRIPT}]})
    assert r.status_code == 200


def test_full_flow(client, fake):
    upload(client, "api-1")
    fake.gemini_answers["c07_closing"] = "no"
    fake.jev_answers["c07_closing"] = "no"
    ev = client.post("/api/evaluations", json={"conversation_id": "api-1"}).json()
    assert ev["status"] == "done" and ev["initial_total"] == ev["final_total"] < 100
    assert ev["conversation"]["transcript"][3]["index"] == 3

    # appeals open only after the reviewer publishes the evaluation
    assert client.post(f"/api/evaluations/{ev['id']}/appeals",
                       json={"criterion_key": "c07_closing", "comment": "x"}).status_code == 409
    client.put(f"/api/evaluations/{ev['id']}/review", json={"published": True})

    # appeal + duplicate guard
    ap = client.post(f"/api/evaluations/{ev['id']}/appeals",
                     json={"criterion_key": "c07_closing", "comment": "попрощался и предложил помощь"}).json()
    assert ap["status"] == "open" and ap["original_answer"] == "no" and ap["fragment"]
    assert client.post(f"/api/evaluations/{ev['id']}/appeals",
                       json={"criterion_key": "c07_closing", "comment": "x"}).status_code == 409

    # AI review is advisory
    rv = client.post(f"/api/appeals/{ap['id']}/ai-review").json()
    assert rv["ai_review"]["appeal_justified"] is True

    # invalid answer rejected, valid change recalculates
    assert client.post(f"/api/appeals/{ap['id']}/decision",
                       json={"decision": "change", "new_answer": "15", "reason": "x"}).status_code == 422
    d = client.post(f"/api/appeals/{ap['id']}/decision",
                    json={"decision": "change", "new_answer": "yes", "reason": "ok", "reviewer": "QA"}).json()
    assert d["final_total"] == 100.0 and d["initial_total"] < 100
    card = client.get(f"/api/evaluations/{ev['id']}").json()
    c7 = next(r for r in card["results"] if r["key"] == "c07_closing")
    assert c7["answer"] == "no" and c7["final_answer"] == "yes"

    stats = client.get("/api/stats").json()
    assert stats["overview"]["evaluated_conversations"] >= 1 and stats["appeals"]["changed"] >= 1
    hm = stats["heatmap"]
    assert hm["criteria"] and hm["operators"]
    assert set(hm["operators"][0]["cells"]) == {c["key"] for c in hm["criteria"]}
    assert client.get(f"/api/evaluations/{ev['id']}/export").json()["cqa_totalscore"] == 100.0


def test_checklist_replace_criterion_and_apply(client, fake):
    upload(client, "api-2")
    body = {**DEFAULT_CHECKLIST, "name": "v2"}
    body["criteria"] = [c for c in DEFAULT_CHECKLIST["criteria"] if c["key"] != "c05_empathy"] + [
        {"key": "c09_name", "name": "Обращение по имени", "type": "binary", "weight": 15,
         "description": "Да — назвал клиента по имени", "na_allowed": True, "na_condition": "имя неизвестно"}]
    fake.gemini_answers["c09_name"] = fake.jev_answers["c09_name"] = "na"
    cl = client.post("/api/checklists?activate=true", json=body).json()
    assert client.get("/api/checklists/active").json()["id"] == cl["id"]
    ev = client.post("/api/evaluations", json={"conversation_id": "api-2"}).json()
    keys = [r["key"] for r in ev["results"]]
    assert "c09_name" in keys and "c05_empathy" not in keys
    assert "Обращение по имени" in client.get(f"/api/checklists/{cl['id']}/prompt-preview").json()["prompt"]
    # restore default as active for other tests
    client.post("/api/checklists/1/activate")


def test_checklist_validation(client):
    bad = {"name": "bad", "criteria": [
        {"key": "a", "name": "A", "type": "flag", "weight": 5, "description": "d"}]}
    assert client.post("/api/checklists", json=bad).status_code == 422
    dup = {"name": "dup", "criteria": [DEFAULT_CHECKLIST["criteria"][0]] * 2}
    assert client.post("/api/checklists", json=dup).status_code == 422


def test_batch(client, fake):
    upload(client, "api-3")
    b = client.post("/api/evaluations/batch", json={"conversation_ids": ["api-3"]}).json()
    assert b["total"] == 1
    assert client.post("/api/evaluations/batch", json={"conversation_ids": ["nope"]}).status_code == 404


def test_frontend_served(client):
    r = client.get("/")
    assert r.status_code == 200 and "CQA" in r.text


def test_excel_export(client, fake):
    from io import BytesIO

    from openpyxl import load_workbook
    upload(client, "xls-1")
    ev = client.post("/api/evaluations", json={"conversation_id": "xls-1"}).json()
    client.put(f"/api/evaluations/{ev['id']}/review", json={"published": True})  # appeals open after publishing
    client.post(f"/api/evaluations/{ev['id']}/appeals", json={"criterion_key": "c07_closing", "comment": "c"})
    r = client.get("/api/export/stats.xlsx")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    wb = load_workbook(BytesIO(r.content))
    assert wb.sheetnames == ["Сводка", "Графики", "Диалоги", "Обоснования", "Критерии", "Операторы", "Грубые ошибки", "Апелляции"]
    rows = list(wb["Диалоги"].values)
    row = next(x for x in rows if x[0] == "xls-1")
    assert row[5] == 100.0 and "Завершение" in rows[0]
    assert any(x[0] == "xls-1" for x in wb["Апелляции"].values)
    assert sum(1 for x in wb["Обоснования"].values if x[0] == "xls-1") == 8
    assert len(wb["Графики"]._charts) >= 4


def test_transcribe_recording_then_evaluate(client, fake):
    r = client.post("/api/conversations/transcribe", files={"file": ("call.mp3", b"ID3fake-mp3-bytes", "audio/mpeg")},
                    data={"conversation_id": "rec 1"})
    assert r.status_code == 200, r.text
    t = r.json()
    assert t["conversation_id"] == "rec-1" and t["language"] == "RU"
    assert [x["timestamp"] for x in t["transcript"]] == ["00:00", "00:03", "00:09", "01:02"]
    assert t["transcript"][2]["text"] == "Где посмотреть тариф?"
    conv = client.get("/api/conversations/rec-1").json()
    assert conv["channel"] == "voice call" and conv["has_audio"]
    a = client.get("/api/conversations/rec-1/audio", headers={"Range": "bytes=0-2"})
    assert a.status_code == 206 and a.content == b"ID3"
    ev = client.post("/api/evaluations", json={"conversation_id": "rec-1"}).json()
    assert ev["status"] == "done"
    assert client.post("/api/conversations/transcribe", files={"file": ("x.txt", b"hi", "text/plain")}).status_code == 415
    assert client.post("/api/conversations/transcribe", files={"file": ("x.mp3", b"", "audio/mpeg")}).status_code == 422


def test_audio_path_cannot_escape_audio_dir(client):
    from app import audio
    import pytest
    with pytest.raises(audio.AudioError):
        audio.local_path("local:../../test.db")
