"""A failed model call still ends the turn with spoken words and a done event."""

import asyncio
import json

from aloud import server


class FailingRunner:
    async def run_async(self, **_):
        raise RuntimeError("429 RESOURCE_EXHAUSTED. {'error': {'code': 429}}")
        yield  # pragma: no cover  (makes this an async generator)


def events(text, monkeypatch):
    monkeypatch.setattr(server, "runner", FailingRunner())

    async def collect():
        return [json.loads(x) async for x in server.run_turn(server.Turn(session="s", text=text))]

    return asyncio.run(collect())


def test_quota_error_is_spoken_then_done(monkeypatch):
    out = events("pay my rent to jane@rent.example", monkeypatch)
    assert [e["type"] for e in out] == ["error", "done"]
    assert "busy" in out[0]["text"]


def test_other_failure_names_the_error():
    assert "ValueError" in server.failure_text(ValueError("x"))
