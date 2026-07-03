"""TechCrunch (Startups category) connector.

Uses TechCrunch's public RSS feed for the "Startups" category
(https://techcrunch.com/category/startups/feed/) - no API key required,
just a standard RSS 2.0 feed intended for public consumption. Parsed
with the standard library's xml.etree.ElementTree to avoid adding a
feedparser dependency for what is a very regular feed format.

Note: TechCrunch items are news articles ABOUT startups (funding
rounds, launches, features), not the startups' own listings - similar
in spirit to how a Hacker News "Show HN" post or a Product Hunt launch
represents the underlying company. Downstream categorization and
scoring treat these the same as any other RawStartup.

Funding-round and executive-reshuffle headlines ("X raises $135M", "Y
appoints new CEO") are filtered out by default - they're genuine news
but don't fit the "buildable opportunity" report template (an already-
funded company doesn't have a meaningful MVP cost or 30-day plan).
"""
from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import requests

from startup_scout.connectors.base import BaseConnector
from startup_scout.models import RawStartup

logger = logging.getLogger(__name__)

FEED_URL = "https://techcrunch.com/category/startups/feed/"
DC_CREATOR_TAG = "{http://purl.org/dc/elements/1.1/}creator"

_TAG_RE = re.compile(r"<[^>]+>")

_NON_PRODUCT_TITLE_PATTERN = re.compile(
    r"\b("
    r"raises?\s+[\$\u20ac\u00a3]|"
    r"series\s+[a-e]\b|"
    r"acquir(e[sd]?|ing|es)|"
    r"\bipo\b|"
    r"valued at|"
    r"lays?\s+off|layoffs?|"
    r"shuts?\s+down|"
    r"steps?\s+down|"
    r"takes?\s+ceo\s+role|"
    r"appoint\w*|"
    r"joins?\s+as|"
    r"named\s+ceo|"
    r"files?\s+for\s+bankruptcy"
    r")",
    re.IGNORECASE,
)


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text or "").strip()


def _is_funding_or_personnel_news(title: str) -> bool:
    return bool(_NON_PRODUCT_TITLE_PATTERN.search(title))


class TechCrunchConnector(BaseConnector):
    name = "techcrunch"

    def fetch(self) -> list[RawStartup]:
        max_results = int(self.settings.get("max_results", 20))
        exclude_funding_news = self.settings.get("exclude_funding_news", True)

        resp = requests.get(
            FEED_URL, timeout=15, headers={"User-Agent": "startup-scout-ai/0.1"}
        )
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        items = root.findall("./channel/item")

        results: list[RawStartup] = []
        for item in items:
            if len(results) >= max_results:
                break

            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if not title or not link:
                continue
            if exclude_funding_news and _is_funding_or_personnel_news(title):
                continue

            description = _strip_html(item.findtext("description") or "")
            categories = [
                (cat.text or "").strip() for cat in item.findall("category") if cat.text
            ]
            creator = (item.findtext(DC_CREATOR_TAG) or "").strip()

            results.append(
                RawStartup(
                    source=self.name,
                    name=title,
                    url=link,
                    description=description,
                    tags=["techcrunch"] + categories,
                    raw_meta={"author": creator},
                )
            )
        return results
