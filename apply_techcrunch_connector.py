"""
One-off script to add a third real, live connector: TechCrunch's
"Startups" category RSS feed. No API key needed - it's a standard
public RSS 2.0 feed, parsed with the standard library (no new
dependency). Follows the same BaseConnector pattern as Hacker News and
Product Hunt, so the pipeline treats it identically to the others.

Usage: put this file in the ROOT of your startup-scout-ai_repo folder
(next to main.py) and run:

    python apply_techcrunch_connector.py

Then:

    python -m pytest
    git add -A
    git commit -m "Add TechCrunch Startups RSS connector"
    git push
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent

TECHCRUNCH_PY = '''"""TechCrunch (Startups category) connector.

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


def _strip_html(text: str) -> str:
    return _TAG_RE.sub("", text or "").strip()


class TechCrunchConnector(BaseConnector):
    name = "techcrunch"

    def fetch(self) -> list[RawStartup]:
        max_results = int(self.settings.get("max_results", 20))
        resp = requests.get(
            FEED_URL, timeout=15, headers={"User-Agent": "startup-scout-ai/0.1"}
        )
        resp.raise_for_status()

        root = ET.fromstring(resp.content)
        items = root.findall("./channel/item")[:max_results]

        results: list[RawStartup] = []
        for item in items:
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if not title or not link:
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
'''

CONNECTORS_INIT_PY = '''"""Connector registry: maps config `type` strings to connector classes."""
from __future__ import annotations

from startup_scout.connectors.base import BaseConnector
from startup_scout.connectors.hacker_news import HackerNewsConnector
from startup_scout.connectors.product_hunt import ProductHuntConnector
from startup_scout.connectors.stubs import StubConnector
from startup_scout.connectors.techcrunch import TechCrunchConnector

CONNECTOR_TYPES: dict[str, type[BaseConnector]] = {
    "hacker_news": HackerNewsConnector,
    "product_hunt": ProductHuntConnector,
    "techcrunch": TechCrunchConnector,
    "stub": StubConnector,
}

__all__ = [
    "BaseConnector",
    "HackerNewsConnector",
    "ProductHuntConnector",
    "TechCrunchConnector",
    "StubConnector",
    "CONNECTOR_TYPES",
]
'''

TEST_TECHCRUNCH_PY = '''from unittest.mock import Mock, patch

from startup_scout.connectors.techcrunch import TechCrunchConnector

SAMPLE_FEED = b"""<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:dc="http://purl.org/dc/elements/1.1/">
<channel>
  <title>TechCrunch</title>
  <item>
    <title>Acme raises $5M to build the future of widgets</title>
    <link>https://techcrunch.com/2026/07/03/acme-raises-5m/</link>
    <description>&lt;p&gt;Acme, a startup building AI-powered widgets, announced a $5M seed round.&lt;/p&gt;</description>
    <category>Startups</category>
    <category>Funding</category>
    <dc:creator>Jane Reporter</dc:creator>
  </item>
  <item>
    <title></title>
    <link>https://techcrunch.com/2026/07/03/no-title/</link>
    <description>Missing title, should be skipped.</description>
  </item>
</channel>
</rss>
"""


def test_fetch_parses_rss_items():
    fake_response = Mock()
    fake_response.raise_for_status = lambda: None
    fake_response.content = SAMPLE_FEED

    with patch("startup_scout.connectors.techcrunch.requests.get", return_value=fake_response) as mock_get:
        connector = TechCrunchConnector({"max_results": 10})
        results = connector.fetch()

    assert mock_get.called
    assert len(results) == 1
    assert results[0].name == "Acme raises $5M to build the future of widgets"
    assert results[0].source == "techcrunch"
    assert "Startups" in results[0].tags
    assert "<p>" not in results[0].description
    assert results[0].raw_meta["author"] == "Jane Reporter"


def test_fetch_skips_items_without_title_or_link():
    fake_response = Mock()
    fake_response.raise_for_status = lambda: None
    fake_response.content = b"""<?xml version="1.0"?>
<rss version="2.0"><channel>
  <item><title></title><link>https://example.com</link></item>
</channel></rss>"""

    with patch("startup_scout.connectors.techcrunch.requests.get", return_value=fake_response):
        connector = TechCrunchConnector({})
        results = connector.fetch()
    assert results == []


def test_safe_fetch_swallows_exceptions():
    with patch("startup_scout.connectors.techcrunch.requests.get", side_effect=ConnectionError("boom")):
        connector = TechCrunchConnector({})
        results = connector.safe_fetch()
    assert results == []
'''


def main():
    tc_path = ROOT / "startup_scout" / "connectors" / "techcrunch.py"
    tc_path.write_text(TECHCRUNCH_PY, encoding="utf-8")
    print(f"Wrote {tc_path}")

    init_path = ROOT / "startup_scout" / "connectors" / "__init__.py"
    init_path.write_text(CONNECTORS_INIT_PY, encoding="utf-8")
    print(f"Wrote {init_path}")

    test_path = ROOT / "tests" / "test_connectors_techcrunch.py"
    test_path.write_text(TEST_TECHCRUNCH_PY, encoding="utf-8")
    print(f"Wrote {test_path}")

    config_path = ROOT / "config" / "config.yaml"
    content = config_path.read_text(encoding="utf-8")
    old = """  techcrunch:
    enabled: false
    type: stub
    reason: "Has an RSS feed (https://techcrunch.com/feed/) - good candidate for the next real connector.\""""
    new = """  techcrunch:
    enabled: true
    type: techcrunch
    max_results: 20"""
    if new in content:
        print(f"{config_path} already up to date, skipping")
    elif old in content:
        config_path.write_text(content.replace(old, new), encoding="utf-8")
        print(f"Updated {config_path}")
    else:
        print(f"WARNING: expected techcrunch stub block not found in {config_path} - add it manually:")
        print(new)

    print("All done. Now run: python -m pytest")


if __name__ == "__main__":
    main()

# END OF FILE MARKER techcrunch-connector
