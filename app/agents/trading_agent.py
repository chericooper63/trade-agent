"""Trading agent skeleton.

Deliberately a placeholder: ``analyze`` returns a neutral signal and
``propose_order`` returns a *simulated* order. No broker or exchange is
contacted. Replace the two methods with your strategy, then wire a real
broker client behind ``settings.broker_configured``.
"""

from dataclasses import dataclass, field

NEUTRAL_SIGNAL = {"action": "hold", "confidence": 0.0}


@dataclass
class TradingAgent:
    """Holds state (positions) and produces analysis plus simulated orders."""

    name: str = "baseline"
    positions: dict[str, float] = field(default_factory=dict)

    def analyze(self, symbol: str) -> dict:
        """Return market analysis for ``symbol`` (placeholder: always neutral)."""
        return {
            "symbol": symbol.upper(),
            **NEUTRAL_SIGNAL,
            "note": "placeholder analysis - strategy not implemented",
        }

    def propose_order(self, symbol: str, quantity: float) -> dict:
        """Turn an analysis into an order proposal. Nothing is submitted."""
        analysis = self.analyze(symbol)
        side = "buy" if analysis["action"] == "buy" else None
        return {
            "symbol": analysis["symbol"],
            "side": side,
            "quantity": quantity,
            "simulated": True,
            "reason": analysis["note"],
        }

    def status(self) -> dict:
        return {
            "agent": self.name,
            "positions": dict(self.positions),
            "simulated": True,
        }


agent = TradingAgent()
