"""Hacker News connector.

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

            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
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
