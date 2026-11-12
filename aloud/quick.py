"""Instant screen-reader commands answered from the accessibility snapshot, with no model call.

"headings", "links", "buttons", "form", "where am I" and "landmarks" are what a screen reader
user asks most, and waiting several seconds for a model to list three headings is the slowest
part of a voice agent. These answers come straight from the tree chrome-devtools-mcp returns.
Anything else goes to the agent.
"""

from __future__ import annotations

import re

LINE = re.compile(r'^(\s*)uid=\S+\s+(\w+)(?:\s+"((?:[^"\\]|\\.)*)")?(.*)$')
ATTR = re.compile(r'(\w+)="((?:[^"\\]|\\.)*)"')
FIELDS = {"textbox", "searchbox", "spinbutton", "combobox", "checkbox", "radio", "slider", "switch", "listbox"}
LANDMARKS = {"banner", "navigation", "main", "complementary", "contentinfo", "search", "form", "region"}

# Spoken phrases, English and French, mapped to a command. Order matters: first match wins.
COMMANDS = [
    ("headings", re.compile(r"\b(headings?|titres?|sections?)\b", re.I)),
    ("links", re.compile(r"\b(links?|liens?)\b", re.I)),
    ("buttons", re.compile(r"\b(buttons?|boutons?)\b", re.I)),
    ("form", re.compile(r"\b(forms?|fields?|formulaire|champs?)\b", re.I)),
    ("landmarks", re.compile(r"\b(landmarks?|regions?|r[ée]gions?)\b", re.I)),
    ("where", re.compile(r"\b(where am i|what page|o[uù] suis[- ]je|quelle page)\b", re.I)),
]
# A command word inside a task ("fill the form with...", "click the pay button") is a task.
ACTION = re.compile(r"\b(fill|type|enter|click|press|pay|buy|send|open|go to|submit|remplis|clique|paye|ach[eè]te|envoie|ouvre)\b", re.I)


def parse(text: str) -> list[dict]:
    """Snapshot lines -> [{role, name, depth, attrs}], in reading order."""
    nodes = []
    for raw in text.splitlines():
        m = LINE.match(raw)
        if not m:
            continue
        indent, role, name, rest = m.groups()
        nodes.append({"role": role, "name": (name or "").strip(), "depth": len(indent) // 2,
                      "attrs": dict(ATTR.findall(rest)),
                      "readonly": bool(re.search(r"\breadonly\b", ATTR.sub("", rest)))})
    return nodes


def selected_page(list_pages: str) -> int | None:
    """The page id list_pages marks [selected], else the first one listed."""
    ids = re.findall(r"^(\d+): .*?(\[selected\])?$", list_pages, re.M)
    chosen = next((i for i, sel in ids if sel), ids[0][0] if ids else None)
    return int(chosen) if chosen is not None else None


def command(text: str) -> str | None:
    """Returns the quick command a sentence asks for, or None when it is a task for the agent."""
    if ACTION.search(text) or len(text.split()) > 8:
        return None
    for name, pattern in COMMANDS:
        if pattern.search(text):
            return name
    return None


def _count(n: int, one: str, many: str) -> str:
    return f"{n} {one if n == 1 else many}"


def _list(items: list[str]) -> str:
    return ". ".join(items) + "." if items else ""


def answer(cmd: str, nodes: list[dict]) -> str:
    """The spoken answer for a quick command, in the style of a screen reader."""
    title = next((n["name"] for n in nodes if n["role"] == "RootWebArea"), "")
    if cmd == "where":
        url = next((n["attrs"].get("url", "") for n in nodes if n["role"] == "RootWebArea"), "")
        h1 = next((n["name"] for n in nodes if n["role"] == "heading" and n["attrs"].get("level") == "1"), "")
        parts = [f"You are on {title or 'an untitled page'}."]
        if h1 and h1 != title:
            parts.append(f"Main heading: {h1}.")
        if url:
            parts.append(f"Address: {re.sub(r'^https?://', '', url)}.")
        return " ".join(parts)
    if cmd == "headings":
        hs = [n for n in nodes if n["role"] == "heading"]
        items = [f"level {h['attrs'].get('level', '?')}, {h['name']}" for h in hs]
        return f"{_count(len(hs), 'heading', 'headings')}. {_list(items)}".strip()
    if cmd == "links":
        ls = [n["name"] for n in nodes if n["role"] == "link" and n["name"]]
        return f"{_count(len(ls), 'link', 'links')}. {_list(ls)}".strip()
    if cmd == "buttons":
        bs = [n["name"] for n in nodes if n["role"] == "button" and n["name"]]
        return f"{_count(len(bs), 'button', 'buttons')}. {_list(bs)}".strip()
    if cmd == "form":
        fs = [n for n in nodes if n["role"] in FIELDS]
        items = []
        for f in fs:
            label = f["name"] or "unlabelled field"
            value = f["attrs"].get("value")
            state = ", read only" if f["readonly"] else ""
            items.append(f"{label}, {f['role']}{state}" + (f", contains {value}" if value else ", empty"))
        if not items:
            return "No form fields on this page."
        return f"{_count(len(fs), 'field', 'fields')}. {_list(items)}"
    if cmd == "landmarks":
        ls = [f"{n['role']}{' ' + n['name'] if n['name'] else ''}" for n in nodes if n["role"] in LANDMARKS]
        return f"{_count(len(ls), 'landmark', 'landmarks')}. {_list(ls)}".strip()
    raise ValueError(cmd)
