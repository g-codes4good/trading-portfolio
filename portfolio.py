"""
portfolio.py — Portfolio data model and operations.

Persistent storage: portfolio_data.json
Each position tracks: ticker, shares, cost_basis/share, term, sector, purchase_date.
Target weights drive the rebalancing and shift-planner logic.
"""

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple


# ─── Data model ──────────────────────────────────────────────────────────────

@dataclass
class Position:
    ticker:        str
    shares:        float
    cost_basis:    float   # per-share average cost
    term:          str     # "short" | "long"
    sector:        str
    purchase_date: str     # ISO date string YYYY-MM-DD
    notes:         str = ""
    strategy:      str = "long-term"

    @property
    def total_cost(self) -> float:
        return self.shares * self.cost_basis

    def is_long_term(self) -> bool:
        """True if held ≥ 365 days (long-term capital gains treatment)."""
        try:
            bought = datetime.strptime(self.purchase_date, "%Y-%m-%d").date()
            return (date.today() - bought).days >= 365
        except ValueError:
            return self.term == "long"

    def days_held(self) -> int:
        try:
            bought = datetime.strptime(self.purchase_date, "%Y-%m-%d").date()
            return (date.today() - bought).days
        except ValueError:
            return 0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Position":
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})


# ─── Portfolio ────────────────────────────────────────────────────────────────

class Portfolio:
    def __init__(self, filepath: str = "portfolio_data.json"):
        self.filepath  = filepath
        self.positions: Dict[str, Position] = {}   # ticker → Position
        self.targets:   Dict[str, float]    = {}   # ticker → target weight 0-1
        self.cash:      float               = 0.0
        self.load()

    # ─── Persistence ─────────────────────────────────────────────────────────

    def save(self) -> None:
        data = {
            "cash": self.cash,
            "targets": self.targets,
            "positions": {t: p.to_dict() for t, p in self.positions.items()},
            "last_updated": datetime.now().isoformat(),
        }
        with open(self.filepath, "w") as f:
            json.dump(data, f, indent=2)

    def load(self) -> None:
        if not os.path.exists(self.filepath):
            return
        try:
            with open(self.filepath) as f:
                data = json.load(f)
            self.cash    = data.get("cash", 0.0)
            self.targets = data.get("targets", {})
            for ticker, pd_ in data.get("positions", {}).items():
                self.positions[ticker] = Position.from_dict(pd_)
        except (json.JSONDecodeError, KeyError):
            pass  # start fresh if file is corrupt

    # ─── Mutations ───────────────────────────────────────────────────────────

    def add_or_update_position(self, ticker: str, shares: float,
                               cost_basis: float, term: str, sector: str,
                               purchase_date: str, notes: str = "",
                               strategy: str = "long-term") -> None:
        ticker = ticker.upper()
        if ticker in self.positions:
            p = self.positions[ticker]
            # Average down/up cost basis
            total_shares = p.shares + shares
            avg_cost = (p.shares * p.cost_basis + shares * cost_basis) / total_shares
            p.shares    = total_shares
            p.cost_basis = round(avg_cost, 4)
            p.notes     = notes or p.notes
            p.strategy  = strategy
        else:
            self.positions[ticker] = Position(
                ticker=ticker, shares=shares, cost_basis=cost_basis,
                term=term, sector=sector, purchase_date=purchase_date,
                notes=notes, strategy=strategy
            )
        self.save()

    def remove_position(self, ticker: str, shares: float = None) -> bool:
        ticker = ticker.upper()
        if ticker not in self.positions:
            return False
        if shares is None or shares >= self.positions[ticker].shares:
            del self.positions[ticker]
        else:
            self.positions[ticker].shares -= shares
        if ticker in self.targets and ticker not in self.positions:
            del self.targets[ticker]
        self.save()
        return True

    def set_target(self, ticker: str, weight: float) -> None:
        ticker = ticker.upper()
        if weight <= 0 and ticker in self.targets:
            del self.targets[ticker]
        else:
            self.targets[ticker] = round(weight, 4)
        self.save()

    def set_cash(self, amount: float) -> None:
        self.cash = max(0.0, amount)
        self.save()

    # ─── Calculations ────────────────────────────────────────────────────────

    def get_total_value(self, prices: Dict[str, float]) -> float:
        equity = sum(p.shares * prices.get(t, p.cost_basis)
                     for t, p in self.positions.items())
        return equity + self.cash

    def get_current_weights(self, prices: Dict[str, float]) -> Dict[str, float]:
        total = self.get_total_value(prices)
        if total == 0:
            return {}
        weights = {}
        for t, p in self.positions.items():
            price = prices.get(t, p.cost_basis)
            weights[t] = (p.shares * price) / total
        weights["CASH"] = self.cash / total
        return weights

    def get_pnl(self, prices: Dict[str, float]) -> Dict[str, dict]:
        result = {}
        for t, p in self.positions.items():
            price     = prices.get(t, p.cost_basis)
            mkt_value = p.shares * price
            cost      = p.total_cost
            gain      = mkt_value - cost
            pct       = (gain / cost * 100) if cost > 0 else 0.0
            result[t] = {
                "price":     round(price, 2),
                "shares":    p.shares,
                "cost":      round(cost, 2),
                "value":     round(mkt_value, 2),
                "gain":      round(gain, 2),
                "gain_pct":  round(pct, 2),
                "long_term": p.is_long_term(),
                "days_held": p.days_held(),
            }
        return result

    # ─── Rebalancing ─────────────────────────────────────────────────────────

    def get_rebalancing_trades(self, prices: Dict[str, float],
                               tolerance: float = 0.02) -> List[dict]:
        """
        Generate trades to move from current weights to target weights.
        tolerance: skip if drift < this fraction (e.g., 0.02 = 2%).
        Returns list of trade dicts sorted: sells first, then buys.
        """
        if not self.targets:
            return []

        total = self.get_total_value(prices)
        current_weights = self.get_current_weights(prices)
        trades = []

        all_tickers = set(self.targets.keys()) | set(self.positions.keys())
        for ticker in all_tickers:
            if ticker == "CASH":
                continue
            target_w  = self.targets.get(ticker, 0.0)
            current_w = current_weights.get(ticker, 0.0)
            drift     = target_w - current_w

            if abs(drift) < tolerance:
                continue

            price = prices.get(ticker)
            if not price:
                continue

            target_value  = total * target_w
            current_value = total * current_w
            delta_value   = target_value - current_value
            delta_shares  = delta_value / price

            pos = self.positions.get(ticker)
            tax_note = ""
            if pos and delta_shares < 0:
                if pos.is_long_term():
                    tax_note = "Long-term gain (favorable rate)"
                else:
                    days = pos.days_held()
                    left = 365 - days
                    tax_note = (f"Short-term gain — {left}d until long-term"
                                if left > 0 else "Long-term gain")

            trades.append({
                "ticker":       ticker,
                "action":       "SELL" if delta_shares < 0 else "BUY",
                "shares":       round(abs(delta_shares), 2),
                "value":        round(abs(delta_value), 2),
                "current_pct":  round(current_w * 100, 1),
                "target_pct":   round(target_w * 100, 1),
                "tax_note":     tax_note,
            })

        # Sells first (free up cash), then buys
        trades.sort(key=lambda x: (0 if x["action"] == "SELL" else 1,
                                   -x["value"]))
        return trades

    # ─── Allocation Shift Planner ─────────────────────────────────────────────

    def plan_allocation_shift(self, new_targets: Dict[str, float],
                              prices: Dict[str, float]) -> dict:
        """
        Compare BEFORE (current targets) and AFTER (new_targets).
        Returns a plan with: before_state, after_state, trades, tax_flags.
        new_targets: {ticker: weight, ...}  weights should sum to ≤ 1.0.
                     'CASH' key is allowed and means remaining cash %.
        """
        total = self.get_total_value(prices)
        current_weights = self.get_current_weights(prices)

        before_rows = []
        all_tickers = set(current_weights.keys()) | set(new_targets.keys())

        for ticker in sorted(all_tickers):
            curr_w    = current_weights.get(ticker, 0.0)
            new_w     = new_targets.get(ticker, 0.0)
            curr_val  = total * curr_w
            new_val   = total * new_w
            delta     = new_val - curr_val

            pos       = self.positions.get(ticker)
            price     = prices.get(ticker, 0.0) if ticker != "CASH" else 1.0
            curr_shrs = pos.shares if pos else (self.cash if ticker == "CASH" else 0.0)
            new_shrs  = new_val / price if price > 0 and ticker != "CASH" else new_val

            tax_flag = ""
            if pos and delta < 0:
                if pos.is_long_term():
                    tax_flag = "LT gain"
                else:
                    tax_flag = f"ST gain ({pos.days_held()}d)"
            elif pos and delta > 0 and pos.is_long_term():
                tax_flag = "adding to LT"

            before_rows.append({
                "ticker":     ticker,
                "curr_w":     round(curr_w * 100, 1),
                "new_w":      round(new_w * 100, 1),
                "curr_val":   round(curr_val, 2),
                "new_val":    round(new_val, 2),
                "delta_val":  round(delta, 2),
                "curr_shrs":  round(curr_shrs, 2) if ticker != "CASH" else None,
                "new_shrs":   round(new_shrs, 2)  if ticker != "CASH" else None,
                "price":      round(price, 2)       if ticker != "CASH" else None,
                "tax_flag":   tax_flag,
            })

        # Trade list
        trades = []
        for row in before_rows:
            if row["ticker"] == "CASH" or abs(row["delta_val"]) < 1.0:
                continue
            action = "BUY" if row["delta_val"] > 0 else "SELL"
            delta_shares = abs(row["delta_val"]) / row["price"] if row["price"] else 0
            trades.append({
                "action":    action,
                "ticker":    row["ticker"],
                "shares":    round(delta_shares, 2),
                "value":     round(abs(row["delta_val"]), 2),
                "tax_flag":  row["tax_flag"],
            })
        trades.sort(key=lambda x: (0 if x["action"] == "SELL" else 1, -x["value"]))

        return {
            "total_value": round(total, 2),
            "rows":        before_rows,
            "trades":      trades,
        }

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def get_tickers(self) -> List[str]:
        return list(self.positions.keys())

    def target_weights_sum(self) -> float:
        return round(sum(self.targets.values()), 4)

    def validate_targets(self) -> Tuple[bool, str]:
        s = self.target_weights_sum()
        if s > 1.001:
            return False, f"Target weights sum to {s*100:.1f}% — must be ≤ 100%"
        if s < 0.5:
            return True, f"Target weights sum to {s*100:.1f}% — remainder will be CASH"
        return True, f"Target weights sum to {s*100:.1f}%"


class Watchlist:
    """
    Loads the watchlist .txt file used by all_signals_strategy.py.
    Sections: #long-term-unheld, #long-term-held, #short-term-unheld, #short-term-held
    """
    DEFAULT_PATHS = [
        "watchlist.txt",
        "/Users/gretali/Documents/Finance/trading/momentum_trading_strategy_watchlist.txt",
    ]

    def __init__(self, filepath: str = None):
        self.filepath = filepath
        self.tickers: dict = {
            'long-term-unheld':  [],
            'long-term-held':    [],
            'short-term-unheld': [],
            'short-term-held':   [],
        }
        if filepath:
            self.load(filepath)
        else:
            for path in self.DEFAULT_PATHS:
                if os.path.exists(path):
                    self.load(path)
                    break

    def load(self, filepath: str) -> None:
        self.tickers = {k: [] for k in self.tickers}
        current_section = None
        try:
            with open(filepath) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith('#long-term-unheld'):
                        current_section = 'long-term-unheld'
                    elif line.startswith('#long-term-held'):
                        current_section = 'long-term-held'
                    elif line.startswith('#short-term-unheld'):
                        current_section = 'short-term-unheld'
                    elif line.startswith('#short-term-held'):
                        current_section = 'short-term-held'
                    elif line and not line.startswith('#') and current_section:
                        self.tickers[current_section].append(line.upper())
            self.filepath = filepath
        except FileNotFoundError:
            pass

    def is_loaded(self) -> bool:
        return bool(self.filepath and any(self.tickers.values()))

    def all_tickers(self) -> List[str]:
        result = []
        for tickers in self.tickers.values():
            result.extend(tickers)
        return list(set(result))
