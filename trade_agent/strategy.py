from __future__ import annotations

import numpy as np
import pandas as pd


class TechnicalSignalGenerator:
    """Create a simple signal from trend and volatility features."""

    def generate(self, market_data: pd.DataFrame) -> dict:
        if market_data.empty:
            return {"signal": "HOLD", "confidence": 0.0, "reason": "No market data"}

        close = market_data["close"].astype(float)
        returns = close.pct_change().dropna()
        short_ma = close.rolling(12).mean().iloc[-1]
        long_ma = close.rolling(30).mean().iloc[-1]
        volatility = returns.std() * np.sqrt(24)

        trend_score = 0.0
        if short_ma > long_ma:
            trend_score = 1.0
        elif short_ma < long_ma:
            trend_score = -1.0

        volatility_score = 0.0
        if volatility < 0.02:
            volatility_score = 1.0
        elif volatility > 0.04:
            volatility_score = -1.0

        latest_return = returns.iloc[-1]
        confidence = min(0.95, max(0.4, abs(latest_return) * 100 + 0.5))

        if trend_score > 0 and volatility_score >= 0:
            signal = "BUY"
        elif trend_score < 0 and volatility_score <= 0:
            signal = "SELL"
        else:
            signal = "HOLD"

        reason = (
            f"trend={trend_score:.2f}, volatility={volatility:.4f}, "
            f"latest_return={latest_return:.4f}"
        )
        return {"signal": signal, "confidence": float(confidence), "reason": reason}


class ResearchStrategyEngine:
    """A minimal multi-factor strategy engine for a research-grade signal score."""

    def generate(self, market_data: pd.DataFrame) -> dict:
        if market_data.empty:
            return {"signal": "HOLD", "score": 0.0, "factors": {}, "reason": "No market data"}

        close = market_data["close"].astype(float)
        returns = close.pct_change().dropna()
        if returns.empty:
            return {"signal": "HOLD", "score": 0.0, "factors": {}, "reason": "No return data"}

        short_ma = close.rolling(12).mean().iloc[-1]
        long_ma = close.rolling(30).mean().iloc[-1]
        latest_return = float(returns.iloc[-1])
        volatility = float(returns.std() * np.sqrt(24))
        volume = market_data.get("volume", pd.Series(np.ones(len(market_data), dtype=float)))
        volume_change = float(volume.pct_change().dropna().mean()) if volume.notna().all() else 0.0

        trend_factor = 1.0 if short_ma >= long_ma else 0.0
        momentum_factor = 1.0 if latest_return >= 0 else 0.0
        volatility_factor = 1.0 if volatility < 0.04 else 0.0
        volume_factor = 1.0 if volume_change >= 0 else 0.0

        score = float(
            (trend_factor * 0.35)
            + (momentum_factor * 0.30)
            + (volatility_factor * 0.20)
            + (volume_factor * 0.15)
        )

        if score >= 0.7:
            signal = "BUY"
        elif score <= 0.35:
            signal = "SELL"
        else:
            signal = "HOLD"

        factors = {
            "trend": round(float(trend_factor), 4),
            "momentum": round(float(momentum_factor), 4),
            "volatility": round(float(volatility_factor), 4),
            "volume": round(float(volume_factor), 4),
            "latest_return": round(float(latest_return), 6),
            "volatility_value": round(float(volatility), 6),
        }

        reason = (
            f"score={score:.2f}, trend={trend_factor}, momentum={momentum_factor}, "
            f"volatility={volatility_factor}, volume={volume_factor}"
        )
        return {"signal": signal, "score": score, "factors": factors, "reason": reason}
