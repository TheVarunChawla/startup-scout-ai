import os
from unittest.mock import Mock, patch

from startup_scout.connectors.reddit import RedditConnector

FAKE_TOKEN_RESPONSE = {"access_token": "fake-token-123", "expires_in": 3600}

FAKE_LISTING_RESPONSE = {
    "data": {
        "children": [
            {
                "data": {
                    "title": "Launched my SaaS for tracking freelance invoices",
                    "url": "https://myinvoicetool.com",
                    "selftext": "Been building this for 3 months, would love feedback.",
                    "score": 42,
                    "num_comments": 8,
                    "author": "builder123",
                    "permalink": "/r/startups/comments/abc123/",
                    "stickied": False,
                }
            },
            {
                "data": {
                    "title": "Weekly self-promotion thread",
                    "url": "",
                    "selftext": "",
                    "score": 1,
                    "num_comments": 0,
                    "author": "AutoModerator",
                    "permalink": "/r/startups/comments/sticky/",
                    "stickied": True,
                }
            },
        ]
    }
}


def _mock_post_and_get():
    token_response = Mock()
    token_response.raise_for_status = lambda: None
    token_response.json = lambda: FAKE_TOKEN_RESPONSE

    listing_response = Mock()
    listing_response.raise_for_status = lambda: None
    listing_response.json = lambda: FAKE_LISTING_RESPONSE

    return token_response, listing_response


def test_fetch_returns_empty_without_credentials(monkeypatch):
    monkeypatch.delenv("REDDIT_CLIENT_ID", raising=False)
    monkeypatch.delenv("REDDIT_CLIENT_SECRET", raising=False)

    connector = RedditConnector({})
    results = connector.fetch()
    assert results == []


def test_fetch_parses_listing_and_skips_stickied(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")

    token_response, listing_response = _mock_post_and_get()

    with patch("startup_scout.connectors.reddit.requests.post", return_value=token_response), \
         patch("startup_scout.connectors.reddit.requests.get", return_value=listing_response):
        connector = RedditConnector({"subreddits": ["startups"], "max_results": 10})
        results = connector.fetch()

    assert len(results) == 1
    assert results[0].name == "Launched my SaaS for tracking freelance invoices"
    assert results[0].source == "reddit_startups"
    assert "r/startups" in results[0].tags


def test_fetch_handles_multiple_subreddits(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")

    token_response, listing_response = _mock_post_and_get()

    with patch("startup_scout.connectors.reddit.requests.post", return_value=token_response), \
         patch("startup_scout.connectors.reddit.requests.get", return_value=listing_response):
        connector = RedditConnector({"subreddits": ["startups", "SideProject"], "max_results": 10})
        results = connector.fetch()

    assert len(results) == 2


def test_safe_fetch_swallows_exceptions(monkeypatch):
    monkeypatch.setenv("REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("REDDIT_CLIENT_SECRET", "secret")

    with patch("startup_scout.connectors.reddit.requests.post", side_effect=ConnectionError("boom")):
        connector = RedditConnector({})
        results = connector.safe_fetch()
    assert results == []
