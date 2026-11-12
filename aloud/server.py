"""The voice console's backend: serves web/ and runs one turn per POST /api/turn.

A turn streams newline-delimited JSON so the console can speak progress while the agent works:
  {"type": "step",  "text": "Reading the page"}        what the agent is doing now
  {"type": "alert", "kind": "blocked"|"confirm"|"warning", "text": ...}   a Guardian verdict
  {"type": "say",   "text": ...}                       a reply to speak
  {"type": "error", "text": ...}                       the turn failed (model quota, tool crash)
  {"type": "done",  "quick": bool, "ms": int}
Screen-reader commands ("headings", "form", "where am I") are answered from the accessibility
snapshot without a model call; see quick.py.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types
from pydantic import BaseModel

from . import agent, quick
from .guardian import result_text

WEB = Path(__file__).resolve().parent.parent / "web"
STEPS = {
    "list_pages": None,
    "select_page": None,
    "transfer_to_agent": None,
    "take_snapshot": "Reading the page",
    "navigate_page": "Opening the page",
    "new_page": "Opening a new tab",
    "fill": "Typing",
    "fill_form": "Filling the form",
    "click": "Pressing",
    "press_key": "Pressing a key",
    "wait_for": "Waiting for the page",
    "set_mandate": "Setting your limits",
    "confirm_pending": "Noted your yes",
    "cancel_pending": "Cancelled",
}

WARNING = "Careful: this page has hidden text that tries to give me orders. I will not follow it."

runner = Runner(app=agent.app, session_service=InMemorySessionService(), auto_create_session=True)
api = FastAPI(title="Aloud")


class Turn(BaseModel):
    session: str
    text: str


def line(**event) -> str:
    return json.dumps(event) + "\n"


def guardian_alert(response: dict) -> dict | None:
    status = str(response.get("status", ""))
    if status == "blocked_by_guardian":
        return {"kind": "blocked", "text": response.get("say_to_user", "")}
    if status == "needs_confirmation":
        return {"kind": "confirm", "text": response.get("say_to_user", "")}
    text = result_text(response)
    if text.startswith("GUARDIAN WARNING"):
        # The raw warning is written for the model; the listener gets one plain sentence.
        return {"kind": "warning", "text": WARNING}
    return None


def failure_text(e: Exception) -> str:
    if "RESOURCE_EXHAUSTED" in str(e) or "429" in str(e):
        return "The model service is busy and I could not finish. Nothing more was done. Say it again to retry."
    return f"I could not finish: {type(e).__name__}. Nothing more was done."


async def snapshot() -> str:
    """One take_snapshot through the agent's own MCP session, so it sees the agent's tab."""
    tools = {t.name: t for t in await agent._browser.get_tools()}
    pages = result_text(await tools["list_pages"].run_async(args={}, tool_context=None))
    page = quick.selected_page(pages)
    if page is None:
        raise LookupError("no page open")
    result = await tools["take_snapshot"].run_async(args={"pageId": page}, tool_context=None)
    if isinstance(result, dict) and result.get("isError"):
        raise RuntimeError(result_text(result))
    return result_text(result)


async def run_turn(turn: Turn) -> AsyncIterator[str]:
    start = time.monotonic()
    cmd = quick.command(turn.text)
    if cmd:
        try:
            text = quick.answer(cmd, quick.parse(await snapshot()))
            yield line(type="say", text=text)
            yield line(type="done", quick=True, ms=int((time.monotonic() - start) * 1000))
            return
        except Exception as e:  # no browser yet, or the tool failed: let the agent try
            yield line(type="step", text=f"Quick read failed ({type(e).__name__}), asking the agent")
    message = types.Content(role="user", parts=[types.Part(text=turn.text)])
    last_step = None
    spoken = set()  # a Guardian question arrives as an alert and again as the agent's words
    try:
        async for event in runner.run_async(user_id="local", session_id=turn.session, new_message=message):
            for part in (event.content.parts if event.content else None) or []:
                if part.function_call:
                    step = STEPS.get(part.function_call.name, part.function_call.name)
                    if step and step != last_step:
                        yield line(type="step", text=step)
                        last_step = step
                elif part.function_response:
                    alert = guardian_alert(part.function_response.response or {})
                    if alert and alert["text"] not in spoken:
                        spoken.add(alert["text"])
                        yield line(type="alert", **alert)
                elif part.text and not part.thought and not event.partial and event.author != "user":
                    text = part.text.strip()
                    if text and not any(text in s or s in text for s in spoken):
                        spoken.add(text)
                        yield line(type="say", text=text)
    except Exception as e:  # a model or tool failure must still end in words, not a dead stream
        yield line(type="error", text=failure_text(e))
    yield line(type="done", quick=False, ms=int((time.monotonic() - start) * 1000))


@api.post("/api/turn")
async def turn(t: Turn) -> StreamingResponse:
    return StreamingResponse(run_turn(t), media_type="application/x-ndjson")


api.mount("/", StaticFiles(directory=WEB, html=True), name="web")


def main() -> None:
    import uvicorn

    uvicorn.run(api, host="127.0.0.1", port=int(os.getenv("PORT", "8000")))
