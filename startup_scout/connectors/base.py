"""Connector interface.

Every data source (Hacker News, Product Hunt, Crunchbase, ...) implements
this interface. The pipeline never knows about individual sources - it
only calls `safe_fetch()` on a list of BaseConnector instances. This is
what lets us add a new source by writing one file and one config block,
without touching the pipeline, scoring, or reporting code.
"""
from __future__ import annotations

import abc
import logging
from typing import Any

from startup_scout.models import RawStartup

logger = logging.getLogger(__name__)


class BaseConnector(abc.ABC):
    """Abstract base class for all data source connectors."""

    #: short machine-friendly name, must match the key in config.yaml's
    #: `connectors` section. Overwritten by the pipeline's connector
    #: registry to the actual config key, so log lines always match config.
    name: str = "base"

    def __init__(self, settings: dict[str, Any] | None = None):
        self.settings = settings or {}

    @abc.abstractmethod
    def fetch(self) -> list[RawStartup]:
        """Return a list of RawStartup objects. Implementations should
        raise on unexpected failures - safe_fetch() below is what
        guarantees the pipeline degrades gracefully, not this method."""
        raise NotImplementedError

    def safe_fetch(self) -> list[RawStartup]:
        """Wrapper used by the pipeline: guarantees a connector failure
        degrades gracefully instead of crashing the daily run."""
        try:
            results = self.fetch()
            logger.info("%s: collected %d items", self.name, len(results))
            return results
        except Exception:
            logger.exception("%s: fetch failed, skipping this source", self.name)
            return []
