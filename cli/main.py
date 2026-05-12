#!/usr/bin/env python3
"""
main.py — Trading Portfolio Manager

Philosophy:
  • Market regime (SPY trend) gates all individual signals.
  • Technical indicators are evidence, not prediction.
  • Uptrend: maximize exposure. Downtrend: minimize loss, protect capital.
  • Tax-efficient rebalancing: prefer selling losers and long-term positions.

Run:  python main.py
"""

import sys
from datetime import date

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from rich.rule import Rule

from data_fetcher import DataFetcher
from portfolio import Portfolio
from indicators import MarketAnalyzer
import display as D

console = Console()
fetcher = DataFetcher()
analyzer = MarketAnalyzer(fetcher)


# ─── Menu helpers ─────────────────────────────────────────────────────────────

MENU = """
[bold cyan]Trading Portfolio Manager[/bold cyan]

 [bold white]Portfolio[/bold white]
   1. View portfolio dashboard
   2. Add / update position
   3. Remove position
   4. Set cash balance
   5. Set target allocations

 [bold white]Analysis[/bold white]
   6. Market regime (SPY)
   7. Technical analysis — single ticker
   8. Portfolio signals (all holdings)
   9. Sector rotation heatmap
  12. Watchlist signals (from watchlist.txt)

 [bold white]Rebalancing[/bold white]
  10. Rebalance to current targets
  11. Allocation shift planner (before/after)

 [bold white]Other[/bold white]
   0. Quit
"""


def banner():
    console.print()
    console.print(Panel(MENU, border_style="cyan", expand=False))


def ask(prompt: str, default: str = "") -> str:
    return Prompt.ask(f"[cyan]{prompt}[/cyan]", default=default).strip()


def ask_ticker() -> str:
    return ask("Ticker symbol").upper()


# ─── Actions ──────────────────────────────────────────────────────────────────

def action_view_portfolio(portfolio: Portfolio):
    tickers = portfolio.get_tickers()
    if not tickers:
        console.print("[yellow]Portfolio is empty. Add positions first.[/yellow]")
        return

    console.print("[dim]Fetching prices...[/dim]")
    prices = fetcher.get_multiple_prices(tickers)

    pnl     = portfolio.get_pnl(prices)
    weights = portfolio.get_current_weights(prices)
    total   = portfolio.get_total_value(prices)

    D.show_portfolio(portfolio.positions, portfolio.cash, prices,
                     weights, portfolio.targets, pnl)


def action_add_position(portfolio: Portfolio):
    ticker = ask_ticker()
    if not ticker:
        return

    # Fetch current price as default
    console.print(f"[dim]Fetching {ticker}...[/dim]")
    price_now = fetcher.get_current_price(ticker)
    price_hint = f"{price_now:.2f}" if price_now else ""
    info = fetcher.get_info(ticker)

    console.print(f"  [dim]Name: {info['name']}  Sector: {info['sector']}[/dim]")

    shares_str = ask("Shares (e.g. 10 or 10.5)")
    try:
        shares = float(shares_str)
    except ValueError:
        console.print("[red]Invalid number of shares.[/red]")
        return

    cost_str = ask("Cost basis per share", default=price_hint)
    try:
        cost = float(cost_str)
    except ValueError:
        console.print("[red]Invalid cost basis.[/red]")
        return

    term = ask("Term (short / long)", default="long").lower()
    if term not in ("short", "long"):
        term = "long"

    strategy = ask("Strategy (long-term / short-term)", default="long-term").lower()
    if strategy not in ("long-term", "short-term"):
        strategy = "long-term"

    sector = ask("Sector", default=info.get("sector", "Unknown"))
    today  = date.today().isoformat()
    pdate  = ask("Purchase date (YYYY-MM-DD)", default=today)
    notes  = ask("Notes (optional)", default="")

    portfolio.add_or_update_position(ticker, shares, cost, term, sector, pdate, notes, strategy)
    console.print(f"[green]✓ {ticker} saved.[/green]")

    # Offer to set a target weight
    if Confirm.ask("Set a target allocation weight for this ticker?", default=False):
        action_set_target_single(portfolio, ticker)


def action_remove_position(portfolio: Portfolio):
    if not portfolio.positions:
        console.print("[yellow]No positions to remove.[/yellow]")
        return
    console.print("  Current tickers: " +
                  ", ".join(f"[cyan]{t}[/cyan]" for t in portfolio.positions))
    ticker = ask_ticker()
    if ticker not in portfolio.positions:
        console.print(f"[red]{ticker} not found.[/red]")
        return

    pos = portfolio.positions[ticker]
    console.print(f"  {ticker}: {pos.shares} shares @ ${pos.cost_basis:.2f}")
    sell_all = Confirm.ask("Remove entire position?", default=True)
    if sell_all:
        portfolio.remove_position(ticker)
        console.print(f"[green]✓ {ticker} removed.[/green]")
    else:
        shares_str = ask("Shares to remove")
        try:
            portfolio.remove_position(ticker, float(shares_str))
            console.print(f"[green]✓ Reduced {ticker}.[/green]")
        except ValueError:
            console.print("[red]Invalid number.[/red]")


def action_set_cash(portfolio: Portfolio):
    current = f"{portfolio.cash:.2f}"
    amt_str = ask(f"Cash balance (current: ${current})", default=current)
    try:
        portfolio.set_cash(float(amt_str))
        console.print(f"[green]✓ Cash set to ${portfolio.cash:,.2f}[/green]")
    except ValueError:
        console.print("[red]Invalid amount.[/red]")


def action_set_target_single(portfolio: Portfolio, ticker: str = None):
    if ticker is None:
        console.print("  Current tickers: " +
                      ", ".join(f"[cyan]{t}[/cyan]" for t in portfolio.positions))
        ticker = ask_ticker()

    current = portfolio.targets.get(ticker, 0.0) * 100
    pct_str = ask(f"Target weight % for {ticker} (0 to remove)", default=f"{current:.1f}")
    try:
        pct = float(pct_str)
        portfolio.set_target(ticker, pct / 100)
        ok, msg = portfolio.validate_targets()
        console.print(f"[green]✓ {ticker} target: {pct:.1f}%[/green]  [{('green' if ok else 'red')}]{msg}[/{'green' if ok else 'red'}]")
    except ValueError:
        console.print("[red]Invalid percentage.[/red]")


def action_set_targets(portfolio: Portfolio):
    console.print(
        "[dim]Set target weights for each position.\n"
        "Weights should sum to ≤ 100%; remainder treated as CASH.\n"
        "Enter 0 to clear a target.[/dim]\n"
    )
    tickers = list(portfolio.positions.keys()) + (
        [t for t in portfolio.targets if t not in portfolio.positions])
    if not tickers:
        console.print("[yellow]Add positions first.[/yellow]")
        return

    for ticker in tickers:
        current = portfolio.targets.get(ticker, 0.0) * 100
        pct_str = ask(f"  {ticker:8s} target %", default=f"{current:.1f}")
        try:
            portfolio.set_target(ticker, float(pct_str) / 100)
        except ValueError:
            pass

    # Optional CASH target
    cash_tgt = portfolio.targets.get("CASH", 0.0) * 100
    pct_str = ask("  CASH     target % (0 = ignore)", default=f"{cash_tgt:.1f}")
    try:
        portfolio.set_target("CASH", float(pct_str) / 100)
    except ValueError:
        pass

    ok, msg = portfolio.validate_targets()
    console.print(f"[{'green' if ok else 'red'}]{msg}[/{'green' if ok else 'red'}]")


def action_market_regime():
    console.print("[dim]Fetching SPY and VIX...[/dim]")
    regime = analyzer.get_market_regime()
    D.show_market_regime(regime)


def action_technical_single():
    ticker = ask_ticker()
    if not ticker:
        return
    strategy   = ask("Strategy (long-term / short-term)", default="long-term").lower()
    check_buys_str = ask("Looking for (buy / sell)", default="buy").lower()
    check_buys = check_buys_str != "sell"
    console.print(f"[dim]Analyzing {ticker}...[/dim]")
    sig = analyzer.analyze_ticker(ticker, strategy=strategy, check_buys=check_buys)
    D.show_technical_signal(sig)


def action_portfolio_signals(portfolio: Portfolio):
    tickers = portfolio.get_tickers()
    if not tickers:
        console.print("[yellow]No positions in portfolio.[/yellow]")
        return
    console.print(f"[dim]Analyzing {len(tickers)} held positions for SELL signals...[/dim]")
    regime  = analyzer.get_market_regime()
    signals = []
    for t in tickers:
        console.print(f"[dim]  {t}...[/dim]", end="\r")
        pos      = portfolio.positions[t]
        strategy = getattr(pos, 'strategy', 'long-term')
        signals.append(analyzer.analyze_ticker(t, strategy=strategy, check_buys=False))
    console.print()
    D.show_portfolio_signals(signals, regime)


def action_watchlist_signals():
    from portfolio import Watchlist
    wl = Watchlist()
    if not wl.is_loaded():
        console.print("[red]No watchlist file found. Expected watchlist.txt in project dir "
                      "or the Finance/trading path.[/red]")
        return

    console.print(f"[dim]Loaded watchlist from: {wl.filepath}[/dim]")
    console.print(f"[dim]Long-term unheld: {wl.tickers['long-term-unheld']}[/dim]")
    console.print(f"[dim]Long-term held: {wl.tickers['long-term-held']}[/dim]")
    console.print(f"[dim]Short-term unheld: {wl.tickers['short-term-unheld']}[/dim]")
    console.print(f"[dim]Short-term held: {wl.tickers['short-term-held']}[/dim]")
    console.print()

    regime  = analyzer.get_market_regime()
    signals = []

    for category, strategy, check_buys in [
        ('long-term-unheld',  'long-term',  True),
        ('long-term-held',    'long-term',  False),
        ('short-term-unheld', 'short-term', True),
        ('short-term-held',   'short-term', False),
    ]:
        for ticker in wl.tickers[category]:
            console.print(f"[dim]  {ticker} ({category})...[/dim]", end="\r")
            sig = analyzer.analyze_ticker(ticker, strategy=strategy, check_buys=check_buys)
            sig._check_buys = check_buys
            signals.append(sig)

    console.print()
    D.show_watchlist_signals(signals, regime)


def action_sector_rotation():
    console.print("[dim]Fetching 11 sector ETFs...[/dim]")
    sectors = analyzer.get_sector_rotation()
    D.show_sector_rotation(sectors)


def action_rebalance(portfolio: Portfolio):
    if not portfolio.targets:
        console.print("[yellow]No target weights set. Use option 5 first.[/yellow]")
        return
    tickers = portfolio.get_tickers()
    console.print("[dim]Fetching prices...[/dim]")
    prices = fetcher.get_multiple_prices(tickers)
    total  = portfolio.get_total_value(prices)
    trades = portfolio.get_rebalancing_trades(prices)
    D.show_rebalancing(trades, total)


def action_allocation_shift(portfolio: Portfolio):
    """Interactive before/after allocation planner."""
    tickers = portfolio.get_tickers()
    if not tickers:
        console.print("[yellow]Add positions first.[/yellow]")
        return

    console.print("[dim]Fetching prices...[/dim]")
    prices = fetcher.get_multiple_prices(tickers)

    console.print(
        "\n[bold]Enter new target allocations.[/bold]  "
        "[dim]Leave blank to keep 0%. Weights should sum to ≤ 100%.[/dim]\n"
    )

    new_targets: dict = {}
    all_tickers = list(portfolio.positions.keys())

    # Show current + ask new
    for ticker in all_tickers:
        curr_w = portfolio.targets.get(ticker, 0.0) * 100
        pct_str = ask(f"  {ticker:8s} new target %", default=f"{curr_w:.1f}")
        try:
            new_targets[ticker] = float(pct_str) / 100
        except ValueError:
            new_targets[ticker] = 0.0

    # Allow adding new tickers
    while True:
        extra = ask("Add a NEW ticker to the plan (or Enter to skip)", default="").upper()
        if not extra:
            break
        price = fetcher.get_current_price(extra)
        if not price:
            console.print(f"[red]Could not fetch price for {extra}.[/red]")
            continue
        pct_str = ask(f"  {extra:8s} target %", default="0.0")
        try:
            new_targets[extra] = float(pct_str) / 100
            prices[extra] = price
        except ValueError:
            pass

    cash_pct = ask("  CASH     target %", default="0.0")
    try:
        new_targets["CASH"] = float(cash_pct) / 100
    except ValueError:
        pass

    total_w = sum(new_targets.values())
    if total_w > 1.001:
        console.print(f"[red]Weights sum to {total_w*100:.1f}% — exceeds 100%. Adjust and retry.[/red]")
        return

    plan = portfolio.plan_allocation_shift(new_targets, prices)
    D.show_allocation_shift(plan)

    if plan["trades"] and Confirm.ask("\nApply these as your new targets?", default=False):
        for ticker, w in new_targets.items():
            portfolio.set_target(ticker, w)
        console.print("[green]✓ New targets saved.[/green]")


# ─── Main loop ────────────────────────────────────────────────────────────────

def main():
    portfolio = Portfolio()
    console.print(Panel(
        f"[bold cyan]Trading Portfolio Manager[/bold cyan]\n"
        f"[dim]Loaded: {len(portfolio.positions)} position(s) | "
        f"Cash: ${portfolio.cash:,.2f} | "
        f"Date: {date.today()}[/dim]",
        border_style="cyan", expand=False))

    ACTIONS = {
        "1":  lambda: action_view_portfolio(portfolio),
        "2":  lambda: action_add_position(portfolio),
        "3":  lambda: action_remove_position(portfolio),
        "4":  lambda: action_set_cash(portfolio),
        "5":  lambda: action_set_targets(portfolio),
        "6":  action_market_regime,
        "7":  action_technical_single,
        "8":  lambda: action_portfolio_signals(portfolio),
        "9":  action_sector_rotation,
        "10": lambda: action_rebalance(portfolio),
        "11": lambda: action_allocation_shift(portfolio),
        "12": action_watchlist_signals,
        "0":  None,
    }

    while True:
        banner()
        choice = ask("Choice", default="1")

        if choice == "0":
            console.print("[dim]Goodbye.[/dim]")
            sys.exit(0)

        action = ACTIONS.get(choice)
        if action is None:
            console.print(f"[red]Unknown option: {choice}[/red]")
            continue

        console.print(Rule())
        try:
            action()
        except KeyboardInterrupt:
            console.print("\n[dim](interrupted)[/dim]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            if "--debug" in sys.argv:
                import traceback
                traceback.print_exc()
        console.print()


if __name__ == "__main__":
    main()
