from datetime import date

from startup_scout.models import Analysis, AnalyzedStartup, RawStartup, ScoreBreakdown, ScoredStartup
from startup_scout.report import ReportGenerator
from startup_scout.trends import TrendReport


def _scored(name, score):
    raw = RawStartup(source="test", name=name, url="https://example.com", description="A test startup")
    analysis = Analysis(
        category="AI SaaS",
        problem="test problem",
        estimated_mvp_cost_inr="₹50,000",
        estimated_mvp_time_weeks="2 weeks",
        potential_risks="test risk",
    )
    return ScoredStartup(analyzed=AnalyzedStartup(raw=raw, analysis=analysis), score=score, breakdown=ScoreBreakdown())


def test_report_contains_required_sections(tmp_path):
    generator = ReportGenerator(tmp_path, top_n=5)
    scored = [_scored("Acme", 90), _scored("Globex", 70)]
    trends = TrendReport(fastest_growing=[("AI SaaS", 0.5)], category_counts={"AI SaaS": 2})

    path = generator.generate(scored, trends, run_date=date(2026, 1, 1))
    content = path.read_text(encoding="utf-8")

    for section in [
        "Executive Summary",
        "Top 5 Opportunities",
        "Trend Analysis",
        "Recommended Opportunity of the Week",
        "Why This Fits Varun",
        "30-Day MVP Plan",
        "Risks",
        "Estimated Budget",
        "Expected Timeline",
        "Recommended Tech Stack",
    ]:
        assert section in content

    assert "Acme" in content


def test_report_ranks_highest_score_first(tmp_path):
    generator = ReportGenerator(tmp_path, top_n=5)
    scored = [_scored("Low", 10), _scored("High", 95)]
    trends = TrendReport(fastest_growing=[], category_counts={})

    path = generator.generate(scored, trends, run_date=date(2026, 1, 2))
    content = path.read_text(encoding="utf-8")

    assert content.index("High") < content.index("Low")


def test_report_handles_empty_input(tmp_path):
    generator = ReportGenerator(tmp_path, top_n=5)
    trends = TrendReport(fastest_growing=[], category_counts={})

    path = generator.generate([], trends, run_date=date(2026, 1, 3))
    content = path.read_text(encoding="utf-8")
    assert "No candidates scored this week" in content
