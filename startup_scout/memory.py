"""Learning from feedback.

Tracks which startups/categories Varun liked or rejected (persisted in
SQLite via db.py) and turns that history into a small, capped score
adjustment per category. This is intentionally a light-touch heuristic
(category like-ratio -> bonus/penalty) rather than a trained model - it's
transparent, debuggable, and good enough to start noticeably favoring
categories he keeps saving and downweighting ones he keeps rejecting.
"""
from __future__ import annotations

import logging

from startup_scout.db import Database

logger = logging.getLogger(__name__)


class MemoryStore:
    def __init__(self, db: Database):
        self.db = db

    def record_feedback(self, startup_id: str, action: str, note: str = "") -> None:
        if action not in ("liked", "rejected"):
            raise ValueError("action must be 'liked' or 'rejected'")
        self.db.save_feedback(startup_id, action, note)

    def category_preferences(self) -> dict[str, float]:
        """category -> like ratio in [-1, 1], where +1 = always liked,
        -1 = always rejected, 0 = no signal / mixed."""
        stats = self.db.get_feedback_by_category()
        prefs: dict[str, float] = {}
        for category, counts in stats.items():
            liked, rejected = counts.get("liked", 0), counts.get("rejected", 0)
            total = liked + rejected
            prefs[category] = 0.0 if total == 0 else (liked - rejected) / total
        return prefs

    def category_adjustment(self, category: str, cap: float) -> float:
        ratio = self.category_preferences().get(category, 0.0)
        return round(ratio * cap, 2)
