from __future__ import annotations

from collections.abc import Callable, Iterable

import pandas as pd

from .data import MarketDataProvider
from .strategy import TechnicalSignalGenerator


class MarketScanner:
    """Scan a configured asset universe and hand ranked candidates to an advisor."""

    def __init__(
        self,
        symbols: Iterable[str] | None = None,
        provider_factory: Callable[[str], object] | None = None,
        signal_generator=None,
    ):
        self.symbols = tuple(dict.fromkeys(symbols or ("AAPL", "MSFT", "TSLA", "BTC-USD", "ETH-USD")))
        if not self.symbols:
            raise ValueError("At least one market symbol is required.")
        self.provider_factory = provider_factory or (lambda symbol: MarketDataProvider(symbol=symbol))
        self.signal_generator = signal_generator or TechnicalSignalGenerator()

    def scan(self) -> dict:
        candidates = []
        failures = []
        for symbol in self.symbols:
            try:
                provider = self.provider_factory(symbol)
                market_data = provider.get_market_data()
                if not isinstance(market_data, pd.DataFrame) or market_data.empty:
                    failures.append({"symbol": symbol, "reason": "No market data"})
                    continue

                signal = self.signal_generator.generate(market_data)
                candidates.append(
                    {
                        "symbol": symbol,
                        "signal": signal.get("signal", "HOLD"),
                        "confidence": float(signal.get("confidence", 0.0)),
                        "reason": signal.get("reason", ""),
                        "price": float(market_data["close"].iloc[-1]),
                        "market_rows": len(market_data),
                        "source": type(provider).__name__,
                    }
                )
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                failures.append({"symbol": symbol, "reason": str(exc)})

        candidates.sort(key=lambda item: item["confidence"], reverse=True)
        actionable = [candidate for candidate in candidates if candidate["signal"] in {"BUY", "SELL"}]
        return {
            "candidates": candidates,
            "actionable": actionable,
            "scanned_symbols": list(self.symbols),
            "failures": failures,
        }
