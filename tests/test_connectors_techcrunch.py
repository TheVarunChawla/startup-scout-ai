from unittest.mock import Mock, patch

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
