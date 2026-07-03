"""Placeholder connectors for sources that need a licensing agreement,
OAuth app registration, or an explicit scraping decision before we can
legally/technically pull data.

Each StubConnector documents *why* it's not live yet (via the `reason`
field in config.yaml) so turning it on later is a matter of writing a
proper connector class and flipping `enabled: true` - the pipeline and
config wiring already treat every source uniformly.
"""
from __future__ import annotations

import logging

from startup_scout.connectors.base import BaseConnector
from startup_scout.models import RawStartup

logger = logging.getLogger(__name__)


class StubConnector(BaseConnector):
    """Generic no-op connector that logs why a source isn't implemented."""

    def __init__(self, settings=None):
        super().__init__(settings)
        self.name = self.settings.get("_registry_key", "stub")

    def fetch(self) -> list[RawStartup]:
        reason = self.settings.get("reason", "not yet implemented")
        logger.info("%s: stub connector - %s", self.name, reason)
        return []
