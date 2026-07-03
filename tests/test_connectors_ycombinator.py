from unittest.mock import Mock, patch

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
