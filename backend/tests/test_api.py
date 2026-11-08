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


def test_operator_can_withdraw_only_an_open_appeal(client, fake):
    upload(client, "api-del")
    ev = client.post("/api/evaluations", json={"conversation_id": "api-del"}).json()
    client.put(f"/api/evaluations/{ev['id']}/review", json={"published": True})
    ap = client.post(f"/api/evaluations/{ev['id']}/appeals",
                     json={"criterion_key": "c05_empathy", "comment": "неверно"}).json()
    assert client.delete(f"/api/appeals/{ap['id']}").json() == {"deleted": ap["id"]}
    assert client.delete(f"/api/appeals/{ap['id']}").status_code == 404
    ap2 = client.post(f"/api/evaluations/{ev['id']}/appeals",
                      json={"criterion_key": "c05_empathy", "comment": "ещё раз"}).json()  # can appeal again
    client.post(f"/api/appeals/{ap2['id']}/decision", json={"decision": "confirm", "reason": "ок"})
    assert client.delete(f"/api/appeals/{ap2['id']}").status_code == 409  # decided: kept for the audit trail


def test_index_links_carry_a_version_so_browsers_never_run_stale_scripts(client):
    html = client.get("/").text
    assert 'src="js/app.js?v=' in html and 'href="css/styles.css?v=' in html


def test_checklist_versions_and_ai_draft(client, fake):
    lst = client.get("/api/checklists").json()
    pdf = next(c for c in lst if c["is_active"])
    assert pdf["submission_ready"] and "evaluations" in pdf
    d = client.post("/api/checklists/generate", json={"brief": "чек-лист для звонков отдела продаж"}).json()["checklist"]
    keys = [c["key"] for c in d["criteria"]]
    assert d["name"] == "Звонки продаж" and len(keys) == len(set(keys)) == 5
    assert sum(c["weight"] for c in d["criteria"]) == 100 and d["criteria"][-1]["type"] == "flag"
    assert [s["value"] for s in d["criteria"][2]["scale"]] == [10, 5, 0]
    saved = client.post("/api/checklists?activate=true", json=d).json()  # the draft is a valid checklist
    active = client.get("/api/checklists/active").json()
    assert active["id"] == saved["id"] and not active["submission_ready"]
    assert client.post(f"/api/checklists/{pdf['id']}/activate").status_code == 200
    assert client.get("/api/checklists/active").json()["submission_ready"]
    assert client.post("/api/checklists/generate", json={"brief": "x"}).status_code == 422


def test_results_use_latest_finished_evaluation(client, fake):
    """A re-run still running (UI warm-up during the submission hour) must not turn a scored dialog into an error."""
    from app import results_export
    from app.db import SessionLocal
    from app.models import Evaluation
    r = client.post("/api/conversations", json={"group": "LATE", "records": [
        {"conversation_id": "late-1", "channel": "agent chat", "language": "RU", "transcript": TRANSCRIPT}]})
    assert r.status_code == 200
    ev = client.post("/api/evaluations", json={"conversation_id": "late-1"}).json()
    with SessionLocal() as db:
        db.add(Evaluation(conversation_id="late-1", checklist_id=ev["checklist_id"], status="running",
                          checklist_snapshot=ev["checklist"]))
        db.commit()
        doc = results_export.build(db, "LATE")
    assert doc["results"][0]["status"] == "ok" and doc["results"][0]["score"]["final_score"] == 100.0
