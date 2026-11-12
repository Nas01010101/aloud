#!/usr/bin/env bash
# Starts the local demo: the demo pages, a Chrome the agent drives, and the voice console.
#   scripts/demo.sh            then open http://127.0.0.1:8000 in another browser window
# The agent's Chrome uses its own profile in $ALOUD_PROFILE, so your everyday browser is untouched.
set -euo pipefail
cd "$(dirname "$0")/.."

DEMO_PORT=${DEMO_PORT:-8770}
CDP_PORT=${CDP_PORT:-9222}
PORT=${PORT:-8000}
PROFILE=${ALOUD_PROFILE:-${TMPDIR:-/tmp}/aloud-chrome}
CHROME=${CHROME_PATH:-"/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"}
[ -x "$CHROME" ] || CHROME=$(command -v google-chrome || command -v chromium || true)
[ -n "$CHROME" ] || { echo "Chrome not found; set CHROME_PATH" >&2; exit 1; }

pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

python3 -m http.server "$DEMO_PORT" --bind 127.0.0.1 --directory demo >/dev/null 2>&1 &
pids+=($!)

"$CHROME" --remote-debugging-port="$CDP_PORT" --user-data-dir="$PROFILE" \
  --no-first-run --no-default-browser-check --window-size=900,900 \
  "http://127.0.0.1:$DEMO_PORT/bank.html" >/dev/null 2>&1 &
pids+=($!)

for _ in $(seq 1 50); do
  curl -sf "http://127.0.0.1:$CDP_PORT/json/version" >/dev/null && break
  sleep 0.2
done

echo "Demo pages:  http://127.0.0.1:$DEMO_PORT/bank.html  and  /shop.html"
echo "Console:     http://127.0.0.1:$PORT"
ALOUD_BROWSER_URL="http://127.0.0.1:$CDP_PORT" PORT="$PORT" uv run python -m aloud
