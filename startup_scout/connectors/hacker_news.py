"""Hacker News connector.

Uses the free, unauthenticated Algolia HN Search API
(https://hn.algolia.com/api) - no API key required, well within its
public rate limits for a once-a-day pull. We search "Show HN" posts plus
a configurable keyword query, since that's where most indie startup
launches on HN show up.
"""
from __future__ import annotations

import logging

import requests

from startup_scout.connectors.base import BaseConnector
from startup_scout.models import RawStartup

logger = logging.getLogger(__name__)

ALGOLIA_SEARCH_URL = "https://hn.algolia.com/api/v1/search_by_date"


class HackerNewsConnector(BaseConnector):
    name = "hacker_news"

    def fetch(self) -> list[RawStartup]:
        query = self.settings.get("query", "Show HN")
        max_results = int(self.settings.get("max_results", 30))
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
            url = hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}"
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


def _clean_title(title: str) -> str:
    prefix = "Show HN:"
    if title.startswith(prefix):
        title = title[len(prefix):].strip()
    return title
