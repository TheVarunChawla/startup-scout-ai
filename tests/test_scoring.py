from startup_scout.models import Analysis, AnalyzedStartup, RawStartup
from startup_scout.scoring import PersonalScorer

WEIGHTS = {
    "skills_match": 15,
    "interests_match": 15,
    "low_investment": 10,
    "india_readiness": 10,
    "ai_potential": 10,
    "ease_of_execution": 10,
    "revenue_potential": 10,
    "competition": 10,
    "scalability": 5,
    "long_term_opportunity": 5,
}

PROFILE = {
    "technical_skills": ["Cyber Security", "AI", "Python", "Automation"],
    "business_interests": ["AI SaaS", "Cyber Security"],
    "avoid": ["Restaurants", "Heavy Manufacturing", "Offline Retail", "Inventory-heavy businesses"],
    "preferred_investment_inr_max": 500000,
}


def _analyzed(category="AI SaaS", cost="₹50,000", complexity="Low", india="High - test", ai="Likely AI-driven"):
    raw = RawStartup(
        source="x", name="SecureAI", url="", description="AI powered cyber security automation tool",
        tags=["python"],
    )
    analysis = Analysis(
        category=category,
        estimated_mvp_cost_inr=cost,
        technical_complexity=complexity,
        india_suitability=india,
        ai_usage=ai,
        business_model="Subscription SaaS",
    )
    return AnalyzedStartup(raw=raw, analysis=analysis)


def test_score_in_valid_range():
    scorer = PersonalScorer(WEIGHTS, PROFILE, memory=None)
    result = scorer.score(_analyzed())
    assert 0 <= result.score <= 100


def test_good_fit_scores_higher_than_avoided_category():
    scorer = PersonalScorer(WEIGHTS, PROFILE, memory=None)
    good = scorer.score(_analyzed(category="AI SaaS"))
    avoided = scorer.score(_analyzed(category="Restaurants"))
    assert good.score > avoided.score


def test_high_complexity_scores_lower_than_low_complexity():
    scorer = PersonalScorer(WEIGHTS, PROFILE, memory=None)
    low = scorer.score(_analyzed(complexity="Low"))
    high = scorer.score(_analyzed(complexity="High"))
    assert low.score > high.score


def test_weights_sum_to_100_in_sample_config():
    assert sum(WEIGHTS.values()) == 100


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


def test_avoid_list_hard_caps_inventory_pos_listing():
    scorer = PersonalScorer(WEIGHTS, PROFILE, memory=None)
    tridly_style = _analyzed(category="B2B Software", cost="\u20b975,000", india="High - test")
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
