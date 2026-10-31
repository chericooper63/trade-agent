from __future__ import annotations

import math
import re


class PortfolioManager:
    """Build a simple portfolio allocation plan for single or multi-symbol trade sets."""

    def __init__(self, target_cash_fraction: float = 0.05):
        self.target_cash_fraction = target_cash_fraction

    def plan(self, signal: str, confidence: float, account_equity: float, proposed_capital: float) -> dict:
        signal_side = "BUY" if signal == "BUY" else "SELL"
        if signal == "HOLD":
            return {
                "side": "HOLD",
                "cash_used": 0.0,
                "cash_remaining": account_equity,
                "confidence": confidence,
            }

        used_capital = proposed_capital
        cash_remaining = max(account_equity - used_capital, 0.0)
        return {
            "side": signal_side,
            "cash_used": used_capital,
            "cash_remaining": cash_remaining,
            "confidence": confidence,
        }

    def plan_portfolio(
        self,
        signals: dict[str, str],
        confidences: dict[str, float],
        account_equity: float,
        proposed_capital: dict[str, float],
        max_risk_budget: float = 1.0,
    ) -> dict:
        account_equity = float(account_equity)
        max_risk_budget = float(max_risk_budget)
        if not math.isfinite(account_equity) or account_equity < 0:
            raise ValueError("account_equity must be finite and non-negative")
        if not math.isfinite(max_risk_budget) or max_risk_budget < 0:
            raise ValueError("max_risk_budget must be finite and non-negative")
        risk_budget_limit = min(max_risk_budget, 1.0)

        positions = {}
        total_cash_used = 0.0
        risk_budget_used = 0.0

        for symbol, signal in signals.items():
            if not isinstance(symbol, str) or not re.fullmatch(r"[A-Z0-9]{1,10}(?:-[A-Z0-9]{1,10})?", symbol):
                raise ValueError(f"Unsupported symbol format: {symbol!r}")
            if signal not in {"BUY", "SELL", "HOLD"}:
                raise ValueError(f"Unsupported portfolio signal for {symbol}: {signal!r}")
            confidence = confidences.get(symbol)
            if confidence is None:
                raise ValueError(f"Missing confidence for portfolio candidate {symbol}.")
            confidence = float(confidence)
            if not math.isfinite(confidence) or not 0.0 <= confidence <= 1.0:
                raise ValueError(f"Confidence for {symbol} must be finite and between 0 and 1.")
            if signal == "HOLD":
                continue

            try:
                capital = float(proposed_capital[symbol])
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Missing or invalid proposed capital for {symbol}.") from exc
            if not math.isfinite(capital) or capital <= 0:
                raise ValueError(f"Proposed capital for {symbol} must be finite and greater than zero.")

            risk_weight = confidence
            risk_budget_used += risk_weight
            total_cash_used += capital
            positions[symbol] = {
                "signal": signal,
                "confidence": confidence,
                "cash_used": capital,
                "risk_weight": risk_weight,
            }

        rejections = []
        if not positions:
            rejections.append("no_actionable_position")
        if total_cash_used > account_equity:
            rejections.append("portfolio_budget_exceeded")
        if risk_budget_used > risk_budget_limit:
            rejections.append("risk_budget_exceeded")
        return {
            "positions": positions,
            "total_cash_used": total_cash_used,
            "risk_budget_used": risk_budget_used,
            "cash_remaining": max(account_equity - total_cash_used, 0.0),
            "risk_budget_limit": risk_budget_limit,
            "approved": not rejections,
            "reason_code": rejections[0] if rejections else "portfolio_approved",
            "rejection_reasons": rejections,
        }
