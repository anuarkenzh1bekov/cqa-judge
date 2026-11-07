"""Streaming: the tolerant parser, the live hub and the events the pipeline emits while Gemini is still writing."""
import asyncio
import json

from app import live, pipeline
from app.checklist import ChecklistIn, DEFAULT_CHECKLIST
from app.llm.partial import parse_partial

CRIT = ChecklistIn(**DEFAULT_CHECKLIST).criteria

FULL = ('{"facts":{"operator_name":"Алина","n":3},"criteria":{"c01":{"analysis":"читаем \\"текст\\" дальше",'
        '"answer":"yes","evidence":[1,2]},"c02":{"analysis":"ещё не до')


def test_every_prefix_is_readable_or_none():
    seen_text = []
    for cut in range(1, len(FULL) + 1):
        d = parse_partial(FULL[:cut])
        assert d is None or isinstance(d, dict)
        if d and "c01" in d.get("criteria", {}) and "analysis" in d["criteria"]["c01"]:
            seen_text.append(d["criteria"]["c01"]["analysis"])
    assert seen_text and seen_text[-1] == 'читаем "текст" дальше'
    assert any(len(a) < len(seen_text[-1]) for a in seen_text)  # the text really grows chunk by chunk


def test_unfinished_pieces_are_dropped():
    assert parse_partial("") is None
    assert parse_partial('{"a":1,"b') == {"a": 1}
    assert parse_partial('{"a":[1,2') == {"a": [1, 2]}
    assert parse_partial('{"a":"x\\') == {"a": "x\\"} or parse_partial('{"a":"x\\') == {"a": "x"}
    assert parse_partial('{"a":tru') in ({}, {"a": None}, None)
    assert parse_partial(json.dumps({"a": [1, {"b": "c"}]})) == {"a": [1, {"b": "c"}]}


def test_hub_replays_the_latest_snapshot_and_closes_on_done():
    async def run():
        live.start("h-1")
        live.publish("h-1", {"type": "partial", "n": 1})
        live.publish("h-1", {"type": "partial", "n": 2})
        q = live.subscribe("h-1")  # joins late: gets the latest snapshot, not the history
        assert (await q.get())["n"] == 2
        live.publish("h-1", {"type": "partial", "n": 3})
        assert (await q.get())["n"] == 3
        live.finish("h-1")
        assert (await q.get())["type"] == "done" and not live.is_active("h-1")
    asyncio.run(run())


def test_pipeline_streams_partial_snapshots(fake, conv):
    events = []
    out = asyncio.run(pipeline.evaluate(conv, CRIT, on_event=events.append))
    kinds = [e["type"] for e in events]
    assert "partial" in kinds
    last = [e for e in events if e["type"] == "partial"][-1]
    assert set(last["criteria"]) == {c.key for c in CRIT}
    assert last["criteria"]["c01_contact"]["answer"] in ("yes", "no", "na")
    assert out["score"]["total"] is not None  # the final result is the same as without streaming


def test_pipeline_falls_back_when_streaming_breaks(fake, conv, monkeypatch):
    from app.llm import gemini

    async def broken(*a, **k):
        raise RuntimeError("stream down")
    monkeypatch.setattr(gemini, "stream_json", broken)
    out = asyncio.run(pipeline.evaluate(conv, CRIT, on_event=lambda e: None))
    assert out["score"]["total"] is not None


def test_live_endpoint_streams_a_running_evaluation_and_says_idle_otherwise(monkeypatch):
    from fastapi.testclient import TestClient

    from app.main import app
    from app.routers import conversations
    monkeypatch.setattr(conversations, "LIVE_WAIT_TICKS", 0)
    with TestClient(app) as c:
        r = c.get("/api/conversations/nobody/live")
        assert r.headers["content-type"].startswith("text/event-stream") and '"idle"' in r.text
        live.start("sse-2")  # a running evaluation; its events are queued up front (a queue is not thread-safe to fill later)
        q = asyncio.Queue()
        q.put_nowait({"type": "partial", "request": "тариф", "criteria": {"c01": {"answer": "yes", "text": "ok", "done": True}}})
        q.put_nowait({"type": "done"})
        monkeypatch.setattr(live, "subscribe", lambda cid: q)
        with c.stream("GET", "/api/conversations/sse-2/live") as s:
            body = "".join(s.iter_text())
        live.finish("sse-2")
        assert '"partial"' in body and '"done"' in body and "тариф" in body
