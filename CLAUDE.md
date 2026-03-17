# CLAUDE.md — ReelBrain MCP Implementation Notes

This file describes the architecture and key decisions for any AI assistant helping maintain or extend this codebase.

## Project Purpose

ReelBrain is an MCP (Model Context Protocol) server that gives Claude Desktop access to a personal "second brain" built from Instagram reels. The user DMs reels to a bot account; the system transcribes, analyzes, and stores them; Claude can then query the memory semantically.

## Key Files

| File | Role |
|------|------|
| `server.py` | MCP server with 6 tools, SSE transport for Railway |
| `memory.py` | Dual-store: SQLite (structured) + ChromaDB (semantic) |
| `analyzer.py` | yt-dlp → faster-whisper → Gemini Flash pipeline |
| `watcher.py` | Instagram DM poller, runs as daemon thread |

## Critical MCP Rules (DO NOT VIOLATE)

1. **No `@mcp.prompt()` decorators** — breaks Claude Desktop
2. **No `prompt` parameter in `FastMCP()`** — breaks Claude Desktop
3. **No Optional/Union/List type hints** — use plain `str = ""`
4. **All docstrings must be single-line** — multi-line causes gateway panic
5. **All tools must return strings** — never return dicts/lists directly
6. **Use `.strip()` to check empty strings** — not just `if param:`

## Transport

The server uses **SSE (Server-Sent Events)** transport, not stdio. This is required for Railway deployment so Claude Desktop can connect over HTTPS. The Claude Desktop config entry uses `"url": "https://...railway.app/sse"` — note the `/sse` suffix.

## Memory Architecture

Two stores are used in parallel:

**SQLite** (`/data/reelbrain.db`)
- Source of truth for all structured reel data
- Used for: `get_recent`, `get_topics`, `get_all_insights`, `get_stats`
- Survives ChromaDB failures

**ChromaDB** (`/data/chroma/`)
- Semantic vector store for `search_memory`
- Embeds: summary + English transcript + topics + insights
- Falls back to SQLite keyword search if unavailable
- Score threshold: 0.3 (Chroma cosine similarity, 1=identical)

## Score Thresholds

- **ChromaDB similarity > 0.6** → Claude should say "from your reels..."
- **ChromaDB similarity 0.3–0.6** → marginal match, use carefully
- **< 0.3 or no results** → answer from own knowledge only

## Watcher Design

The watcher runs as a **daemon thread** inside the same process as the MCP server. This means:
- One Railway service handles everything
- Watcher auto-restarts if the server restarts
- DMs are polled every `POLL_INTERVAL_SECONDS` (default 600)

The watcher uses instaloader's private API to access DM inbox. Instagram may occasionally require re-authentication — the session is cached at `/data/instagram_session`.

## Adding a New Tool

1. Add the function to `server.py`
2. Decorate with `@mcp.tool()`
3. Keep docstring to ONE line
4. Default all params to `""` not `None`
5. Return a formatted string with emoji prefix (✅/❌/📊 etc.)
6. Add error handling with try/except
7. Update `system_prompt.txt` if the tool should be called automatically

## Environment Variables

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `GEMINI_API_KEY` | Yes | — | From aistudio.google.com |
| `INSTAGRAM_BOT_USERNAME` | Yes | — | Bot account username |
| `INSTAGRAM_BOT_PASSWORD` | Yes | — | Bot account password |
| `POLL_INTERVAL_SECONDS` | No | 600 | DM poll frequency |
| `WHISPER_MODEL` | No | small | tiny/base/small/medium |
| `PORT` | No | 8000 | Set by Railway automatically |
| `DB_PATH` | No | /data/reelbrain.db | SQLite path |
| `CHROMA_PATH` | No | /data/chroma | ChromaDB path |

## Dependency Notes

- `faster-whisper` requires `ffmpeg` — installed in Dockerfile via apt
- The Whisper `small` model is pre-downloaded during Docker build to avoid slow cold starts
- `chromadb >= 0.5.0` uses the new `PersistentClient` API (not the old `Client`)
- `instaloader >= 4.12.0` is required for Python 3.11 compatibility

## Railway Volume

The `/data` volume must be mounted for persistence. Without it:
- SQLite resets on every deploy (all reels lost)
- ChromaDB resets on every deploy
- Instagram session resets (requires re-login)

## Common Failure Modes

| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| Watcher not running | Missing Instagram credentials | Set env vars in Railway |
| Gemini 429 errors | Free tier rate limit hit | Add delay between reels; auto-retried |
| ChromaDB dimension error | Model changed between deploys | Delete `/data/chroma` and re-embed |
| `tools/list` returns empty | Multi-line docstring in a tool | Fix docstring to single line |
| Claude Desktop can't connect | Wrong URL format in config | Ensure URL ends with `/sse` |
