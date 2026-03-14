"""
Live Mode — runs the trading agent with a real-time web dashboard.

Usage:
    python -m agent.live
    python -m agent.live --port 8080

Then open http://localhost:5555 in your browser.
The dashboard auto-refreshes every 5 seconds with live data.
"""

from __future__ import annotations

import argparse
import sys

import structlog

from agent.config import load_config, PROJECT_ROOT


def setup_logging(level: str, fmt: str, log_file: str) -> None:
    """Configure structlog for the agent."""
    import logging

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

    # Suppress Flask's noisy request logging
    logging.getLogger("werkzeug").setLevel(logging.WARNING)

    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.ConsoleRenderer(),
    ]

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run agent with live dashboard")
    parser.add_argument("--port", type=int, default=5555, help="Dashboard port (default: 5555)")
    args = parser.parse_args()

    cfg = load_config()
    setup_logging(cfg.logging.level, cfg.logging.format, cfg.logging.log_file)
    log = structlog.get_logger()

    log.info("agent.startup", mode=cfg.mode, exchange=cfg.exchange.name)
    log.info("agent.config", pairs=cfg.trading.pairs, strategy=cfg.strategy.name)

    # Start the dashboard web server in a background thread
    from agent.server import start_server
    start_server(port=args.port)
    log.info("dashboard.started", url=f"http://localhost:{args.port}")
    print(f"\n  >>> Live Dashboard: http://localhost:{args.port}")
    print(f"  >>> Open this URL in your browser!\n")

    if cfg.mode == "live":
        log.warning("agent.live_mode", msg="LIVE TRADING - real money at risk!")

    # Start the agent loop (blocks until Ctrl+C)
    from agent.loop import AgentLoop
    agent = AgentLoop(cfg)
    agent.start()


if __name__ == "__main__":
    main()
