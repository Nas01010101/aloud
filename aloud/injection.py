"""Prompt-injection screening for page text the agent reads.

Model Armor (sanitizeUserPrompt, pi_and_jailbreak filter) is the primary check. The regexes
from extension/heuristics.js run when Model Armor is not configured or unreachable, so the
demo still flags the planted instruction offline.
"""

from __future__ import annotations

import os
import re

import httpx

AGENT_PHRASES = [
    re.compile(r"ignore (all |any )?(previous|prior|above) (instructions|prompts)", re.I),
    re.compile(r"\b(ai|llm|agent|assistant|gemini|model)\b[^.]{0,40}\b(must|should|now|instead)\b", re.I),
    re.compile(r"\b(send|transfer|pay|forward|email)\b[^.]{0,60}\b(to|vers|à)\b[^.]{0,40}(@|iban|account|wallet)", re.I),
    re.compile(r"system prompt|new instructions|you are now|disregard", re.I),
    re.compile(r"ignore(z)? (les|toutes les) instructions", re.I),
]


def heuristic_hits(text: str) -> list[str]:
    hits = []
    for line in text.splitlines():
        if len(line.strip()) >= 15 and any(p.search(line) for p in AGENT_PHRASES):
            hits.append(line.strip()[:300])
    return hits[:20]


_creds = None


def _token() -> str | None:
    # A token refresh can take seconds; every snapshot is screened, so refresh only on expiry.
    global _creds
    try:
        import google.auth
        import google.auth.transport.requests

        if _creds is None:
            _creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        if not _creds.valid:
            _creds.refresh(google.auth.transport.requests.Request())
        return _creds.token
    except Exception:
        return None


def model_armor(text: str) -> dict | None:
    """Returns {"match": bool, "filters": [...]} or None when Model Armor is not set up."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    template = os.getenv("MODEL_ARMOR_TEMPLATE")
    loc = os.getenv("MODEL_ARMOR_LOCATION", "us-central1")
    token = _token() if project and template else None
    if not token:
        return None
    url = (
        f"https://modelarmor.{loc}.rep.googleapis.com/v1/projects/{project}"
        f"/locations/{loc}/templates/{template}:sanitizeUserPrompt"
    )
    try:
        r = httpx.post(
            url,
            json={"userPromptData": {"text": text[:20000]}},
            headers={"Authorization": f"Bearer {token}"},
            timeout=8,
        )
        r.raise_for_status()
    except httpx.HTTPError:
        return None
    res = r.json().get("sanitizationResult", {})
    hit = [
        name
        for name, f in (res.get("filterResults") or {}).items()
        if re.search(r"'matchState': 'MATCH_FOUND'", str(f))
    ]
    return {"match": res.get("filterMatchState") == "MATCH_FOUND", "filters": hit}


def screen(text: str) -> dict:
    """Returns {"flagged": bool, "source": "model_armor"|"heuristic", "detail": [...]}."""
    hits = heuristic_hits(text)
    ma = model_armor(text)
    if ma is not None:
        return {"flagged": ma["match"] or bool(hits), "source": "model_armor", "detail": ma["filters"] + hits}
    return {"flagged": bool(hits), "source": "heuristic", "detail": hits}
