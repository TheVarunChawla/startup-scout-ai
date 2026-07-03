"""
One-off script fixing two problems you spotted in the first YC-only
weekly report:

1. Trend percentages were nonsense ("AI SaaS: +37300% vs. last week").
   Cause: when a category had ZERO data in the prior week (which is
   every category, on the very first weekly run), the code fell back to
   treating the raw count itself as if it were a growth rate - so a
   category with 373 new items displayed as "+37300%". Fix: when there
   is no real prior-week baseline yet, the report now says
   "New this week (N found)" instead of inventing a percentage. Once a
   category has genuine history in both weeks, it still shows a normal
   "+45% vs. last week" style percentage.

2. Categorization could be swayed by a source's own generic tags (e.g.
   a YC industry tag literally called "Developer Tools") even when the
   company's own name/description clearly pointed elsewhere (e.g.
   Klarify - "AI Agent for Therapists" - got labeled "Developer Tools").
   Fix: the startup's own name + description now count 3x more than its
   tags when scoring categories, so a real content signal beats an
   incidental tag match.

Usage: put this file in the ROOT of your startup-scout-ai_repo folder
(next to main.py) and run:

    python apply_trend_category_fix_v2.py

Then:

    python -m pytest
    git add -A
    git commit -m "Fix trend percentage explosion and tag-biased categorization"
    git push
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

TRENDS_PY = '''"""Trend analysis over the historical SQLite data.

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
'''

CATEGORIZE_PY = '''"""Rule-based categorization.

A lightweight keyword scorer is enough here (and cheap/deterministic,
unlike an LLM call) because the category taxonomy is small and mostly
about routing into Varun's stated interest areas. If this needs to get
smarter later, swap the scoring body for an LLM call behind the same
`categorize()` signature - callers don't need to change.

The startup's own name + description count 3x more than its tags when
scoring. Some sources (like Y Combinator) attach their own generic
industry tags (e.g. "Developer Tools") to a company; those tags are
still a useful signal, but a real content match in the company's own
description should win over an incidental tag match.
"""
from __future__ import annotations

from startup_scout.models import RawStartup

CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "AI SaaS": ["ai", "artificial intelligence", "llm", "machine learning", "genai", "copilot", "agent"],
    "Cyber Security": ["security", "cyber", "infosec", "encryption", "privacy", "vulnerability", "pentest", "compliance"],
    "Education": ["learning", "course", "education", "edtech", "training", "tutor", "student"],
    "Automation": ["automation", "workflow", "no-code", "low-code", "zapier", "rpa"],
    "Developer Tools": ["developer", "api", "sdk", "devtools", "cli", "framework", "open source", "github"],
    "B2B Software": ["b2b", "enterprise", "saas", "crm", "erp"],
    "Productivity": ["productivity", "notes", "calendar", "task", "todo", "collaboration"],
    "Digital Products": ["ebook", "template", "digital product", "notion template"],
    "Fintech": ["fintech", "payments", "banking", "invoice", "accounting", "finance"],
    "Healthtech": ["health", "medical", "fitness", "wellness", "clinic"],
}

DEFAULT_CATEGORY = "Other"

# How much more the startup's own name/description counts than its tags.
PRIMARY_TEXT_WEIGHT = 3


def categorize(startup: RawStartup) -> str:
    primary_text = " ".join([startup.name, startup.description]).lower()
    tag_text = " ".join(startup.tags).lower()

    best_category = DEFAULT_CATEGORY
    best_score = 0.0
    for category, keywords in CATEGORY_KEYWORDS.items():
        primary_score = sum(1 for kw in keywords if kw in primary_text)
        tag_score = sum(1 for kw in keywords if kw in tag_text)
        score = primary_score * PRIMARY_TEXT_WEIGHT + tag_score
        if score > best_score:
            best_score = score
            best_category = category
    return best_category
'''

REPORT_PY = '''"""Markdown weekly report generation.

Renders the sections required by the spec (executive summary, top 5,
trends, recommendation of the week, 30-day plan, risks, budget,
timeline, tech stack) from a list of ScoredStartup + a TrendReport.
Pure string templating - no Jinja dependency needed for a document
this structured.

Each pick also gets a plain-English "what they do" line (using the
source's own one-liner when available, since that is usually clearer
than an auto-truncated description) and a simple, jargon-free note on
how you could build something similar yourself.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

from startup_scout.models import ScoredStartup
from startup_scout.trends import TrendReport


def _plain_what_they_do(item: ScoredStartup) -> str:
    one_liner = (item.analyzed.raw.raw_meta or {}).get("one_liner", "").strip()
    if one_liner:
        return one_liner
    return item.analyzed.analysis.problem


def _plain_how_to_build(item: ScoredStartup) -> str:
    complexity = item.analyzed.analysis.technical_complexity
    category = item.analyzed.analysis.category
    mvp_weeks = item.analyzed.analysis.estimated_mvp_time_weeks

    complexity_line = {
        "Low": "This looks simple to build - a lot of it could come from ready-made tools plus a bit of your own code.",
        "Medium": "This is medium difficulty - you would need a working app plus 1-2 features that genuinely work well.",
        "High": "This is a harder build - it likely needs real technical depth before it feels like a finished product.",
    }.get(complexity, "How hard this is to build isn't clear from the listing alone - worth a closer look.")

    return (
        f"Pick ONE core problem this solves, build just that one part first, and show it to "
        f"5-10 people in the \\"{category}\\" space before adding anything else. {complexity_line} "
        f"Rough time to a testable first version: {mvp_weeks}."
    )


class ReportGenerator:
    def __init__(self, output_dir: str | Path, top_n: int = 5):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.top_n = top_n

    def generate(
        self,
        scored: list[ScoredStartup],
        trends: TrendReport,
        run_date: date | None = None,
    ) -> Path:
        run_date = run_date or date.today()
        ranked = sorted(scored, key=lambda s: s.score, reverse=True)
        top = ranked[: self.top_n]

        md = self._render(ranked, top, trends, run_date)
        out_path = self.output_dir / f"{run_date.isoformat()}.md"
        out_path.write_text(md, encoding="utf-8")
        return out_path

    def _render(
        self,
        ranked: list[ScoredStartup],
        top: list[ScoredStartup],
        trends: TrendReport,
        run_date: date,
    ) -> str:
        lines: list[str] = []
        add = lines.append

        add(f"# Startup Scout AI - Weekly Report ({run_date.isoformat()})")
        add("")
        add("## Executive Summary")
        add(
            f"Collected and scored {len(ranked)} candidate opportunities this week. "
            f"{len(top)} are highlighted below as the strongest matches for Varun's profile."
        )
        add("")

        add("## Top 5 Opportunities")
        for i, item in enumerate(top, start=1):
            a = item.analyzed.analysis
            add(f"### {i}. {item.name} - Score: {item.score}/100")
            add(f"- **Source:** {item.analyzed.raw.source} | **Category:** {a.category}")
            add(f"- **URL:** {item.analyzed.raw.url}")
            add(f"- **What they do:** {_plain_what_they_do(item)}")
            add(f"- **How you could build something like this:** {_plain_how_to_build(item)}")
            add(f"- **India suitability:** {a.india_suitability}")
            add(f"- **Estimated MVP cost:** {a.estimated_mvp_cost_inr} | **Time:** {a.estimated_mvp_time_weeks}")
            add(f"- **Id (for feedback):** `{item.id}`")
            add("")

        add("## Trend Analysis")
        add("### Fastest Growing Categories")
        if trends.fastest_growing:
            for category, growth in trends.fastest_growing:
                add(f"- {category}: {growth}")
        else:
            add("- Not enough historical data yet - check back after a few weeks of runs.")
        add("")

        add("### New Technologies")
        add("- (Populated once LLM analysis mode is enabled - see `analysis.mode` in config.yaml)")
        add("")

        add("### New Business Models")
        add("- (Populated once LLM analysis mode is enabled - see `analysis.mode` in config.yaml)")
        add("")

        if top:
            best = top[0]
            a = best.analyzed.analysis
            add("## Recommended Opportunity of the Week")
            add(f"**{best.name}** ({a.category}) - Score {best.score}/100")
            add("")

            add('## "Why This Fits Varun"')
            add(
                f"- Skills overlap: {best.breakdown.skills_match}/10\\n"
                f"- Interest alignment: {best.breakdown.interests_match}/10\\n"
                f"- Investment fit: {best.breakdown.low_investment}/10\\n"
                f"- India readiness: {best.breakdown.india_readiness}/10\\n"
                f"- AI potential: {best.breakdown.ai_potential}/10"
            )
            add("")

            add("## 30-Day MVP Plan")
            add("1. Week 1: Validate demand (10 customer conversations, landing page + waitlist).")
            add("2. Week 2: Build a thin-slice MVP covering the single core workflow.")
            add("3. Week 3: Onboard 5-10 pilot users, collect feedback, iterate pricing.")
            add("4. Week 4: Public launch (Product Hunt / Hacker News / LinkedIn) + first paid conversions.")
            add("")

            add("## Risks")
            add(f"- {a.potential_risks}")
            add("")

            add("## Estimated Budget")
            add(f"- {a.estimated_mvp_cost_inr} (within the Rs 5 lakh preferred cap)")
            add("")

            add("## Expected Timeline")
            add(f"- MVP: {a.estimated_mvp_time_weeks}; 30-day plan above to first paying customers.")
            add("")

            add("## Recommended Tech Stack")
            add(
                "- Backend: Python (FastAPI), SQLite/Postgres\\n"
                "- Frontend: React or a no-code tool for the MVP\\n"
                "- AI: Claude API for any AI-powered features\\n"
                "- Infra: GitHub Actions for CI/CD, a low-cost cloud host (Railway/Render/AWS free tier)"
            )
            add("")
        else:
            add("## Recommended Opportunity of the Week")
            add("- No candidates scored this week - check connector configuration.")
            add("")

        return "\\n".join(lines)
'''

TEST_TRENDS_PY = '''from datetime import date, timedelta

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
'''

CATEGORIZE_EXTRA_TEST = '''

def test_own_description_beats_generic_source_tag():
    # Regression test: a YC-style generic industry tag ("Developer Tools")
    # should not out-vote a clear signal in the company's own description.
    s = RawStartup(
        source="y_combinator",
        name="Klarify",
        url="",
        description="AI Agent for Therapists",
        tags=["y_combinator", "Developer Tools"],
    )
    assert categorize(s) == "AI SaaS"
'''


def main():
    trends_path = ROOT / "startup_scout" / "trends.py"
    trends_path.write_text(TRENDS_PY, encoding="utf-8")
    print(f"Wrote {trends_path}")

    categorize_path = ROOT / "startup_scout" / "categorize.py"
    categorize_path.write_text(CATEGORIZE_PY, encoding="utf-8")
    print(f"Wrote {categorize_path}")

    report_path = ROOT / "startup_scout" / "report.py"
    report_path.write_text(REPORT_PY, encoding="utf-8")
    print(f"Wrote {report_path}")

    test_trends_path = ROOT / "tests" / "test_trends.py"
    test_trends_path.write_text(TEST_TRENDS_PY, encoding="utf-8")
    print(f"Wrote {test_trends_path}")

    test_categorize_path = ROOT / "tests" / "test_categorize.py"
    content = test_categorize_path.read_text(encoding="utf-8")
    if "test_own_description_beats_generic_source_tag" in content:
        print(f"{test_categorize_path} already up to date, skipping")
    else:
        test_categorize_path.write_text(content.rstrip("\n") + "\n" + CATEGORIZE_EXTRA_TEST, encoding="utf-8")
        print(f"Updated {test_categorize_path}")

    print(
        "\nAll done. Now run: python -m pytest\n"
        "Trend percentages will now show 'New this week (N found)' until a\n"
        "category has real history in two consecutive weekly runs, and\n"
        "categorization now trusts a company's own description 3x more than\n"
        "any generic source tag."
    )


if __name__ == "__main__":
    main()

# END OF FILE MARKER trend-category-fix-v2
