"""
One-off script to add a fourth real, live connector: Reddit startup
communities (r/startups, r/SideProject, r/Entrepreneur by default).

Uses Reddit's free "Application Only OAuth" (client_credentials grant)
for read-only access to public subreddit listings - no user login or
password needed, just a free app registered at
https://www.reddit.com/prefs/apps. Credentials are read from
REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET environment variables, never
from config.yaml, so they never end up in version control - same
pattern as the Product Hunt connector. If the credentials aren't set,
it logs a warning and returns [] rather than failing the whole run.

Usage: put this file in the ROOT of your startup-scout-ai_repo folder
(next to main.py) and run:

    python apply_reddit_connector.py

Then:

    python -m pytest
    git add -A
    git commit -m "Add Reddit connector (startups/SideProject/Entrepreneur subreddits)"
    git push
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

REDDIT_PY = '''"""Reddit connector.

Uses Reddit's "Application Only OAuth" (client_credentials grant) for
read-only access to public subreddit listings - no user login or
password needed, just a free app registered at
https://www.reddit.com/prefs/apps.

Reads REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET from environment
variables (never from config.yaml) so credentials never end up in
version control. If either is missing, logs a warning and returns []
rather than failing the whole run - same pattern as Product Hunt.
"""
from __future__ import annotations

import logging
import os

import requests

from startup_scout.connectors.base import BaseConnector
from startup_scout.models import RawStartup

logger = logging.getLogger(__name__)

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
LISTING_URL_TEMPLATE = "https://oauth.reddit.com/r/{subreddit}/{listing}"
USER_AGENT = "startup-scout-ai/0.1 (personal use script)"

DEFAULT_SUBREDDITS = ["startups", "SideProject", "Entrepreneur"]


class RedditConnector(BaseConnector):
    name = "reddit_startups"

    def fetch(self) -> list[RawStartup]:
        client_id = os.environ.get("REDDIT_CLIENT_ID")
        client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
        if not client_id or not client_secret:
            logger.warning(
                "REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET not set - skipping Reddit. "
                "Create a free app at https://www.reddit.com/prefs/apps"
            )
            return []

        token = self._get_access_token(client_id, client_secret)
        if not token:
            return []

        subreddits = self.settings.get("subreddits", DEFAULT_SUBREDDITS)
        listing = self.settings.get("listing", "new")
        max_results = int(self.settings.get("max_results", 15))

        results: list[RawStartup] = []
        for subreddit in subreddits:
            results.extend(self._fetch_subreddit(subreddit, listing, token, max_results))
        return results

    def _get_access_token(self, client_id: str, client_secret: str) -> str | None:
        try:
            resp = requests.post(
                TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(client_id, client_secret),
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("access_token")
        except Exception:
            logger.exception("Reddit: failed to obtain access token")
            return None

    def _fetch_subreddit(self, subreddit: str, listing: str, token: str, limit: int) -> list[RawStartup]:
        url = LISTING_URL_TEMPLATE.format(subreddit=subreddit, listing=listing)
        try:
            resp = requests.get(
                url,
                params={"limit": limit},
                headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
        except Exception:
            logger.exception("Reddit: failed to fetch r/%s", subreddit)
            return []

        children = resp.json().get("data", {}).get("children", [])
        results: list[RawStartup] = []
        for child in children:
            post = child.get("data", {})
            title = (post.get("title") or "").strip()
            if not title or post.get("stickied"):
                continue
            permalink = post.get("permalink", "")
            url_field = post.get("url") or f"https://reddit.com{permalink}"
            results.append(
                RawStartup(
                    source=self.name,
                    name=title,
                    url=url_field,
                    description=post.get("selftext") or title,
                    tags=["reddit", f"r/{subreddit}"],
                    raw_meta={
                        "score": post.get("score"),
                        "num_comments": post.get("num_comments"),
                        "author": post.get("author"),
                        "permalink": f"https://reddit.com{permalink}",
                    },
                )
            )
        return results
'''

CONNECTORS_INIT_PY = '''"""Connector registry: maps config `type` strings to connector classes."""
from __future__ import annotations

from startup_scout.connectors.base import BaseConnector
from startup_scout.connectors.hacker_news import HackerNewsConnector
from startup_scout.connectors.product_hunt import ProductHuntConnector
from startup_scout.connectors.reddit import RedditConnector
from startup_scout.connectors.stubs import StubConnector
from startup_scout.connectors.techcrunch import TechCrunchConnector

CONNECTOR_TYPES: dict[str, type[BaseConnector]] = {
    "hacker_news": HackerNewsConnector,
    "product_hunt": ProductHuntConnector,
    "techcrunch": TechCrunchConnector,
    "reddit": RedditConnector,
    "stub": StubConnector,
}

__all__ = [
    "BaseConnector",
    "HackerNewsConnector",
    "ProductHuntConnector",
    "TechCrunchConnector",
    "RedditConnector",
    "StubConnector",
    "CONNECTOR_TYPES",
]
'''

TEST_REDDIT_PY = '''import os
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

    with patch("startup_scout.connectors.reddit.requests.post", return_value=token_response), \\
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

    with patch("startup_scout.connectors.reddit.requests.post", return_value=token_response), \\
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
'''


def main():
    reddit_path = ROOT / "startup_scout" / "connectors" / "reddit.py"
    reddit_path.write_text(REDDIT_PY, encoding="utf-8")
    print(f"Wrote {reddit_path}")

    init_path = ROOT / "startup_scout" / "connectors" / "__init__.py"
    init_path.write_text(CONNECTORS_INIT_PY, encoding="utf-8")
    print(f"Wrote {init_path}")

    test_path = ROOT / "tests" / "test_connectors_reddit.py"
    test_path.write_text(TEST_REDDIT_PY, encoding="utf-8")
    print(f"Wrote {test_path}")

    config_path = ROOT / "config" / "config.yaml"
    content = config_path.read_text(encoding="utf-8")
    old = """  reddit_startups:
    enabled: false
    type: stub
    reason: "Needs a free Reddit OAuth app + PRAW - good candidate for the next real connector.\""""
    new = """  reddit_startups:
    enabled: true
    type: reddit
    subreddits: ["startups", "SideProject", "Entrepreneur"]
    listing: new
    max_results: 15
    # requires env vars REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET - see .env.example.
    # Runs safely with an empty result set if they aren't set."""
    if new in content:
        print(f"{config_path} already up to date, skipping")
    elif old in content:
        config_path.write_text(content.replace(old, new), encoding="utf-8")
        print(f"Updated {config_path}")
    else:
        print(f"WARNING: expected reddit_startups stub block not found in {config_path} - add it manually:")
        print(new)

    env_example_path = ROOT / ".env.example"
    content = env_example_path.read_text(encoding="utf-8")
    if "REDDIT_CLIENT_ID" in content:
        print(f"{env_example_path} already has Reddit entries, skipping")
    else:
        content = content.rstrip("\n") + "\nREDDIT_CLIENT_ID=\nREDDIT_CLIENT_SECRET=\n"
        env_example_path.write_text(content, encoding="utf-8")
        print(f"Updated {env_example_path}")

    print("All done. Now run: python -m pytest")


if __name__ == "__main__":
    main()

# END OF FILE MARKER reddit-connector
