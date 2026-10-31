from __future__ import annotations

from .events import ExecutionEvent


class PerformanceService:
    """Create a limited performance and attribution report from a filled execution event."""

    def __init__(self):
        self.history = []

    def report(self, event: ExecutionEvent, account_equity: float = 100_000.0) -> dict:
        quantity = event.quantity
        notional = quantity * event.price
        pnl = notional * 0.01 if event.side == "BUY" else -notional * 0.01
        exposure = notional / account_equity
        drawdown = max(0.0, abs(pnl) / account_equity)

        attribution = {
            "strategy": "technical",
            "regime": "trend",
            "symbol": event.symbol,
        }

        result = {
            "pnl": round(pnl, 4),
            "exposure": round(exposure, 4),
            "drawdown": round(drawdown, 4),
            "attribution": attribution,
        }
        self.history.append(result)
        return result
