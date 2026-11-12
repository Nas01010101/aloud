# Aloud

Voice browser assistant for blind and low-vision people, built on Google ADK with Gemini on Vertex AI. A Guardian plugin checks every browser tool call against the user's spoken mandate before it reaches Chrome. The hackathon entry it grew from is https://github.com/Nas01010101/compass.

## Layout

| Path | Contents |
|---|---|
| `aloud/agent.py` | Orchestrator, reader and navigator agents, chrome-devtools-mcp wiring, model choice |
| `aloud/server.py` | FastAPI: serves `web/`, streams one turn per `POST /api/turn` as NDJSON |
| `aloud/quick.py` | Screen-reader commands answered from the accessibility snapshot, no model call |
| `aloud/guardian.py` | Guardian ADK plugin, runs before and after every tool call |
| `aloud/policy.py` | Mandate checks: recipient, amount, site, forbidden data, expiry |
| `aloud/mandate.py` | Sentence to mandate with Gemini structured output |
| `aloud/injection.py` | Model Armor screening and local injection patterns |
| `aloud/cloud.py` | Web Risk lookups and receipts (Firestore or `receipts.jsonl`) |
| `web/` | Voice console: push-to-talk, speech out, earcons, ARIA live log |
| `demo/bank.html` | Demo bank page with a planted instruction for AI assistants |
| `scripts/demo.sh` | Starts the demo page, a Chrome on :9222 and the console on :8000 |
| `scripts/a11y_check.py`, `scripts/record_gif.py` | axe-core audit; records `docs/demo.gif` |

## Rules

- Every Guardian check in `policy.py` and `guardian.py` has a test in `tests/`. A new or changed check ships with its test.
- Console changes keep `scripts/a11y_check.py` at 0 violations. Every control works by keyboard and is announced by a screen reader.
- Anything the console speaks is short and plain: no markdown, no URLs read character by character.
- Never commit `aloud/.env`, API keys or service account files. `aloud/.env.example` lists the variables.
- Work on a branch and open a PR. Commit messages are one lowercase past-tense line, for example "added expiry check to policy".

## Test

```bash
uv run pytest -q
uv run --group demo python scripts/a11y_check.py   # needs scripts/demo.sh running
```
