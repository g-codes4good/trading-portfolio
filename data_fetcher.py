"""
data_fetcher.py — yfinance wrapper with in-memory caching.
Cache TTL: 15 min for prices, 60 min for history/info.
"""

import time
from typing import Dict, Optional, Any
import pandas as pd
import yfinance as yf


class DataFetcher:
    PRICE_TTL  = 900    # 15 min
    HISTORY_TTL = 3600  # 60 min

    def __init__(self):
        self._cache: Dict[str, Dict] = {}

    # ─── internal ────────────────────────────────────────────────────────────

    def _get(self, key: str) -> Optional[Any]:
        entry = self._cache.get(key)
        if entry and time.time() - entry["ts"] < entry["ttl"]:
            return entry["data"]
        return None

    def _set(self, key: str, data: Any, ttl: int) -> None:
        self._cache[key] = {"data": data, "ts": time.time(), "ttl": ttl}

    def _ticker(self, symbol: str) -> yf.Ticker:
        key = f"_obj_{symbol}"
        obj = self._get(key)
        if obj is None:
            obj = yf.Ticker(symbol)
            self._set(key, obj, self.HISTORY_TTL)
        return obj

    # ─── public API ──────────────────────────────────────────────────────────

    def get_current_price(self, ticker: str) -> Optional[float]:
        key = f"price_{ticker}"
        cached = self._get(key)
        if cached is not None:
            return cached
        try:
            t = self._ticker(ticker)
            data = t.fast_info
            price = float(data.last_price)
            self._set(key, price, self.PRICE_TTL)
            return price
        except Exception:
            try:
                hist = self.get_history(ticker, period="5d")
                if hist is not None and not hist.empty:
                    return float(hist["Close"].iloc[-1])
            except Exception:
                pass
            return None

    def get_multiple_prices(self, tickers: list) -> Dict[str, float]:
        missing = [t for t in tickers if self._get(f"price_{t}") is None]
        if missing:
            try:
                raw = yf.download(missing, period="2d", progress=False, auto_adjust=True)
                if "Close" in raw.columns:
                    closes = raw["Close"].iloc[-1]
                    for sym, price in closes.items():
                        if pd.notna(price):
                            self._set(f"price_{sym}", float(price), self.PRICE_TTL)
            except Exception:
                pass
        result = {}
        for t in tickers:
            p = self.get_current_price(t)
            if p:
                result[t] = p
        return result

    def get_history(self, ticker: str, period: str = "1y",
                    interval: str = "1d") -> Optional[pd.DataFrame]:
        key = f"hist_{ticker}_{period}_{interval}"
        cached = self._get(key)
        if cached is not None:
            return cached
        try:
            df = yf.download(ticker, period=period, interval=interval,
                             progress=False, auto_adjust=True)
            if df.empty:
                return None
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            self._set(key, df, self.HISTORY_TTL)
            return df
        except Exception:
            return None

    def get_info(self, ticker: str) -> Dict[str, Any]:
        key = f"info_{ticker}"
        cached = self._get(key)
        if cached is not None:
            return cached
        try:
            info = self._ticker(ticker).info
            result = {
                "name":   info.get("longName") or info.get("shortName", ticker),
                "sector": info.get("sector", "Unknown"),
                "industry": info.get("industry", "Unknown"),
                "beta":   info.get("beta"),
                "market_cap": info.get("marketCap"),
            }
            self._set(key, result, self.HISTORY_TTL)
            return result
        except Exception:
            return {"name": ticker, "sector": "Unknown", "industry": "Unknown",
                    "beta": None, "market_cap": None}

    def invalidate(self, ticker: str = None) -> None:
        """Clear cache for one ticker, or everything if ticker is None."""
        if ticker:
            self._cache = {k: v for k, v in self._cache.items()
                           if not k.endswith(f"_{ticker}")}
        else:
            self._cache.clear()
