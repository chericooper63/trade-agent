from __future__ import annotations

import math
from typing import Any
from uuid import uuid4

import pandas as pd

from .data import MarketDataProvider, SourceAwareMarketDataProvider
from .execution import SimulatedBroker
from .policy import ProductionPolicy
from .review import ReviewAgent
from .strategy import TechnicalSignalGenerator
from .storage import RunStorage
from .team import LearningJournal


class DataAgent:
    """Owns market-data collection and normalization for the trading workflow."""

    def __init__(
        self,
        symbol: str = "AAPL",
        periods: int = 120,
        source: str = "sample_csv",
        provider: MarketDataProvider | None = None,
    ):
        self.symbol = symbol
        self.periods = periods
        self.source = source
        if provider is not None:
            self.provider = provider
        elif (source or "sample_csv").strip().lower() in {"sample_csv", "csv", "paper_csv"}:
            self.provider = MarketDataProvider(symbol=symbol, periods=periods)
        else:
            self.provider = SourceAwareMarketDataProvider(symbol=symbol, source=source)

    def collect(self, symbol: str | None = None, periods: int | None = None) -> pd.DataFrame:
        if symbol is not None:
            self.symbol = symbol
        if periods is not None:
            self.periods = periods
        if (self.source or "sample_csv").strip().lower() in {"sample_csv", "csv", "paper_csv"}:
            self.provider = MarketDataProvider(symbol=self.symbol, periods=self.periods)
        else:
            self.provider = SourceAwareMarketDataProvider(symbol=self.symbol, source=self.source)
        return self.provider.get_market_data()


class StrategyAgent:
    """Transforms market-state data into a deliberate signal and confidence output."""

    def __init__(self, generator: TechnicalSignalGenerator | None = None):
        self.generator = generator or TechnicalSignalGenerator()

    def evaluate(self, market_data: pd.DataFrame) -> dict[str, Any]:
        signal = self.generator.generate(market_data)
        return {
            "signal": signal.get("signal", "HOLD"),
            "confidence": float(signal.get("confidence", 0.0)),
            "reason": signal.get("reason", "No signal reason provided."),
            "agent": "strategy_agent",
        }


class PolicyAgent:
    """The policy gatekeeper keeps all trading in a paper-first, account-aware framework."""

    def __init__(self, **kwargs: Any):
        self.policy = ProductionPolicy(**kwargs)

    def evaluate(self, mode: str | None = None, account_id: str | None = None, manual_approval: bool = False) -> dict[str, Any]:
        execution_mode = mode or self.policy.mode
        gate = self.policy.execution_gate(execution_mode, account_id=account_id, manual_approval=manual_approval)
        return {
            **gate,
            "agent": "policy_guard",
            "paper_mode": execution_mode == "paper",
        }


class ExecutionSimulationAgent:
    """Paper-only execution simulator requiring explicit policy and risk approval."""

    def __init__(
        self,
        broker: SimulatedBroker | None = None,
        fee_bps: float = 5.0,
        slippage_bps: float = 5.0,
    ):
        if fee_bps < 0 or slippage_bps < 0:
            raise ValueError("Execution simulation costs cannot be negative.")
        self.broker = broker or SimulatedBroker()
        self.fee_bps = float(fee_bps)
        self.slippage_bps = float(slippage_bps)
        self.allow_live = False

    def execute(
        self,
        signal: str,
        order_size: float,
        price: float,
        *,
        mode: str,
        policy_gate: dict[str, Any],
        risk_decision: dict[str, Any],
        portfolio_decision: dict[str, Any] | None = None,
        symbol: str | None = None,
        account_id: str | None = None,
        run_id: str = "",
        order_id: str | None = None,
    ) -> dict[str, Any]:
        if mode != "paper":
            raise ValueError("ExecutionSimulationAgent only supports paper execution.")
        if not isinstance(policy_gate, dict) or not policy_gate.get("allowed") or policy_gate.get("approval_status") != "paper":
            raise ValueError("Paper simulation requires an allowed paper policy gate.")
        if not isinstance(risk_decision, dict) or not risk_decision.get("approved"):
            raise ValueError("Paper simulation requires an approved risk decision.")
        if not isinstance(portfolio_decision, dict) or not portfolio_decision.get("approved"):
            raise ValueError("Paper simulation requires an approved portfolio decision.")
        if (
            signal not in {"BUY", "SELL"}
            or not math.isfinite(float(order_size))
            or float(order_size) <= 0.0
            or not math.isfinite(float(price))
            or float(price) <= 0.0
        ):
            raise ValueError("Paper simulation requires a valid side, positive quantity, and positive price.")

        if symbol:
            self.broker.symbol = symbol
        result = self.broker.execute(signal, float(order_size), float(price))
        notional = abs(float(order_size) * float(price))
        return {
            **result,
            "order_id": order_id or uuid4().hex,
            "account_id": account_id or "local-paper",
            "run_id": run_id,
            "route": "local_simulator",
            "mode": "paper",
            "simulated": True,
            "allow_live": False,
            "approval_status": "paper",
            "estimated_fee": notional * self.fee_bps / 10_000.0,
            "estimated_slippage": notional * self.slippage_bps / 10_000.0,
        }


class LearningAgent:
    """Reviews paper cycles and records execution outcomes as durable evidence."""

    def __init__(self, journal: LearningJournal | None = None, review_agent: ReviewAgent | None = None):
        self.journal = journal or LearningJournal(storage=RunStorage())
        self.review_agent = review_agent or ReviewAgent(journal=self.journal)
        self.allow_live = False

    def review_cycle(
        self,
        portfolio: dict[str, Any],
        risk: dict[str, Any],
        decision: dict[str, Any],
        execution: dict[str, Any],
    ) -> dict[str, Any]:
        if self.allow_live:
            raise ValueError("LearningAgent is paper-only and cannot enable live execution.")
        if not isinstance(execution, dict) or execution.get("mode") != "paper":
            raise ValueError("LearningAgent only reviews paper-mode decision outcomes.")
        if execution.get("status") == "filled" and not execution.get("simulated"):
            raise ValueError("A filled learning outcome must be identified as a paper simulation.")

        review = self.review_agent.evaluate(portfolio, risk, decision)
        symbols = list((portfolio.get("positions") or {}).keys())
        if not symbols and decision.get("selected_symbol"):
            symbols = [str(decision["selected_symbol"])]

        entries = []
        for symbol in symbols:
            entry = self.journal.record(
                "execution_learning_agent",
                symbol,
                {
                    "signal": decision.get("signal", "HOLD"),
                    "confidence": float(decision.get("confidence", 0.0)),
                    "risk_approved": bool(risk.get("approved", False)),
                },
                {
                    "execution_status": execution.get("status", "unknown"),
                    "mode": "paper",
                    "simulated": bool(execution.get("simulated", False)),
                    "estimated_fee": float(execution.get("estimated_fee", 0.0)),
                    "estimated_slippage": float(execution.get("estimated_slippage", 0.0)),
                    "review_status": review.get("review_status"),
                },
                "Paper execution outcome recorded for review; this evidence does not authorize live execution.",
            )
            entries.append(entry)
            if self.journal.storage is not None:
                self.journal.storage.store({"learning_entry": entry})

        return {
            **review,
            "paper_mode": True,
            "allow_live": False,
            "execution_status": execution.get("status", "unknown"),
            "learning_entries": entries,
        }
