from __future__ import annotations

from .backtest import Backtester
from .scanner import MarketScanner


class ResearchAgent:
    """Validate scanner candidates before they reach portfolio or execution roles."""

    def __init__(self, scanner: MarketScanner, backtester_factory=None):
        self.scanner = scanner
        self.backtester_factory = backtester_factory or (lambda provider: Backtester(provider))

    def evaluate(self, scan_result: dict, account_equity: float, proposed_capital: float) -> dict:
        reports = []
        failures = []
        for candidate in scan_result.get("candidates", []):
            symbol = candidate["symbol"]
            try:
                provider = self.scanner.provider_factory(symbol)
                metrics = self.backtester_factory(provider).run(account_equity, proposed_capital)
                reports.append(
                    {
                        "symbol": symbol,
                        "signal": candidate["signal"],
                        "confidence": candidate["confidence"],
                        "metrics": metrics,
                        "research_passed": bool(metrics.get("paper_ready", False)),
                    }
                )
            except (KeyError, TypeError, ValueError, IndexError) as exc:
                failures.append({"symbol": symbol, "reason": str(exc)})

        reports.sort(
            key=lambda item: (
                item["research_passed"],
                item["metrics"].get("total_return", 0.0),
                item["confidence"],
            ),
            reverse=True,
        )
        qualified = [report for report in reports if report["research_passed"]]
        return {
            "reports": reports,
            "qualified": qualified,
            "failures": failures,
            "account_equity": float(account_equity),
            "proposed_capital": float(proposed_capital),
        }
