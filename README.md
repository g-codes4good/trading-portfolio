# Trading Portfolio Analysis

An AI-powered technical analysis platform with two interfaces: command-line for deep analysis and web for quick portfolio checks. Organizes stocks into four categories (long-term held, long-term unheld, short-term held, short-term unheld) and provides real-time technical signals.

**Built with:** Python + CLI, Cloudflare Pages, vanilla JavaScript, and AI-assisted development

## Quick Start

### Web Version (Browser)
```bash
npm install
npm run dev
# Visit http://localhost:8788
```

### CLI Version (Terminal)
```bash
cd cli
python -m pip install -r requirements.txt
python main.py
```

## Project Structure

This is a **monorepo** with separate implementations of the same analysis engine:

```
trading-portfolio/
├── public/                       # Static files (web interface)
│   └── index.html               # Form + results display
├── functions/                    # Cloudflare Pages Functions
│   └── api/
│       └── analyze.js           # Technical analysis API
├── cli/                          # Command-line interface (Python)
│   ├── main.py                   # Interactive menu
│   ├── data_fetcher.py          # Live data via yfinance
│   ├── indicators.py            # Technical analysis engine
│   ├── portfolio.py             # Portfolio state management
│   ├── display.py               # Rich terminal output
│   └── requirements.txt
├── shared/                       # Documentation & logic
│   └── ANALYSIS_LOGIC.md        # Core algorithm reference
├── wrangler.toml                # Cloudflare Pages config
├── package.json                 # Web dependencies
└── README.md                    # This file
```

## Features

- 📊 **Multi-category stock management** — Organize by strategy (long/short × held/unheld)
- 📈 **Technical analysis** — EMA, RSI, ADX, pullback detection
- 🎯 **Smart signals** — BUY/SELL/HOLD based on market regime
- 📅 **Historical analysis** — Analyze any date with both versions
- 🌐 **Dual interfaces** — CLI for power users, web for quick checks

## How Analysis Works

Both versions implement the same algorithm:

1. **Fetch OHLCV data** for each stock (live from Yahoo Finance)
2. **Calculate indicators**:
   - Trend: 200-day EMA (long-term) or 50-day EMA (short-term)
   - Momentum: RSI (14-period)
   - Strength: ADX (14-period)
   - Entry points: Pullback detection (5% long-term, 3% short-term)
3. **Generate signals** based on market regime (bull/bear/transition)
4. **Display results** with criteria met/unmet

See [`shared/ANALYSIS_LOGIC.md`](shared/ANALYSIS_LOGIC.md) for technical details.

## Deployment

### Web Version to Cloudflare Pages
Connected via GitHub—automatically deploys on push!

Dashboard settings:
- **Build output directory:** `public`
- **Build command:** (blank)

Live at: `trading-portfolio.pages.dev`

### CLI Version
No deployment needed—runs locally after installing Python dependencies.

## About AI Usage

This project was developed with AI assistance. Both interfaces implement the same trading logic—Claude AI helped design the technical analysis engine, form layouts, and API architecture to showcase modern fintech patterns.

## Future Enhancements

- **Shared**: MACD, Bollinger Bands, sector rotation, backtesting
- **CLI**: Portfolio persistence, interactive watchlist editor
- **Web**: Real-time updates, alert system, historical comparison charts
