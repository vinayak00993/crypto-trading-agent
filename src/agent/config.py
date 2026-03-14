"""
Configuration system for the trading agent.

Loading priority (each layer overrides the previous):
  1. configs/config.default.yaml   — shipped defaults
  2. configs/config.local.yaml     — your personal overrides (git-ignored)
  3. Environment variables          — prefixed AGENT_ (e.g. AGENT_MODE=live)
  4. .env file                      — loaded via python-dotenv
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]  # two levels up from src/agent/
CONFIGS_DIR = PROJECT_ROOT / "configs"


# ---------------------------------------------------------------------------
# Config sub-models
# ---------------------------------------------------------------------------
class ExchangeConfig(BaseModel):
    name: str = "kraken"
    sandbox: bool = False
    rate_limit_ms: int = 1200


class TradingConfig(BaseModel):
    pairs: list[str] = Field(default_factory=lambda: ["BTC/USDT", "ETH/USDT"])
    base_currency: str = "USDT"
    default_timeframe: str = "1h"


class StrategyConfig(BaseModel):
    name: str = "sma_crossover"
    params: dict = Field(default_factory=dict)


class RiskConfig(BaseModel):
    max_position_pct: float = 5.0
    max_open_positions: int = 3
    stop_loss_pct: float = 3.0
    take_profit_pct: float = 6.0
    max_daily_loss_pct: float = 10.0

    @field_validator("max_position_pct", "stop_loss_pct", "take_profit_pct", "max_daily_loss_pct")
    @classmethod
    def must_be_positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("Percentage values must be > 0")
        return v


class PaperConfig(BaseModel):
    starting_balance: float = 10_000.0


class LoggingConfig(BaseModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    format: Literal["console", "json"] = "console"
    log_file: str = "logs/agent.log"


class SchedulerConfig(BaseModel):
    strategy_interval_seconds: int = 60


# ---------------------------------------------------------------------------
# Root config
# ---------------------------------------------------------------------------
class AgentConfig(BaseModel):
    """Top-level configuration — the single source of truth for the agent."""

    mode: Literal["paper", "live"] = "paper"
    exchange: ExchangeConfig = Field(default_factory=ExchangeConfig)
    trading: TradingConfig = Field(default_factory=TradingConfig)
    strategy: StrategyConfig = Field(default_factory=StrategyConfig)
    risk: RiskConfig = Field(default_factory=RiskConfig)
    paper: PaperConfig = Field(default_factory=PaperConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    scheduler: SchedulerConfig = Field(default_factory=SchedulerConfig)


# ---------------------------------------------------------------------------
# Loader
# ---------------------------------------------------------------------------
def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge *override* into *base* (mutates base)."""
    for key, value in override.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value
    return base


def load_config(config_path: Path | None = None) -> AgentConfig:
    """
    Build the final AgentConfig by layering sources.

    Parameters
    ----------
    config_path : Path, optional
        Explicit path to a YAML file. If omitted the loader looks for
        config.default.yaml then config.local.yaml inside configs/.
    """
    merged: dict = {}

    # Layer 1 — defaults
    default_file = CONFIGS_DIR / "config.default.yaml"
    if default_file.exists():
        with open(default_file) as f:
            _deep_merge(merged, yaml.safe_load(f) or {})

    # Layer 2 — local overrides
    local_file = CONFIGS_DIR / "config.local.yaml"
    if local_file.exists():
        with open(local_file) as f:
            _deep_merge(merged, yaml.safe_load(f) or {})

    # Layer 3 — explicit file (e.g. passed via CLI)
    if config_path and config_path.exists():
        with open(config_path) as f:
            _deep_merge(merged, yaml.safe_load(f) or {})

    # Layer 4 — environment variables (flat overrides for top-level keys)
    env_mode = os.getenv("AGENT_MODE")
    if env_mode:
        merged["mode"] = env_mode

    return AgentConfig(**merged)
