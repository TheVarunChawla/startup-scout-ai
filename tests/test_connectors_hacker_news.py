from unittest.mock import Mock, patch

from startup_scout.connectors.hacker_news import HackerNewsConnector


def test_fetch_parses_hits():
    fake_response = Mock()
    fake_response.raise_for_status = lambda: None
    fake_response.json = lambda: {
        "hits": [
            {
                "title": "Show HN: My Cool Startup",
                "url": "https://example.com",
                "story_text": None,
                "points": 42,
                "num_comments": 5,
                "author": "someone",
                "objectID": "123",
                "_tags": ["show_hn"],
            }
        ]
    }
    with patch("startup_scout.connectors.hacker_news.requests.get", return_value=fake_response) as mock_get:
        connector = HackerNewsConnector({"query": "startup", "max_results": 10})
        results = connector.fetch()

    assert mock_get.called
    assert len(results) == 1
    assert results[0].name == "My Cool Startup"
    assert results[0].source == "hacker_news"
    assert results[0].raw_meta["points"] == 42


def test_fetch_skips_items_without_title():
    fake_response = Mock()
    fake_response.raise_for_status = lambda: None
    fake_response.json = lambda: {"hits": [{"title": "", "url": "https://example.com"}]}
    with patch("startup_scout.connectors.hacker_news.requests.get", return_value=fake_response):
        connector = HackerNewsConnector({})
        results = connector.fetch()
    assert results == []


def test_safe_fetch_swallows_exceptions():
    with patch("startup_scout.connectors.hacker_news.requests.get", side_effect=ConnectionError("boom")):
        connector = HackerNewsConnector({})
        results = connector.safe_fetch()
    assert results == []
