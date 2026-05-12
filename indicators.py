"""
indicators.py — Technical analysis engine.

Philosophy (aligned with all_signals_strategy.py):
  - EMA (not SMA) for trend: 200-day for long-term, 50-day for short-term
  - ADX rising/falling as signal confirmation (not just strength threshold)
  - RSI divergence: hidden bullish (buy signal) and bearish (sell signal)
  - Pullback detection: 5% from recent high (long-term), 3% (short-term)
  - Market regime: composite of ^GSPC, ^IXIC, ^DJI, ^RUT with EMA + volatility bands
  - Volume surge as supplemental confirmation
  - Criteria-based signals with explicit met/unmet lists
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
import pandas as pd
import numpy as np

try:
    import ta
    TA_AVAILABLE = True
except ImportError:
    TA_AVAILABLE = False

from data_fetcher import DataFetcher


SECTOR_ETFS = {
    "Technology":             "XLK",
    "Financials":             "XLF",
    "Healthcare":             "XLV",
    "Energy":                 "XLE",
    "Industrials":            "XLI",
    "Utilities":              "XLU",
    "Real Estate":            "XLRE",
    "Communication Services": "XLC",
    "Consumer Discretionary": "XLY",
    "Consumer Staples":       "XLP",
    "Materials":              "XLB",
}

INDEX_TICKERS = ['^GSPC', '^IXIC', '^DJI', '^RUT']


@dataclass
class TechnicalSignal:
    ticker:         str
    signal:         str          # BUY | HOLD | SELL
    strategy:       str          # long-term | short-term
    trend:          str          # UPTREND | DOWNTREND | SIDEWAYS
    momentum:       str          # BULLISH | BEARISH | NEUTRAL
    rsi:            float = 0.0
    adx:            float = 0.0
    adx_rising:     bool  = False
    above_50ema:    bool  = False
    above_200ema:   bool  = False
    pullback_pct:   float = 0.0
    rsi_divergence: str   = "none"   # hidden_bullish | bearish | none
    macd_bullish:   bool  = False
    atr:            float = 0.0
    rs_vs_spy:      float = 0.0
    score:          int   = 0        # supplemental score (MACD, volume, RS)
    criteria_met:   List[str] = field(default_factory=list)
    criteria_unmet: List[str] = field(default_factory=list)
    notes:          List[str] = field(default_factory=list)


@dataclass
class MarketRegime:
    regime:           str    # BULL | BEAR | TRANSITION
    strength:         str    # STRONG | MODERATE | WEAK
    market_zone:      str    # BULL | BEAR | TRANSITION
    composite_value:  float = 0.0
    composite_ema200: float = 0.0
    upper_band:       float = 0.0
    lower_band:       float = 0.0
    vix:              float = 0.0
    notes:            List[str] = field(default_factory=list)


# ─── Indicator helpers ────────────────────────────────────────────────────────

def _calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def _calc_adx(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """Manual ADX calculation (matches all_signals_strategy.py)."""
    highs  = df['High']
    lows   = df['Low']
    closes = df['Close']

    tr = pd.DataFrame({
        'h_l':  highs - lows,
        'h_pc': (highs - closes.shift(1)).abs(),
        'l_pc': (lows  - closes.shift(1)).abs(),
    }).max(axis=1)

    plus_dm  = highs.diff()
    minus_dm = lows.diff()
    plus_dm[plus_dm < 0]   = 0
    minus_dm[minus_dm > 0] = 0
    minus_dm = minus_dm.abs()

    atr      = tr.ewm(alpha=1/period, adjust=False).mean()
    plus_di  = 100 * (plus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    minus_di = 100 * (minus_dm.ewm(alpha=1/period, adjust=False).mean() / atr)
    dx       = 100 * ((plus_di - minus_di).abs() / (plus_di + minus_di))
    return dx.ewm(alpha=1/period, adjust=False).mean()


def _calc_rsi(series: pd.Series, period: int = 14) -> pd.Series:
    delta = series.diff()
    gain  = delta.where(delta > 0, 0).ewm(alpha=1/period, adjust=False).mean()
    loss  = delta.where(delta < 0, 0).abs().ewm(alpha=1/period, adjust=False).mean()
    rs    = gain / loss
    return 100 - (100 / (1 + rs))


def _detect_rsi_divergence(data: pd.DataFrame, lookback: int = 90) -> str:
    """
    Returns 'hidden_bullish', 'bearish', or 'none'.
    data must have columns: High, Low, RSI.
    Mirrors logic from all_signals_strategy.py.
    """
    if len(data) < lookback + 2:
        return "none"

    recent = data.iloc[-lookback:]

    # Hidden bullish: price makes lower low, RSI makes higher low
    low1_date  = recent['Low'].idxmin()
    after_low1 = recent.loc[recent.index > low1_date]
    if not after_low1.empty:
        rsi_lows = after_low1['RSI'].sort_values()
        if not rsi_lows.empty:
            low2_date = rsi_lows.index[0]
            if (recent.loc[low1_date, 'Low'] < recent.loc[low2_date, 'Low'] and
                    recent.loc[low1_date, 'RSI'] > recent.loc[low2_date, 'RSI']):
                return "hidden_bullish"

    # Bearish: price makes higher high, RSI makes lower high
    high1_date  = recent['High'].idxmax()
    after_high1 = recent.loc[recent.index > high1_date]
    if not after_high1.empty:
        rsi_highs = after_high1['RSI'].sort_values(ascending=False)
        if not rsi_highs.empty:
            high2_date = rsi_highs.index[0]
            if (recent.loc[high1_date, 'High'] > recent.loc[high2_date, 'High'] and
                    recent.loc[high1_date, 'RSI'] < recent.loc[high2_date, 'RSI']):
                return "bearish"

    return "none"


class MarketAnalyzer:
    def __init__(self, fetcher: DataFetcher):
        self.fetcher = fetcher

    # ─── Market Regime ───────────────────────────────────────────────────────

    def get_market_regime(self) -> MarketRegime:
        """
        Composite index of ^GSPC, ^IXIC, ^DJI, ^RUT normalized to 100.
        EMA(200) + volatility bands (EMA ± 1 rolling std dev).
        Zone crossings trigger regime change notes.
        """
        import yfinance as yf
        regime = MarketRegime(regime="TRANSITION", strength="WEAK",
                              market_zone="TRANSITION")

        try:
            raw = yf.download(INDEX_TICKERS, period="2y", progress=False,
                              auto_adjust=True)
            if raw.empty:
                regime.notes.append("Could not fetch index data")
                return regime

            closes = raw['Close'] if isinstance(raw.columns, pd.MultiIndex) else raw[['Close']]
            closes = closes[INDEX_TICKERS].dropna()

            if len(closes) < 200:
                regime.notes.append("Insufficient index history for composite")
                return regime

            normalized = closes.divide(closes.iloc[0]) * 100
            composite  = normalized.mean(axis=1)

        except Exception as e:
            regime.notes.append(f"Index data error: {e}")
            return regime

        ema200      = _calc_ema(composite, 200)
        rolling_std = composite.rolling(window=200).std()
        upper_band  = ema200 + rolling_std
        lower_band  = ema200 - rolling_std

        latest     = float(composite.iloc[-1])
        prev       = float(composite.iloc[-2])
        ema_now    = float(ema200.iloc[-1])
        up_now     = float(upper_band.iloc[-1])
        lo_now     = float(lower_band.iloc[-1])
        up_prev    = float(upper_band.iloc[-2])
        lo_prev    = float(lower_band.iloc[-2])

        regime.composite_value  = round(latest, 2)
        regime.composite_ema200 = round(ema_now, 2)
        regime.upper_band       = round(up_now, 2)
        regime.lower_band       = round(lo_now, 2)

        # Current zone
        if latest > up_now:
            regime.market_zone = "BULL"
        elif latest < lo_now:
            regime.market_zone = "BEAR"
        else:
            regime.market_zone = "TRANSITION"

        # Detect zone crossings (same logic as all_signals_strategy.py)
        if prev > up_prev and latest <= up_now:
            regime.regime, regime.strength = "TRANSITION", "MODERATE"
            regime.notes.append(
                "Market crossed from BULL into transition zone — consider reducing risk / moving into cash")
        elif prev < lo_prev and latest >= lo_now:
            regime.regime, regime.strength = "TRANSITION", "MODERATE"
            regime.notes.append(
                "Market crossed from BEAR into transition zone — potential recovery, consider re-entering stocks")
        elif latest > up_now:
            regime.regime, regime.strength = "BULL", "STRONG"
            regime.notes.append("Composite above upper volatility band — strong bull trend")
        elif latest < lo_now:
            regime.regime, regime.strength = "BEAR", "STRONG"
            regime.notes.append("Composite below lower volatility band — bear trend")
        else:
            regime.regime, regime.strength = "TRANSITION", "MODERATE"
            regime.notes.append("Composite in transition zone (between volatility bands)")

        # VIX context
        vix_df = self.fetcher.get_history("^VIX", period="5d")
        if vix_df is not None and not vix_df.empty:
            regime.vix = round(float(vix_df["Close"].iloc[-1]), 1)
            if regime.vix > 30:
                regime.notes.append(f"VIX elevated at {regime.vix} — high fear/volatility")
            elif regime.vix < 15:
                regime.notes.append(f"VIX low at {regime.vix} — complacency, watch for spike")

        return regime

    # ─── Individual Ticker ───────────────────────────────────────────────────

    def analyze_ticker(self, ticker: str, strategy: str = "long-term",
                       check_buys: bool = True) -> TechnicalSignal:
        """
        strategy : "long-term"  → 200 EMA, 5% pullback, RSI divergence, ADX rising
                   "short-term" → 50 EMA, 3% pullback, RSI 30-50 bounce, ADX falling
        check_buys : True  = unheld, look for BUY signal
                     False = held, look for SELL signal
        """
        sig = TechnicalSignal(ticker=ticker, signal="HOLD", strategy=strategy,
                              trend="SIDEWAYS", momentum="NEUTRAL")

        df = self.fetcher.get_history(ticker, period="2y")
        if df is None or len(df) < 50:
            sig.notes.append("Insufficient data for analysis")
            return sig

        close  = df["Close"].squeeze()
        high   = df["High"].squeeze()
        low    = df["Low"].squeeze()
        volume = df["Volume"].squeeze() if "Volume" in df.columns else None
        price  = float(close.iloc[-1])

        # ── EMAs ─────────────────────────────────────────────────────────────
        ema50  = _calc_ema(close, 50)
        ema200 = _calc_ema(close, 200)
        sig.above_50ema  = price > float(ema50.iloc[-1])
        sig.above_200ema = price > float(ema200.iloc[-1])

        if sig.above_200ema and float(ema50.iloc[-1]) > float(ema200.iloc[-1]):
            sig.trend = "UPTREND"
        elif not sig.above_200ema and float(ema50.iloc[-1]) < float(ema200.iloc[-1]):
            sig.trend = "DOWNTREND"
        else:
            sig.trend = "SIDEWAYS"

        # ── ADX (manual — rising/falling tracked) ────────────────────────────
        adx_series = _calc_adx(df)
        sig.adx        = round(float(adx_series.iloc[-1]), 1)
        sig.adx_rising = (float(adx_series.iloc[-1]) > float(adx_series.iloc[-2])
                          if len(adx_series) > 1 else False)

        # ── RSI ───────────────────────────────────────────────────────────────
        rsi_series = _calc_rsi(close)
        sig.rsi    = round(float(rsi_series.iloc[-1]), 1)

        # ── RSI divergence ────────────────────────────────────────────────────
        lookback = 90 if strategy == "long-term" else 30
        data_df  = pd.DataFrame({'Close': close, 'High': high,
                                  'Low': low,   'RSI':  rsi_series})
        sig.rsi_divergence = _detect_rsi_divergence(data_df, lookback=lookback)

        # ── Pullback from recent high ─────────────────────────────────────────
        recent_high = float(data_df.iloc[-lookback:]['High'].max())
        if recent_high > price:
            sig.pullback_pct = round((recent_high - price) / recent_high * 100, 1)

        # ── Supplemental: MACD, ATR, relative strength ────────────────────────
        supp_score = 0
        if TA_AVAILABLE:
            macd_ind     = ta.trend.MACD(close)
            m_val        = float(macd_ind.macd().iloc[-1])
            s_val        = float(macd_ind.macd_signal().iloc[-1])
            sig.macd_bullish = m_val > s_val
            supp_score += 1 if sig.macd_bullish else -1

            atr_ind = ta.volatility.AverageTrueRange(high, low, close)
            sig.atr = round(float(atr_ind.average_true_range().iloc[-1]), 2)

        if volume is not None and len(volume) >= 20:
            vol_avg = float(volume.rolling(20).mean().iloc[-1])
            vol_now = float(volume.iloc[-1])
            if vol_now > vol_avg * 1.2:
                if float(close.iloc[-1]) > float(close.iloc[-2]):
                    supp_score += 1
                    sig.notes.append("Volume surge on up move — institutional buying")
                else:
                    supp_score -= 1
                    sig.notes.append("Volume surge on down move — institutional selling")

        spy_df = self.fetcher.get_history("SPY", period="3mo")
        if spy_df is not None and not spy_df.empty:
            spy_close = spy_df["Close"].squeeze()
            periods   = min(63, len(close) - 1, len(spy_close) - 1)
            if periods > 10:
                ticker_ret  = (float(close.iloc[-1]) / float(close.iloc[-periods]) - 1) * 100
                spy_ret     = (float(spy_close.iloc[-1]) / float(spy_close.iloc[-periods]) - 1) * 100
                sig.rs_vs_spy = round(ticker_ret - spy_ret, 1)
                if sig.rs_vs_spy > 5:
                    supp_score += 1
                    sig.notes.append(f"Outperforming SPY by {sig.rs_vs_spy:+.1f}% (3mo) ↑")
                elif sig.rs_vs_spy < -5:
                    supp_score -= 1
                    sig.notes.append(f"Underperforming SPY by {sig.rs_vs_spy:+.1f}% (3mo) ↓")

        sig.score    = supp_score
        sig.momentum = ("BULLISH" if sig.macd_bullish and sig.rsi > 50
                        else "BEARISH" if not sig.macd_bullish and sig.rsi < 50
                        else "NEUTRAL")

        # ── Primary signal criteria ───────────────────────────────────────────
        if strategy == "long-term":
            self._apply_long_term_criteria(sig, check_buys)
        else:
            self._apply_short_term_criteria(sig, check_buys, volume, close)

        return sig

    def _apply_long_term_criteria(self, sig: TechnicalSignal,
                                   check_buys: bool) -> None:
        if check_buys:
            if sig.above_200ema:
                sig.criteria_met.append("Price above 200-day EMA")
            else:
                sig.criteria_unmet.append("Price not above 200-day EMA")

            if sig.adx_rising:
                sig.criteria_met.append("ADX rising (trend strengthening)")
            else:
                sig.criteria_unmet.append("ADX not rising")

            if sig.rsi_divergence == "hidden_bullish":
                sig.criteria_met.append("Hidden bullish RSI divergence detected")
            else:
                sig.criteria_unmet.append("No hidden bullish divergence")

            if sig.pullback_pct >= 5.0:
                sig.criteria_met.append(
                    f"Pullback {sig.pullback_pct:.1f}% from recent high (≥5%)")
            else:
                sig.criteria_unmet.append(
                    f"No significant pullback (current: {sig.pullback_pct:.1f}%)")

            if not sig.criteria_unmet:
                sig.signal = "BUY"

        else:  # sell
            if sig.rsi_divergence == "bearish":
                sig.criteria_met.append("Bearish RSI divergence detected")
            else:
                sig.criteria_unmet.append("No bearish RSI divergence")

            if not sig.above_200ema:
                sig.criteria_met.append("Price below 200-day EMA")
            else:
                sig.criteria_unmet.append("Price not below 200-day EMA")

            if not sig.criteria_unmet:
                sig.signal = "SELL"

    def _apply_short_term_criteria(self, sig: TechnicalSignal, check_buys: bool,
                                    volume, close: pd.Series) -> None:
        if check_buys:
            if sig.above_50ema:
                sig.criteria_met.append("Price above 50-day EMA")
            else:
                sig.criteria_unmet.append("Price not above 50-day EMA")

            rsi_bounce = 30 < sig.rsi < 50
            if rsi_bounce:
                sig.criteria_met.append(
                    f"RSI in oversold bounce range 30–50 (current: {sig.rsi:.1f})")
            else:
                sig.criteria_unmet.append(
                    f"RSI not in bounce range (current: {sig.rsi:.1f})")

            if sig.pullback_pct >= 3.0:
                sig.criteria_met.append(
                    f"Pullback {sig.pullback_pct:.1f}% from recent high (≥3%)")
            else:
                sig.criteria_unmet.append(
                    f"No significant pullback (current: {sig.pullback_pct:.1f}%)")

            if volume is not None and len(volume) >= 20:
                vol_avg = float(volume.rolling(20).mean().iloc[-1])
                if float(volume.iloc[-1]) > vol_avg * 1.2:
                    sig.criteria_met.append("Volume surge ≥20% above 20-day avg")
                else:
                    sig.criteria_unmet.append("No significant volume surge")

            # Core three required; volume is supplemental
            if sig.above_50ema and rsi_bounce and sig.pullback_pct >= 3.0:
                sig.signal = "BUY"

        else:  # sell
            rsi_ob = sig.rsi > 70
            if rsi_ob:
                sig.criteria_met.append(f"RSI overbought: {sig.rsi:.1f} (>70)")
            else:
                sig.criteria_unmet.append(f"RSI not overbought (current: {sig.rsi:.1f})")

            if not sig.above_50ema:
                sig.criteria_met.append("Price below 50-day EMA")
            else:
                sig.criteria_unmet.append("Price not below 50-day EMA")

            adx_falling = not sig.adx_rising
            if adx_falling:
                sig.criteria_met.append("ADX falling (trend weakening)")
            else:
                sig.criteria_unmet.append("ADX not falling")

            if (rsi_ob and not sig.above_50ema) or (not sig.above_50ema and adx_falling):
                sig.signal = "SELL"

    # ─── Sector Rotation ─────────────────────────────────────────────────────

    def get_sector_rotation(self) -> List[Dict]:
        """Rank sector ETFs by 1-month and 3-month momentum vs SPY."""
        results = []
        spy_1m = spy_3m = 1.0

        spy_df = self.fetcher.get_history("SPY", period="6mo")
        if spy_df is not None:
            spy_c = spy_df["Close"].squeeze()
            if len(spy_c) >= 21:
                spy_1m = float(spy_c.iloc[-1]) / float(spy_c.iloc[-22])
            if len(spy_c) >= 63:
                spy_3m = float(spy_c.iloc[-1]) / float(spy_c.iloc[-63])

        for sector, etf in SECTOR_ETFS.items():
            df = self.fetcher.get_history(etf, period="6mo")
            if df is None or df.empty:
                continue
            c = df["Close"].squeeze()
            mo1 = mo3 = 0.0
            if len(c) >= 22:
                mo1 = round((float(c.iloc[-1]) / float(c.iloc[-22]) - 1) * 100, 1)
            if len(c) >= 63:
                mo3 = round((float(c.iloc[-1]) / float(c.iloc[-63]) - 1) * 100, 1)
            spy_1m_pct = round((spy_1m - 1) * 100, 1)
            spy_3m_pct = round((spy_3m - 1) * 100, 1)
            results.append({
                "sector": sector, "etf": etf,
                "1mo": mo1, "3mo": mo3,
                "rs_1mo": round(mo1 - spy_1m_pct, 1),
                "rs_3mo": round(mo3 - spy_3m_pct, 1),
            })

        results.sort(key=lambda x: x["rs_3mo"], reverse=True)
        return results
