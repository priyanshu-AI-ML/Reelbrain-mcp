# 🧠 ReelBrain MCP

Turn Instagram reels into a permanent, searchable second brain — powered by Whisper, Gemini Flash, and ChromaDB.

DM any reel to your bot account → it gets transcribed + analyzed → Claude remembers it forever.

---

## How It Works

```
You DM a reel → bot polls every 10 min → yt-dlp downloads it
→ faster-whisper transcribes (Hinglish/Hindi/English)
→ Gemini Flash translates + extracts insights + topics
→ SQLite + ChromaDB store everything permanently
→ Claude searches memory on every question you ask
```

---

## Free Stack

| Tool | Purpose | Cost |
|------|---------|------|
| yt-dlp | Download reels | Free |
| faster-whisper | Transcribe audio (CPU) | Free |
| Gemini Flash | Analyze + translate | Free (15 RPM) |
| ChromaDB | Semantic vector search | Free (embedded) |
| SQLite | Structured data store | Free (built-in) |
| Railway | 24/7 hosting | Free tier |
| instaloader | Watch Instagram DMs | Free |

---

## Prerequisites

- Python 3.11+ (only for local testing; Railway uses Docker)
- Docker (for local testing)
- A **separate** Instagram account to use as the bot (not your main account)
- Gemini API key from [aistudio.google.com](https://aistudio.google.com/)
- Railway account at [railway.app](https://railway.app/)

---

## Deploy to Railway (Step-by-Step)

### Step 1 — Push to GitHub

```bash
git init
git add .
git commit -m "Initial ReelBrain commit"
git remote add origin https://github.com/YOUR_USERNAME/reelbrain-mcp.git
git push -u origin main
```

### Step 2 — Create Railway Project

1. Go to [railway.app](https://railway.app/) → **New Project**
2. Choose **Deploy from GitHub repo**
3. Select your `reelbrain-mcp` repo
4. Railway detects the Dockerfile and starts building automatically

### Step 3 — Add a Volume (for persistent memory)

1. In your Railway project, click **+ New** → **Volume**
2. Set mount path to `/data`
3. This keeps your SQLite + ChromaDB data safe across redeploys

### Step 4 — Set Environment Variables

In Railway dashboard → your service → **Variables**, add:

| Variable | Value |
|----------|-------|
| `GEMINI_API_KEY` | Your Gemini Flash API key |
| `IG_BOT_USERNAME` | Your bot Instagram username |
| `IG_BOT_PASSWORD` | Your bot Instagram password |
| `POLL_INTERVAL_SECONDS` | `600` (10 minutes) |
| `WHISPER_MODEL` | `small` |

### Step 5 — Get Your Railway URL

After deploy succeeds:
1. Go to your service → **Settings** → **Networking** → **Generate Domain**
2. Copy the URL, e.g. `https://reelbrain-mcp-production.up.railway.app`

### Step 6 — Configure Claude Desktop

Find your Claude Desktop config file:
- **macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
- **Windows**: `%APPDATA%\Claude\claude_desktop_config.json`
- **Linux**: `~/.config/Claude/claude_desktop_config.json`

Add this (replace the URL with yours):

```json
{
  "mcpServers": {
    "reelbrain": {
      "command": "npx",
      "args": [
        "mcp-remote",
        "https://reelbrain-mcp-production.up.railway.app/sse"
      ]
    }
  }
}
```

> **Note**: `mcp-remote` connects Claude Desktop to remote SSE MCP servers.
> Install it with: `npm install -g mcp-remote`

### Step 7 — Add System Prompt

1. In Claude Desktop, open **Settings** → **Project Instructions** (or your custom project)
2. Paste the full contents of `system_prompt.txt`

### Step 8 — Test It!

1. DM an Instagram reel to your bot account
2. Wait up to 10 minutes (the first poll cycle)
3. Ask Claude: *"What have I learned recently?"*
4. Claude will answer from your reels automatically ✅

---

## MCP Tools

| Tool | What it does |
|------|-------------|
| `search_memory` | Semantic search by topic or question |
| `get_recent_reels` | Last N analyzed reels |
| `get_topics` | All auto-detected topic categories |
| `summarize_learning` | Full dump of all insights, filterable by topic |
| `analyze_reel_url` | Manually analyze a reel URL right now |
| `get_stats` | Total reels, date range, top topics |

---

## Behavior Rules

| Scenario | Behavior |
|----------|----------|
| Same reel sent again | Re-analyzes and overwrites |
| Reel fails to process | Retries 3× → skips + logs |
| No matching topic | Claude answers from own knowledge, no mention of ReelBrain |
| Topic match found | Claude says "From your reels..." + uses insight |
| Video file after analysis | Deleted immediately (temp dir) |
| Memory retention | Forever — never auto-deleted |

---

## Local Testing

```bash
# Copy env vars
cp .env.example .env
# Fill in your values in .env

# Install dependencies
pip install -r requirements.txt

# Test server (stdio mode for local debug)
python server.py

# Test analyzer standalone
python -c "
import asyncio
from analyzer import analyze_reel
result = asyncio.run(analyze_reel('https://www.instagram.com/reel/YOUR_SHORTCODE/'))
print(result)
"

# Test watcher standalone
python watcher.py
```

---

## Troubleshooting

**Watcher not picking up DMs**
- Confirm `IG_BOT_USERNAME` and `IG_BOT_PASSWORD` are correct
- Instagram may challenge the login — check Railway logs for 2FA or challenge errors
- Try logging in once locally with instaloader to resolve the challenge

**Gemini quota exceeded**
- Free tier = 15 RPM. If you send many reels at once, the watcher will slow down naturally
- Add `await asyncio.sleep(4)` between analyses in `watcher.py` if hitting limits

**Claude Desktop not seeing tools**
- Ensure `mcp-remote` is installed: `npm install -g mcp-remote`
- Check the Railway URL ends in `/sse`
- Restart Claude Desktop fully after editing the config

**ChromaDB error on startup**
- Make sure the Railway volume is mounted at `/data`
- Delete `/data/chroma` and restart to rebuild the index from SQLite

---

## Security

- Instagram credentials are stored only as Railway environment variables (never in code)
- All data is stored in your private Railway volume
- The MCP server has no public write endpoints — analysis is triggered only by DMs to your bot account

---

## License

MIT
