"""MNQ paper account accounting."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class AccountState:
    initial_balance: float = 10_000.0
    cash_balance: float = 10_000.0
    realized_pnl: float = 0.0
    unrealized_pnl: float = 0.0
    equity: float = 10_000.0
    peak_equity: float = 10_000.0
    drawdown: float = 0.0
    max_drawdown: float = 0.0
    commissions: float = 0.0
    slippage_cost: float = 0.0
    open_position: str = "FLAT"

    def to_dict(self) -> dict:
        return asdict(self)


def mnq_gross_pnl(
    entry_price: float,
    exit_price: float,
    quantity: int = 1,
    point_value: float = 2.0,
) -> float:
    """LONG gross PnL: (exit - entry) * point_value * qty."""
    return (exit_price - entry_price) * point_value * quantity


def apply_fill_costs(
    *,
    commission_per_side: float,
    slippage_ticks: int,
    tick_value: float,
    quantity: int,
) -> tuple[float, float]:
    commission = commission_per_side * quantity
    slippage_cost = slippage_ticks * tick_value * quantity
    return commission, slippage_cost


def simulate_market_fill_price(
    *,
    signal_price: float,
    side: str,
    tick_size: float = 0.25,
    slippage_ticks: int = 1,
) -> float:
    """Realistic market fill: buy pays up, sell receives down."""
    slip = slippage_ticks * tick_size
    if side.upper() == "BUY":
        return signal_price + slip
    if side.upper() == "SELL":
        return signal_price - slip
    raise ValueError(f"Unknown side: {side}")


def mark_to_market(
    account: AccountState,
    *,
    position_state: str,
    entry_price: Optional[float],
    current_price: Optional[float],
    quantity: int,
    point_value: float,
) -> AccountState:
    unrealized = 0.0
    if (
        position_state == "LONG"
        and entry_price is not None
        and current_price is not None
    ):
        unrealized = (current_price - entry_price) * point_value * quantity

    equity = account.cash_balance + unrealized
    peak = max(account.peak_equity, equity)
    dd = peak - equity
    max_dd = max(account.max_drawdown, dd)

    account.unrealized_pnl = unrealized
    account.equity = equity
    account.peak_equity = peak
    account.drawdown = dd
    account.max_drawdown = max_dd
    account.open_position = position_state
    return account


def performance_from_trades(trades: list[dict], initial_balance: float) -> dict:
    closed = [t for t in trades if t.get("status") == "CLOSED" and t.get("net_pnl") is not None]
    pnls = [float(t["net_pnl"]) for t in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p <= 0]
    gross_profit = sum(wins)
    gross_loss = abs(sum(losses))
    pf = (gross_profit / gross_loss) if gross_loss > 0 else (float("inf") if gross_profit > 0 else 0.0)

    streak = 0
    longest_losing = 0
    for p in pnls:
        if p <= 0:
            streak += 1
            longest_losing = max(longest_losing, streak)
        else:
            streak = 0

    realized = sum(pnls)
    return {
        "total_trades": len(closed),
        "winning_trades": len(wins),
        "losing_trades": len(losses),
        "win_rate": (len(wins) / len(closed) * 100.0) if closed else 0.0,
        "profit_factor": pf if pf != float("inf") else None,
        "profit_factor_display": "∞" if pf == float("inf") else round(pf, 4),
        "average_trade": (realized / len(closed)) if closed else 0.0,
        "largest_winner": max(wins) if wins else 0.0,
        "largest_loser": min(losses) if losses else 0.0,
        "longest_losing_streak": longest_losing,
        "total_net_pnl": realized,
        "ending_balance": initial_balance + realized,
    }
