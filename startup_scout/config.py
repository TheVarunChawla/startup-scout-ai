"""YAML configuration loading.

Keeping config in YAML (not hardcoded) is what makes connectors,
scoring weights, and report options tunable without touching code -
this is the "configurable connectors" and "YAML configuration"
requirement from the spec.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "config.yaml"
DEFAULT_PROFILE_PATH = Path(__file__).resolve().parent.parent / "config" / "profile.yaml"


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


@dataclass
class AppConfig:
    raw: dict[str, Any]
    profile: dict[str, Any]

    @classmethod
    def load(
        cls,
        config_path: Path | str = DEFAULT_CONFIG_PATH,
        profile_path: Path | str = DEFAULT_PROFILE_PATH,
    ) -> "AppConfig":
        return cls(
            raw=_load_yaml(Path(config_path)),
            profile=_load_yaml(Path(profile_path)),
        )

    @property
    def connectors(self) -> dict[str, Any]:
        return self.raw.get("connectors", {})

    @property
    def scoring_weights(self) -> dict[str, float]:
        return self.raw.get("scoring", {}).get("weights", {})

    @property
    def report_settings(self) -> dict[str, Any]:
        return self.raw.get("report", {})

    @property
    def db_path(self) -> str:
        return self.raw.get("database", {}).get("path", "data/startup_scout.db")

    @property
    def analysis_settings(self) -> dict[str, Any]:
        return self.raw.get("analysis", {})
