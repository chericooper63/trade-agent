from __future__ import annotations

from .data import CSVMarketDataProvider


class MarketDataService:
    """A real service-like package for retrieving OHLCV-style data."""

    def __init__(self, provider=None):
        self.provider = provider or CSVMarketDataProvider()

    def fetch(self, symbol: str) -> object:
        frame = self.provider.get_market_data()
        if symbol:
            frame = frame.copy()
            frame["symbol"] = symbol
        return frame
