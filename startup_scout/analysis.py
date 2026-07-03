"""AI analysis stage.

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
_AI_ACRONYM_PATTERN = re.compile(r"\b(ai|ml|llm|gpt|nlp|genai)\b")
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
        "Low": ("\u20b920,000 - \u20b975,000", "1-3 weeks"),
        "Medium": ("\u20b975,000 - \u20b93,00,000", "4-8 weeks"),
        "High": ("\u20b93,00,000 - \u20b910,00,000+", "10+ weeks"),
    }[complexity]


def _estimate_india_suitability(text: str) -> str:
    if any(k in text for k in ("us only", "usa only", "requires fda", "requires ce mark")):
        return "Low - regulatory/geographic constraints noted in listing"
    if any(k in text for k in ("global", "remote", "saas", "api", "developer")):
        return "High - digital-first products port well to India"
    return "Medium - needs manual localization review"
