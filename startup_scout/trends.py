"""Trend analysis over the historical SQLite data.

Compares category volume in the trailing `window_days` window against
the window before it to estimate which categories are heating up.
Deliberately simple (no external trend APIs) so it works entirely from
data this project has already collected - it gets more accurate the
longer the daily pipeline has been running.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from startup_scout.db import Database

RECENT_WINDOW_DAYS = 7


@dataclass
class TrendReport:
    fastest_growing: list[tuple[str, float]]
    category_counts: dict[str, int]


class TrendAnalyzer:
    def __init__(self, db: Database, window_days: int = RECENT_WINDOW_DAYS):
        self.db = db
        self.window_days = window_days

    def analyze(self, as_of: date | None = None) -> TrendReport:
        as_of = as_of or date.today()
        recent_start = as_of - timedelta(days=self.window_days)
        prior_start = recent_start - timedelta(days=self.window_days)

        recent_counts = self.db.category_counts_since(recent_start)
        # category_counts_since(prior_start) covers prior_start..today, i.e.
        # prior window + recent window combined - subtract recent_n to
        # isolate the prior-only window without a second date filter.
        total_since_prior = self.db.category_counts_since(prior_start)

        growth: list[tuple[str, float]] = []
        for category, recent_n in recent_counts.items():
            prior_n = max(total_since_prior.get(category, 0) - recent_n, 0)
            growth_rate = (recent_n - prior_n) / prior_n if prior_n else float(recent_n)
            growth.append((category, round(growth_rate, 2)))

        growth.sort(key=lambda pair: pair[1], reverse=True)
        return TrendReport(fastest_growing=growth[:5], category_counts=recent_counts)
