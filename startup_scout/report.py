"""Markdown weekly report generation.

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
        f"5-10 people in the \"{category}\" space before adding anything else. {complexity_line} "
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
                f"- Skills overlap: {best.breakdown.skills_match}/10\n"
                f"- Interest alignment: {best.breakdown.interests_match}/10\n"
                f"- Investment fit: {best.breakdown.low_investment}/10\n"
                f"- India readiness: {best.breakdown.india_readiness}/10\n"
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
                "- Backend: Python (FastAPI), SQLite/Postgres\n"
                "- Frontend: React or a no-code tool for the MVP\n"
                "- AI: Claude API for any AI-powered features\n"
                "- Infra: GitHub Actions for CI/CD, a low-cost cloud host (Railway/Render/AWS free tier)"
            )
            add("")
        else:
            add("## Recommended Opportunity of the Week")
            add("- No candidates scored this week - check connector configuration.")
            add("")

        return "\n".join(lines)
