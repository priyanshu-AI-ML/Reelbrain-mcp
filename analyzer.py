#!/usr/bin/env python3
"""
ReelBrain Analyzer — downloads reel, transcribes with Whisper, analyzes with Gemini Flash.
"""
import os
import sys
import json
import logging
import asyncio
import tempfile
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import httpx

logger = logging.getLogger("reelbrain-analyzer")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

WHISPER_MODEL = os.environ.get("WHISPER_MODEL", "small")  # tiny/small/medium


def _extract_shortcode(url: str) -> str:
    """Pull the reel shortcode from an Instagram URL."""
    parts = [p for p in url.rstrip("/").split("/") if p]
    for i, p in enumerate(parts):
        if p in ("reel", "reels", "p") and i + 1 < len(parts):
            return parts[i + 1]
    return parts[-1] if parts else url


def _download_reel(url: str, out_dir: str) -> str:
    """Download reel audio/video to a temp file using yt-dlp. Returns file path."""
    out_template = os.path.join(out_dir, "reel.%(ext)s")
    cmd = [
        "yt-dlp",
        "--no-playlist",
        "--format", "bestaudio/best",
        "--output", out_template,
        "--quiet",
        "--no-warnings",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(f"yt-dlp failed: {result.stderr.strip()}")

    for f in Path(out_dir).iterdir():
        if f.name.startswith("reel."):
            return str(f)
    raise RuntimeError("yt-dlp did not produce an output file")


def _transcribe(audio_path: str) -> str:
    """Transcribe audio using faster-whisper. Returns raw transcript text."""
    from faster_whisper import WhisperModel
    model = WhisperModel(WHISPER_MODEL, device="cpu", compute_type="int8")
    segments, _ = model.transcribe(audio_path, beam_size=5, language=None)
    return " ".join(seg.text.strip() for seg in segments).strip()


async def _gemini_analyze(transcript: str) -> dict:
    """Send transcript to Gemini Flash for analysis. Returns structured dict."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY environment variable not set")

    prompt = f"""You are analyzing an Instagram reel transcript that may be in Hindi, Hinglish, or English.

TRANSCRIPT:
{transcript}

Respond ONLY with valid JSON (no markdown, no backticks):
{{
  "transcript_en": "<full English translation of transcript>",
  "summary": "<2-3 sentence summary in English>",
  "topics": ["<topic1>", "<topic2>", "<topic3>"],
  "insights": ["<key lesson 1>", "<key lesson 2>", "<key lesson 3>"],
  "content_type": "<one of: tutorial|gaming|motivation|finance|tech|health|cooking|comedy|news|other>",
  "language": "<detected language: Hindi|Hinglish|English|Other>"
}}

Rules:
- topics: 2-5 short lowercase tags (e.g. "personal finance", "coding", "gym")
- insights: 2-4 actionable takeaways in English
- summary: plain English, no bullet points
- content_type: pick the single best fit"""

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.2, "maxOutputTokens": 1024}
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{GEMINI_URL}?key={GEMINI_API_KEY}",
            json=payload,
            headers={"Content-Type": "application/json"}
        )
        resp.raise_for_status()
        data = resp.json()

    raw = data["candidates"][0]["content"]["parts"][0]["text"]
    # Strip any accidental markdown fencing
    raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
    return json.loads(raw)


async def analyze_reel(url: str) -> dict:
    """Full pipeline: download → transcribe → analyze → return structured data."""
    shortcode = _extract_shortcode(url)
    logger.info(f"Analyzing reel: {shortcode}")

    with tempfile.TemporaryDirectory() as tmp:
        # Step 1: Download
        try:
            audio_path = _download_reel(url, tmp)
            logger.info(f"Downloaded to {audio_path}")
        except Exception as e:
            logger.error(f"Download failed for {shortcode}: {e}")
            raise

        # Step 2: Transcribe
        try:
            transcript = _transcribe(audio_path)
            logger.info(f"Transcript ({len(transcript)} chars): {transcript[:80]}...")
        except Exception as e:
            logger.error(f"Transcription failed for {shortcode}: {e}")
            raise
        # File auto-deleted when TemporaryDirectory exits

    # Step 3: Analyze with Gemini (outside tmp block — file already gone, we have transcript)
    try:
        analysis = await _gemini_analyze(transcript)
    except Exception as e:
        logger.error(f"Gemini analysis failed for {shortcode}: {e}")
        raise

    return {
        "id": shortcode,
        "transcript": transcript,
        "transcript_en": analysis.get("transcript_en", transcript),
        "summary": analysis.get("summary", ""),
        "topics": analysis.get("topics", []),
        "insights": analysis.get("insights", []),
        "content_type": analysis.get("content_type", "other"),
        "language": analysis.get("language", "unknown"),
        "date": datetime.now(timezone.utc).isoformat(),
        "overwrite": True,
    }


async def analyze_with_retry(url: str, retries: int = 3) -> dict:
    """Analyze a reel with up to N retries on failure."""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return await analyze_reel(url)
        except Exception as e:
            last_err = e
            logger.warning(f"Attempt {attempt}/{retries} failed for {url}: {e}")
            if attempt < retries:
                await asyncio.sleep(5 * attempt)
    logger.error(f"All {retries} attempts failed for {url}: {last_err}")
    raise last_err
