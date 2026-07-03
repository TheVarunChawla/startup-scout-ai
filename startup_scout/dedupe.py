"""Deduplication.

Two startups are considered duplicates if either:
  1. Their normalized URLs share the same domain + path, or
  2. Their normalized names are identical, or
  3. Their names are >= SIMILARITY_THRESHOLD similar (difflib) - catches
     "Acme Inc" vs "Acme, Inc." posted on two different sources.

We keep the first-seen item, but merge tags/sources from the duplicate(s)
into it so the surviving record shows every source it was found on.
"""
from __future__ import annotations

import logging
import re
from difflib import SequenceMatcher
from urllib.parse import urlparse

from startup_scout.models import RawStartup

logger = logging.getLogger(__name__)

SIMILARITY_THRESHOLD = 0.88


def _normalize_name(name: str) -> str:
    name = name.lower().strip()
    name = re.sub(r"[^a-z0-9\s]", "", name)
    name = re.sub(r"\s+", " ", name)
    return name


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url if "://" in url else f"//{url}", scheme="https")
    netloc = parsed.netloc.lower()
    if netloc.startswith("www."):
        netloc = netloc[4:]
    path = parsed.path.rstrip("/")
    return f"{netloc}{path}"


def _is_duplicate(a: RawStartup, b: RawStartup) -> bool:
    url_a, url_b = _normalize_url(a.url), _normalize_url(b.url)
    if url_a and url_b and url_a == url_b:
        return True

    name_a, name_b = _normalize_name(a.name), _normalize_name(b.name)
    if name_a and name_a == name_b:
        return True

    ratio = SequenceMatcher(None, name_a, name_b).ratio()
    return ratio >= SIMILARITY_THRESHOLD


def dedupe_startups(startups: list[RawStartup]) -> list[RawStartup]:
    """O(n^2) is fine here - daily batches are a few hundred items at most."""
    kept: list[RawStartup] = []
    for candidate in startups:
        match = next((k for k in kept if _is_duplicate(candidate, k)), None)
        if match is None:
            kept.append(candidate)
            continue
        # Merge provenance into the surviving record.
        merged_tags = sorted(set(match.tags) | set(candidate.tags) | {candidate.source})
        match.tags = merged_tags
        logger.debug(
            "Dropped duplicate %r (source=%s) - matches kept item %r (source=%s)",
            candidate.name, candidate.source, match.name, match.source,
        )
    return kept
