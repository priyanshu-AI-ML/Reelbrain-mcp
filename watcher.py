#!/usr/bin/env python3
"""
ReelBrain Watcher — polls Instagram DMs every 10 minutes and auto-analyzes new reels.
"""
import os
import sys
import time
import logging
import asyncio
from datetime import datetime, timezone

import instaloader

from analyzer import analyze_with_retry
from memory import ReelMemory

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stderr
)
logger = logging.getLogger("reelbrain-watcher")

IG_USERNAME = os.environ.get("IG_BOT_USERNAME", "")
IG_PASSWORD = os.environ.get("IG_BOT_PASSWORD", "")
POLL_INTERVAL = int(os.environ.get("POLL_INTERVAL_SECONDS", "600"))  # 10 min default

INSTAGRAM_URL_PATTERNS = [
    "instagram.com/reel/",
    "instagram.com/p/",
    "instagram.com/reels/",
]


def _extract_reel_urls(text: str) -> list:
    """Pull all Instagram reel URLs out of a message string."""
    urls = []
    for word in text.split():
        word = word.strip(".,!?\"'")
        if any(pat in word for pat in INSTAGRAM_URL_PATTERNS):
            if not word.startswith("http"):
                word = "https://" + word
            urls.append(word)
    return urls


class DMWatcher:
    def __init__(self):
        self.memory = ReelMemory()
        self.loader = instaloader.Instaloader()
        self._processed_msg_ids = set()
        self._load_processed_ids()

    def _load_processed_ids(self):
        """Load already-processed message IDs from memory DB to survive restarts."""
        try:
            ids = self.memory.get_processed_message_ids()
            self._processed_msg_ids = set(ids)
            logger.info(f"Loaded {len(self._processed_msg_ids)} processed message IDs")
        except Exception as e:
            logger.warning(f"Could not load processed IDs: {e}")

    def login(self):
        """Log in to Instagram. Raises on failure."""
        if not IG_USERNAME or not IG_PASSWORD:
            raise RuntimeError("IG_BOT_USERNAME and IG_BOT_PASSWORD must be set")
        try:
            self.loader.login(IG_USERNAME, IG_PASSWORD)
            logger.info(f"Logged in as @{IG_USERNAME}")
        except Exception as e:
            logger.error(f"Instagram login failed: {e}")
            raise

    async def _process_dm(self, thread, msg):
        """Process a single DM message — extract and analyze any reel URLs."""
        msg_id = str(msg.id)
        if msg_id in self._processed_msg_ids:
            return

        text = getattr(msg, 'text', '') or ''
        urls = _extract_reel_urls(text)

        if not urls:
            # Mark as seen so we don't recheck it every cycle
            self._processed_msg_ids.add(msg_id)
            self.memory.mark_message_processed(msg_id)
            return

        for url in urls:
            shortcode = url.rstrip("/").split("/")[-1]
            logger.info(f"New reel in DM from thread {thread.id}: {shortcode}")
            try:
                result = await analyze_with_retry(url, retries=3)
                self.memory.upsert(result)
                logger.info(f"✅ Stored reel {shortcode} — {result['summary'][:60]}...")
            except Exception as e:
                logger.error(f"❌ Failed to process reel {shortcode} after retries: {e}")

        self._processed_msg_ids.add(msg_id)
        self.memory.mark_message_processed(msg_id)

    async def poll_once(self):
        """Single poll cycle — check all DM threads for new reels."""
        logger.info("Polling Instagram DMs...")
        try:
            profile = instaloader.Profile.from_username(self.loader.context, IG_USERNAME)
            # instaloader direct message access via context
            threads = self.loader.context.get_inbox()
            count = 0
            for thread in threads:
                for msg in thread.items:
                    await self._process_dm(thread, msg)
                    count += 1
            logger.info(f"Poll complete — checked {count} messages")
        except Exception as e:
            logger.error(f"Poll error: {e}")

    async def run(self):
        """Main loop — login once, then poll every POLL_INTERVAL seconds."""
        self.login()
        logger.info(f"Watcher started. Polling every {POLL_INTERVAL}s")
        while True:
            await self.poll_once()
            logger.info(f"Sleeping {POLL_INTERVAL}s until next poll...")
            await asyncio.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    watcher = DMWatcher()
    asyncio.run(watcher.run())
