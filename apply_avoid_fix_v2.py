"""
One-off script to fix a real scoring bug: the "avoid" list (Restaurants,
Heavy Manufacturing, Offline Retail, Inventory-heavy businesses) never
actually excluded anything, because it only checked the assigned
CATEGORY label ("B2B Software", "AI SaaS", etc.) against the avoid
list - and none of our category names contain words like "retail" or
"inventory", so the check was structurally incapable of firing. This
let Tridly (a POS + inventory tracker) score 69.2/100 and land in the
top 5, directly contradicting a stated hard constraint.

Fix: check the actual listing text (name + description + tags) against
a curated keyword list per avoid category, and if it matches, hard-cap
the final score at 5/100 - low enough that it can never compete with a
genuinely good match, regardless of how well it scores on every other
criterion.

Usage: put this file in the ROOT of your startup-scout-ai_repo folder
(next to main.py) and run:

    python apply_avoid_fix_v2.py

Then:

    python -m pytest
    git add -A
    git commit -m "Fix avoid-list: check listing text, not just category label, and hard-cap matches"
    git push
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

SCORING_PY = '''"""Personal scoring: maps an AnalyzedStartup -> 0-100 score against
Varun's profile (config/profile.yaml).

Design: each criterion produces a 0-10 sub-score, weights (summing to
100) come from config.yaml so tuning "what matters" doesn't require a
code change. Memory-based adjustments (see memory.py) are applied last,
as a bounded bonus/penalty, so historical feedback nudges rankings
without ever letting it overwhelm the base fit-to-profile score.

Avoid-list items (config/profile.yaml `avoid:`) are a hard constraint,
not just a soft scoring criterion - a match hard-caps the final score
so an avoided business can never outrank a genuinely good one, no
matter how well it scores on every other sub-criterion.
"""
from __future__ import annotations

import re

from startup_scout.memory import MemoryStore
from startup_scout.models import AnalyzedStartup, ScoreBreakdown, ScoredStartup

MAX_MEMORY_ADJUSTMENT = 10.0
AVOID_HARD_CAP = 5.0

_SKILL_STOPWORDS = {"and", "or", "the", "of", "for"}

# Curated substring triggers per avoid label. Checking against the raw
# label text alone ("Inventory-heavy businesses") would almost never
# match real listing text verbatim - these are the actual words a
# listing is likely to use.
AVOID_KEYWORDS: dict[str, list[str]] = {
    "restaurants": ["restaurant", "cafe", "diner", "eatery", "food truck", "menu ordering"],
    "heavy manufacturing": ["manufacturing", "factory", "assembly line", "heavy machinery", "industrial plant"],
    "offline retail": ["retail store", "brick and mortar", "physical store", "point of sale", "storefront", "in-store"],
    "inventory-heavy businesses": ["inventory", "warehousing", "warehouse", "stock management", "supply chain logistics"],
}


def _tokenize_skill(skill: str) -> list[str]:
    """Break a (possibly multi-word) skill into its significant words, so
    "Cyber Security" matches text that only says "security" - requiring
    the full literal phrase was systematically under-scoring relevant
    listings that only used part of a two-word skill name."""
    words = re.findall(r"[a-z0-9]+", skill.lower())
    return [w for w in words if w not in _SKILL_STOPWORDS]


def _is_avoided(profile: dict, text: str) -> bool:
    avoid_labels = [a.lower() for a in profile.get("avoid", [])]
    for label in avoid_labels:
        keywords = AVOID_KEYWORDS.get(label, [label])
        if any(kw in text for kw in keywords):
            return True
    return False


class PersonalScorer:
    def __init__(self, weights: dict[str, float], profile: dict, memory: MemoryStore | None = None):
        self.weights = weights
        self.profile = profile
        self.memory = memory

    def score(self, analyzed: AnalyzedStartup) -> ScoredStartup:
        text = _searchable_text(analyzed)
        avoided = _is_avoided(self.profile, text)

        sub_scores = {
            "skills_match": self._skills_match(text),
            "interests_match": 0.0 if avoided else self._interests_match(analyzed.analysis.category),
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
        if avoided:
            final_score = min(final_score, AVOID_HARD_CAP)

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
        cat_lower = category.lower()
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

TEST_APPEND = '''

def test_avoid_list_hard_caps_inventory_pos_listing():
    scorer = PersonalScorer(WEIGHTS, PROFILE, memory=None)
    tridly_style = _analyzed(category="B2B Software", cost="\\u20b975,000", india="High - test")
    tridly_style.raw.name = "Tridly"
    tridly_style.raw.description = (
        "An all-in-one POS, Smart Inventory Tracker, Automated Invoicing "
        "system, and Instant WhatsApp Store builder for small businesses."
    )
    result = scorer.score(tridly_style)
    assert result.score <= 5.0


def test_avoid_list_hard_caps_restaurant_listing():
    scorer = PersonalScorer(WEIGHTS, PROFILE, memory=None)
    restaurant_style = _analyzed(category="Other")
    restaurant_style.raw.name = "TableTime"
    restaurant_style.raw.description = "A reservation and table management app for restaurants and cafes."
    result = scorer.score(restaurant_style)
    assert result.score <= 5.0


def test_avoid_list_does_not_affect_unrelated_listings():
    scorer = PersonalScorer(WEIGHTS, PROFILE, memory=None)
    good = _analyzed(category="AI SaaS")
    result = scorer.score(good)
    assert result.score > 5.0
'''


def main():
    scoring_path = ROOT / "startup_scout" / "scoring.py"
    scoring_path.write_text(SCORING_PY, encoding="utf-8")
    print(f"Wrote {scoring_path}")

    test_scoring_path = ROOT / "tests" / "test_scoring.py"
    content = test_scoring_path.read_text(encoding="utf-8")

    old_profile_avoid = '"avoid": ["Restaurants", "Offline Retail"],'
    new_profile_avoid = '"avoid": ["Restaurants", "Heavy Manufacturing", "Offline Retail", "Inventory-heavy businesses"],'
    if new_profile_avoid in content:
        print(f"{test_scoring_path} PROFILE avoid list already up to date")
    elif old_profile_avoid in content:
        content = content.replace(old_profile_avoid, new_profile_avoid)
        test_scoring_path.write_text(content, encoding="utf-8")
        print(f"Widened avoid list in {test_scoring_path}")
    else:
        print(f"WARNING: expected PROFILE avoid line not found in {test_scoring_path} - check manually")

    content = test_scoring_path.read_text(encoding="utf-8")
    if "test_avoid_list_hard_caps_inventory_pos_listing" in content:
        print(f"{test_scoring_path} already has the new tests, skipping")
    else:
        test_scoring_path.write_text(content + TEST_APPEND, encoding="utf-8")
        print(f"Appended new tests to {test_scoring_path}")

    print("All done. Now run: python -m pytest")


if __name__ == "__main__":
    main()

# END OF FILE MARKER 12345
