from datetime import date, timedelta

from startup_scout.db import Database
from startup_scout.trends import TrendAnalyzer


def _insert(db, category, day, n=1):
    with db._connect() as conn:
        for i in range(n):
            conn.execute(
                "INSERT INTO startups (id, source, name, url, description, tags, category, first_seen_date, last_seen_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    f"{category}-{day.isoformat()}-{i}",
                    "test",
                    "Name",
                    "",
                    "",
                    "[]",
                    category,
                    day.isoformat(),
                    day.isoformat(),
                ),
            )


def test_category_with_no_prior_history_shows_new_label_not_percentage(tmp_path):
    db = Database(tmp_path / "test.db")
    today = date(2026, 7, 3)
    _insert(db, "AI SaaS", today, n=3)

    report = TrendAnalyzer(db).analyze(as_of=today)
    labels = dict(report.fastest_growing)

    assert labels["AI SaaS"] == "New this week (3 found)"
    assert "%" not in labels["AI SaaS"]


def test_category_with_prior_history_shows_percentage(tmp_path):
    db = Database(tmp_path / "test.db")
    today = date(2026, 7, 3)
    prior_day = today - timedelta(days=10)
    _insert(db, "Fintech", prior_day, n=2)
    _insert(db, "Fintech", today, n=4)

    report = TrendAnalyzer(db).analyze(as_of=today)
    labels = dict(report.fastest_growing)

    assert labels["Fintech"] == "+100% vs. last week"


def test_no_data_returns_empty_fastest_growing(tmp_path):
    db = Database(tmp_path / "test.db")
    report = TrendAnalyzer(db).analyze(as_of=date(2026, 7, 3))
    assert report.fastest_growing == []
