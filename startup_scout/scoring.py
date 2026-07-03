"""Personal scoring: maps an AnalyzedStartup -> 0-100 score against
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
            if words and any(re.search(rf"\b{re.escape(w)}\b", text) for w in words):
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
        # Parse the *lower* bound out of strings like "\u20b975,000 - \u20b93,00,000".
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
