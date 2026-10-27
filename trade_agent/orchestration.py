from __future__ import annotations

import math
import os
from datetime import datetime, timezone
from numbers import Real
from typing import Any
from uuid import uuid4

from .agent import MultiLayerTradeAgent
from .config import AgentConfig, parse_environment_bool
from .events import AgentResult
from .monitoring import MonitoringService
from .orders import Order
from .storage import RunStorage
from .team import AgentMessage, build_default_team


class AgentOrchestrator:
    """Run one governed paper decision cycle and persist its complete result."""

    def __init__(
        self,
        agent: MultiLayerTradeAgent | None = None,
        storage: RunStorage | None = None,
    ):
        self.agent = agent or MultiLayerTradeAgent(config=AgentConfig.from_env())
        self.storage = storage or RunStorage()
        self.monitor = MonitoringService(storage=self.storage)
        self.team = build_default_team()
        self.agent.learning_agent.journal.storage = self.storage
        self.agent.learning_agent.review_agent.journal = self.agent.learning_agent.journal

    def run(self) -> dict[str, Any]:
        run_id = uuid4().hex
        started_at = datetime.now(timezone.utc).isoformat()
        self.team = build_default_team()
        agent_results: list[dict[str, Any]] = []
        account_id = self.agent.config.account_id or "local-paper"
        self.storage.store_audit_event(
            {
                "event_type": "run_started",
                "run_id": run_id,
                "timestamp": started_at,
                "mode": self.agent.config.mode,
                "account_id": account_id,
            }
        )

        def record_agent(
            name: str,
            role: str,
            status: str,
            confidence: float,
            payload: dict[str, Any],
            evidence: dict[str, Any],
            reason: str = "",
        ) -> dict[str, Any]:
            result = AgentResult.create(
                agent_name=name,
                role=role,
                status=status,
                confidence=confidence,
                payload=payload,
                evidence=evidence,
                reason=reason,
                run_id=run_id,
            ).as_dict()
            result = self._json_safe(result)
            agent_results.append(result)
            self.storage.store_audit_event(
                {"event_type": "agent_result", "run_id": run_id, "result": result}
            )
            return result

        try:
            if self.agent.config.kill_switch or parse_environment_bool(
                os.environ,
                "TRADE_AGENT_KILL_SWITCH",
                False,
            ):
                raise ValueError("The kill switch is active; no decision cycle or order was run.")

            policy_gate = self.agent.policy_agent.evaluate(
                mode=self.agent.config.mode,
                account_id=self.agent.config.account_id or None,
                manual_approval=False,
            )
            if self.agent.config.mode != "paper":
                raise ValueError("The canonical orchestrator is paper-only; no live order was sent.")

            market_data = self.agent.data_agent.collect(symbol=self.agent.symbol)
            required_columns = {"close", "timestamp"}
            missing_columns = sorted(required_columns.difference(market_data.columns))
            if market_data.empty or missing_columns:
                raise ValueError(f"Market data is empty or missing required columns: {missing_columns}.")
            if "symbol" in market_data.columns and not (market_data["symbol"] == self.agent.symbol).all():
                raise ValueError("Market data contains symbols outside the configured decision symbol.")
            closes = market_data["close"].astype(float)
            if not closes.map(math.isfinite).all() or (closes <= 0).any():
                raise ValueError("Market data contains invalid or non-positive prices.")
            latest_price = float(closes.iloc[-1])
            data_source = type(self.agent.data_agent.provider).__name__
            data_result = record_agent(
                "data_curator",
                "data",
                "completed",
                1.0,
                {
                    "symbol": self.agent.symbol,
                    "source": data_source,
                    "rows": len(market_data),
                },
                {
                    "columns": list(market_data.columns),
                    "latest_timestamp": str(market_data["timestamp"].iloc[-1]),
                    "latest_price": latest_price,
                },
            )

            signal = self.agent.strategy_agent.evaluate(market_data)
            if signal["signal"] not in {"BUY", "SELL", "HOLD"}:
                raise ValueError(f"Strategy emitted unsupported signal: {signal['signal']!r}.")
            signal_confidence = float(signal["confidence"])
            if not math.isfinite(signal_confidence) or not 0.0 <= signal_confidence <= 1.0:
                raise ValueError("Strategy confidence must be finite and between zero and one.")
            signal_result = record_agent(
                "strategy_architect",
                "strategy",
                "completed",
                signal_confidence,
                signal,
                {"symbol": self.agent.symbol, "market_data_rows": len(market_data)},
                str(signal.get("reason", "")),
            )

            market_scan = self.agent.scanner.scan()
            research = self.agent.research_agent.evaluate(
                market_scan,
                self.agent.account_equity,
                self.agent.proposal_capital,
            )
            qualified = research.get("qualified", [])
            candidate = (
                max(qualified, key=lambda item: float(item.get("confidence", 0.0)))
                if qualified
                else None
            )
            if candidate is not None and candidate.get("symbol") != self.agent.symbol:
                raise ValueError("Research selected a symbol outside the configured decision symbol.")
            research_result = record_agent(
                "alpha_researcher",
                "research",
                "completed" if candidate else "rejected",
                float(candidate.get("confidence", 0.0)) if candidate else 0.0,
                research,
                {
                    "qualified_count": len(qualified),
                    "scanned_symbols": market_scan.get("scanned_symbols", []),
                },
                "" if candidate else "No research-qualified candidate is available.",
            )

            if candidate is None:
                portfolio = self.agent.portfolio_manager.plan_portfolio(
                    {}, {}, self.agent.account_equity, {},
                    max_risk_budget=self.agent.config.per_account_risk_budget,
                )
                decision_signal = signal["signal"]
                decision_confidence = signal_confidence
                selected_symbol = self.agent.symbol
            else:
                decision_signal = str(candidate["signal"])
                decision_confidence = float(candidate["confidence"])
                selected_symbol = str(candidate["symbol"])
                portfolio = self.agent.portfolio_manager.plan_portfolio(
                    {selected_symbol: decision_signal},
                    {selected_symbol: decision_confidence},
                    self.agent.account_equity,
                    {selected_symbol: self.agent.proposal_capital},
                    max_risk_budget=self.agent.config.per_account_risk_budget,
                )
            portfolio["side"] = decision_signal
            portfolio["confidence"] = decision_confidence
            portfolio_result = record_agent(
                "portfolio_manager",
                "portfolio",
                "approved" if portfolio["approved"] else "rejected",
                decision_confidence,
                portfolio,
                {
                    "account_equity_budget": self.agent.account_equity,
                    "proposed_capital": self.agent.proposal_capital,
                },
                "" if portfolio["approved"] else ", ".join(portfolio["rejection_reasons"]),
            )

            if portfolio["approved"]:
                risk = self.agent.risk_manager.evaluate(
                    decision_signal,
                    decision_confidence,
                    self.agent.account_equity,
                    self.agent.proposal_capital,
                )
            else:
                risk = {
                    "approved": False,
                    "reason_code": "portfolio_rejected",
                    "reason": "Risk evaluation is blocked because portfolio approval was rejected.",
                    "position_size": 0.0,
                }
            risk_result = record_agent(
                "risk_chief",
                "risk",
                "approved" if risk["approved"] else "rejected",
                decision_confidence,
                risk,
                {
                    "portfolio_approved": bool(portfolio["approved"]),
                    "max_position_size": self.agent.config.max_position_size,
                    "max_daily_loss_limit": self.agent.config.max_daily_loss,
                },
                str(risk.get("reason", "")),
            )
            policy_result = record_agent(
                "policy_guard",
                "execution_policy",
                "approved" if policy_gate.get("allowed") else "rejected",
                1.0,
                policy_gate,
                {
                    "mode": self.agent.config.mode,
                    "account_id": account_id,
                    "live_execution_available": False,
                },
                str(policy_gate.get("reason", "")),
            )

            decision = {
                "signal": decision_signal,
                "confidence": decision_confidence,
                "approved": bool(risk["approved"] and portfolio["approved"]),
                "selected_symbol": selected_symbol,
            }
            decision_audit = self.monitor.build_decision_audit(
                {
                    **signal,
                    "signal": decision_signal,
                    "confidence": decision_confidence,
                },
                risk,
                {
                    "account_id": account_id,
                    "mode": "paper",
                    "manual_approval": False,
                    "portfolio_approved": bool(portfolio["approved"]),
                    "policy_approved": bool(policy_gate.get("allowed")),
                    "run_id": run_id,
                },
            )
            can_execute = (
                bool(portfolio["approved"])
                and bool(risk["approved"])
                and self.monitor.is_approved_for_execution(decision_audit, account_id)
                and policy_gate.get("allowed") is True
            )
            order = None
            if can_execute:
                quantity = int(float(risk["position_size"]) // latest_price)
                if quantity <= 0:
                    can_execute = False
                    trade = {
                        "status": "rejected",
                        "reason_code": "position_below_minimum_quantity",
                        "reason": "Approved capital cannot fund one whole share at the latest price.",
                        "mode": "paper",
                        "simulated": False,
                        "allow_live": False,
                    }
                else:
                    order = {
                        "order_id": uuid4().hex,
                        "run_id": run_id,
                        "account_id": account_id,
                        "symbol": selected_symbol,
                        "side": decision_signal,
                        "quantity": quantity,
                        "price": latest_price,
                        "route": "local_simulator",
                        "mode": "paper",
                        "audit": decision_audit,
                    }
                    self.storage.store_audit_event(
                        {"event_type": "order_created", "run_id": run_id, "order": order}
                    )
                    trade = self.agent.execution_agent.execute(
                        decision_signal,
                        quantity,
                        latest_price,
                        mode="paper",
                        policy_gate=policy_gate,
                        risk_decision=risk,
                        portfolio_decision=portfolio,
                        symbol=selected_symbol,
                        account_id=account_id,
                        run_id=run_id,
                        order_id=order["order_id"],
                    )
                    trade["price"] = latest_price
                    trade["quantity"] = quantity
                    trade["audit"] = decision_audit
                    self.storage.store_audit_event(
                        {
                            "event_type": "execution",
                            "run_id": run_id,
                            "order": order,
                            "trade": trade,
                        }
                    )
            else:
                reason = (
                    risk.get("reason")
                    if not risk.get("approved")
                    else ", ".join(portfolio.get("rejection_reasons", []))
                )
                trade = {
                    "status": "rejected",
                    "reason_code": risk.get("reason_code", portfolio.get("reason_code")),
                    "reason": reason or "Execution approval is missing.",
                    "mode": "paper",
                    "simulated": False,
                    "allow_live": False,
                }
            execution_result = record_agent(
                "execution_steward",
                "execution",
                "completed" if trade["status"] == "filled" else "rejected",
                decision_confidence,
                {"order": order, "trade": trade},
                {
                    "policy_approved": bool(policy_gate.get("allowed")),
                    "portfolio_approved": bool(portfolio["approved"]),
                    "risk_approved": bool(risk["approved"]),
                },
                str(trade.get("reason", "")),
            )

            review = self.agent.learning_agent.review_cycle(
                portfolio,
                risk,
                decision,
                trade if trade.get("status") == "filled" else {**trade, "mode": "paper"},
            )
            review_result = record_agent(
                "learning_reviewer",
                "review",
                "completed",
                decision_confidence,
                review,
                {"execution_status": trade.get("status"), "risk_approved": bool(risk["approved"])},
                str(review.get("review_status", "")),
            )

            handoffs = [
                ("data_curator", "strategy_architect", "market_data", data_result),
                ("strategy_architect", "alpha_researcher", "strategy_signal", signal_result),
                ("alpha_researcher", "portfolio_manager", "research_result", research_result),
                ("portfolio_manager", "risk_chief", "portfolio_approval", portfolio_result),
                ("risk_chief", "policy_guard", "risk_approval", risk_result),
                ("policy_guard", "execution_steward", "execution_policy", policy_result),
                ("execution_steward", "learning_reviewer", "execution_outcome", execution_result),
            ]
            for sender, recipient, message_type, payload in handoffs:
                message = AgentMessage(
                    sender,
                    recipient,
                    message_type,
                    {"result": payload},
                    run_id=run_id,
                )
                self.team.send(message)
                self.storage.store_audit_event(
                    {
                        "event_type": "agent_handoff",
                        "run_id": run_id,
                        "message": self._json_safe(
                            {
                                "sender_id": message.sender_id,
                                "recipient_id": message.recipient_id,
                                "message_type": message.message_type,
                                "payload": message.payload,
                                "message_id": message.message_id,
                                "run_id": message.run_id,
                                "created_at": message.created_at,
                            }
                        ),
                    }
                )

            status = (
                "completed"
                if trade.get("status") == "filled"
                else "rejected"
                if trade.get("status") == "rejected"
                else "completed"
            )
            result = {
                "run_id": run_id,
                "started_at": started_at,
                "completed_at": datetime.now(timezone.utc).isoformat(),
                "status": status,
                "mode": "paper",
                "account": {
                    "account_id": account_id,
                    "kind": "local_virtual",
                    "equity": self.agent.account_equity,
                    "equity_source": "configured_local_paper_budget",
                },
                "market_data_rows": len(market_data),
                "signal": signal,
                "portfolio": portfolio,
                "risk": risk,
                "trade": trade,
                "order": order,
                "decision_audit": decision_audit,
                "execution_simulation": {
                    "mode": "paper",
                    "simulated": bool(trade.get("simulated", False)),
                    "allow_live": False,
                    "policy_gate": policy_gate,
                },
                "review": review,
                "market_scan": market_scan,
                "research": research,
                "metrics": candidate.get("metrics") if candidate else None,
                "agents": agent_results,
                "team_messages": [self._json_safe(message.__dict__) for message in self.team.messages],
                "team_snapshot": self._json_safe(self.team.snapshot()),
                "final_summary": {
                    "run_id": run_id,
                    "status": status,
                    "mode": "paper",
                    "symbol": selected_symbol,
                    "signal": decision_signal,
                    "confidence": decision_confidence,
                    "portfolio_approved": bool(portfolio["approved"]),
                    "risk_approved": bool(risk["approved"]),
                    "trade_status": trade.get("status"),
                    "review_status": review.get("review_status"),
                },
            }
            result = self._json_safe(result)
            result["report_path"] = str(self.storage.latest_path)
            self.storage.store_audit_event(
                {
                    "event_type": "final_summary",
                    "run_id": run_id,
                    "timestamp": result["completed_at"],
                    "summary": result["final_summary"],
                }
            )
            self.storage.store(result)
            return result
        except Exception as exc:
            self.storage.store_audit_event(
                {
                    "event_type": "run_failed",
                    "run_id": run_id,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "reason": str(exc),
                    "error_type": type(exc).__name__,
                }
            )
            raise

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_safe(item) for item in value]
        if isinstance(value, Real) and not isinstance(value, bool):
            number = float(value)
            return number if math.isfinite(number) else None
        if hasattr(value, "item"):
            return cls._json_safe(value.item())
        return value
