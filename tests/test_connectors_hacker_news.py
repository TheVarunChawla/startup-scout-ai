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


def test_fetch_excludes_ask_hn_threads():
    fake_response = Mock()
    fake_response.raise_for_status = lambda: None
    fake_response.json = lambda: {
        "hits": [
            {
                "title": "Ask HN: How do you validate startup ideas?",
                "url": "https://news.ycombinator.com/item?id=1",
                "_tags": ["story", "ask_hn"],
                "objectID": "1",
            },
            {
                "title": "Show HN: My Cool Startup",
                "url": "https://example.com",
                "_tags": ["story", "show_hn"],
                "objectID": "2",
            },
        ]
    }
    with patch("startup_scout.connectors.hacker_news.requests.get", return_value=fake_response):
        connector = HackerNewsConnector({})
        results = connector.fetch()
    assert len(results) == 1
    assert results[0].name == "My Cool Startup"


def test_fetch_excludes_known_news_domains():
    fake_response = Mock()
    fake_response.raise_for_status = lambda: None
    fake_response.json = lambda: {
        "hits": [
            {
                "title": "Startup sues Big Corp over AI claims",
                "url": "https://www.theregister.com/legal/story",
                "_tags": ["story"],
                "objectID": "3",
            },
            {
                "title": "My New SaaS Tool",
                "url": "https://mysaas.com",
                "_tags": ["story"],
                "objectID": "4",
            },
        ]
    }
    with patch("startup_scout.connectors.hacker_news.requests.get", return_value=fake_response):
        connector = HackerNewsConnector({})
        results = connector.fetch()
    assert len(results) == 1
    assert results[0].name == "My New SaaS Tool"


def test_exclude_domains_setting_is_additive():
    fake_response = Mock()
    fake_response.raise_for_status = lambda: None
    fake_response.json = lambda: {
        "hits": [
            {
                "title": "Some Post",
                "url": "https://customblocked.example.com/post",
                "_tags": ["story"],
                "objectID": "5",
            },
        ]
    }
    with patch("startup_scout.connectors.hacker_news.requests.get", return_value=fake_response):
        connector = HackerNewsConnector({"exclude_domains": ["customblocked.example.com"]})
        results = connector.fetch()
    assert results == []
