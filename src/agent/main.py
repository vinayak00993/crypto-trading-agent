"""
Main entry point for the Crypto Trading Agent.

Usage:
    trading-agent                    # uses default config
    python -m agent.main             # alternative
"""

from __future__ import annotations

import sys

import structlog

from agent.config import load_config, PROJECT_ROOT


def setup_logging(level: str, fmt: str, log_file: str) -> None:
    """Configure structlog for the agent."""
    import logging

    # Ensure log directory exists
    log_path = PROJECT_ROOT / log_file
    log_path.parent.mkdir(parents=True, exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, level),
        format="%(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_path),
        ],
    )

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if fmt == "json":
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


def main() -> None:
    """Load config, wire up components, and start the agent loop."""
    cfg = load_config()

    setup_logging(cfg.logging.level, cfg.logging.format, cfg.logging.log_file)
    log = structlog.get_logger()

    log.info("agent.startup", mode=cfg.mode, exchange=cfg.exchange.name)
    log.info(
        "agent.config",
        pairs=cfg.trading.pairs,
        strategy=cfg.strategy.name,
        timeframe=cfg.trading.default_timeframe,
    )

    if cfg.mode == "live":
        log.warning("agent.live_mode", msg="⚠️  LIVE TRADING — real money at risk!")

    # Build and start the agent loop
    from agent.loop import AgentLoop

    agent = AgentLoop(cfg)
    agent.start()


if __name__ == "__main__":
    main()
