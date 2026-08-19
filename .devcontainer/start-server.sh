#!/usr/bin/env bash
# Starts the Dextor dashboard automatically whenever this Codespace (re)starts,
# so opening the Codespace is enough - no need to type `uvicorn` yourself. Bound
# to 0.0.0.0 (not the default 127.0.0.1) so Codespaces' port-forwarding proxy
# can actually reach it. api.py's own startup hook handles the once-a-day
# auto-fetch, so by the time the dashboard tab loads, today's listings are
# already being pulled in the background.
set -e
cd "$(dirname "$0")/.."

if pgrep -f "uvicorn api:app" > /dev/null; then
  echo "Dextor server already running, skipping."
  exit 0
fi

nohup uvicorn api:app --host 0.0.0.0 --port 8000 --reload > /tmp/dextor-server.log 2>&1 &
disown
echo "Started Dextor server (pid $!). Logs: /tmp/dextor-server.log"
