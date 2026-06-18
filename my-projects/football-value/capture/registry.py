"""
Central registry of football data sources.
Single source of truth for: source names, reliability priors, fetch module, confidence maps.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Literal

_Confidence = Literal["high", "medium", "low"]


class SourceType(Enum):
    OPEN      = "open"
    SEMI_OPEN = "semi_open"
    GATED     = "gated"


_DEFAULT_CONFIDENCE: dict[str, str] = {
    "home_score":    "high",
    "away_score":    "high",
    "home_xg":       "medium",
    "away_xg":       "medium",
    "home_shots":    "medium",
    "away_shots":    "medium",
    "home_sot":      "medium",
    "away_sot":      "medium",
    "home_corners":  "medium",
    "away_corners":  "medium",
    "home_possession": "low",
    "away_possession": "low",
    "home_win":      "high",
    "draw":          "high",
    "away_win":      "high",
    "over_2_5":      "high",
    "under_2_5":     "high",
}

_STATSBOMB_CONFIDENCE: dict[str, str] = {
    **_DEFAULT_CONFIDENCE,
    "home_xg":     "high",
    "away_xg":     "high",
    "home_shots":  "high",
    "away_shots":  "high",
}

_BETEXPLORER_CONFIDENCE: dict[str, str] = {
    **_DEFAULT_CONFIDENCE,
    "home_win":  "high",
    "draw":      "high",
    "away_win":  "high",
    "over_2_5":  "high",
    "under_2_5": "high",
    "home_xg":   "low",
}

_ODDS_API_CONFIDENCE: dict[str, str] = {
    **_DEFAULT_CONFIDENCE,
    "home_win":  "high",
    "draw":      "high",
    "away_win":  "high",
    "over_2_5":  "high",
    "under_2_5": "high",
    "home_xg":   "low",
}


@dataclass(frozen=True)
class SourceConfig:
    name:                  str
    reliability:           float
    fetch_module:          str
    fetch_fn:              str
    base_url:              str
    source_type:           SourceType = SourceType.OPEN
    confidence_map:        dict = field(default_factory=lambda: dict(_DEFAULT_CONFIDENCE))
    completeness_ceiling:  float = 1.0
    rate_limit_s:          float = 0.0


_CONFIGS: list[SourceConfig] = [
    SourceConfig(
        "openfootball", 0.90, "capture.sources.openfootball", "fetch",
        "https://github.com/openfootball/world-cup",
        source_type=SourceType.OPEN,
        completeness_ceiling=0.55,
    ),
    SourceConfig(
        "statsbomb", 0.98, "capture.sources.statsbomb", "fetch",
        "https://github.com/statsbomb/open-data",
        source_type=SourceType.OPEN,
        confidence_map=_STATSBOMB_CONFIDENCE,
        completeness_ceiling=1.0,
    ),
    SourceConfig(
        "football_data", 0.85, "capture.sources.football_data", "fetch",
        "https://www.football-data.co.uk",
        source_type=SourceType.OPEN,
        completeness_ceiling=0.70,
    ),
    SourceConfig(
        "fifa_fdcp", 0.95, "capture.sources.fifa_fdcp", "fetch",
        "https://givevoicetofootball.fifa.com/api/v1",
        source_type=SourceType.OPEN,
        completeness_ceiling=0.65,
    ),
    SourceConfig(
        "api_football", 0.80, "capture.sources.api_football", "fetch",
        "https://v3.football.api-sports.io",
        source_type=SourceType.OPEN,
        completeness_ceiling=0.75,
        rate_limit_s=1.0,
    ),
    SourceConfig(
        "betexplorer", 0.88, "capture.sources.betexplorer", "fetch",
        "https://www.betexplorer.com",
        source_type=SourceType.SEMI_OPEN,
        confidence_map=_BETEXPLORER_CONFIDENCE,
        completeness_ceiling=0.50,
        rate_limit_s=3.0,
    ),
    SourceConfig(
        "the_odds_api", 0.92, "capture.sources.the_odds_api", "fetch",
        "https://api.the-odds-api.com/v4",
        source_type=SourceType.GATED,
        confidence_map=_ODDS_API_CONFIDENCE,
        completeness_ceiling=0.90,
        rate_limit_s=0.0,
    ),
    SourceConfig(
        "fbref", 0.93, "capture.sources.fbref", "fetch",
        "https://fbref.com",
        source_type=SourceType.SEMI_OPEN,
        confidence_map={
            **_DEFAULT_CONFIDENCE,
            "home_xg":   "high",
            "away_xg":   "high",
            "home_shots": "high",
            "away_shots": "high",
            "home_corners": "high",
            "away_corners": "high",
        },
        completeness_ceiling=0.85,
        rate_limit_s=4.5,
    ),
]

REGISTRY: dict[str, SourceConfig] = {c.name: c for c in _CONFIGS}

SOURCE_TIERS: dict[str, list[str]] = {
    "seed":        ["openfootball", "statsbomb"],
    "calibration": ["football_data", "fbref"],
    "live":        ["fifa_fdcp", "api_football"],
    "odds":        ["the_odds_api", "betexplorer"],
}

_source_stats: dict[str, dict] = {}


def field_confidence(source_name: str, field_type: str) -> _Confidence:
    cfg = REGISTRY.get(source_name)
    if cfg is None:
        return "medium"
    return cfg.confidence_map.get(field_type, "medium")


def resolve_fetcher(source_name: str) -> Callable:
    import importlib
    cfg = REGISTRY.get(source_name)
    if not cfg:
        raise ValueError(f"Unknown source: {source_name!r}")
    mod = importlib.import_module(cfg.fetch_module)
    return getattr(mod, cfg.fetch_fn)


def update_source_stats(source_name: str, *, success: bool, latency_s: float) -> None:
    stats = _source_stats.setdefault(source_name, {
        "total": 0, "successes": 0, "failures": 0, "latency_avg_s": 0.0
    })
    stats["total"] += 1
    if success:
        stats["successes"] += 1
    else:
        stats["failures"] += 1
    prev = stats["latency_avg_s"]
    stats["latency_avg_s"] = round(prev + (latency_s - prev) / stats["total"], 2)


def get_source_stats(source_name: str) -> dict:
    return _source_stats.get(source_name, {})
