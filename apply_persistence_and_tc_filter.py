"""
One-off script for two changes:

1. Make the SQLite database (data/startup_scout.db) persist across both
   local runs and the scheduled GitHub Actions run, so feedback you give
   locally actually affects future scored reports (local or CI), and
   trend analysis in CI finally accumulates real history instead of
   starting from an empty database every single scheduled run (which is
   why you were seeing nonsense numbers like "+5200% vs prior period" -
   there was never a "prior period" to compare against; CI's db never
   persisted at all until now).

   The workflow already force-adds data/ (from the earlier reports-
   conflict fix), so the only change needed is un-gitignoring
   data/*.db.

   Heads up: unlike reports/*.md, the database is a single binary file,
   so if both a local run and a CI run modify it before you sync, git
   will flag a conflict on that one file. Same fix as before applies:
   `git checkout --theirs data/startup_scout.db` (keep CI's) or
   `--ours` (keep local's) - you just pick one side's version, since
   binary files can't be line-merged. To minimize how often this
   happens: `git pull` before running locally, and commit+push right
   after you run or give feedback.

2. Filter TechCrunch's "Startups" category feed to exclude funding-
   round and executive-reshuffle headlines ("X raises $135M", "Y
   appoints new CEO", "Z acquires W"). These are real, on-topic startup
   news, but they don't fit the report's per-item template - an
   already-funded company doesn't have a meaningful "MVP cost" or
   "30-Day MVP Plan". Keeps genuine product-launch style articles.

Usage: put this file in the ROOT of your startup-scout-ai_repo folder
(next to main.py) and run:

    python apply_persistence_and_tc_filter.py

Then:

    python -m pytest
    git add -A
    git commit -m "Persist database across local/CI runs; filter TechCrunch funding/personnel news"
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
    r"\\b("
    r"raises?\\s+[\\$\\u20ac\\u00a3]|"
    r"series\\s+[a-e]\\b|"
    r"acquir(e[sd]?|ing|es)|"
    r"\\bipo\\b|"
    r"valued at|"
    r"lays?\\s+off|layoffs?|"
    r"shuts?\\s+down|"
    r"steps?\\s+down|"
    r"takes?\\s+ceo\\s+role|"
    r"appoints?\\b|"
    r"joins?\\s+as|"
    r"named\\s+ceo|"
    r"files?\\s+for\\s+bankruptcy"
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
    <title>Widgetly launches an AI tool that designs your widgets for you</title>
    <link>https://techcrunch.com/2026/07/03/widgetly-launches/</link>
    <description>&lt;p&gt;Widgetly wants to make widget design effortless with AI.&lt;/p&gt;</description>
    <category>Startups</category>
    <category>AI</category>
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
    assert results[0].name == "Widgetly launches an AI tool that designs your widgets for you"
    assert results[0].source == "techcrunch"
    assert "Startups" in results[0].tags
    assert "<p>" not in results[0].description
    assert results[0].raw_meta["author"] == "Jane Reporter"


def test_fetch_excludes_funding_news_by_default():
    fake_response = Mock()
    fake_response.raise_for_status = lambda: None
    fake_response.content = SAMPLE_FEED

    with patch("startup_scout.connectors.techcrunch.requests.get", return_value=fake_response):
        connector = TechCrunchConnector({})
        results = connector.fetch()

    names = [r.name for r in results]
    assert not any("raises $" in n for n in names)


def test_funding_news_filter_can_be_disabled():
    fake_response = Mock()
    fake_response.raise_for_status = lambda: None
    fake_response.content = SAMPLE_FEED

    with patch("startup_scout.connectors.techcrunch.requests.get", return_value=fake_response):
        connector = TechCrunchConnector({"exclude_funding_news": False})
        results = connector.fetch()

    assert len(results) == 2


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


def test_funding_headline_patterns_detected_directly():
    from startup_scout.connectors.techcrunch import _is_funding_or_personnel_news

    assert _is_funding_or_personnel_news("Acme raises $5M Series A")
    assert _is_funding_or_personnel_news("BigCo acquires Startup Inc")
    assert _is_funding_or_personnel_news("Jane Doe appointed as new CEO of Acme")
    assert _is_funding_or_personnel_news("Startup shuts down after failing to raise")
    assert not _is_funding_or_personnel_news("Widgetly launches an AI-powered design tool")
'''


def main():
    gitignore_path = ROOT / ".gitignore"
    content = gitignore_path.read_text(encoding="utf-8")
    old_line = "data/*.db\\n"
    if "data/*.db" not in content:
        print(f"{gitignore_path} has no data/*.db rule, nothing to remove")
    else:
        lines = [ln for ln in content.splitlines() if ln.strip() != "data/*.db"]
        new_content = "\\n".join(lines) + "\\n"
        gitignore_path.write_text(new_content, encoding="utf-8")
        print(f"Removed 'data/*.db' rule from {gitignore_path} - database will now be tracked")

    tc_path = ROOT / "startup_scout" / "connectors" / "techcrunch.py"
    tc_path.write_text(TECHCRUNCH_PY, encoding="utf-8")
    print(f"Wrote {tc_path}")

    test_path = ROOT / "tests" / "test_connectors_techcrunch.py"
    test_path.write_text(TEST_TECHCRUNCH_PY, encoding="utf-8")
    print(f"Wrote {test_path}")

    print(
        "\\nAll done. Now run: python -m pytest\\n"
        "Then commit data/startup_scout.db along with the code changes so\\n"
        "your existing local history starts syncing with CI from now on."
    )


if __name__ == "__main__":
    main()

# END OF FILE MARKER persistence-and-tc-filter
