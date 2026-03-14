"""Smoke tests for the configuration system."""

from agent.config import AgentConfig, load_config


def test_defaults_produce_valid_config():
    """Loading with only the default YAML should return a valid AgentConfig."""
    cfg = load_config()
    assert isinstance(cfg, AgentConfig)
    assert cfg.mode == "paper"
    assert cfg.exchange.name == "kraken"
    assert len(cfg.trading.pairs) > 0


def test_paper_mode_is_default():
    """Safety check — the default mode must always be paper trading."""
    cfg = load_config()
    assert cfg.mode == "paper", "Default mode MUST be 'paper' to prevent accidental live trading"


def test_risk_limits_are_set():
    """Risk management values should be present and positive."""
    cfg = load_config()
    assert cfg.risk.max_position_pct > 0
    assert cfg.risk.stop_loss_pct > 0
    assert cfg.risk.max_daily_loss_pct > 0
