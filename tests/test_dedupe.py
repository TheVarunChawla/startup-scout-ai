from startup_scout.dedupe import dedupe_startups
from startup_scout.models import RawStartup


def _startup(name, url, source="test"):
    return RawStartup(source=source, name=name, url=url, description="")


def test_exact_duplicate_by_url_is_removed():
    items = [
        _startup("Acme", "https://acme.com"),
        _startup("Acme Inc", "https://acme.com/"),
    ]
    result = dedupe_startups(items)
    assert len(result) == 1


def test_similar_names_are_merged():
    items = [
        _startup("Acme Startup", "https://a.com"),
        _startup("Acme Startup!", "https://b.com"),
    ]
    result = dedupe_startups(items)
    assert len(result) == 1


def test_distinct_startups_are_kept():
    items = [
        _startup("Acme", "https://acme.com"),
        _startup("Globex", "https://globex.com"),
    ]
    result = dedupe_startups(items)
    assert len(result) == 2


def test_surviving_record_merges_tags_and_sources():
    items = [
        RawStartup(source="hacker_news", name="Acme", url="https://acme.com", tags=["show-hn"]),
        RawStartup(source="product_hunt", name="Acme", url="https://acme.com", tags=["saas"]),
    ]
    result = dedupe_startups(items)
    assert len(result) == 1
    assert "product_hunt" in result[0].tags
    assert "show-hn" in result[0].tags
