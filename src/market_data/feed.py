"""
Market Data Feed — fetches OHLCV candle data from crypto exchanges.

Uses the `ccxt` library which provides a unified API across 100+ exchanges.
Supports both one-time fetches and continuous polling.
"""

from __future__ import annotations

from datetime import datetime, timezone

import ccxt
import pandas as pd
import structlog

from agent.config import ExchangeConfig, TradingConfig

log = structlog.get_logger()


class MarketDataFeed:
    """
    Connects to a crypto exchange and fetches candlestick (OHLCV) data.

    Parameters
    ----------
    exchange_cfg : ExchangeConfig
        Exchange name, sandbox mode, rate limits.
    trading_cfg : TradingConfig
        Which pairs and timeframe to fetch.
    """

    def __init__(self, exchange_cfg: ExchangeConfig, trading_cfg: TradingConfig) -> None:
        self.exchange_cfg = exchange_cfg
        self.trading_cfg = trading_cfg
        self._exchange: ccxt.Exchange | None = None

    # ------------------------------------------------------------------
    # Connection
    # ------------------------------------------------------------------
    def connect(self) -> None:
        """Initialize the ccxt exchange connection."""
        exchange_class = getattr(ccxt, self.exchange_cfg.name, None)
        if exchange_class is None:
            raise ValueError(
                f"Unknown exchange: '{self.exchange_cfg.name}'. "
                f"Supported: {', '.join(ccxt.exchanges[:10])}..."
            )

        config = {
            "enableRateLimit": True,
            "rateLimit": self.exchange_cfg.rate_limit_ms,
        }

        self._exchange = exchange_class(config)

        # Only enable sandbox if the exchange supports it
        if self.exchange_cfg.sandbox:
            try:
                self._exchange.set_sandbox_mode(True)
                log.info("market_data.sandbox_enabled", exchange=self.exchange_cfg.name)
            except Exception:
                log.info(
                    "market_data.sandbox_not_supported",
                    exchange=self.exchange_cfg.name,
                    msg="Exchange has no sandbox/testnet — using live public data (read-only)",
                )

        # Some exchanges need markets loaded first
        self._exchange.load_markets()

        log.info(
            "market_data.connected",
            exchange=self.exchange_cfg.name,
            sandbox=self.exchange_cfg.sandbox,
            num_markets=len(self._exchange.markets),
        )

    @property
    def exchange(self) -> ccxt.Exchange:
        """Return the live exchange connection, or raise if not connected."""
        if self._exchange is None:
            raise RuntimeError("Call .connect() before using the market data feed.")
        return self._exchange

    # ------------------------------------------------------------------
    # Fetching candles
    # ------------------------------------------------------------------
    def fetch_candles(
        self,
        pair: str,
        timeframe: str | None = None,
        limit: int = 100,
    ) -> pd.DataFrame:
        """
        Fetch OHLCV candle data for a single trading pair.

        Parameters
        ----------
        pair : str
            e.g. "BTC/USDT"
        timeframe : str, optional
            e.g. "1h", "15m", "1d". Defaults to config value.
        limit : int
            Number of candles to fetch (max depends on exchange, usually 500–1000).

        Returns
        -------
        pd.DataFrame
            Columns: open, high, low, close, volume
            Index: DatetimeIndex (UTC)
        """
        tf = timeframe or self.trading_cfg.default_timeframe

        log.debug("market_data.fetching", pair=pair, timeframe=tf, limit=limit)

        raw = self.exchange.fetch_ohlcv(pair, timeframe=tf, limit=limit)

        if not raw:
            log.warning("market_data.empty", pair=pair, timeframe=tf)
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])

        df = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df.set_index("timestamp", inplace=True)

        log.info(
            "market_data.fetched",
            pair=pair,
            timeframe=tf,
            candles=len(df),
            latest=str(df.index[-1]),
            close=float(df["close"].iloc[-1]),
        )

        return df

    def fetch_all_pairs(self, timeframe: str | None = None, limit: int = 100) -> dict[str, pd.DataFrame]:
        """
        Fetch candles for every pair listed in config.

        Returns
        -------
        dict[str, pd.DataFrame]
            Mapping of pair name → candle DataFrame.
        """
        results: dict[str, pd.DataFrame] = {}

        for pair in self.trading_cfg.pairs:
            try:
                results[pair] = self.fetch_candles(pair, timeframe=timeframe, limit=limit)
            except Exception as e:
                log.error("market_data.fetch_failed", pair=pair, error=str(e))

        return results

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------
    def get_current_price(self, pair: str) -> float:
        """Fetch the latest ticker price for a pair."""
        ticker = self.exchange.fetch_ticker(pair)
        price = ticker.get("last", 0.0)
        log.debug("market_data.price", pair=pair, price=price)
        return float(price)

    def get_all_prices(self) -> dict[str, float]:
        """Get current prices for all configured pairs."""
        prices: dict[str, float] = {}
        for pair in self.trading_cfg.pairs:
            try:
                prices[pair] = self.get_current_price(pair)
            except Exception as e:
                log.error("market_data.price_failed", pair=pair, error=str(e))
        return prices
