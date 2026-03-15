"""
External Data Feeds for ML Meta-Learner v3

Fetches market context data from free APIs (no API keys needed):
  - Fear & Greed Index (alternative.me)
  - BTC perpetual funding rate (Binance Futures)
  - BTC open interest (Binance Futures)
  - Long/short account ratio (Binance Futures)
  - Taker buy/sell ratio (Binance Futures)
  - BTC dominance + 24h/7d change (alternative.me)
  - Global crypto market cap change (CoinGecko)
  - S&P 500 daily change (Yahoo Finance)
"""

from __future__ import annotations

import json
import time
from typing import Any

import structlog

log = structlog.get_logger()


class ExternalData:
    """Fetches market context data from free APIs."""

    def __init__(self) -> None:
        self._cache: dict[str, Any] = {}
        self._cache_times: dict[str, float] = {}
        self._cache_ttl = 300

    def _fetch_json(self, url: str, key: str) -> Any:
        """Cached JSON fetch."""
        now = time.time()
        if key in self._cache and (now - self._cache_times.get(key, 0)) < self._cache_ttl:
            return self._cache[key]

        try:
            import urllib.request
            req = urllib.request.Request(url, headers={"User-Agent": "CryptoBot/3.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
                self._cache[key] = data
                self._cache_times[key] = now
                return data
        except Exception as e:
            log.debug("external_data.fetch_failed", key=key, error=str(e))
            return self._cache.get(key)

    def get_fear_greed(self) -> dict:
        data = self._fetch_json(
            "https://api.alternative.me/fng/?limit=1&format=json", "fng"
        )
        if data and "data" in data:
            return {
                "fg_value": int(data["data"][0]["value"]),
                "fg_class": data["data"][0]["value_classification"],
            }
        return {"fg_value": 50, "fg_class": "Neutral"}

    def get_funding_rates(self) -> dict:
        data = self._fetch_json(
            "https://fapi.binance.com/fapi/v1/fundingRate?symbol=BTCUSDT&limit=1",
            "binance_funding"
        )
        if data and isinstance(data, list) and len(data) > 0:
            rate = float(data[0].get("fundingRate", 0))
            return {"funding_rate": rate}
        return {"funding_rate": 0.0}

    def get_open_interest(self) -> dict:
        data = self._fetch_json(
            "https://fapi.binance.com/fapi/v1/openInterest?symbol=BTCUSDT",
            "binance_oi"
        )
        if data and "openInterest" in data:
            return {"btc_open_interest": float(data["openInterest"])}
        return {"btc_open_interest": 0.0}

    def get_long_short_ratio(self) -> dict:
        data = self._fetch_json(
            "https://fapi.binance.com/futures/data/globalLongShortAccountRatio?symbol=BTCUSDT&period=1h&limit=1",
            "binance_ls"
        )
        if data and isinstance(data, list) and len(data) > 0:
            ratio = float(data[0].get("longShortRatio", 1.0))
            long_pct = float(data[0].get("longAccount", 0.5))
            return {"long_short_ratio": ratio, "long_account_pct": long_pct}
        return {"long_short_ratio": 1.0, "long_account_pct": 0.5}

    def get_taker_buy_sell(self) -> dict:
        data = self._fetch_json(
            "https://fapi.binance.com/futures/data/takerlongshortRatio?symbol=BTCUSDT&period=1h&limit=1",
            "binance_taker"
        )
        if data and isinstance(data, list) and len(data) > 0:
            ratio = float(data[0].get("buySellRatio", 1.0))
            return {"taker_buy_sell_ratio": ratio}
        return {"taker_buy_sell_ratio": 1.0}

    def get_btc_dominance(self) -> dict:
        data = self._fetch_json(
            "https://api.alternative.me/v2/ticker/bitcoin/?convert=USD", "btc_dom"
        )
        if data and "data" in data:
            btc_data = data["data"].get("1", {})
            quotes = btc_data.get("quotes", {}).get("USD", {})
            return {
                "btc_dominance": quotes.get("market_cap_dominance", 50),
                "btc_24h_change": quotes.get("percent_change_24h", 0),
                "btc_7d_change": quotes.get("percent_change_7d", 0),
            }
        return {"btc_dominance": 50, "btc_24h_change": 0, "btc_7d_change": 0}

    def get_global_market(self) -> dict:
        data = self._fetch_json(
            "https://api.coingecko.com/api/v3/global", "coingecko_global"
        )
        if data and "data" in data:
            d = data["data"]
            return {
                "market_cap_change_24h": d.get("market_cap_change_percentage_24h_usd", 0),
                "active_cryptos": d.get("active_cryptocurrencies", 0),
            }
        return {"market_cap_change_24h": 0, "active_cryptos": 0}

    def get_sp500(self) -> dict:
        try:
            data = self._fetch_json(
                "https://query1.finance.yahoo.com/v8/finance/chart/SPY?interval=1d&range=5d",
                "sp500"
            )
            if data and "chart" in data:
                result = data["chart"].get("result", [{}])[0]
                closes = result.get("indicators", {}).get("quote", [{}])[0].get("close", [])
                if len(closes) >= 2 and closes[-1] and closes[-2]:
                    change = ((closes[-1] - closes[-2]) / closes[-2]) * 100
                    return {"sp500_daily_change": round(change, 2)}
        except Exception:
            pass
        return {"sp500_daily_change": 0.0}

    # --- Google Trends for crypto keywords (trendspyg) ---
    def get_google_trends(self) -> dict:
        now = time.time()
        key = "google_trends"
        if key in self._cache and (now - self._cache_times.get(key, 0)) < 3600:
            return self._cache[key]

        try:
            from trendspyg import TrendsClient
            client = TrendsClient()
            data = client.interest_over_time(keywords=["bitcoin", "crypto crash", "buy crypto"], timeframe="now 7-d")
            if data is not None and not data.empty:
                latest = data.iloc[-1]
                result = {
                    "trends_bitcoin": int(latest.get("bitcoin", 50)),
                    "trends_crash": int(latest.get("crypto crash", 0)),
                    "trends_buy": int(latest.get("buy crypto", 0)),
                }
                self._cache[key] = result
                self._cache_times[key] = now
                log.info("external.google_trends_fetched", **result)
                return result
        except Exception as e:
            log.debug("external.google_trends_failed", error=str(e))

        cached = self._cache.get(key, {"trends_bitcoin": 50, "trends_crash": 0, "trends_buy": 0})
        return cached

    def get_all(self) -> dict:
        features = {}
        features.update(self.get_fear_greed())
        features.update(self.get_funding_rates())
        features.update(self.get_open_interest())
        features.update(self.get_long_short_ratio())
        features.update(self.get_taker_buy_sell())
        features.update(self.get_btc_dominance())
        features.update(self.get_global_market())
        features.update(self.get_sp500())
        features.update(self.get_google_trends())
        return features
