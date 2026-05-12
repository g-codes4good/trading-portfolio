# Trading Portfolio Analysis Logic

This document describes the core analysis logic shared across both CLI and web implementations.

## Philosophy

- **Market regime gates all signals** — SPY trend determines overall market direction (bull/bear/transition)
- **Technical indicators are evidence, not prediction** — EMA, RSI, ADX provide signals, not certainty
- **Strategy-driven analysis** — Different rules for long-term vs. short-term holdings
- **Tax-efficient positioning** — Prefer selling losers and long-term positions when rebalancing

## Core Indicators

### Trend Detection
- **Long-term**: 200-day Exponential Moving Average (EMA)
- **Short-term**: 50-day EMA
- **Signal**: Price above EMA = UPTREND, below = DOWNTREND

### Momentum
- **RSI (14-period)** — Relative Strength Index
  - RSI > 70: Overbought (potential sell signal)
  - RSI < 30: Oversold (potential buy signal)
  - RSI 30-70: Neutral

### Trend Strength
- **ADX (14-period)** — Average Directional Index
  - Rising ADX: Trend strengthening
  - Falling ADX: Trend weakening
  - Used for confirmation, not primary signal

### Entry/Exit Points
- **Pullback Detection**: 
  - Long-term: 5% pullback from recent high
  - Short-term: 3% pullback from recent high
- **Volume surge**: Supplemental confirmation for breakouts

## Signal Generation Rules

### Long-term Holdings
**BUY Signal:**
- Price above 200-day EMA
- RSI < 70 (not overbought)
- Pullback < 5% from recent high
- Market regime is BULL or TRANSITION

**SELL Signal:**
- Price below 200-day EMA, OR
- RSI > 70 (overbought)
- Market regime is BEAR

**HOLD:** Everything else

### Short-term Holdings
**BUY Signal:**
- Price above 50-day EMA
- RSI < 70
- Pullback < 3% from recent high
- ADX rising

**SELL Signal:**
- Price below 50-day EMA, OR
- RSI > 80 (strongly overbought)
- Market regime is BEAR

**HOLD:** Everything else

## Market Regime Assessment

Determined by SPY (S&P 500) analysis:

- **BULL**: SPY above 200-day EMA + rising ADX
- **BEAR**: SPY below 200-day EMA + falling ADX
- **TRANSITION**: Crossing between zones

Strength levels:
- **STRONG**: High ADX, clear trend
- **MODERATE**: Medium ADX, established direction
- **WEAK**: Low ADX, choppy movement

## Implementation Notes

### Python CLI
- Located in `cli/`
- Uses `ta` library for technical analysis
- Real-time data via yfinance
- Interactive menu-driven interface
- Can save portfolio state locally

### Web Version
- Located in `web/`
- JavaScript implementation of analysis logic
- Cloudflare Pages Functions for API
- Browser-based UI with responsive design
- Real-time data fetching from public APIs

## Data Sources

Both implementations pull live data from:
- Yahoo Finance API (via yfinance or equivalent)
- Returns OHLCV (Open, High, Low, Close, Volume) data

## Future Enhancements

- MACD crossover signals
- Bollinger Bands for volatility assessment
- Volume-weighted average price (VWAP)
- Sector rotation analysis
- Portfolio backtesting
