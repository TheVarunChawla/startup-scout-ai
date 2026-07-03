from startup_scout.analysis import AIAnalyzer, _looks_ai_driven
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
