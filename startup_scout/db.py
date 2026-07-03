"""SQLite persistence for historical analysis and feedback.

Plain sqlite3 (no ORM) - the schema is small and stable, and this keeps
the project dependency-light and easy to inspect with any SQLite
browser. All JSON-shaped fields (analysis details, score breakdowns) are
stored as TEXT columns holding json.dumps output.
"""
from __future__ import annotations

import json
import logging
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from startup_scout.models import ScoredStartup

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS startups (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL,
    name TEXT NOT NULL,
    url TEXT,
    description TEXT,
    tags TEXT,
    category TEXT,
    first_seen_date TEXT NOT NULL,
    last_seen_date TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis (
    startup_id TEXT PRIMARY KEY REFERENCES startups(id),
    analysis_json TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS scores (
    startup_id TEXT NOT NULL REFERENCES startups(id),
    score REAL NOT NULL,
    breakdown_json TEXT NOT NULL,
    ranked_date TEXT NOT NULL,
    PRIMARY KEY (startup_id, ranked_date)
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    startup_id TEXT NOT NULL REFERENCES startups(id),
    action TEXT NOT NULL CHECK(action IN ('liked', 'rejected')),
    note TEXT,
    created_at TEXT NOT NULL
);
"""


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    def upsert_scored_startup(self, scored: ScoredStartup, run_date: date | None = None) -> None:
        run_date = run_date or date.today()
        today_str = run_date.isoformat()
        now = datetime.now(timezone.utc).isoformat()
        raw = scored.analyzed.raw
        analysis = scored.analyzed.analysis

        with self._connect() as conn:
            existing = conn.execute(
                "SELECT first_seen_date FROM startups WHERE id = ?", (raw.id,)
            ).fetchone()
            first_seen = existing["first_seen_date"] if existing else today_str

            conn.execute(
                """
                INSERT INTO startups (id, source, name, url, description, tags, category, first_seen_date, last_seen_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    last_seen_date = excluded.last_seen_date,
                    category = excluded.category,
                    description = excluded.description
                """,
                (
                    raw.id, raw.source, raw.name, raw.url, raw.description,
                    json.dumps(raw.tags), analysis.category, first_seen, today_str,
                ),
            )
            conn.execute(
                """
                INSERT INTO analysis (startup_id, analysis_json, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(startup_id) DO UPDATE SET
                    analysis_json = excluded.analysis_json,
                    updated_at = excluded.updated_at
                """,
                (raw.id, json.dumps(analysis.to_dict()), now),
            )
            conn.execute(
                """
                INSERT INTO scores (startup_id, score, breakdown_json, ranked_date)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(startup_id, ranked_date) DO UPDATE SET
                    score = excluded.score,
                    breakdown_json = excluded.breakdown_json
                """,
                (raw.id, scored.score, json.dumps(scored.breakdown.to_dict()), today_str),
            )

    def save_feedback(self, startup_id: str, action: str, note: str = "") -> None:
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO feedback (startup_id, action, note, created_at) VALUES (?, ?, ?, ?)",
                (startup_id, action, note, datetime.now(timezone.utc).isoformat()),
            )

    def get_feedback_by_category(self) -> dict[str, dict[str, int]]:
        query = """
            SELECT s.category AS category, f.action AS action, COUNT(*) AS n
            FROM feedback f
            JOIN startups s ON s.id = f.startup_id
            GROUP BY s.category, f.action
        """
        result: dict[str, dict[str, int]] = {}
        with self._connect() as conn:
            for row in conn.execute(query):
                result.setdefault(row["category"], {})[row["action"]] = row["n"]
        return result

    def get_top_scores_for_date(self, run_date: date, limit: int = 5) -> list[sqlite3.Row]:
        with self._connect() as conn:
            return conn.execute(
                """
                SELECT s.*, st.name, st.url, st.category, st.source
                FROM scores s
                JOIN startups st ON st.id = s.startup_id
                WHERE s.ranked_date = ?
                ORDER BY s.score DESC
                LIMIT ?
                """,
                (run_date.isoformat(), limit),
            ).fetchall()

    def category_counts_since(self, since: date) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT category, COUNT(*) AS n FROM startups WHERE first_seen_date >= ? GROUP BY category",
                (since.isoformat(),),
            ).fetchall()
        return {row["category"]: row["n"] for row in rows}
