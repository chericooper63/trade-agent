from __future__ import annotations

import os
from pathlib import Path

import numpy as np
import pandas as pd


class MarketDataProvider:
    """Generate synthetic OHLCV market data for a demo agent."""

    def __init__(self, symbol: str = "AAPL", start: str = "2024-01-02", periods: int = 200):
        self.symbol = symbol
        self.start = start
        self.periods = periods

    def get_market_data(self) -> pd.DataFrame:
        rng = np.random.default_rng(42)
        timestamps = pd.date_range(self.start, periods=self.periods, freq="1h")
        base_price = 150.0 + rng.normal(0, 8, self.periods)
        drift = np.linspace(0, 2.5, self.periods)
        prices = base_price + drift
        closes = np.maximum(prices, 10)

        data = pd.DataFrame(
            {
                "symbol": self.symbol,
                "timestamp": timestamps,
                "open": closes * (1 + rng.normal(0, 0.002, self.periods)),
                "high": closes * (1 + np.abs(rng.normal(0, 0.004, self.periods))),
                "low": closes * (1 - np.abs(rng.normal(0, 0.004, self.periods))),
                "close": closes,
                "volume": rng.integers(500_000, 1_500_000, self.periods),
            }
        )
        return data.sort_values("timestamp").reset_index(drop=True)


class CSVMarketDataProvider:
    """Read a CSV file with OHLCV columns and return a pandas DataFrame."""

    def __init__(self, csv_path: str | Path | None = None):
        self.csv_path = csv_path or str(Path(__file__).resolve().parent / "sample_market_data.csv")

    def get_market_data(self) -> pd.DataFrame:
        if not os.path.exists(self.csv_path):
            return self._build_sample_csv_and_data()

        data = pd.read_csv(self.csv_path)
        required_columns = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
        missing = sorted(required_columns.difference(data.columns))
        if missing:
            raise ValueError(f"Missing required market columns: {missing}")
        return data

    def _build_sample_csv_and_data(self) -> pd.DataFrame:
        sample = MarketDataProvider(periods=40).get_market_data()
        Path(self.csv_path).parent.mkdir(parents=True, exist_ok=True)
        sample.to_csv(self.csv_path, index=False)
        return sample


class SourceAwareMarketDataProvider:
    """A provider that requires an explicit source contract for any data origin."""

    def __init__(self, symbol: str = "AAPL", source: str = "sample_csv", csv_path: str | Path | None = None):
        self.symbol = symbol
        self.source = source
        self.csv_path = csv_path or str(Path(__file__).resolve().parent / "sample_market_data.csv")

    def get_market_data(self) -> pd.DataFrame:
        if not self.source or not self.source.strip():
            raise ValueError("Market data source is required and cannot be empty.")

        provider = CSVMarketDataProvider(csv_path=self.csv_path)
        try:
            data = provider.get_market_data()
        except ValueError:
            data = pd.read_csv(self.csv_path)
            if "symbol" not in data.columns:
                data = data.copy()
                data["symbol"] = self.symbol
                return data
            raise

        if "symbol" in data.columns:
            return data
        data = data.copy()
        data["symbol"] = self.symbol
        return data


class RealMarketDataProvider(SourceAwareMarketDataProvider):
    """A paper-safe real-data adapter contract for explicit market sources.

    This intentionally does not enable live broker connectivity or secret-based
    market-data access by default. It simply requires an explicit source string
    and supports the repository's safe CSV-backed data path until a configured
    external provider is added behind the same contract.
    """

    def __init__(
        self,
        symbol: str = "AAPL",
        source: str = "sample_csv",
        csv_path: str | Path | None = None,
    ):
        super().__init__(symbol=symbol, source=source, csv_path=csv_path)
        self.allowed_sources = {"sample_csv", "csv", "paper_csv", "alpaca", "polygon", "yfinance"}

    def get_market_data(self) -> pd.DataFrame:
        normalized_source = (self.source or "").strip().lower()
        if not normalized_source:
            raise ValueError("Market data source is required and cannot be empty.")
        if normalized_source in {"sample_csv", "csv", "paper_csv"}:
            return super().get_market_data()
        if normalized_source in {"alpaca", "polygon", "yfinance"}:
            return super().get_market_data()
        raise ValueError(f"Unsupported market-data source contract: {self.source}")


class FreePublicMarketDataProvider(RealMarketDataProvider):
    """A public/free provider abstraction that gracefully falls back to the sample CSV.

    This keeps the repository usable without any secret token or commercial
    market-data subscription. The intended public/free source is a sample CSV
    file until an environment-specific provider adapter is configured.
    """

    def __init__(self, symbol: str = "AAPL", csv_path: str | Path | None = None):
        super().__init__(symbol=symbol, source="sample_csv", csv_path=csv_path)
        self.source = "sample_csv"

    def get_market_data(self) -> pd.DataFrame:
        return super().get_market_data()
