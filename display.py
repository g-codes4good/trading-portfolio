"""
display.py — All Rich-based terminal rendering.
"""

from typing import Dict, List, Optional
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.columns import Columns
from rich import box
from rich.rule import Rule

console = Console()


# ─── Color helpers ───────────────────────────────────────────────────────────

def _green(s): return f"[bold green]{s}[/bold green]"
def _red(s):   return f"[bold red]{s}[/bold red]"
def _yellow(s):return f"[yellow]{s}[/yellow]"
def _cyan(s):  return f"[cyan]{s}[/cyan]"
def _dim(s):   return f"[dim]{s}[/dim]"
def _bold(s):  return f"[bold]{s}[/bold]"

def _color_pct(v: float) -> str:
    s = f"{v:+.2f}%"
    return _green(s) if v > 0 else _red(s) if v < 0 else _dim(s)

def _color_val(v: float) -> str:
    s = f"${v:,.2f}"
    return _green(s) if v > 0 else _red(s) if v < 0 else _dim(s)

def _signal_color(signal: str) -> str:
    colors = {
        "STRONG BUY":  "bold bright_green",
        "BUY":         "green",
        "HOLD":        "yellow",
        "SELL":        "red",
        "STRONG SELL": "bold bright_red",
    }
    c = colors.get(signal, "white")
    return f"[{c}]{signal}[/{c}]"

def _regime_color(regime: str, strength: str) -> str:
    if regime == "BULL":
        c = "bold bright_green" if strength == "STRONG" else "green"
    elif regime == "BEAR":
        c = "bold bright_red" if strength == "STRONG" else "red"
    else:
        c = "yellow"
    return f"[{c}]{strength} {regime}[/{c}]"


# ─── Market Regime ────────────────────────────────────────────────────────────

def show_market_regime(regime) -> None:
    zone_color = {"BULL": "green", "BEAR": "red", "TRANSITION": "yellow"}
    zone_str   = zone_color.get(regime.market_zone, "white")

    lines = [
        f"Regime:        {_regime_color(regime.regime, regime.strength)}",
        f"Market Zone:   [{zone_str}]{regime.market_zone}[/{zone_str}]",
        f"Composite:     {_bold(str(regime.composite_value))}  "
        f"EMA(200): {_bold(str(regime.composite_ema200))}",
        f"Upper Band:    {_bold(str(regime.upper_band))}  "
        f"Lower Band: {_bold(str(regime.lower_band))}",
        f"VIX:           {_bold(str(regime.vix)) if regime.vix else _dim('N/A')}",
    ]
    if regime.notes:
        lines.append("")
        lines.append(_bold("Observations:"))
        for n in regime.notes:
            lines.append(f"  • {n}")

    console.print(Panel("\n".join(lines),
                        title="[bold cyan]Market Regime — Composite Index[/bold cyan]",
                        border_style="cyan", expand=False))


# ─── Portfolio Dashboard ─────────────────────────────────────────────────────

def show_portfolio(positions, cash: float, prices: Dict[str, float],
                   current_weights: Dict[str, float],
                   targets: Dict[str, float],
                   pnl: Dict[str, dict]) -> None:

    total = sum(p["value"] for p in pnl.values()) + cash
    total_cost = sum(p["cost"] for p in pnl.values())
    total_gain = total - total_cost
    total_gain_pct = (total_gain / total_cost * 100) if total_cost else 0

    # Header
    header = (
        f"Total Value: {_bold(f'${total:,.2f}')}"
        f"  Cash: {_bold(f'${cash:,.2f}')} ({cash/total*100:.1f}%)"
        f"  Total P&L: {_color_val(total_gain)} ({_color_pct(total_gain_pct)})"
    )
    console.print(Panel(header, title="[bold cyan]Portfolio[/bold cyan]",
                        border_style="cyan", expand=False))

    if not positions:
        console.print(_dim("  No positions."))
        return

    tbl = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold white")
    for col, just in [
        ("Ticker", "left"), ("Term", "left"), ("Sector", "left"),
        ("Shares", "right"), ("Price", "right"), ("Mkt Value", "right"),
        ("Cost Basis", "right"), ("P&L $", "right"), ("P&L %", "right"),
        ("Weight", "right"), ("Target", "right"), ("Drift", "right"),
        ("Days Held", "right"),
    ]:
        tbl.add_column(col, justify=just)

    for ticker, p in sorted(pnl.items()):
        pos      = positions.get(ticker)
        w        = current_weights.get(ticker, 0.0) * 100
        tgt      = targets.get(ticker, 0.0) * 100
        drift    = w - tgt
        term_lbl = ("[green]LONG[/green]" if p["long_term"] else "[yellow]SHORT[/yellow]")

        tbl.add_row(
            _bold(ticker),
            term_lbl,
            pos.sector if pos else "",
            str(p["shares"]),
            f"${p['price']:,.2f}",
            f"${p['value']:,.2f}",
            f"${p['cost']:,.2f}",
            _color_val(p["gain"]),
            _color_pct(p["gain_pct"]),
            f"{w:.1f}%",
            f"{tgt:.1f}%" if tgt > 0 else _dim("—"),
            (_color_pct(drift) if tgt > 0 else _dim("—")),
            str(p["days_held"]),
        )

    if cash > 0:
        w = current_weights.get("CASH", 0.0) * 100
        tgt = targets.get("CASH", 0.0) * 100
        drift = w - tgt
        tbl.add_row(
            _bold("CASH"), _dim("—"), _dim("—"), _dim("—"),
            _dim("—"), f"${cash:,.2f}", f"${cash:,.2f}",
            _dim("$0.00"), _dim("0.00%"),
            f"{w:.1f}%",
            f"{tgt:.1f}%" if tgt > 0 else _dim("—"),
            (_color_pct(drift) if tgt > 0 else _dim("—")),
            _dim("—"),
        )

    console.print(tbl)


# ─── Technical Analysis ───────────────────────────────────────────────────────

def show_technical_signal(sig) -> None:
    adx_dir = "[green]↑ Rising[/green]" if sig.adx_rising else "[red]↓ Falling[/red]"
    div_map  = {
        "hidden_bullish": "[green]Hidden Bullish[/green]",
        "bearish":        "[red]Bearish[/red]",
        "none":           _dim("None"),
    }
    lines = [
        f"Signal:      {_signal_color(sig.signal)}  "
        f"[dim]({sig.strategy}, {'looking for BUY' if sig.signal != 'SELL' else 'looking for SELL'})[/dim]",
        f"Trend:       {_bold(sig.trend)}  |  Momentum: {_bold(sig.momentum)}",
        f"RSI(14):     {_bold(str(sig.rsi))}",
        f"200 EMA:     {'[green]ABOVE ✓[/green]' if sig.above_200ema else '[red]BELOW ✗[/red]'}  "
        f"50 EMA: {'[green]ABOVE[/green]' if sig.above_50ema else '[red]BELOW[/red]'}",
        f"ADX(14):     {_bold(str(sig.adx))}  {adx_dir}  "
        f"ATR: {_bold(str(sig.atr))}",
        f"RSI Div:     {div_map.get(sig.rsi_divergence, _dim('None'))}",
        f"Pullback:    {_bold(f'{sig.pullback_pct:.1f}%')} from recent high",
        f"vs SPY(3mo): {_color_pct(sig.rs_vs_spy)}  "
        f"MACD: {'[green]Bullish[/green]' if sig.macd_bullish else '[red]Bearish[/red]'}",
    ]

    if sig.criteria_met or sig.criteria_unmet:
        lines.append("")
        lines.append(_bold("Signal Criteria:"))
        for c in sig.criteria_met:
            lines.append(f"  [green]✓[/green] {c}")
        for c in sig.criteria_unmet:
            lines.append(f"  [red]✗[/red] {c}")

    if sig.notes:
        lines.append("")
        lines.append(_bold("Supplemental:"))
        for n in sig.notes:
            lines.append(f"  • {n}")

    console.print(Panel("\n".join(lines),
                        title=f"[bold cyan]Technical Analysis — {sig.ticker}[/bold cyan]",
                        border_style="cyan", expand=False))


# ─── Rebalancing trades ───────────────────────────────────────────────────────

def show_rebalancing(trades: List[dict], total: float) -> None:
    if not trades:
        console.print(Panel("[green]Portfolio is within tolerance of all targets.[/green]",
                            title="Rebalancing", border_style="green", expand=False))
        return

    tbl = Table(box=box.SIMPLE_HEAVY, header_style="bold white",
                title=f"Rebalancing Trades  (total portfolio: ${total:,.2f})")
    tbl.add_column("Action", justify="center")
    tbl.add_column("Ticker", justify="left")
    tbl.add_column("Shares", justify="right")
    tbl.add_column("Est. Value", justify="right")
    tbl.add_column("Current %", justify="right")
    tbl.add_column("Target %", justify="right")
    tbl.add_column("Tax Note", justify="left")

    for t in trades:
        action_str = ("[green]BUY[/green]" if t["action"] == "BUY"
                      else "[red]SELL[/red]")
        tbl.add_row(
            action_str,
            _bold(t["ticker"]),
            str(t["shares"]),
            f"${t['value']:,.2f}",
            f"{t['current_pct']:.1f}%",
            f"{t['target_pct']:.1f}%",
            _yellow(t["tax_note"]) if t["tax_note"] else _dim("—"),
        )

    console.print(tbl)


# ─── Allocation Shift Planner ─────────────────────────────────────────────────

def show_allocation_shift(plan: dict) -> None:
    total = plan["total_value"]

    # Before / After side-by-side
    before_tbl = Table(title="BEFORE", box=box.SIMPLE, header_style="bold white")
    after_tbl  = Table(title="AFTER",  box=box.SIMPLE, header_style="bold white")

    for tbl in (before_tbl, after_tbl):
        tbl.add_column("Ticker", justify="left")
        tbl.add_column("Weight", justify="right")
        tbl.add_column("Value",  justify="right")

    for row in plan["rows"]:
        tk = _bold(row["ticker"])
        before_tbl.add_row(tk, f"{row['curr_w']:.1f}%", f"${row['curr_val']:,.2f}")
        after_tbl.add_row(
            tk,
            _green(f"{row['new_w']:.1f}%") if row["new_w"] > row["curr_w"]
            else _red(f"{row['new_w']:.1f}%") if row["new_w"] < row["curr_w"]
            else f"{row['new_w']:.1f}%",
            f"${row['new_val']:,.2f}",
        )

    console.print(f"\n  Portfolio total: {_bold(f'${total:,.2f}')}\n")
    console.print(Columns([
        Panel(before_tbl, border_style="dim"),
        Panel(after_tbl,  border_style="green"),
    ]))

    # Trade list
    if plan["trades"]:
        tbl2 = Table(title="Trades to Execute", box=box.SIMPLE_HEAVY,
                     header_style="bold white")
        tbl2.add_column("Action",    justify="center")
        tbl2.add_column("Ticker",    justify="left")
        tbl2.add_column("Shares",    justify="right")
        tbl2.add_column("Est. Value",justify="right")
        tbl2.add_column("Tax Flag",  justify="left")

        for t in plan["trades"]:
            tbl2.add_row(
                "[green]BUY[/green]" if t["action"] == "BUY" else "[red]SELL[/red]",
                _bold(t["ticker"]),
                str(t["shares"]),
                f"${t['value']:,.2f}",
                _yellow(t["tax_flag"]) if t["tax_flag"] else _dim("—"),
            )
        console.print(tbl2)
    else:
        console.print(_green("  No trades needed — allocations already match."))


# ─── Sector Rotation ─────────────────────────────────────────────────────────

def show_sector_rotation(sectors: List[dict]) -> None:
    tbl = Table(box=box.SIMPLE_HEAVY, header_style="bold white",
                title="Sector Rotation — Relative Strength vs SPY")
    tbl.add_column("Sector",    justify="left")
    tbl.add_column("ETF",       justify="center")
    tbl.add_column("1-mo Ret",  justify="right")
    tbl.add_column("3-mo Ret",  justify="right")
    tbl.add_column("RS 1mo",    justify="right")
    tbl.add_column("RS 3mo",    justify="right")
    tbl.add_column("Signal",    justify="center")

    for s in sectors:
        rs3 = s["rs_3mo"]
        signal = ("LEADING" if rs3 > 3 else
                  "LAGGING" if rs3 < -3 else
                  "IN LINE")
        sig_str = (_green("LEADING") if signal == "LEADING" else
                   _red("LAGGING") if signal == "LAGGING" else
                   _dim("IN LINE"))
        tbl.add_row(
            s["sector"], _bold(s["etf"]),
            _color_pct(s["1mo"]),
            _color_pct(s["3mo"]),
            _color_pct(s["rs_1mo"]),
            _color_pct(s["rs_3mo"]),
            sig_str,
        )

    console.print(tbl)
    console.print(_dim("  RS = return relative to SPY for same period"))


# ─── Multi-ticker summary ─────────────────────────────────────────────────────

def show_portfolio_signals(signals: list, regime) -> None:
    tbl = Table(box=box.SIMPLE_HEAVY, header_style="bold white",
                title="Portfolio Technical Signals")
    tbl.add_column("Ticker",   justify="left")
    tbl.add_column("Strategy", justify="center")
    tbl.add_column("Signal",   justify="center")
    tbl.add_column("Trend",    justify="center")
    tbl.add_column("RSI",      justify="right")
    tbl.add_column("200 EMA",  justify="center")
    tbl.add_column("ADX",      justify="right")
    tbl.add_column("ADX Dir",  justify="center")
    tbl.add_column("Divergence", justify="center")
    tbl.add_column("Pullback", justify="right")
    tbl.add_column("vs SPY",   justify="right")

    div_map = {
        "hidden_bullish": "[green]Hid.Bull[/green]",
        "bearish":        "[red]Bearish[/red]",
        "none":           _dim("—"),
    }

    for sig in signals:
        tbl.add_row(
            _bold(sig.ticker),
            _dim(sig.strategy),
            _signal_color(sig.signal),
            ("[green]UP[/green]"  if sig.trend == "UPTREND"   else
             "[red]DOWN[/red]"   if sig.trend == "DOWNTREND" else _dim("SIDE")),
            str(sig.rsi),
            ("[green]✓[/green]" if sig.above_200ema else "[red]✗[/red]"),
            str(sig.adx),
            ("[green]↑[/green]" if sig.adx_rising else "[red]↓[/red]"),
            div_map.get(sig.rsi_divergence, _dim("—")),
            f"{sig.pullback_pct:.1f}%",
            _color_pct(sig.rs_vs_spy),
        )

    regime_str = _regime_color(regime.regime, regime.strength)
    console.print(tbl)
    console.print(f"  Market regime: {regime_str}  "
                  f"[dim](zone: {regime.market_zone})[/dim]")


def show_watchlist_signals(signals: list, regime) -> None:
    buy_signals  = [s for s in signals if s.signal == "BUY"]
    sell_signals = [s for s in signals if s.signal == "SELL"]
    hold_signals = [s for s in signals if s.signal == "HOLD"]

    for group, label, color in [
        (buy_signals,  "BUY Signals",  "green"),
        (sell_signals, "SELL Signals", "red"),
        (hold_signals, "No Signal",    "dim"),
    ]:
        if not group:
            continue
        tbl = Table(box=box.SIMPLE_HEAVY, header_style="bold white",
                    title=f"[{color}]{label}[/{color}]")
        tbl.add_column("Ticker",     justify="left")
        tbl.add_column("Strategy",   justify="center")
        tbl.add_column("Watching",   justify="center")
        tbl.add_column("Trend",      justify="center")
        tbl.add_column("RSI",        justify="right")
        tbl.add_column("ADX",        justify="right")
        tbl.add_column("ADX Dir",    justify="center")
        tbl.add_column("Divergence", justify="center")
        tbl.add_column("Pullback",   justify="right")
        tbl.add_column("vs SPY",     justify="right")

        div_map = {
            "hidden_bullish": "[green]Hid.Bull[/green]",
            "bearish":        "[red]Bearish[/red]",
            "none":           _dim("—"),
        }

        for sig in group:
            watch = "[green]BUY[/green]" if getattr(sig, '_check_buys', True) else "[red]SELL[/red]"
            tbl.add_row(
                _bold(sig.ticker),
                _dim(sig.strategy),
                watch,
                ("[green]UP[/green]"  if sig.trend == "UPTREND"   else
                 "[red]DOWN[/red]"   if sig.trend == "DOWNTREND" else _dim("SIDE")),
                str(sig.rsi),
                str(sig.adx),
                ("[green]↑[/green]" if sig.adx_rising else "[red]↓[/red]"),
                div_map.get(sig.rsi_divergence, _dim("—")),
                f"{sig.pullback_pct:.1f}%",
                _color_pct(sig.rs_vs_spy),
            )

            if sig.criteria_met or sig.criteria_unmet:
                met_str   = "  ".join(f"[green]✓[/green] {c}" for c in sig.criteria_met)
                unmet_str = "  ".join(f"[red]✗[/red] {c}" for c in sig.criteria_unmet)
                detail = (met_str + ("  " if met_str and unmet_str else "") + unmet_str)
                tbl.add_row(_dim(""), _dim(""), _dim(""), _dim(""), _dim(""),
                            _dim(""), _dim(""), _dim(""), _dim(""), detail)

        console.print(tbl)

    regime_str = _regime_color(regime.regime, regime.strength)
    console.print(f"  Market regime: {regime_str}  [dim](zone: {regime.market_zone})[/dim]")
