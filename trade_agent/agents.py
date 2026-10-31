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


class LiveExecutionAgent:
    """Live execution agent that submits real orders through a broker adapter."""

    def __init__(
        self,
        broker_adapter,
        fee_bps: float = 5.0,
        slippage_bps: float = 5.0,
    ):
        if fee_bps < 0 or slippage_bps < 0:
            raise ValueError("Execution costs cannot be negative.")
        self.broker_adapter = broker_adapter
        self.fee_bps = float(fee_bps)
        self.slippage_bps = float(slippage_bps)
        self.allow_live = True

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
        if mode != "live":
            raise ValueError("LiveExecutionAgent only supports live execution.")
        if not isinstance(policy_gate, dict) or not policy_gate.get("allowed"):
            raise ValueError("Live execution requires an allowed policy gate.")
        if policy_gate.get("approval_status") != "approved":
            raise ValueError("Live execution requires an approved policy gate.")
        if not isinstance(risk_decision, dict) or not risk_decision.get("approved"):
            raise ValueError("Live execution requires an approved risk decision.")
        if not isinstance(portfolio_decision, dict) or not portfolio_decision.get("approved"):
            raise ValueError("Live execution requires an approved portfolio decision.")
        if (
            signal not in {"BUY", "SELL"}
            or not math.isfinite(float(order_size))
            or float(order_size) <= 0.0
            or not math.isfinite(float(price))
            or float(price) <= 0.0
        ):
            raise ValueError("Live execution requires a valid side, positive quantity, and positive price.")

        from .orders import Order

        order = Order(symbol=symbol or "", side=signal, quantity=int(order_size), price=float(price))
        broker_result = self.broker_adapter.place(
            order,
            account_id=account_id,
            manual_approval=True,
            risk_approved=True,
        )
        notional = abs(float(order_size) * float(price))
        return {
            **broker_result,
            "order_id": order_id or uuid4().hex,
            "account_id": account_id or "live",
            "run_id": run_id,
            "route": "live_broker",
            "mode": "live",
            "simulated": False,
            "allow_live": True,
            "approval_status": "approved",
            "estimated_fee": notional * self.fee_bps / 10_000.0,
            "estimated_slippage": notional * self.slippage_bps / 10_000.0,
        }


class LearningAgent:
    """Reviews trading cycles and records execution outcomes as durable evidence."""

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
        if not isinstance(execution, dict):
            raise ValueError("LearningAgent requires an execution outcome dict.")
        execution_mode = execution.get("mode", "paper")
        if execution_mode not in {"paper", "live"}:
            raise ValueError(f"LearningAgent only reviews paper or live outcomes; got {execution_mode!r}.")
        if execution.get("status") == "filled" and execution_mode == "paper" and not execution.get("simulated"):
            raise ValueError("A filled paper outcome must be identified as a paper simulation.")

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
                    "mode": execution_mode,
                    "simulated": bool(execution.get("simulated", False)),
                    "estimated_fee": float(execution.get("estimated_fee", 0.0)),
                    "estimated_slippage": float(execution.get("estimated_slippage", 0.0)),
                    "review_status": review.get("review_status"),
                },
                f"{execution_mode.capitalize()} execution outcome recorded for review.",
            )
            entries.append(entry)
            if self.journal.storage is not None:
                self.journal.storage.store({"learning_entry": entry})

        return {
            **review,
            "paper_mode": execution_mode == "paper",
            "allow_live": execution_mode == "live",
            "execution_status": execution.get("status", "unknown"),
            "learning_entries": entries,
        }
