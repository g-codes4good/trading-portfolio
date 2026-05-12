# Trading Portfolio Analysis

An AI-powered web application for technical analysis of stock portfolios. Organizes stocks into four categories (long-term held, long-term unheld, short-term held, short-term unheld) and provides real-time technical signals.

**Built with:** Cloudflare Pages, Pages Functions, vanilla JavaScript, and AI-assisted development

## Features

- 📊 **Multi-category stock management** — Organize holdings and watchlist into four strategy-based categories
- 📈 **Technical analysis** — Real-time EMA, RSI, ADX, and pullback detection
- 🎯 **Smart signals** — BUY/SELL/HOLD recommendations based on market regime and technical indicators
- 📅 **Historical analysis** — Analyze portfolio performance on any date
- 🌐 **Cloud-deployed** — Live on Cloudflare Pages for instant access

## Local Development

Install dependencies:
```bash
npm install
```

Run development server:
```bash
npm run dev
```

Visit `http://localhost:8788`

## Deployment

Deploy to Cloudflare Pages:
```bash
npm run deploy
```

## How It Works

1. **Input stocks** in four categories and select analysis date
2. **API analyzes** each stock using:
   - 200-day EMA (long-term) / 50-day EMA (short-term) for trend
   - RSI (14) for momentum
   - ADX for trend strength
   - Pullback detection for entry points
3. **Market regime** assessment via SPY analysis
4. **Signals generated** based on technical criteria

## About AI Usage

This project was developed with AI assistance. The technical analysis engine, frontend form design, and API architecture were collaboratively designed with Claude AI to showcase modern trading technology patterns.

## Project Structure

```
├── public/
│   └── index.html           # Frontend form and results display
├── functions/
│   └── api/
│       └── analyze.js       # Technical analysis API endpoint
├── wrangler.toml            # Cloudflare Pages configuration
├── package.json             # Dependencies
└── README.md                # This file
```

## Future Enhancements

- Portfolio persistence (save/load analysis history)
- More advanced indicators (MACD, Bollinger Bands)
- Real-time price updates via WebSocket
- Portfolio backtesting
- Email alerts for signals
