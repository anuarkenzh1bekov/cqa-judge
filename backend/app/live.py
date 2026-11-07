"""Live progress of running evaluations, keyed by conversation id (in memory, one process).

The pipeline publishes snapshots while Gemini is still writing; the SSE endpoint fans them out to every open card.
A subscriber that joins late gets the latest snapshot, not the whole history.
"""
import asyncio

_subs: dict[str, set[asyncio.Queue]] = {}
_last: dict[str, dict] = {}
_active: set[str] = set()


def is_active(cid: str) -> bool:
    return cid in _active


def publish(cid: str, event: dict) -> None:
    if event.get("type") == "partial":
        _last[cid] = event
    for q in list(_subs.get(cid, ())):
        q.put_nowait(event)


def start(cid: str) -> None:
    _active.add(cid)
    _last.pop(cid, None)
    publish(cid, {"type": "start"})


def finish(cid: str) -> None:
    _active.discard(cid)
    _last.pop(cid, None)
    publish(cid, {"type": "done"})


def subscribe(cid: str) -> asyncio.Queue:
    q: asyncio.Queue = asyncio.Queue()
    _subs.setdefault(cid, set()).add(q)
    if cid in _last:
        q.put_nowait(_last[cid])
    return q


def unsubscribe(cid: str, q: asyncio.Queue) -> None:
    _subs.get(cid, set()).discard(q)
    if not _subs.get(cid):
        _subs.pop(cid, None)
