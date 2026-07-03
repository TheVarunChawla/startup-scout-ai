"""
One-off script to apply the Hacker News noise-filtering fix directly to
your local checkout, without relying on `git am` / patch files (which
weren't syncing reliably).

Usage: put this file in the ROOT of your startup-scout-ai_repo folder
(next to main.py) and run:

    python apply_hn_filtering_fix.py

Then:

    python -m pytest
    git add -A
    git commit -m "Filter Hacker News noise: exclude Ask HN/Tell HN/Poll threads and major news-site domains; consolidate connector status table in README"
    git push
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

HACKER_NEWS_PY = '''"""Hacker News connector.

Uses the free, unauthenticated Algolia HN Search API
(https://hn.algolia.com/api) - no API key required, well within its
public rate limits for a once-a-day pull. We search stories matching a
configurable keyword query, since that's where most indie startup
launches on HN show up.

Post-fetch filtering removes two kinds of noise a plain keyword search
pulls in:
  1. Discussion threads ("Ask HN:", "Tell HN:", "Poll:") - these aren't
     startups, just conversations that happen to mention "startup".
  2. Links to major news/media outlets - a story *about* a startup
     (funding news, a lawsuit, a controversy) is not the startup's own
     listing, and the rest of the pipeline (analysis, scoring) assumes
     the item it receives IS the startup.
"""
from __future__ import annotations

import logging
from urllib.parse import urlparse

import requests

from startup_scout.connectors.base import BaseConnector
from startup_scout.models import RawStartup

logger = logging.getLogger(__name__)

ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"

ASK_HN_TAG = "ask_hn"
NON_STARTUP_TITLE_PREFIXES = ("Ask HN:", "Tell HN:", "Poll:")

# News/media domains that commonly surface in a "startup" keyword search
# because they write ABOUT startups, not because the linked page is one.
# Extendable per-deployment via `exclude_domains` in config.yaml.
DEFAULT_EXCLUDED_DOMAINS = {
    "theregister.com", "techcrunch.com", "arstechnica.com", "theverge.com",
    "wired.com", "bloomberg.com", "reuters.com", "nytimes.com", "forbes.com",
    "businessinsider.com", "engadget.com", "cnet.com", "zdnet.com",
    "bbc.com", "cnbc.com", "venturebeat.com", "washingtonpost.com",
}


class HackerNewsConnector(BaseConnector):
    name = "hacker_news"

    def fetch(self) -> list[RawStartup]:
        query = self.settings.get("query", "Show HN")
        max_results = int(self.settings.get("max_results", 30))
        exclude_ask_hn = self.settings.get("exclude_ask_hn", True)
        excluded_domains = DEFAULT_EXCLUDED_DOMAINS | set(self.settings.get("exclude_domains", []))

        params = {
            "tags": "story",
            "query": query,
            "hitsPerPage": max_results,
        }
        resp = requests.get(ALGOLIA_SEARCH_URL, params=params, timeout=15)
        resp.raise_for_status()
        hits = resp.json().get("hits", [])

        results: list[RawStartup] = []
        for hit in hits:
            title = (hit.get("title") or "").strip()
            if not title:
                continue
            if exclude_ask_hn and _is_discussion_thread(hit, title):
                continue

            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get(\'objectID\')}"
            if _domain(url) in excluded_domains:
                continue

            results.append(
                RawStartup(
                    source=self.name,
                    name=_clean_title(title),
                    url=url,
                    description=hit.get("story_text") or title,
                    tags=["hacker-news"] + (hit.get("_tags") or []),
                    raw_meta={
                        "points": hit.get("points"),
                        "num_comments": hit.get("num_comments"),
                        "author": hit.get("author"),
                        "objectID": hit.get("objectID"),
                    },
                )
            )
        return results


def _is_discussion_thread(hit: dict, title: str) -> bool:
    if ASK_HN_TAG in (hit.get("_tags") or []):
        return True
    return title.startswith(NON_STARTUP_TITLE_PREFIXES)


def _domain(url: str) -> str:
    netloc = urlparse(url).netloc.lower()
    return netloc[4:] if netloc.startswith("www.") else netloc


def _clean_title(title: str) -> str:
    prefix = "Show HN:"
    if title.startswith(prefix):
        title = title[len(prefix):].strip()
    return title
'''

CONFIG_YAML_OLD = '''  hacker_news:
    enabled: true
    type: hacker_news
    query: "startup"
    max_results: 30'''

CONFIG_YAML_NEW = '''  hacker_news:
    enabled: true
    type: hacker_news
    query: "startup"
    max_results: 30
    exclude_ask_hn: true  # drop "Ask HN:" / "Tell HN:" / "Poll:" discussion threads
    exclude_domains: []    # extra domains to exclude, beyond the connector's built-in news-site list'''

README_OLD = '''| Connector | Status | Notes |
|---|---|---|
| Hacker News | **Live** | Free Algolia HN Search API, no key required. |
| Product Hunt | **Live**, needs credential | Free GraphQL API v2, requires `PRODUCT_HUNT_TOKEN` env var. Runs and returns `[]` with a warning if unset — never breaks the pipeline. |
| Y Combinator | Stub | No public bulk API. |
| YC Requests for Startups | Stub | Static page; needs a permitted HTML parse. |
| Indie Hackers | Stub | No public API; ToS restricts scraping. |
| BetaList | Stub | No public API documented. |
| TechCrunch Startups | Stub | Has an RSS feed — good candidate for the next real connector. |
| Crunchbase | Stub | Requires a paid API license. |
| Wellfound | Stub | No public API; ToS restricts scraping. |
| F6S | Stub | No public API. |
| OpenVC | Stub | No public API documented. |
| Seedtable | Stub | No public API documented. |
| Reddit startup communities | Stub | Needs a free Reddit OAuth app + PRAW — good candidate for the next real connector. |
| GitHub Trending | Stub | No official API; scraping github.com/trending needs an explicit policy decision. |
| AI / startup newsletters | Stub | Needs per-newsletter RSS/email parsing config. |'''

README_NEW = '''| Connector | Status | Why |
|---|---|---|
| Hacker News | **Live** | Free Algolia HN Search API, no key required. Filters out Ask HN/Tell HN/Poll discussion threads and major news-site domains so only startup listings come through. |
| Product Hunt | **Live**, needs credential | Free GraphQL API v2, requires `PRODUCT_HUNT_TOKEN` env var. Runs and returns `[]` with a warning if unset — never breaks the pipeline. |
| Y Combinator directory | Stub | No public export/API |
| YC Requests for Startups | Stub | Static page, would need scraping |
| Wellfound, Indie Hackers, F6S, OpenVC, Seedtable, BetaList | Stub | No public API, most ToS-restrict scraping |
| Crunchbase | Stub | API exists but requires a paid license |
| Reddit | Stub | Needs a free OAuth app registration (5-minute setup, then it's a real connector) |
| GitHub Trending | Stub | No official API — scraping is common practice but flagged here as a policy decision |
| TechCrunch | Stub | Has a public RSS feed — this is the easiest one to make real |
| AI / startup newsletters | Stub | Needs per-newsletter RSS/email parsing config. |'''

TEST_APPEND = '''

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
'''


def main():
    # 1. Overwrite the connector file completely.
    hn_path = ROOT / "startup_scout" / "connectors" / "hacker_news.py"
    hn_path.write_text(HACKER_NEWS_PY, encoding="utf-8")
    print(f"Wrote {hn_path}")

    # 2. Patch config.yaml (insert two new keys under hacker_news:).
    config_path = ROOT / "config" / "config.yaml"
    content = config_path.read_text(encoding="utf-8")
    if CONFIG_YAML_NEW in content:
        print(f"{config_path} already up to date, skipping")
    elif CONFIG_YAML_OLD in content:
        config_path.write_text(content.replace(CONFIG_YAML_OLD, CONFIG_YAML_NEW), encoding="utf-8")
        print(f"Updated {config_path}")
    else:
        print(f"WARNING: expected block not found in {config_path} - leaving untouched, check manually")

    # 3. Replace the connector status table in README.md.
    readme_path = ROOT / "README.md"
    content = readme_path.read_text(encoding="utf-8")
    if README_NEW in content:
        print(f"{readme_path} already up to date, skipping")
    elif README_OLD in content:
        readme_path.write_text(content.replace(README_OLD, README_NEW), encoding="utf-8")
        print(f"Updated {readme_path}")
    else:
        print(f"WARNING: expected table not found in {readme_path} - leaving untouched, check manually")

    # 4. Append the three new tests, if not already present.
    test_path = ROOT / "tests" / "test_connectors_hacker_news.py"
    content = test_path.read_text(encoding="utf-8")
    if "test_fetch_excludes_ask_hn_threads" in content:
        print(f"{test_path} already has the new tests, skipping")
    else:
        test_path.write_text(content + TEST_APPEND, encoding="utf-8")
        print(f"Updated {test_path}")

    print("\\nDone. Now run: python -m pytest")


if __name__ == "__main__":
    main()
