#!/usr/bin/env python3
"""
ReelBrain Memory — SQLite for structured data + ChromaDB for semantic search.
"""
import os
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import chromadb
from chromadb.utils import embedding_functions

logger = logging.getLogger("reelbrain-memory")

DATA_DIR = os.environ.get("DATA_DIR", "/data")
DB_PATH = os.path.join(DATA_DIR, "reelbrain.db")
CHROMA_DIR = os.path.join(DATA_DIR, "chroma")


class ReelMemory:
    def __init__(self):
        Path(DATA_DIR).mkdir(parents=True, exist_ok=True, mode=0o777)
        self._init_sqlite()
        self._init_chroma()

    # ──────────────────────────────────────────────────────────────────
    # SQLite Setup
    # ──────────────────────────────────────────────────────────────────

    def _init_sqlite(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        cur = self.conn.cursor()
        cur.executescript("""
            CREATE TABLE IF NOT EXISTS reels (
                id            TEXT PRIMARY KEY,
                transcript    TEXT,
                transcript_en TEXT,
                summary       TEXT,
                topics        TEXT,
                insights      TEXT,
                content_type  TEXT,
                language      TEXT,
                date          TEXT
            );

            CREATE TABLE IF NOT EXISTS processed_messages (
                msg_id TEXT PRIMARY KEY,
                seen_at TEXT
            );
        """)
        self.conn.commit()
        logger.info(f"SQLite ready at {DB_PATH}")

    # ──────────────────────────────────────────────────────────────────
    # ChromaDB Setup
    # ──────────────────────────────────────────────────────────────────

    def _init_chroma(self):
        try:
            client = chromadb.PersistentClient(path=CHROMA_DIR)
        except Exception:
            import shutil
            shutil.rmtree(CHROMA_DIR, ignore_errors=True)
            Path(CHROMA_DIR).mkdir(parents=True, exist_ok=True)
            client = chromadb.PersistentClient(path=CHROMA_DIR)
        ef = embedding_functions.DefaultEmbeddingFunction()
        self.collection = client.get_or_create_collection(
            name="reels",
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"}
        )
        logger.info(f"ChromaDB ready at {CHROMA_DIR}")

    # ──────────────────────────────────────────────────────────────────
    # Write
    # ──────────────────────────────────────────────────────────────────

    def upsert(self, reel: dict):
        """Insert or overwrite a reel in both stores."""
        rid = reel["id"]

        # SQLite upsert
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO reels (id, transcript, transcript_en, summary, topics, insights, content_type, language, date)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                transcript    = excluded.transcript,
                transcript_en = excluded.transcript_en,
                summary       = excluded.summary,
                topics        = excluded.topics,
                insights      = excluded.insights,
                content_type  = excluded.content_type,
                language      = excluded.language,
                date          = excluded.date
        """, (
            rid,
            reel.get("transcript", ""),
            reel.get("transcript_en", ""),
            reel.get("summary", ""),
            json.dumps(reel.get("topics", [])),
            json.dumps(reel.get("insights", [])),
            reel.get("content_type", "other"),
            reel.get("language", "unknown"),
            reel.get("date", datetime.now(timezone.utc).isoformat()),
        ))
        self.conn.commit()

        # ChromaDB upsert — embed summary + transcript_en + topics for rich search
        search_text = " ".join([
            reel.get("summary", ""),
            reel.get("transcript_en", ""),
            " ".join(reel.get("topics", [])),
            " ".join(reel.get("insights", [])),
        ]).strip()

        self.collection.upsert(
            ids=[rid],
            documents=[search_text],
            metadatas=[{
                "id": rid,
                "date": reel.get("date", ""),
                "content_type": reel.get("content_type", "other"),
                "language": reel.get("language", "unknown"),
                "topics": json.dumps(reel.get("topics", [])),
            }]
        )
        logger.info(f"Upserted reel {rid}")

    def mark_message_processed(self, msg_id: str):
        cur = self.conn.cursor()
        cur.execute("""
            INSERT OR IGNORE INTO processed_messages (msg_id, seen_at) VALUES (?, ?)
        """, (msg_id, datetime.now(timezone.utc).isoformat()))
        self.conn.commit()

    # ──────────────────────────────────────────────────────────────────
    # Read
    # ──────────────────────────────────────────────────────────────────

    def _row_to_dict(self, row) -> dict:
        d = dict(row)
        d["topics"] = json.loads(d.get("topics", "[]"))
        d["insights"] = json.loads(d.get("insights", "[]"))
        return d

    def search(self, query: str, top_k: int = 5) -> list:
        """Semantic search via ChromaDB, hydrate full records from SQLite."""
        results = self.collection.query(
            query_texts=[query],
            n_results=min(top_k, max(1, self.collection.count())),
            include=["distances", "metadatas"]
        )
        ids = results["ids"][0] if results["ids"] else []
        distances = results["distances"][0] if results["distances"] else []

        # Filter: cosine distance < 0.4 means similarity > 0.6
        good_ids = [rid for rid, dist in zip(ids, distances) if dist < 0.4]
        if not good_ids:
            return []

        cur = self.conn.cursor()
        placeholders = ",".join("?" * len(good_ids))
        rows = cur.execute(
            f"SELECT * FROM reels WHERE id IN ({placeholders})", good_ids
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_recent(self, n: int = 5) -> list:
        cur = self.conn.cursor()
        rows = cur.execute(
            "SELECT * FROM reels ORDER BY date DESC LIMIT ?", (n,)
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_all(self, topic_filter: str = None) -> list:
        cur = self.conn.cursor()
        if topic_filter:
            rows = cur.execute(
                "SELECT * FROM reels WHERE topics LIKE ? ORDER BY date DESC",
                (f"%{topic_filter}%",)
            ).fetchall()
        else:
            rows = cur.execute("SELECT * FROM reels ORDER BY date DESC").fetchall()
        return [self._row_to_dict(r) for r in rows]

    def get_all_topics(self) -> dict:
        cur = self.conn.cursor()
        rows = cur.execute("SELECT topics FROM reels").fetchall()
        counts = {}
        for row in rows:
            for topic in json.loads(row["topics"] or "[]"):
                counts[topic] = counts.get(topic, 0) + 1
        return counts

    def get_stats(self) -> dict:
        cur = self.conn.cursor()
        total = cur.execute("SELECT COUNT(*) FROM reels").fetchone()[0]
        if total == 0:
            return {"total": 0}
        oldest = cur.execute("SELECT MIN(date) FROM reels").fetchone()[0]
        newest = cur.execute("SELECT MAX(date) FROM reels").fetchone()[0]
        langs = [r[0] for r in cur.execute(
            "SELECT DISTINCT language FROM reels WHERE language IS NOT NULL"
        ).fetchall()]
        ctypes = [r[0] for r in cur.execute(
            "SELECT DISTINCT content_type FROM reels WHERE content_type IS NOT NULL"
        ).fetchall()]
        all_topics = self.get_all_topics()
        top_topics = sorted(all_topics.items(), key=lambda x: -x[1])[:5]
        return {
            "total": total,
            "oldest": oldest or "",
            "newest": newest or "",
            "languages": langs,
            "content_types": ctypes,
            "top_topics": top_topics,
        }

    def get_processed_message_ids(self) -> list:
        cur = self.conn.cursor()
        rows = cur.execute("SELECT msg_id FROM processed_messages").fetchall()
        return [r["msg_id"] for r in rows]

