from __future__ import annotations

import pandas as pd


class AlphaAgentRegistry:
    """Example registry for simple alpha-producing strategies.

    This keeps the current code demonstrably multi-agent in form without
    depending on external services.
    """

    def __init__(self):
        self.agents = {
            "momentum": self._momentum_signal,
            "mean_reversion": self._mean_reversion_signal,
            "volatility": self._volatility_signal,
        }

    def run(self, market_data: pd.DataFrame) -> dict:
        signals = {}
        for name, handler in self.agents.items():
            try:
                signals[name] = handler(market_data)
            except Exception:
                signals[name] = "HOLD"

        aggregate = "BUY" if sum(1 for value in signals.values() if value == "BUY") >= 2 else "HOLD"
        return {"signals": signals, "aggregated_signal": aggregate}

    def _momentum_signal(self, market_data: pd.DataFrame) -> str:
        close = market_data["close"].astype(float)
        returns = close.pct_change().dropna()
        return "BUY" if returns.iloc[-1] > 0 else "SELL"

    def _mean_reversion_signal(self, market_data: pd.DataFrame) -> str:
        close = market_data["close"].astype(float)
        rolling_mean = close.rolling(10).mean().iloc[-1]
        latest = close.iloc[-1]
        return "BUY" if latest < rolling_mean else "SELL"

    def _volatility_signal(self, market_data: pd.DataFrame) -> str:
        close = market_data["close"].astype(float)
        returns = close.pct_change().dropna()
        vol = returns.std()
        return "BUY" if vol < 0.01 else "HOLD"
