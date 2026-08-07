"""Frozen SMA4750 + Band50 long-only state strategy.

IMPORTANT:
- State / level conditions (NOT CrossAbove / CrossBelow)
- Evaluate on bar close
- LONG ONLY, no pyramiding
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Sequence


class PositionState(str, Enum):
    FLAT = "FLAT"
    LONG = "LONG"


class SignalType(str, Enum):
    NONE = "NONE"
    ENTER_LONG = "ENTER_LONG"
    EXIT_LONG = "EXIT_LONG"


@dataclass(frozen=True)
class StrategyDecision:
    signal: SignalType
    position_before: PositionState
    close: float
    sma: Optional[float]
    entry_threshold: Optional[float]
    exit_threshold: Optional[float]
    reason: str


def compute_sma(closes: Sequence[float], period: int) -> Optional[float]:
    if len(closes) < period:
        return None
    window = closes[-period:]
    return float(sum(window) / period)


def evaluate_signal(
    *,
    close: float,
    closes: Sequence[float],
    position: PositionState,
    sma_period: int = 4750,
    band_points: float = 50.0,
) -> StrategyDecision:
    sma = compute_sma(closes, sma_period)
    if sma is None:
        return StrategyDecision(
            signal=SignalType.NONE,
            position_before=position,
            close=close,
            sma=None,
            entry_threshold=None,
            exit_threshold=None,
            reason=f"Insufficient bars for SMA({sma_period})",
        )

    entry_threshold = sma + band_points
    exit_threshold = sma - band_points

    if position == PositionState.FLAT:
        if close > entry_threshold:
            return StrategyDecision(
                signal=SignalType.ENTER_LONG,
                position_before=position,
                close=close,
                sma=sma,
                entry_threshold=entry_threshold,
                exit_threshold=exit_threshold,
                reason="Close > SMA + Band while FLAT",
            )
        return StrategyDecision(
            signal=SignalType.NONE,
            position_before=position,
            close=close,
            sma=sma,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            reason="FLAT and Close not above entry threshold",
        )

    # LONG
    if close < exit_threshold:
        return StrategyDecision(
            signal=SignalType.EXIT_LONG,
            position_before=position,
            close=close,
            sma=sma,
            entry_threshold=entry_threshold,
            exit_threshold=exit_threshold,
            reason="Close < SMA - Band while LONG",
        )

    return StrategyDecision(
        signal=SignalType.NONE,
        position_before=position,
        close=close,
        sma=sma,
        entry_threshold=entry_threshold,
        exit_threshold=exit_threshold,
        reason="LONG and Close not below exit threshold (no second entry)",
    )
