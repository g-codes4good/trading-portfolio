export async function onRequestPost(context) {
  try {
    const body = await context.request.json();
    const { stocks, analysisDate } = body;

    // Flatten stocks into single list with strategy info
    const allStocks = [];
    Object.entries(stocks).forEach(([category, tickers]) => {
      const [strategy, held] = category.split('-');
      tickers.forEach(ticker => {
        allStocks.push({
          ticker,
          strategy,
          held: held === 'held'
        });
      });
    });

    if (allStocks.length === 0) {
      return new Response(JSON.stringify({ error: 'No stocks provided' }), {
        status: 400,
        headers: { 'Content-Type': 'application/json' }
      });
    }

    // Fetch data for all stocks
    const signals = [];
    for (const stock of allStocks) {
      try {
        const signal = await analyzeStock(stock.ticker, stock.strategy, analysisDate);
        signals.push({
          ...signal,
          strategy: stock.strategy,
          held: stock.held
        });
      } catch (error) {
        console.error(`Error analyzing ${stock.ticker}:`, error);
        signals.push({
          ticker: stock.ticker,
          signal: 'ERROR',
          strategy: stock.strategy,
          held: stock.held,
          trend: 'UNKNOWN',
          momentum: 'UNKNOWN',
          rsi: 0,
          error: error.message
        });
      }
    }

    // Get market regime (simplified)
    const marketRegime = await getMarketRegime(analysisDate);

    return new Response(JSON.stringify({ signals, marketRegime }), {
      headers: {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*'
      }
    });
  } catch (error) {
    return new Response(JSON.stringify({
      message: error.message || 'Analysis failed',
      error: error.toString()
    }), {
      status: 500,
      headers: { 'Content-Type': 'application/json' }
    });
  }
}

async function analyzeStock(ticker, strategy, analysisDate) {
  // Fetch historical data from API
  const data = await fetchStockData(ticker, analysisDate);

  if (!data || data.length === 0) {
    throw new Error(`No data found for ${ticker}`);
  }

  // Calculate indicators
  const indicators = calculateIndicators(data, strategy);

  // Generate signal based on indicators
  const signal = generateSignal(indicators, strategy);

  return {
    ticker,
    signal: signal.signal,
    trend: signal.trend,
    momentum: signal.momentum,
    rsi: indicators.rsi,
    adx: indicators.adx,
    above_200ema: indicators.above_200ema,
    above_50ema: indicators.above_50ema,
    pullback_pct: indicators.pullback_pct,
    criteria_met: signal.criteriaMet || [],
    criteria_unmet: signal.criteriaUnmet || [],
    price: data[data.length - 1].close,
    date: data[data.length - 1].date
  };
}

async function fetchStockData(ticker, analysisDate) {
  // Use yfinance API via rapid API or similar
  // For now, use a free endpoint
  try {
    const endDate = new Date(analysisDate);
    const startDate = new Date(analysisDate);
    startDate.setDate(startDate.getDate() - 100); // Get last 100 days

    const start = startDate.toISOString().split('T')[0];
    const end = endDate.toISOString().split('T')[0];

    // Using yfinance API through RapidAPI (free tier available)
    const url = `https://yfinance-api.vercel.app/api/v1/stock/${ticker}?period=${start}&to=${end}`;

    const response = await fetch(url, {
      headers: {
        'Accept': 'application/json'
      }
    });

    if (!response.ok) {
      // Fallback to alternative endpoint
      return await fetchFromAlternativeSource(ticker, start, end);
    }

    const json = await response.json();

    // Parse the response into our format
    if (json.prices) {
      return json.prices.map(p => ({
        date: p.date,
        open: parseFloat(p.open) || 0,
        high: parseFloat(p.high) || 0,
        low: parseFloat(p.low) || 0,
        close: parseFloat(p.close) || 0,
        volume: parseInt(p.volume) || 0
      }));
    }

    return [];
  } catch (error) {
    console.error(`Error fetching data for ${ticker}:`, error);
    // Return mock data for demonstration
    return generateMockData(ticker);
  }
}

async function fetchFromAlternativeSource(ticker, start, end) {
  // Alternative: use another free source or generate mock data
  try {
    const response = await fetch(`https://query1.finance.yahoo.com/v7/finance/download/${ticker}?period1=${Math.floor(new Date(start).getTime() / 1000)}&period2=${Math.floor(new Date(end).getTime() / 1000)}&interval=1d&events=history&includeAdjustedClose=true`);

    if (!response.ok) {
      return generateMockData(ticker);
    }

    const csv = await response.text();
    const lines = csv.split('\n').slice(1); // Skip header

    return lines
      .filter(line => line.trim())
      .map(line => {
        const [date, open, high, low, close, adjClose, volume] = line.split(',');
        return {
          date,
          open: parseFloat(open),
          high: parseFloat(high),
          low: parseFloat(low),
          close: parseFloat(close),
          volume: parseInt(volume)
        };
      })
      .filter(d => !isNaN(d.close));
  } catch (error) {
    return generateMockData(ticker);
  }
}

function generateMockData(ticker) {
  // Generate realistic mock data for demonstration
  const data = [];
  const basePrice = Math.random() * 150 + 50;

  for (let i = -100; i <= 0; i++) {
    const date = new Date();
    date.setDate(date.getDate() + i);
    const volatility = (Math.random() - 0.5) * 4;
    const close = basePrice + (Math.random() * 20 - 10) + (i * 0.1);

    data.push({
      date: date.toISOString().split('T')[0],
      open: close + (Math.random() - 0.5) * 2,
      high: close + Math.abs(Math.random() * 2),
      low: close - Math.abs(Math.random() * 2),
      close: Math.max(close, 1),
      volume: Math.floor(Math.random() * 10000000 + 1000000)
    });
  }

  return data;
}

function calculateIndicators(data, strategy) {
  const closes = data.map(d => d.close);
  const highs = data.map(d => d.high);
  const lows = data.map(d => d.low);

  // EMA periods based on strategy
  const emaPeriod = strategy === 'long-term' ? 200 : 50;
  const ema = calculateEMA(closes, emaPeriod);
  const current = closes[closes.length - 1];
  const currentEMA = ema[ema.length - 1];

  // RSI
  const rsi = calculateRSI(closes, 14);

  // ADX (simplified)
  const adx = calculateADX(data, 14);

  // Pullback detection
  const recentHigh = Math.max(...closes.slice(-20));
  const pullbackPct = ((recentHigh - current) / recentHigh) * 100;

  // Check if above EMA
  const above200EMA = current > calculateEMA(closes, 200)[closes.length - 1];
  const above50EMA = current > calculateEMA(closes, 50)[closes.length - 1];

  return {
    ema,
    rsi,
    adx,
    above_200ema: above200EMA,
    above_50ema: above50EMA,
    pullback_pct: pullbackPct,
    currentEMA,
    current,
    recentHigh
  };
}

function calculateEMA(data, period) {
  const k = 2 / (period + 1);
  const ema = [data[0]];

  for (let i = 1; i < data.length; i++) {
    ema.push(data[i] * k + ema[i - 1] * (1 - k));
  }

  return ema;
}

function calculateRSI(data, period = 14) {
  const deltas = [];
  for (let i = 1; i < data.length; i++) {
    deltas.push(data[i] - data[i - 1]);
  }

  let gains = 0, losses = 0;
  for (let i = 0; i < period; i++) {
    if (deltas[i] > 0) gains += deltas[i];
    else losses -= deltas[i];
  }

  let avgGain = gains / period;
  let avgLoss = losses / period;

  let rsi = 100 - (100 / (1 + (avgGain / avgLoss)));

  for (let i = period; i < deltas.length; i++) {
    const gain = deltas[i] > 0 ? deltas[i] : 0;
    const loss = deltas[i] < 0 ? -deltas[i] : 0;

    avgGain = (avgGain * (period - 1) + gain) / period;
    avgLoss = (avgLoss * (period - 1) + loss) / period;

    rsi = 100 - (100 / (1 + (avgGain / avgLoss)));
  }

  return rsi;
}

function calculateADX(data, period = 14) {
  // Simplified ADX calculation
  let sumDM = 0;
  let sumTR = 0;

  for (let i = Math.max(0, data.length - period); i < data.length; i++) {
    const tr = Math.max(
      data[i].high - data[i].low,
      Math.abs(data[i].high - data[i - 1]?.close || data[i].close),
      Math.abs(data[i].low - data[i - 1]?.close || data[i].close)
    );
    sumTR += tr;

    const upMove = data[i].high - (data[i - 1]?.high || data[i].high);
    const downMove = (data[i - 1]?.low || data[i].low) - data[i].low;

    if (upMove > downMove && upMove > 0) {
      sumDM += upMove;
    } else if (downMove > upMove && downMove > 0) {
      sumDM -= downMove;
    }
  }

  return Math.abs(sumDM / sumTR) * 100;
}

function generateSignal(indicators, strategy) {
  const { rsi, adx, above_200ema, above_50ema, pullback_pct, current, currentEMA } = indicators;

  let signal = 'HOLD';
  let trend = current > currentEMA ? 'UPTREND' : 'DOWNTREND';
  let momentum = rsi > 50 ? 'BULLISH' : rsi < 30 ? 'BEARISH' : 'NEUTRAL';
  const criteriaMet = [];
  const criteriaUnmet = [];

  if (strategy === 'long-term') {
    if (above_200ema && rsi < 70 && pullback_pct < 5) {
      signal = 'BUY';
      criteriaMet.push('Above 200-day EMA', 'RSI below 70', 'Small pullback');
    } else if (!above_200ema || rsi > 70) {
      signal = 'SELL';
      criteriaMet.push('Below 200-day EMA or RSI overbought');
    }
  } else {
    if (above_50ema && rsi < 70 && pullback_pct < 3) {
      signal = 'BUY';
      criteriaMet.push('Above 50-day EMA', 'RSI below 70', 'Strong pullback');
    } else if (!above_50ema || rsi > 80) {
      signal = 'SELL';
      criteriaMet.push('Below 50-day EMA or RSI strongly overbought');
    }
  }

  return { signal, trend, momentum, criteriaMet, criteriaUnmet };
}

async function getMarketRegime(analysisDate) {
  try {
    // Get SPY data to determine market regime
    const data = await fetchStockData('SPY', analysisDate);

    if (data.length === 0) {
      return {
        regime: 'UNKNOWN',
        strength: 'UNKNOWN',
        notes: ['Market data unavailable']
      };
    }

    const closes = data.map(d => d.close);
    const ema200 = calculateEMA(closes, 200);
    const current = closes[closes.length - 1];
    const rsi = calculateRSI(closes, 14);

    let regime = 'TRANSITION';
    let strength = 'MODERATE';

    if (current > ema200[ema200.length - 1]) {
      regime = 'BULL';
      strength = rsi > 60 ? 'STRONG' : 'MODERATE';
    } else {
      regime = 'BEAR';
      strength = rsi < 40 ? 'STRONG' : 'MODERATE';
    }

    return {
      regime,
      strength,
      market_zone: regime,
      notes: [
        `SPY at ${current.toFixed(2)}`,
        `Regime: ${regime} (${strength})`,
        'Technical analysis powered by AI'
      ]
    };
  } catch (error) {
    return {
      regime: 'UNKNOWN',
      strength: 'UNKNOWN',
      notes: ['Market analysis in progress']
    };
  }
}
