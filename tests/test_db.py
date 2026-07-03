from datetime import date

from startup_scout.db import Database
from startup_scout.models import Analysis, AnalyzedStartup, RawStartup, ScoreBreakdown, ScoredStartup


def _scored(name="Acme", score=80.0, category="AI SaaS"):
    raw = RawStartup(source="test", name=name, url=f"https://{name.lower()}.com", description="")
    analysis = Analysis(category=category)
    analyzed = AnalyzedStartup(raw=raw, analysis=analysis)
    breakdown = ScoreBreakdown()
    return ScoredStartup(analyzed=analyzed, score=score, breakdown=breakdown)


def test_upsert_and_query_top_scores(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert_scored_startup(_scored("Acme", 90.0), run_date=date(2026, 1, 1))
    db.upsert_scored_startup(_scored("Globex", 60.0), run_date=date(2026, 1, 1))

    top = db.get_top_scores_for_date(date(2026, 1, 1), limit=5)
    assert len(top) == 2
    assert top[0]["name"] == "Acme"  # highest score first


def test_feedback_roundtrip(tmp_path):
    db = Database(tmp_path / "test.db")
    scored = _scored("Acme", 90.0, category="AI SaaS")
    db.upsert_scored_startup(scored, run_date=date(2026, 1, 1))

    db.save_feedback(scored.analyzed.id, "liked", "great fit")
    stats = db.get_feedback_by_category()
    assert stats["AI SaaS"]["liked"] == 1


def test_category_counts_since(tmp_path):
    db = Database(tmp_path / "test.db")
    db.upsert_scored_startup(_scored("Acme", 90.0, category="AI SaaS"), run_date=date(2026, 1, 10))
    db.upsert_scored_startup(_scored("Globex", 60.0, category="Fintech"), run_date=date(2026, 1, 10))

    counts = db.category_counts_since(date(2026, 1, 1))
    assert counts.get("AI SaaS") == 1
    assert counts.get("Fintech") == 1

    counts_later = db.category_counts_since(date(2026, 1, 15))
    assert counts_later == {}
