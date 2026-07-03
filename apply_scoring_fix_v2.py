"""
One-off script to fix two scoring accuracy bugs found in real reports:

1. AI-potential detection used raw substring checks for "ai"/"ml", which
   false-positive-match inside ordinary words ("domain", "email",
   "waiting" all contain "ai"; "html" contains "ml"). Fixed to use
   word-boundary matching for short acronyms, keeping substring matching
   only for longer, unambiguous phrases ("machine learning", "chatgpt").

2. Skills-match scoring required a profile skill's *exact* multi-word
   phrase ("Cyber Security") to appear verbatim in a listing. A
   Kubernetes security scanner that says "security" but never the exact
   phrase "cyber security" scored 5/10 on skills overlap despite being
   squarely on-topic. Fixed to match on any significant word within a
   multi-word skill.

Usage: put this file in the ROOT of your startup-scout-ai_repo folder
(next to main.py) and run:

    python apply_scoring_fix_v2.py

Then:

    python -m pytest
    git add -A
    git commit -m "Fix AI-detection false positives and overly literal skills matching"
    git push
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

ANALYSIS_PY = '''"""AI analysis stage.

Two modes, selected via config.yaml `analysis.mode`:

- "heuristic" (default): fast, free, deterministic rule-of-thumb
  estimates. This is what runs in CI/tests and for anyone who hasn't
  set an API key yet - the pipeline should always produce a full report
  end-to-end with zero external LLM dependency.
- "llm": calls Anthropic's API with a structured prompt and parses JSON
  back into the same Analysis fields. Requires ANTHROPIC_API_KEY.

Both paths return the same `Analysis` dataclass, so scoring/reporting
code never needs to know which mode produced it.
"""
from __future__ import annotations

import json
import logging
import os
import re

from startup_scout.categorize import categorize
from startup_scout.models import Analysis, AnalyzedStartup, RawStartup

logger = logging.getLogger(__name__)

ANALYSIS_PROMPT_TEMPLATE = """You are a startup analyst. Analyze this startup and respond with ONLY a
JSON object (no markdown fences) with these exact keys: problem, customer_type,
business_model, pricing_model, estimated_market_size, ai_usage,
technical_complexity, founder_advantage, india_suitability,
estimated_mvp_cost_inr, estimated_mvp_time_weeks, competitive_landscape,
possible_improvements, potential_risks, why_now, long_term_opportunity.

Founder profile: {profile_summary}

Startup name: {name}
Description: {description}
Source: {source}
Tags: {tags}
"""

# Standalone acronyms need word-boundary matching - checking these as raw
# substrings produces constant false positives ("ai" inside "domain",
# "email", "waiting"; "ml" inside "html"). Longer, more specific phrases
# are safe to match as plain substrings since they rarely appear inside
# unrelated words.
_AI_ACRONYM_PATTERN = re.compile(r"\\b(ai|ml|llm|gpt|nlp|genai)\\b")
_AI_PHRASE_KEYWORDS = (
    "artificial intelligence", "machine learning", "generative ai",
    "large language model", "neural network", "deep learning",
    "chatgpt", "openai", "computer vision", "natural language processing",
)


def _looks_ai_driven(text: str) -> bool:
    lowered = text.lower()
    if _AI_ACRONYM_PATTERN.search(lowered):
        return True
    return any(phrase in lowered for phrase in _AI_PHRASE_KEYWORDS)


class AIAnalyzer:
    def __init__(self, config, profile: dict):
        self.mode = config.analysis_settings.get("mode", "heuristic")
        self.model = config.analysis_settings.get("llm_model", "claude-sonnet-5")
        self.profile = profile

    def analyze(self, raw: RawStartup) -> AnalyzedStartup:
        category = categorize(raw)
        if self.mode == "llm" and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                analysis = self._analyze_with_llm(raw)
                analysis.category = category
                return AnalyzedStartup(raw=raw, analysis=analysis)
            except Exception:
                logger.exception(
                    "%s: LLM analysis failed, falling back to heuristic", raw.name
                )
        analysis = self._analyze_heuristic(raw)
        analysis.category = category
        return AnalyzedStartup(raw=raw, analysis=analysis)

    def _analyze_with_llm(self, raw: RawStartup) -> Analysis:
        import anthropic  # imported lazily - optional dependency

        client = anthropic.Anthropic()
        profile_summary = (
            f"{self.profile.get('profession')}, skills: "
            f"{', '.join(self.profile.get('technical_skills', []))}"
        )
        prompt = ANALYSIS_PROMPT_TEMPLATE.format(
            profile_summary=profile_summary,
            name=raw.name,
            description=raw.description,
            source=raw.source,
            tags=", ".join(raw.tags),
        )
        message = client.messages.create(
            model=self.model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(
            block.text for block in message.content if getattr(block, "type", "") == "text"
        )
        data = json.loads(text)
        valid_fields = Analysis.__dataclass_fields__
        return Analysis(**{k: str(v) for k, v in data.items() if k in valid_fields})

    def _analyze_heuristic(self, raw: RawStartup) -> Analysis:
        text = f"{raw.name} {raw.description} {' '.join(raw.tags)}".lower()
        ai_usage = "Likely AI-driven" if _looks_ai_driven(text) else "Not evident from listing"
        technical_complexity = _estimate_complexity(text)
        mvp_cost, mvp_weeks = _estimate_mvp(technical_complexity)

        return Analysis(
            problem=f"Inferred from listing: {raw.description[:200] or raw.name}",
            customer_type="B2B" if any(k in text for k in ("enterprise", "team", "business", "b2b")) else "B2C",
            business_model=(
                "Subscription (assumed SaaS default)"
                if "saas" in text or "subscription" in text
                else "Unclear from listing - verify manually"
            ),
            pricing_model="Not disclosed in source listing",
            estimated_market_size="Unknown - requires manual market sizing",
            ai_usage=ai_usage,
            technical_complexity=technical_complexity,
            founder_advantage="Unscored - requires manual founder-fit review",
            india_suitability=_estimate_india_suitability(text),
            estimated_mvp_cost_inr=mvp_cost,
            estimated_mvp_time_weeks=mvp_weeks,
            competitive_landscape="Not assessed (heuristic mode) - enable LLM analysis for a real competitor scan",
            possible_improvements="Not assessed (heuristic mode)",
            potential_risks="Not assessed (heuristic mode)",
            why_now="Not assessed (heuristic mode)",
            long_term_opportunity="Not assessed (heuristic mode)",
        )


def _estimate_complexity(text: str) -> str:
    hard_signals = ("infrastructure", "hardware", "chip", "biotech", "blockchain protocol", "compiler")
    easy_signals = ("template", "notion", "newsletter", "directory", "chrome extension")
    if any(s in text for s in hard_signals):
        return "High"
    if any(s in text for s in easy_signals):
        return "Low"
    return "Medium"


def _estimate_mvp(complexity: str) -> tuple[str, str]:
    return {
        "Low": ("\\u20b920,000 - \\u20b975,000", "1-3 weeks"),
        "Medium": ("\\u20b975,000 - \\u20b93,00,000", "4-8 weeks"),
        "High": ("\\u20b93,00,000 - \\u20b910,00,000+", "10+ weeks"),
    }[complexity]


def _estimate_india_suitability(text: str) -> str:
    if any(k in text for k in ("us only", "usa only", "requires fda", "requires ce mark")):
        return "Low - regulatory/geographic constraints noted in listing"
    if any(k in text for k in ("global", "remote", "saas", "api", "developer")):
        return "High - digital-first products port well to India"
    return "Medium - needs manual localization review"
'''

SCORING_PY = '''"""Personal scoring: maps an AnalyzedStartup -> 0-100 score against
Varun's profile (config/profile.yaml).

Design: each criterion produces a 0-10 sub-score, weights (summing to
100) come from config.yaml so tuning "what matters" doesn't require a
code change. Memory-based adjustments (see memory.py) are applied last,
as a bounded bonus/penalty, so historical feedback nudges rankings
without ever letting it overwhelm the base fit-to-profile score.
"""
from __future__ import annotations

import re

from startup_scout.memory import MemoryStore
from startup_scout.models import AnalyzedStartup, ScoreBreakdown, ScoredStartup

MAX_MEMORY_ADJUSTMENT = 10.0

_SKILL_STOPWORDS = {"and", "or", "the", "of", "for"}


def _tokenize_skill(skill: str) -> list[str]:
    """Break a (possibly multi-word) skill into its significant words, so
    "Cyber Security" matches text that only says "security" - requiring
    the full literal phrase was systematically under-scoring relevant
    listings that only used part of a two-word skill name."""
    words = re.findall(r"[a-z0-9]+", skill.lower())
    return [w for w in words if w not in _SKILL_STOPWORDS]


class PersonalScorer:
    def __init__(self, weights: dict[str, float], profile: dict, memory: MemoryStore | None = None):
        self.weights = weights
        self.profile = profile
        self.memory = memory

    def score(self, analyzed: AnalyzedStartup) -> ScoredStartup:
        text = _searchable_text(analyzed)

        sub_scores = {
            "skills_match": self._skills_match(text),
            "interests_match": self._interests_match(analyzed.analysis.category),
            "low_investment": self._low_investment(analyzed.analysis.estimated_mvp_cost_inr),
            "india_readiness": self._india_readiness(analyzed.analysis.india_suitability),
            "ai_potential": self._ai_potential(analyzed.analysis.ai_usage),
            "ease_of_execution": self._ease_of_execution(analyzed.analysis.technical_complexity),
            "revenue_potential": self._revenue_potential(analyzed.analysis.business_model),
            "competition": self._competition(analyzed.analysis.competitive_landscape),
            "scalability": self._scalability(text),
            "long_term_opportunity": self._long_term(analyzed.analysis.long_term_opportunity),
        }

        weighted_total = 0.0
        for key, sub_score in sub_scores.items():
            weight = self.weights.get(key, 0)
            weighted_total += (sub_score / 10.0) * weight

        memory_adjustment = 0.0
        if self.memory is not None:
            memory_adjustment = self.memory.category_adjustment(
                analyzed.analysis.category, cap=MAX_MEMORY_ADJUSTMENT
            )

        final_score = max(0.0, min(100.0, weighted_total + memory_adjustment))

        breakdown = ScoreBreakdown(memory_adjustment=memory_adjustment, **sub_scores)
        return ScoredStartup(analyzed=analyzed, score=round(final_score, 1), breakdown=breakdown)

    # -- individual sub-scorers, each returns 0-10 -------------------------

    def _skills_match(self, text: str) -> float:
        skills = self.profile.get("technical_skills", [])
        hits = 0
        for skill in skills:
            words = _tokenize_skill(skill)
            if words and any(re.search(rf"\\b{re.escape(w)}\\b", text) for w in words):
                hits += 1
        return min(10.0, hits * 2.5)

    def _interests_match(self, category: str) -> float:
        interests = [i.lower() for i in self.profile.get("business_interests", [])]
        avoid = [a.lower() for a in self.profile.get("avoid", [])]
        cat_lower = category.lower()
        if any(a in cat_lower for a in avoid):
            return 0.0
        return 10.0 if any(i in cat_lower or cat_lower in i for i in interests) else 4.0

    def _low_investment(self, mvp_cost_str: str) -> float:
        # Parse the *lower* bound out of strings like "\\u20b975,000 - \\u20b93,00,000".
        digits = "".join(c for c in mvp_cost_str.split("-")[0] if c.isdigit())
        if not digits:
            return 5.0
        lower_bound = int(digits)
        budget_cap = self.profile.get("preferred_investment_inr_max", 500_000)
        if lower_bound <= budget_cap * 0.2:
            return 10.0
        if lower_bound <= budget_cap:
            return 7.0
        return 2.0

    def _india_readiness(self, india_suitability: str) -> float:
        s = india_suitability.lower()
        if s.startswith("high"):
            return 10.0
        if s.startswith("medium"):
            return 5.0
        if s.startswith("low"):
            return 1.0
        return 5.0

    def _ai_potential(self, ai_usage: str) -> float:
        return 10.0 if "likely ai" in ai_usage.lower() else 3.0

    def _ease_of_execution(self, technical_complexity: str) -> float:
        return {"Low": 10.0, "Medium": 6.0, "High": 2.0}.get(technical_complexity, 5.0)

    def _revenue_potential(self, business_model: str) -> float:
        s = business_model.lower()
        if "subscription" in s or "saas" in s:
            return 10.0
        if "consulting" in s:
            return 7.0
        return 4.0

    def _competition(self, competitive_landscape: str) -> float:
        s = competitive_landscape.lower()
        if "not assessed" in s or not s.strip():
            return 5.0
        if "crowded" in s or "saturated" in s:
            return 2.0
        if "few competitors" in s or "underserved" in s:
            return 9.0
        return 5.0

    def _scalability(self, text: str) -> float:
        return 8.0 if any(k in text for k in ("saas", "digital", "software", "platform", "api")) else 4.0

    def _long_term(self, long_term_opportunity: str) -> float:
        s = long_term_opportunity.lower()
        if "not assessed" in s or not s.strip():
            return 5.0
        return 7.0


def _searchable_text(analyzed: AnalyzedStartup) -> str:
    return " ".join(
        [
            analyzed.raw.name,
            analyzed.raw.description,
            " ".join(analyzed.raw.tags),
            analyzed.analysis.category,
            analyzed.analysis.business_model,
        ]
    ).lower()
'''

TEST_ANALYSIS_PY = '''from startup_scout.analysis import AIAnalyzer, _looks_ai_driven
from startup_scout.models import RawStartup


class _FakeConfig:
    analysis_settings = {"mode": "heuristic", "llm_model": "test"}


def test_ai_word_boundary_avoids_false_positives():
    assert not _looks_ai_driven("this domain remains available via email")
    assert not _looks_ai_driven("html template for a waiting list")


def test_ai_word_boundary_detects_real_ai_mentions():
    assert _looks_ai_driven("an ai-powered assistant")
    assert _looks_ai_driven("built with gpt-4 and llm orchestration")
    assert _looks_ai_driven("uses machine learning models")
    assert _looks_ai_driven("(AI) generated content")


def test_heuristic_analysis_does_not_false_positive_on_geospoof_style_text():
    analyzer = AIAnalyzer(_FakeConfig(), profile={})
    raw = RawStartup(
        source="hacker_news",
        name="GeoSpoof - your VPN hides your IP, but the browser leaks your location",
        url="https://geospoof.com",
        description=(
            "I started building GeoSpoof after I noticed my IP says one country, "
            "but the browser still hands sites my real location. Websites were "
            "flagging me because of this discrepancy, so I remain cautious about "
            "which domain I visit and always double check my email settings again."
        ),
        tags=["hacker-news", "show_hn"],
    )
    analyzed = analyzer.analyze(raw)
    assert analyzed.analysis.ai_usage == "Not evident from listing"


def test_heuristic_analysis_detects_genuine_ai_product():
    analyzer = AIAnalyzer(_FakeConfig(), profile={})
    raw = RawStartup(
        source="product_hunt",
        name="LexAIGuard",
        url="https://lexaiguard.com",
        description="LexAIGuard uses AI to generate audit-ready compliance reports.",
        tags=["product-hunt", "artificial-intelligence"],
    )
    analyzed = analyzer.analyze(raw)
    assert analyzed.analysis.ai_usage == "Likely AI-driven"
'''

TEST_SCORING_APPEND = '''

def test_skills_match_on_partial_word_not_exact_phrase():
    scorer = PersonalScorer(WEIGHTS, PROFILE, memory=None)
    # Profile skill is "Cyber Security" (two words); listing only says
    # "security", never the exact phrase - should still count as a hit.
    k8scan_style = _analyzed(category="Cyber Security")
    k8scan_style.raw.description = "An open-source Kubernetes security scanner running security checks."
    result = scorer.score(k8scan_style)
    assert result.breakdown.skills_match > 0


def test_skills_match_does_not_false_positive_on_unrelated_text():
    scorer = PersonalScorer(WEIGHTS, PROFILE, memory=None)
    unrelated = _analyzed(category="Other")
    unrelated.raw.name = "Random Newsletter Tool"
    unrelated.raw.description = "A simple weekly email digest for readers, no tech skills mentioned here."
    unrelated.raw.tags = []
    result = scorer.score(unrelated)
    assert result.breakdown.skills_match == 0
'''


def main():
    analysis_path = ROOT / "startup_scout" / "analysis.py"
    analysis_path.write_text(ANALYSIS_PY, encoding="utf-8")
    print(f"Wrote {analysis_path}")

    scoring_path = ROOT / "startup_scout" / "scoring.py"
    scoring_path.write_text(SCORING_PY, encoding="utf-8")
    print(f"Wrote {scoring_path}")

    test_analysis_path = ROOT / "tests" / "test_analysis.py"
    test_analysis_path.write_text(TEST_ANALYSIS_PY, encoding="utf-8")
    print(f"Wrote {test_analysis_path}")

    test_scoring_path = ROOT / "tests" / "test_scoring.py"
    content = test_scoring_path.read_text(encoding="utf-8")
    if "test_skills_match_on_partial_word_not_exact_phrase" in content:
        print(f"{test_scoring_path} already has the new tests, skipping")
    else:
        test_scoring_path.write_text(content + TEST_SCORING_APPEND, encoding="utf-8")
        print(f"Updated {test_scoring_path}")

    print("All done. Now run: python -m pytest")


if __name__ == "__main__":
    main()

# END OF FILE - trailing marker to catch truncation issues
