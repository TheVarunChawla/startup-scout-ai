"""Y Combinator connector.

Y Combinator has no official public API and no bulk export. This
connector uses a free, openly published mirror of YC's own public
Algolia search index (the same data that powers the "Startups"
directory on ycombinator.com), maintained at
https://github.com/yc-oss/api. That project fetches YC's Algolia index
directly (not by scraping rendered HTML) once a day via its own GitHub
Actions workflow, and publishes the result as static JSON files - so
this connector just does a plain HTTP GET, no scraping and no
credentials needed.

To keep results fresh and small, this pulls specific YC batches (by
default, the most recent ones) rather than "all 5,900+ companies ever
funded". Update `batches` in config.yaml every ~6 months when YC
announces a new batch (check https://yc-oss.github.io/api/meta.json
for the current list).
"""
from __future__ import annotations

import logging

import requests

from startup_scout.connectors.base import BaseConnector
from startup_scout.models import RawStartup

logger = logging.getLogger(__name__)

BATCH_URL_TEMPLATE = "https://yc-oss.github.io/api/batches/{batch}.json"
DEFAULT_BATCHES = ["summer-2026", "spring-2026", "winter-2026"]


class YCombinatorConnector(BaseConnector):
    name = "y_combinator"

    def fetch(self) -> list[RawStartup]:
        batches = self.settings.get("batches", DEFAULT_BATCHES)
        max_per_batch = int(self.settings.get("max_per_batch", 200))

        results: list[RawStartup] = []
        for batch in batches:
            results.extend(self._fetch_batch(batch, max_per_batch))
        return results

    def _fetch_batch(self, batch: str, limit: int) -> list[RawStartup]:
        url = BATCH_URL_TEMPLATE.format(batch=batch)
        try:
            resp = requests.get(url, timeout=20, headers={"User-Agent": "startup-scout-ai/0.1"})
            resp.raise_for_status()
            companies = resp.json()
        except Exception:
            logger.exception("Y Combinator: failed to fetch batch %r", batch)
            return []

        results: list[RawStartup] = []
        for company in companies[:limit]:
            name = (company.get("name") or "").strip()
            if not name:
                continue
            one_liner = (company.get("one_liner") or "").strip()
            long_description = (company.get("long_description") or "").strip()
            tags = list(company.get("tags") or [])
            industries = list(company.get("industries") or [])

            results.append(
                RawStartup(
                    source=self.name,
                    name=name,
                    url=company.get("website") or company.get("url") or "",
                    description=long_description or one_liner,
                    tags=["y_combinator", batch] + industries + tags,
                    raw_meta={
                        "one_liner": one_liner,
                        "batch": company.get("batch"),
                        "team_size": company.get("team_size"),
                        "yc_url": company.get("url"),
                    },
                )
            )
        return results
