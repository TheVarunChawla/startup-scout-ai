"""Connector registry: maps config `type` strings to connector classes."""
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
