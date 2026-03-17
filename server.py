#!/usr/bin/env python3
"""
ReelBrain MCP Server - Semantic memory from Instagram reels via Railway SSE transport.
"""
import os
import sys
import logging
from mcp.server.fastmcp import FastMCP
from memory import ReelMemory

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("reelbrain-server")

mcp = FastMCP("reelbrain")
memory = ReelMemory()


@mcp.tool()
async def search_memory(question: str = "") -> str:
    """Search stored reel insights by topic or question using semantic similarity."""
    if not question.strip():
        return "❌ Error: question is required"
    try:
        results = memory.search(question, top_k=5)
        if not results:
            return "🔍 No matching reels found for that topic."
        lines = [f"🧠 From your reels — {len(results)} match(es) found:\n"]
        for r in results:
            lines.append(f"📌 [{r['date'][:10]}] {r['summary']}")
            lines.append(f"   Topics: {', '.join(r['topics'])}")
            for ins in r['insights']:
                lines.append(f"   • {ins}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"search_memory error: {e}")
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def get_recent_reels(count: str = "5") -> str:
    """Get the most recently analyzed reels, newest first."""
    try:
        n = int(count.strip()) if count.strip() else 5
        reels = memory.get_recent(n)
        if not reels:
            return "📭 No reels analyzed yet. DM a reel to your bot account to get started."
        lines = [f"📺 Last {len(reels)} analyzed reel(s):\n"]
        for r in reels:
            lines.append(f"🎬 {r['id']} [{r['date'][:10]}]")
            lines.append(f"   {r['summary']}")
            lines.append(f"   Language: {r['language']} | Type: {r['content_type']}")
            lines.append(f"   Topics: {', '.join(r['topics'])}\n")
        return "\n".join(lines)
    except ValueError:
        return f"❌ Error: count must be a number, got: {count}"
    except Exception as e:
        logger.error(f"get_recent_reels error: {e}")
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def get_topics(filter_tag: str = "") -> str:
    """List all auto-detected topic categories across every analyzed reel."""
    try:
        topics = memory.get_all_topics()
        if not topics:
            return "📭 No topics found. Analyze some reels first."
        if filter_tag.strip():
            topics = {k: v for k, v in topics.items() if filter_tag.lower() in k.lower()}
            if not topics:
                return f"🔍 No topics matching '{filter_tag}' found."
        lines = ["📊 Topics across your reels:\n"]
        for topic, count in sorted(topics.items(), key=lambda x: -x[1]):
            lines.append(f"  • {topic} ({count} reel{'s' if count > 1 else ''})")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"get_topics error: {e}")
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def summarize_learning(topic_filter: str = "") -> str:
    """Dump all insights from your reels, optionally filtered by topic."""
    try:
        reels = memory.get_all(topic_filter.strip() if topic_filter.strip() else None)
        if not reels:
            msg = f" about '{topic_filter}'" if topic_filter.strip() else ""
            return f"📭 No reels{msg} found."
        lines = [f"🧠 Full brain dump — {len(reels)} reel(s):\n"]
        for r in reels:
            lines.append(f"━━━ {r['id']} [{r['date'][:10]}] ━━━")
            lines.append(f"📝 {r['summary']}")
            lines.append(f"🏷  {', '.join(r['topics'])}")
            lines.append("💡 Key insights:")
            for ins in r['insights']:
                lines.append(f"   • {ins}")
            lines.append("")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"summarize_learning error: {e}")
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def analyze_reel_url(url: str = "") -> str:
    """Manually trigger analysis of a single Instagram reel URL."""
    if not url.strip():
        return "❌ Error: url is required"
    try:
        from analyzer import analyze_reel
        result = await analyze_reel(url.strip())
        if result:
            memory.upsert(result)
            return (
                f"✅ Reel analyzed and stored!\n\n"
                f"📝 Summary: {result['summary']}\n"
                f"🏷  Topics: {', '.join(result['topics'])}\n"
                f"💡 Insights:\n" + "\n".join(f"   • {i}" for i in result['insights'])
            )
        return "❌ Analysis failed — check logs for details."
    except Exception as e:
        logger.error(f"analyze_reel_url error: {e}")
        return f"❌ Error: {str(e)}"


@mcp.tool()
async def get_stats(dummy: str = "") -> str:
    """Show total reels stored, date range, top topics, and content type breakdown."""
    try:
        stats = memory.get_stats()
        if stats['total'] == 0:
            return "📭 No reels analyzed yet."
        lines = [
            "📊 ReelBrain Stats\n",
            f"  🎬 Total reels:   {stats['total']}",
            f"  📅 First reel:    {stats['oldest'][:10]}",
            f"  📅 Latest reel:   {stats['newest'][:10]}",
            f"  🌐 Languages:     {', '.join(stats['languages'])}",
            f"  🎭 Content types: {', '.join(stats['content_types'])}",
            "\n🏆 Top topics:",
        ]
        for topic, count in stats['top_topics']:
            lines.append(f"   • {topic}: {count}")
        return "\n".join(lines)
    except Exception as e:
        logger.error(f"get_stats error: {e}")
        return f"❌ Error: {str(e)}"



    port = int(os.environ.get("PORT", 8000))
    logger.info(f"Starting ReelBrain MCP server on port {port}...")
    try:
        mcp.run(transport="sse", host="0.0.0.0", port=port)
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)



    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount

    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting ReelBrain MCP server on port {port}...")

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp._mcp_server.run(streams[0], streams[1], mcp._mcp_server.create_initialization_options())

    app = Starlette(routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ])

    uvicorn.run(app, host="0.0.0.0", port=port)



    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount

    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting ReelBrain MCP server on port {port}...")

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp._mcp_server.run(streams[0], streams[1], mcp._mcp_server.create_initialization_options())

    app = Starlette(routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ])

    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    import uvicorn
    from mcp.server.sse import SseServerTransport
    from starlette.applications import Starlette
    from starlette.routing import Route, Mount

    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting ReelBrain MCP server on port {port}...")

    sse = SseServerTransport("/messages/")

    async def handle_sse(request):
        async with sse.connect_sse(request.scope, request.receive, request._send) as streams:
            await mcp._mcp_server.run(streams[0], streams[1], mcp._mcp_server.create_initialization_options())

    app = Starlette(routes=[
        Route("/sse", endpoint=handle_sse),
        Mount("/messages/", app=sse.handle_post_message),
    ])

    uvicorn.run(app, host="0.0.0.0", port=port)
