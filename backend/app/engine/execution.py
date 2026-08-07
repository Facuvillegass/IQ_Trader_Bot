"""Paper execution simulator — market orders, 1-tick slippage, commissions."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

from backend.app.config import Settings
from backend.app.db.database import Database
from backend.app.engine.accounting import (
    AccountState,
    apply_fill_costs,
    mark_to_market,
    mnq_gross_pnl,
    simulate_market_fill_price,
)
from backend.app.engine.strategy import PositionState, SignalType

logger = logging.getLogger("trading")


@dataclass
class ExecutionResult:
    filled: bool
    fill_price: Optional[float] = None
    trade_id: Optional[int] = None
    message: str = ""


class PaperBroker:
    """PAPER-ONLY broker. Refuses any non-paper mode."""

    def __init__(self, db: Database, settings: Settings, account: AccountState):
        if settings.trading_mode != "PAPER":
            raise RuntimeError("Live trading is blocked. TRADING_MODE must be PAPER.")
        self.db = db
        self.settings = settings
        self.account = account

    def execute(
        self,
        *,
        signal_type: SignalType,
        signal_id: Optional[int],
        bar_ts: str,
        signal_price: float,
        fill_ts: str,
        exit_reason: str,
        position_before: PositionState,
    ) -> ExecutionResult:
        if self.settings.trading_mode != "PAPER":
            raise RuntimeError("Blocked: attempted non-paper execution")

        if signal_type == SignalType.ENTER_LONG:
            if position_before != PositionState.FLAT:
                return ExecutionResult(False, message="Already long — no pyramid")
            return self._enter_long(signal_id, bar_ts, signal_price, fill_ts)

        if signal_type == SignalType.EXIT_LONG:
            if position_before != PositionState.LONG:
                return ExecutionResult(False, message="Flat — nothing to exit")
            return self._exit_long(
                signal_id, bar_ts, signal_price, fill_ts, exit_reason
            )

        return ExecutionResult(False, message="No actionable signal")

    def _enter_long(
        self,
        signal_id: Optional[int],
        bar_ts: str,
        signal_price: float,
        fill_ts: str,
    ) -> ExecutionResult:
        order_key = f"order:BUY:{bar_ts}:{signal_price}"
        fill_key = f"fill:BUY:{bar_ts}:{signal_price}"

        order_id = self.db.insert_order(
            {
                "idempotency_key": order_key,
                "signal_id": signal_id,
                "side": "BUY",
                "quantity": self.settings.quantity,
                "signal_price": signal_price,
                "status": "SUBMITTED",
            }
        )
        if order_id is None:
            return ExecutionResult(False, message="Duplicate order suppressed")

        fill_price = simulate_market_fill_price(
            signal_price=signal_price,
            side="BUY",
            tick_size=self.settings.tick_size,
            slippage_ticks=self.settings.slippage_ticks,
        )
        commission, slip_cost = apply_fill_costs(
            commission_per_side=self.settings.commission_per_side,
            slippage_ticks=self.settings.slippage_ticks,
            tick_value=self.settings.tick_value,
            quantity=self.settings.quantity,
        )

        fill_id = self.db.insert_fill(
            {
                "idempotency_key": fill_key,
                "order_id": order_id,
                "fill_ts": fill_ts,
                "fill_price": fill_price,
                "signal_price": signal_price,
                "quantity": self.settings.quantity,
                "side": "BUY",
                "slippage_ticks": self.settings.slippage_ticks,
                "slippage_cost": slip_cost,
                "commission": commission,
                "commission_normalized": commission,
            }
        )
        if fill_id is None:
            return ExecutionResult(False, message="Duplicate fill suppressed")

        # Cash reflects fees immediately; futures margin not modeled beyond cash PnL.
        self.account.cash_balance -= commission
        self.account.commissions += commission
        self.account.slippage_cost += slip_cost
        self.account.realized_pnl -= commission

        trade_id = self.db.open_trade(
            {
                "entry_signal_time": bar_ts,
                "entry_time": fill_ts,
                "entry_signal_price": signal_price,
                "entry_fill_price": fill_price,
                "quantity": self.settings.quantity,
            }
        )
        self.db.set_position(
            {
                "state": PositionState.LONG.value,
                "quantity": self.settings.quantity,
                "entry_time": fill_ts,
                "entry_price": fill_price,
                "entry_signal_time": bar_ts,
                "entry_signal_price": signal_price,
                "open_trade_id": trade_id,
            }
        )
        mark_to_market(
            self.account,
            position_state="LONG",
            entry_price=fill_price,
            current_price=fill_price,
            quantity=self.settings.quantity,
            point_value=self.settings.point_value,
        )
        self.db.insert_snapshot(
            {
                "ts": fill_ts,
                "cash_balance": self.account.cash_balance,
                "realized_pnl": self.account.realized_pnl,
                "unrealized_pnl": self.account.unrealized_pnl,
                "equity": self.account.equity,
                "peak_equity": self.account.peak_equity,
                "drawdown": self.account.drawdown,
                "max_drawdown": self.account.max_drawdown,
                "commissions": self.account.commissions,
                "slippage_cost": self.account.slippage_cost,
                "open_position": "LONG",
                "reason": "ENTRY",
            }
        )

        logger.info(
            "FILL BUY qty=%s signal=%.2f fill=%.2f commission=%.2f ts=%s",
            self.settings.quantity,
            signal_price,
            fill_price,
            commission,
            fill_ts,
        )
        return ExecutionResult(True, fill_price=fill_price, trade_id=trade_id, message="Entered LONG")

    def _exit_long(
        self,
        signal_id: Optional[int],
        bar_ts: str,
        signal_price: float,
        fill_ts: str,
        exit_reason: str,
    ) -> ExecutionResult:
        pos = self.db.get_position()
        if pos["state"] != PositionState.LONG.value or not pos.get("open_trade_id"):
            return ExecutionResult(False, message="No open long")

        order_key = f"order:SELL:{bar_ts}:{signal_price}:{exit_reason}"
        fill_key = f"fill:SELL:{bar_ts}:{signal_price}:{exit_reason}"

        order_id = self.db.insert_order(
            {
                "idempotency_key": order_key,
                "signal_id": signal_id,
                "side": "SELL",
                "quantity": self.settings.quantity,
                "signal_price": signal_price,
                "status": "SUBMITTED",
            }
        )
        if order_id is None:
            return ExecutionResult(False, message="Duplicate order suppressed")

        fill_price = simulate_market_fill_price(
            signal_price=signal_price,
            side="SELL",
            tick_size=self.settings.tick_size,
            slippage_ticks=self.settings.slippage_ticks,
        )
        commission, slip_cost = apply_fill_costs(
            commission_per_side=self.settings.commission_per_side,
            slippage_ticks=self.settings.slippage_ticks,
            tick_value=self.settings.tick_value,
            quantity=self.settings.quantity,
        )
        fill_id = self.db.insert_fill(
            {
                "idempotency_key": fill_key,
                "order_id": order_id,
                "fill_ts": fill_ts,
                "fill_price": fill_price,
                "signal_price": signal_price,
                "quantity": self.settings.quantity,
                "side": "SELL",
                "slippage_ticks": self.settings.slippage_ticks,
                "slippage_cost": slip_cost,
                "commission": commission,
                "commission_normalized": commission,
            }
        )
        if fill_id is None:
            return ExecutionResult(False, message="Duplicate fill suppressed")

        entry_price = float(pos["entry_price"])
        trade_id = int(pos["open_trade_id"])
        open_trade = self.db.get_open_trade()
        # Entry commission already booked; add exit commission + both sides slippage conceptually.
        # Slippage is embedded in fill prices for gross_pnl; we also track explicit slippage_cost.
        entry_commission = self.settings.commission_per_side * self.settings.quantity
        total_commission = entry_commission + commission
        # Slippage both sides
        total_slip = (
            self.settings.slippage_ticks
            * self.settings.tick_value
            * self.settings.quantity
            * 2
        )

        gross = mnq_gross_pnl(
            entry_price,
            fill_price,
            quantity=self.settings.quantity,
            point_value=self.settings.point_value,
        )
        # Net uses fill prices (slippage in prices) + commissions only to avoid double-counting slip.
        net = gross - commission  # entry commission already removed from cash
        net_normalized = gross - (
            self.settings.commission_per_side * self.settings.quantity
        )  # exit side; entry already deducted similarly historically

        self.account.cash_balance += gross - commission
        self.account.commissions += commission
        self.account.slippage_cost += slip_cost
        self.account.realized_pnl += gross - commission
        self.account.unrealized_pnl = 0.0

        mark_to_market(
            self.account,
            position_state="FLAT",
            entry_price=None,
            current_price=fill_price,
            quantity=0,
            point_value=self.settings.point_value,
        )

        self.db.close_trade(
            trade_id,
            {
                "exit_signal_time": bar_ts,
                "exit_time": fill_ts,
                "exit_signal_price": signal_price,
                "exit_fill_price": fill_price,
                "gross_pnl": gross,
                "commission": total_commission,
                "commission_normalized": total_commission,
                "slippage_cost": total_slip,
                "net_pnl": gross - total_commission,
                "net_pnl_normalized": gross - total_commission,
                "balance_after": self.account.cash_balance,
                "equity_after": self.account.equity,
                "exit_reason": exit_reason,
            },
        )
        self.db.set_position(
            {
                "state": PositionState.FLAT.value,
                "quantity": 0,
                "entry_time": None,
                "entry_price": None,
                "entry_signal_time": None,
                "entry_signal_price": None,
                "open_trade_id": None,
            }
        )
        self.db.insert_snapshot(
            {
                "ts": fill_ts,
                "cash_balance": self.account.cash_balance,
                "realized_pnl": self.account.realized_pnl,
                "unrealized_pnl": 0.0,
                "equity": self.account.equity,
                "peak_equity": self.account.peak_equity,
                "drawdown": self.account.drawdown,
                "max_drawdown": self.account.max_drawdown,
                "commissions": self.account.commissions,
                "slippage_cost": self.account.slippage_cost,
                "open_position": "FLAT",
                "reason": exit_reason,
            }
        )

        logger.info(
            "FILL SELL qty=%s signal=%.2f fill=%.2f gross=%.2f reason=%s ts=%s",
            self.settings.quantity,
            signal_price,
            fill_price,
            gross,
            exit_reason,
            fill_ts,
        )
        # silence unused
        _ = open_trade
        _ = net
        _ = net_normalized
        return ExecutionResult(True, fill_price=fill_price, trade_id=trade_id, message="Exited LONG")
