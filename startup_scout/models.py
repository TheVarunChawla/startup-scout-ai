"""Core data models shared across the pipeline.

Using plain dataclasses (rather than a heavier ORM) keeps the domain
model easy to read, easy to serialize to JSON/SQLite, and dependency-free.
Each stage of the pipeline (collect -> dedupe -> categorize -> analyze ->
score) enriches the previous stage's dataclass rather than mutating a
single God object, which keeps stage boundaries explicit and testable.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _make_id(source: str, name: str, url: str) -> str:
    """Deterministic id so re-collecting the same startup upserts cleanly."""
    key = f"{source}:{name.strip().lower()}:{url.strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]


@dataclass
class RawStartup:
    """A startup as it comes out of a connector, before any enrichment."""

    source: str
    name: str
    url: str
    description: str = ""
    tags: list[str] = field(default_factory=list)
    raw_meta: dict[str, Any] = field(default_factory=dict)
    collected_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    id: str = ""

    def __post_init__(self) -> None:
        if not self.id:
            self.id = _make_id(self.source, self.name, self.url)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Analysis:
    """AI-derived analysis fields, one per startup."""

    problem: str = ""
    customer_type: str = ""
    business_model: str = ""
    pricing_model: str = ""
    estimated_market_size: str = ""
    ai_usage: str = ""
    technical_complexity: str = ""
    founder_advantage: str = ""
    india_suitability: str = ""
    estimated_mvp_cost_inr: str = ""
    estimated_mvp_time_weeks: str = ""
    competitive_landscape: str = ""
    possible_improvements: str = ""
    potential_risks: str = ""
    why_now: str = ""
    long_term_opportunity: str = ""
    category: str = "Uncategorized"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AnalyzedStartup:
    raw: RawStartup
    analysis: Analysis

    @property
    def id(self) -> str:
        return self.raw.id


@dataclass
class ScoreBreakdown:
    skills_match: float = 0
    interests_match: float = 0
    low_investment: float = 0
    india_readiness: float = 0
    ai_potential: float = 0
    ease_of_execution: float = 0
    revenue_potential: float = 0
    competition: float = 0
    scalability: float = 0
    long_term_opportunity: float = 0
    memory_adjustment: float = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ScoredStartup:
    analyzed: AnalyzedStartup
    score: float
    breakdown: ScoreBreakdown

    @property
    def id(self) -> str:
        return self.analyzed.id

    @property
    def name(self) -> str:
        return self.analyzed.raw.name
