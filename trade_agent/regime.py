from __future__ import annotations

import pandas as pd


class RegimeDetector:
    """Produces a simple regime label from close-to-close trend behavior."""

    def detect(self, market_data: pd.DataFrame) -> dict:
        if market_data.empty:
            return {"label": "UNKNOWN", "confidence": 0.0}

        returns = market_data["close"].pct_change().dropna()
        avg_return = float(returns.mean())
        volatility = float(returns.std())

        if avg_return > 0 and volatility < 0.01:
            label = "TRENDING_UP"
            confidence = 0.75
        elif avg_return < 0 and volatility < 0.01:
            label = "TRENDING_DOWN"
            confidence = 0.75
        elif volatility > 0.02:
            label = "HIGH_VOLATILITY"
            confidence = 0.8
        else:
            label = "SIDEWAYS"
            confidence = 0.6

        return {"label": label, "confidence": confidence}
