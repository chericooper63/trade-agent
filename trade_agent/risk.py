from __future__ import annotations

import math


class RiskManager:
    """Applies simple risk constraints to a proposed trade signal."""

    def __init__(self, max_position_size: float = 1.0, max_daily_loss: float = 0.02):
        self.max_position_size = max_position_size
        self.max_daily_loss = max_daily_loss

    def evaluate(self, signal: str, confidence: float, account_equity: float, proposed_capital: float) -> dict:
        try:
            confidence = float(confidence)
            account_equity = float(account_equity)
            proposed_capital = float(proposed_capital)
        except (TypeError, ValueError):
            return self._reject("invalid_risk_input", "Risk inputs must be numeric.")
        if signal not in {"BUY", "SELL"}:
            return self._reject("no_actionable_signal", "Risk requires a BUY or SELL signal.")
        if (
            not math.isfinite(confidence)
            or not 0.0 <= confidence <= 1.0
            or not math.isfinite(account_equity)
            or account_equity <= 0.0
            or not math.isfinite(proposed_capital)
            or proposed_capital <= 0.0
        ):
            return self._reject("invalid_risk_input", "Risk inputs must be finite and positive where required.")
        if confidence < 0.45:
            return self._reject("confidence_below_threshold", "Signal confidence is below the risk threshold.")
        if proposed_capital > account_equity * self.max_position_size:
            return self._reject("position_limit_exceeded", "Position exceeds max position size.")

        position_size = min(proposed_capital, account_equity * self.max_position_size)
        return {
            "approved": True,
            "reason_code": "risk_approved",
            "reason": "Risk constraints passed",
            "position_size": position_size,
        }

    @staticmethod
    def _reject(reason_code: str, reason: str) -> dict:
        return {
            "approved": False,
            "reason_code": reason_code,
            "reason": reason,
            "position_size": 0.0,
        }
