"""Trend analysis over the historical SQLite data.

Compares category volume in the trailing `window_days` window against
the window before it to estimate which categories are heating up.
Deliberately simple (no external trend APIs) so it works entirely from
data this project has already collected - it gets more accurate the
longer the weekly pipeline has been running.

Categories with no real data in the PRIOR window (most categories, on
the very first run, or any time a category first appears) are reported
as "New this week (N found)" rather than a percentage - dividing by a
zero baseline would otherwise produce meaningless numbers like
"+37300%".
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from startup_scout.db import Database

RECENT_WINDOW_DAYS = 7


@dataclass
class TrendReport:
    # Each entry is (category, a ready-to-display string) - e.g.
    # ("Fintech", "+45% vs. last week") or
    # ("AI SaaS", "New this week (12 found)").
    fastest_growing: list[tuple[str, str]]
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

        established: list[tuple[str, float, int]] = []
        new: list[tuple[str, int]] = []
        for category, recent_n in recent_counts.items():
            prior_n = max(total_since_prior.get(category, 0) - recent_n, 0)
            if prior_n == 0:
                # No real prior-week baseline yet for this category - a raw
                # count masquerading as a percentage here is meaningless.
                new.append((category, recent_n))
            else:
                rate = round((recent_n - prior_n) / prior_n, 2)
                established.append((category, rate, recent_n))

        established.sort(key=lambda item: item[1], reverse=True)
        new.sort(key=lambda item: item[1], reverse=True)

        fastest_growing: list[tuple[str, str]] = [
            (category, f"{rate:+.0%} vs. last week") for category, rate, _ in established
        ] + [
            (category, f"New this week ({count} found)") for category, count in new
        ]

        return TrendReport(fastest_growing=fastest_growing[:5], category_counts=recent_counts)
