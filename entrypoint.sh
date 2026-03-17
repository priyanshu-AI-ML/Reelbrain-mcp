#!/bin/bash
# ReelBrain entrypoint — starts MCP SSE server + DM watcher in parallel

set -e

echo "[entrypoint] Starting ReelBrain..."
echo "[entrypoint] DATA_DIR=$DATA_DIR"
echo "[entrypoint] PORT=${PORT:-8000}"

# Start the DM watcher in the background
echo "[entrypoint] Launching watcher.py in background..."
python watcher.py &
WATCHER_PID=$!
echo "[entrypoint] Watcher PID: $WATCHER_PID"

# Start the MCP server in the foreground (Railway needs a bound port)
echo "[entrypoint] Launching server.py on port ${PORT:-8000}..."
python server.py

# If server exits, kill watcher too
kill $WATCHER_PID 2>/dev/null || true
