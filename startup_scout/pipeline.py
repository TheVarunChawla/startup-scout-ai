"""Daily pipeline orchestration.

This is the single place that wires connectors -> dedupe -> categorize
-> analyze -> score -> persist -> trend-analyze -> report. Every stage
is a separate, independently-testable module; this file only sequences
them, so it stays short and easy to reason about even as more
connectors/stages are added.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from startup_scout.analysis import AIAnalyzer
from startup_scout.config import AppConfig
from startup_scout.connectors import CONNECTOR_TYPES
from startup_scout.connectors.base import BaseConnector
from startup_scout.db import Database
from startup_scout.dedupe import dedupe_startups
from startup_scout.memory import MemoryStore
from startup_scout.models import RawStartup, ScoredStartup
from startup_scout.report import ReportGenerator
from startup_scout.scoring import PersonalScorer
from startup_scout.trends import TrendAnalyzer

logger = logging.getLogger(__name__)


def build_connectors(config: AppConfig) -> list[BaseConnector]:
    connectors: list[BaseConnector] = []
    for key, settings in config.connectors.items():
        if not settings.get("enabled", False):
            continue
        conn_type = settings.get("type", "stub")
        cls = CONNECTOR_TYPES.get(conn_type)
        if cls is None:
            logger.warning("Unknown connector type %r for %r - skipping", conn_type, key)
            continue
        merged_settings = {**settings, "_registry_key": key}
        connector = cls(merged_settings)
        connector.name = key
        connectors.append(connector)
    return connectors


@dataclass
class PipelineResult:
    scored: list[ScoredStartup]
    report_path: Path


class DailyPipeline:
    def __init__(self, config: AppConfig):
        self.config = config
        self.db = Database(config.db_path)
        self.memory = MemoryStore(self.db)
        self.analyzer = AIAnalyzer(config, config.profile)
        self.scorer = PersonalScorer(config.scoring_weights, config.profile, self.memory)
        self.report_generator = ReportGenerator(
            config.report_settings.get("output_dir", "reports"),
            top_n=config.report_settings.get("top_n", 5),
        )
        self.trend_analyzer = TrendAnalyzer(self.db)

    def collect(self) -> list[RawStartup]:
        connectors = build_connectors(self.config)
        if not connectors:
            logger.warning("No connectors enabled - check config/config.yaml")
        collected: list[RawStartup] = []
        for connector in connectors:
            collected.extend(connector.safe_fetch())
        return collected

    def run(self, run_date: date | None = None) -> PipelineResult:
        run_date = run_date or date.today()

        raw = self.collect()
        logger.info("Collected %d raw items across all sources", len(raw))

        deduped = dedupe_startups(raw)
        logger.info("%d items remain after deduplication", len(deduped))

        scored: list[ScoredStartup] = []
        for item in deduped:
            analyzed = self.analyzer.analyze(item)
            scored_item = self.scorer.score(analyzed)
            self.db.upsert_scored_startup(scored_item, run_date=run_date)
            scored.append(scored_item)

        trends = self.trend_analyzer.analyze(run_date)
        report_path = self.report_generator.generate(scored, trends, run_date)
        logger.info("Report written to %s", report_path)

        return PipelineResult(scored=scored, report_path=report_path)
