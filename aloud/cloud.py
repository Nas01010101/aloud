"""Google Cloud calls the Guardian makes: Web Risk lookups and Firestore receipts.

Each degrades to a local fallback (no lookup, a JSONL file) when credentials are absent, so
tests and the offline demo run without a project.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

from .injection import _token

THREATS = ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE"]
# Test hook: hosts listed here count as Web Risk hits (the real list cannot be seeded).
LOCAL_UNSAFE = {h for h in os.getenv("ALOUD_UNSAFE_HOSTS", "").split(",") if h}


def web_risk(url: str) -> list[str]:
    """Returns the threat types Web Risk reports for url; [] when clean or not configured."""
    from .policy import host

    if host(url) in LOCAL_UNSAFE:
        return ["SOCIAL_ENGINEERING"]
    key = os.getenv("WEB_RISK_API_KEY")
    params = [("uri", url)] + [("threatTypes", t) for t in THREATS]
    headers = {}
    if key:
        params.append(("key", key))
    else:
        token = _token()
        if not token:
            return []
        headers = {"Authorization": f"Bearer {token}"}
        if os.getenv("GOOGLE_CLOUD_PROJECT"):
            headers["x-goog-user-project"] = os.environ["GOOGLE_CLOUD_PROJECT"]
    try:
        r = httpx.get("https://webrisk.googleapis.com/v1/uris:search", params=params, headers=headers, timeout=5)
        r.raise_for_status()
    except httpx.HTTPError:
        return []
    return r.json().get("threat", {}).get("threatTypes", [])


def write_receipt(receipt: dict) -> str:
    """Stores a receipt in Firestore (collection "receipts"), else appends to a local JSONL."""
    receipt = {**receipt, "ts": time.time()}
    if os.getenv("GOOGLE_CLOUD_PROJECT") and os.getenv("ALOUD_FIRESTORE", "1") == "1":
        try:
            from google.cloud import firestore

            ref = firestore.Client().collection("receipts").document()
            ref.set(receipt)
            return f"firestore:receipts/{ref.id}"
        except Exception:
            pass
    path = Path(os.getenv("ALOUD_RECEIPTS", "receipts.jsonl"))
    with path.open("a") as f:
        f.write(json.dumps(receipt, ensure_ascii=False) + "\n")
    return f"file:{path}"
