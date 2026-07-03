"""
One-off script that simplifies the project per your request:

1. Adds a real Y Combinator connector. YC has no official API, but a
   free, openly published project (https://github.com/yc-oss/api)
   fetches YC's own public Algolia search index once a day via its own
   GitHub Actions workflow (not by scraping rendered HTML) and
   publishes the result as plain static JSON files. This connector just
   does a normal HTTP GET against those files - no scraping, no
   credentials, no ToS gray area.

2. Turns OFF Hacker News, Product Hunt, TechCrunch, and Reddit in
   config.yaml (enabled: false). Their code stays in the repo (it took
   real effort to build and test, and disabling costs nothing at
   runtime) but none of them will run anymore - only Y Combinator will.

3. Switches the GitHub Actions schedule from daily to weekly (every
   Monday). Bonus: the existing 7-day trend window now lines up exactly
   with "since last week's report" instead of being an awkward daily
   comparison.

4. Rewrites the report to explain every pick in plain English: what the
   company actually does (using YC's own one-liner, which is usually
   much clearer than an auto-extracted description) and a simple,
   jargon-free note on how you could build something similar yourself.

5. Updates tests/test_report.py's "Day" wording to "Week" to match.

Usage: put this file in the ROOT of your startup-scout-ai_repo folder
(next to main.py) and run:

    python apply_yc_simplify_final.py

Then:

    python -m pytest
    git add -A
    git commit -m "Simplify to Y Combinator only, weekly cadence, plain-English report"
    git push
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

YCOMBINATOR_PY = '''"""Y Combinator connector.

Y Combinator has no official public API and no bulk export. This
connector uses a free, openly published mirror of YC's own public
Algolia search index (the same data that powers the "Startups"
directory on ycombinator.com), maintained at
https://github.com/yc-oss/api. That project fetches YC's Algolia index
directly (not by scraping rendered HTML) once a day via its own GitHub
Actions workflow, and publishes the result as static JSON files - so
this connector just does a plain HTTP GET, no scraping and no
credentials needed.

To keep results fresh and small, this pulls specific YC batches (by
default, the most recent ones) rather than "all 5,900+ companies ever
funded". Update `batches` in config.yaml every ~6 months when YC
announces a new batch (check https://yc-oss.github.io/api/meta.json
for the current list).
"""
from __future__ import annotations

import logging

import requests

from startup_scout.connectors.base import BaseConnector
from startup_scout.models import RawStartup

logger = logging.getLogger(__name__)

BATCH_URL_TEMPLATE = "https://yc-oss.github.io/api/batches/{batch}.json"
DEFAULT_BATCHES = ["summer-2026", "spring-2026", "winter-2026"]


class YCombinatorConnector(BaseConnector):
    name = "y_combinator"

    def fetch(self) -> list[RawStartup]:
        batches = self.settings.get("batches", DEFAULT_BATCHES)
        max_per_batch = int(self.settings.get("max_per_batch", 200))

        results: list[RawStartup] = []
        for batch in batches:
            results.extend(self._fetch_batch(batch, max_per_batch))
        return results

    def _fetch_batch(self, batch: str, limit: int) -> list[RawStartup]:
        url = BATCH_URL_TEMPLATE.format(batch=batch)
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": "startup-scout-ai/0.1"})
            resp.raise_for_status()
            companies = resp.json()
        except Exception:
            logger.exception("Y Combinator: failed to fetch batch %r", batch)
            return []

        results: list[RawStartup] = []
        for company in companies[:limit]:
            name = (company.get("name") or "").strip()
            if not name:
                continue
            one_liner = (company.get("one_liner") or "").strip()
            long_description = (company.get("long_description") or "").strip()
            tags = list(company.get("tags") or [])
            industries = list(company.get("industries") or [])

            results.append(
                RawStartup(
                    source=self.name,
                    name=name,
                    url=company.get("website") or company.get("url") or "",
                    description=long_description or one_liner,
                    tags=["y_combinator", batch] + industries + tags,
                    raw_meta={
                        "one_liner": one_liner,
                        "batch": company.get("batch"),
                        "team_size": company.get("team_size"),
                        "yc_url": company.get("url"),
                    },
                )
            )
        return results
'''

CONNECTORS_INIT_PY = '''"""Connector registry: maps config `type` strings to connector classes."""
from __future__ import annotations

from startup_scout.connectors.base import BaseConnector
from startup_scout.connectors.hacker_news import HackerNewsConnector
from startup_scout.connectors.product_hunt import ProductHuntConnector
from startup_scout.connectors.reddit import RedditConnector
from startup_scout.connectors.stubs import StubConnector
from startup_scout.connectors.techcrunch import TechCrunchConnector
from startup_scout.connectors.ycombinator import YCombinatorConnector

CONNECTOR_TYPES: dict[str, type[BaseConnector]] = {
    "hacker_news": HackerNewsConnector,
    "product_hunt": ProductHuntConnector,
    "techcrunch": TechCrunchConnector,
    "reddit": RedditConnector,
    "y_combinator": YCombinatorConnector,
    "stub": StubConnector,
}

__all__ = [
    "BaseConnector",
    "HackerNewsConnector",
    "ProductHuntConnector",
    "TechCrunchConnector",
    "RedditConnector",
    "YCombinatorConnector",
    "StubConnector",
    "CONNECTOR_TYPES",
]
'''

TEST_YCOMBINATOR_PY = '''from unittest.mock import Mock, patch

from startup_scout.connectors.ycombinator import YCombinatorConnector

FAKE_BATCH_RESPONSE = [
    {
        "name": "SecureStack",
        "one_liner": "Automated security scanning for Kubernetes clusters.",
        "long_description": "SecureStack scans your Kubernetes clusters for misconfigurations and vulnerabilities.",
        "website": "https://securestack.example.com",
        "url": "https://www.ycombinator.com/companies/securestack",
        "tags": ["Security", "DevSecOps", "Kubernetes"],
        "industries": ["B2B", "Security"],
        "batch": "Summer 2026",
        "team_size": 4,
    },
    {
        "name": "",
        "one_liner": "Should be skipped, no name.",
        "website": "https://example.com",
    },
]


def test_fetch_parses_batch_json():
    fake_response = Mock()
    fake_response.raise_for_status = lambda: None
    fake_response.json = lambda: FAKE_BATCH_RESPONSE

    with patch("startup_scout.connectors.ycombinator.requests.get", return_value=fake_response) as mock_get:
        connector = YCombinatorConnector({"batches": ["summer-2026"], "max_per_batch": 10})
        results = connector.fetch()

    assert mock_get.called
    assert len(results) == 1
    assert results[0].name == "SecureStack"
    assert results[0].source == "y_combinator"
    assert "Security" in results[0].tags
    assert results[0].raw_meta["one_liner"] == "Automated security scanning for Kubernetes clusters."


def test_fetch_combines_multiple_batches():
    fake_response = Mock()
    fake_response.raise_for_status = lambda: None
    fake_response.json = lambda: FAKE_BATCH_RESPONSE

    with patch("startup_scout.connectors.ycombinator.requests.get", return_value=fake_response):
        connector = YCombinatorConnector({"batches": ["summer-2026", "spring-2026"], "max_per_batch": 10})
        results = connector.fetch()

    # 1 valid company per batch (the empty-name one is skipped) x 2 batches
    assert len(results) == 2


def test_max_per_batch_is_respected():
    many_companies = [
        {"name": f"Company{i}", "one_liner": "x", "website": "https://example.com"}
        for i in range(20)
    ]
    fake_response = Mock()
    fake_response.raise_for_status = lambda: None
    fake_response.json = lambda: many_companies

    with patch("startup_scout.connectors.ycombinator.requests.get", return_value=fake_response):
        connector = YCombinatorConnector({"batches": ["summer-2026"], "max_per_batch": 5})
        results = connector.fetch()

    assert len(results) == 5


def test_safe_fetch_swallows_exceptions():
    with patch("startup_scout.connectors.ycombinator.requests.get", side_effect=ConnectionError("boom")):
        connector = YCombinatorConnector({"batches": ["summer-2026"]})
        results = connector.safe_fetch()
    assert results == []
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
                add(f"- {category}: {growth:+.0%} vs. last week")
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

WORKFLOW_YML = '''name: Weekly Startup Scout Run

on:
  schedule:
    - cron: "30 3 * * 1"  # Every Monday, 09:00 IST
  workflow_dispatch: {}

permissions:
  contents: write

jobs:
  run-pipeline:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run weekly pipeline
        env:
          PRODUCT_HUNT_TOKEN: ${{ secrets.PRODUCT_HUNT_TOKEN }}
          REDDIT_CLIENT_ID: ${{ secrets.REDDIT_CLIENT_ID }}
          REDDIT_CLIENT_SECRET: ${{ secrets.REDDIT_CLIENT_SECRET }}
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
        run: python main.py run

      - name: Commit report and database
        run: |
          git config user.name "startup-scout-bot"
          git config user.email "actions@github.com"
          git add -f reports/ data/
          git diff --cached --quiet || git commit -m "Weekly report: $(date +%F)"
          git push
'''

TEST_REPORT_REPLACEMENTS = [
    ("Recommended Opportunity of the Day", "Recommended Opportunity of the Week"),
    ("No candidates scored today", "No candidates scored this week"),
]


def main():
    yc_path = ROOT / "startup_scout" / "connectors" / "ycombinator.py"
    yc_path.write_text(YCOMBINATOR_PY, encoding="utf-8")
    print(f"Wrote {yc_path}")

    init_path = ROOT / "startup_scout" / "connectors" / "__init__.py"
    init_path.write_text(CONNECTORS_INIT_PY, encoding="utf-8")
    print(f"Wrote {init_path}")

    test_path = ROOT / "tests" / "test_connectors_ycombinator.py"
    test_path.write_text(TEST_YCOMBINATOR_PY, encoding="utf-8")
    print(f"Wrote {test_path}")

    report_path = ROOT / "startup_scout" / "report.py"
    report_path.write_text(REPORT_PY, encoding="utf-8")
    print(f"Wrote {report_path}")

    workflow_path = ROOT / ".github" / "workflows" / "daily.yml"
    workflow_path.write_text(WORKFLOW_YML, encoding="utf-8")
    print(f"Wrote {workflow_path} (now runs weekly, every Monday)")

    test_report_path = ROOT / "tests" / "test_report.py"
    if test_report_path.exists():
        report_test_content = test_report_path.read_text(encoding="utf-8")
        report_test_changed = False
        for old_text, new_text in TEST_REPORT_REPLACEMENTS:
            if old_text in report_test_content:
                report_test_content = report_test_content.replace(old_text, new_text)
                report_test_changed = True
        if report_test_changed:
            test_report_path.write_text(report_test_content, encoding="utf-8")
            print(f"Updated {test_report_path} (Day -> Week wording)")
        else:
            print(f"{test_report_path} already up to date, skipping")

    config_path = ROOT / "config" / "config.yaml"
    content = config_path.read_text(encoding="utf-8")

    replacements = [
        ("""  hacker_news:
    enabled: true
    type: hacker_news""", """  hacker_news:
    enabled: false
    type: hacker_news"""),
        ("""  product_hunt:
    enabled: true
    type: product_hunt""", """  product_hunt:
    enabled: false
    type: product_hunt"""),
        ("""  techcrunch:
    enabled: true
    type: techcrunch""", """  techcrunch:
    enabled: false
    type: techcrunch"""),
        ("""  reddit_startups:
    enabled: true
    type: reddit""", """  reddit_startups:
    enabled: false
    type: reddit"""),
        ("""  y_combinator:
    enabled: false
    type: stub
    reason: "No public bulk API; YC company directory has no export endpoint.\"""", """  y_combinator:
    enabled: true
    type: y_combinator
    batches: ["summer-2026", "spring-2026", "winter-2026"]
    max_per_batch: 200
    # update the batch list every ~6 months when YC announces a new one -
    # see https://yc-oss.github.io/api/meta.json for the current list"""),
    ]

    changed = False
    for old, new in replacements:
        if new in content:
            continue
        if old in content:
            content = content.replace(old, new)
            changed = True
        else:
            print(f"WARNING: expected block not found (already edited differently?):\n{old[:60]}...")

    if changed:
        config_path.write_text(content, encoding="utf-8")
        print(f"Updated {config_path}")
    else:
        print(f"{config_path} already up to date, skipping")

    print(
        "\nAll done. Now run: python -m pytest\n"
        "Only Y Combinator will collect data going forward - Hacker News, "
        "Product Hunt, TechCrunch, and Reddit are turned off (their code is "
        "still there if you want them back later, just flip enabled: true)."
    )


if __name__ == "__main__":
    main()

# END OF FILE MARKER yc-simplify-final
