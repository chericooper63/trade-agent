import json
import logging
import os
import tempfile
import threading
import unittest
from pathlib import Path
import urllib.request
from unittest.mock import patch

import numpy as np
import pandas as pd

from trade_agent.agent import MultiLayerTradeAgent
from trade_agent.advisor import AdvisorFilter
from trade_agent.agents import (
    DataAgent,
    ExecutionSimulationAgent,
    LearningAgent,
    LiveExecutionAgent,
    PolicyAgent,
    StrategyAgent,
)
from trade_agent.alpha import AlphaAgentRegistry
from trade_agent.backtest import Backtester
from trade_agent.broker import (
    AlpacaLiveBrokerAdapter,
    AlpacaPaperBrokerAdapter,
    BrokerAdapter,
    LiveBrokerAdapter,
    PaperBrokerAdapter,
)
from trade_agent.cli import main as run_cli, parse_args
from trade_agent.config import AgentConfig
from trade_agent.data import (
    CSVMarketDataProvider,
    FreePublicMarketDataProvider,
    MarketDataProvider,
    RealMarketDataProvider,
    SourceAwareMarketDataProvider,
)
from trade_agent.events import AgentEvent, ExecutionEvent, MarketDataEvent, OrderEvent, SignalEvent, RiskEvent
from trade_agent.execution import ExecutionService, SimulatedBroker
from trade_agent.env import EnvironmentPolicy
from trade_agent.frontend import FrontendAdapter
from trade_agent.intelligence import IntelligenceModel
from trade_agent.knowledge_graph import KnowledgeGraph
from trade_agent.market_service import MarketDataService
from trade_agent.monitoring import MonitoringService
from trade_agent.orchestration import AgentOrchestrator
from trade_agent.orders import Order, OrderBook, OrderRouter
from trade_agent.performance import PerformanceService
from trade_agent.policy import ProductionPolicy
from trade_agent.portfolio import PortfolioManager
from trade_agent.regime import RegimeDetector
from trade_agent.report import AuditReportService
from trade_agent.review import ReviewAgent
from trade_agent.risk import RiskManager
from trade_agent.scanner import MarketScanner
from trade_agent.security import ProductionReadinessGate, SecurityManager
from trade_agent.server import DashboardServer
from trade_agent.startup import StartupError, retry_call
from trade_agent.storage import RunStorage
from trade_agent.strategy import ResearchStrategyEngine, TechnicalSignalGenerator
from trade_agent.team import AgentMessage, AgentProfile, AgentTeam, LearningJournal, build_default_team
from trade_agent.api import DashboardAPI


class TradeAgentTests(unittest.TestCase):
    def test_market_data_provider_generates_table(self):
        provider = MarketDataProvider(symbol="MSFT", periods=50)
        market_data = provider.get_market_data()

        self.assertIsInstance(market_data, pd.DataFrame)
        self.assertEqual(len(market_data), 50)
        self.assertIn("close", market_data.columns)
        self.assertIn("volume", market_data.columns)

    def test_strategy_generator_returns_valid_signal(self):
        provider = MarketDataProvider(symbol="AAPL", periods=80)
        market_data = provider.get_market_data()
        signal = TechnicalSignalGenerator().generate(market_data)

        self.assertIn(signal["signal"], {"BUY", "SELL", "HOLD"})
        self.assertGreaterEqual(signal["confidence"], 0.0)
        self.assertIn("reason", signal)

    def test_research_strategy_engine_scores_multiple_factors(self):
        provider = MarketDataProvider(symbol="AAPL", periods=200)
        market_data = provider.get_market_data().copy()
        market_data["close"] = np.linspace(100, 120, len(market_data))
        market_data["volume"] = np.linspace(750000, 1200000, len(market_data))

        result = ResearchStrategyEngine().generate(market_data)

        self.assertIn(result["signal"], {"BUY", "SELL", "HOLD"})
        self.assertGreaterEqual(result["score"], 0.0)
        self.assertLessEqual(result["score"], 1.0)
        self.assertIn("factors", result)
        self.assertIn("reason", result)

    def test_risk_manager_approves_or_rejects_signal(self):
        risk = RiskManager()
        approved = risk.evaluate("BUY", 0.6, 100_000, 5_000)
        self.assertTrue(approved["approved"])
        self.assertGreater(approved["position_size"], 0)

        rejected = risk.evaluate("BUY", 0.2, 100_000, 5_000)
        self.assertFalse(rejected["approved"])

    def test_full_equity_proposal_passes_sizing_cap(self):
        risk = RiskManager()
        security = SecurityManager()

        risk_result = risk.evaluate("BUY", 0.8, 1_000.0, 1_000.0)
        security_result = security.evaluate("BUY", 0.8, 1_000.0, 1_000.0)

        self.assertTrue(risk_result["approved"])
        self.assertEqual(risk_result["position_size"], 1_000.0)
        self.assertTrue(security_result["approved"])

    def test_config_has_expected_defaults(self):
        config = AgentConfig()

        self.assertEqual(config.symbol, "AAPL")
        self.assertEqual(config.account_equity, 100_000.0)
        self.assertEqual(config.proposal_capital, 5_000.0)

    def test_portfolio_manager_allocates_position(self):
        manager = PortfolioManager()
        allocation = manager.plan("BUY", 0.75, 100_000.0, 5_000.0)

        self.assertEqual(allocation["side"], "BUY")
        self.assertGreaterEqual(allocation["cash_used"], 0)
        self.assertLessEqual(allocation["cash_used"], 5_000.0)

    def test_portfolio_manager_enforces_cross_asset_risk_budget(self):
        manager = PortfolioManager()
        allocation = manager.plan_portfolio(
            {
                "AAPL": "BUY",
                "MSFT": "BUY",
                "NVDA": "BUY",
            },
            {
                "AAPL": 0.7,
                "MSFT": 0.6,
                "NVDA": 0.8,
            },
            100_000.0,
            {"AAPL": 5_000.0, "MSFT": 4_000.0, "NVDA": 6_000.0},
        )

        self.assertIn("positions", allocation)
        self.assertIn("total_cash_used", allocation)
        self.assertIn("risk_budget_used", allocation)
        self.assertGreater(allocation["risk_budget_used"], 1.0)
        self.assertFalse(allocation["approved"])
        self.assertEqual(allocation["reason_code"], "risk_budget_exceeded")
        self.assertLessEqual(allocation["total_cash_used"], 100_000.0)

    def test_portfolio_manager_rejects_invalid_account_budget_inputs(self):
        manager = PortfolioManager()

        with self.assertRaises(ValueError):
            manager.plan_portfolio({}, {}, -1.0, {}, max_risk_budget=1.0)
        with self.assertRaises(ValueError):
            manager.plan_portfolio({}, {}, 100_000.0, {}, max_risk_budget=-0.1)

    def test_live_decision_audit_requires_explicit_manual_approval(self):
        signal = {"signal": "BUY", "confidence": 0.75, "reason": "trend=1.00"}
        risk = {"approved": True, "position_size": 5000.0, "reason": "Risk constraints passed"}
        account = {"account_id": "personal-primary", "mode": "live", "manual_approval": False}

        monitoring = MonitoringService()
        audit = monitoring.build_decision_audit(signal, risk, account)

        self.assertEqual(audit["approval_status"], "pending")
        self.assertFalse(monitoring.is_approved_for_execution(audit, "personal-primary"))
        with self.assertRaisesRegex(ValueError, "manual approval"):
            monitoring.approve_decision(audit, "personal-primary", approver="owner")

        account["manual_approval"] = True
        pending_audit = monitoring.build_decision_audit(signal, risk, account)
        approved = monitoring.approve_decision(pending_audit, "personal-primary", approver="owner")
        self.assertTrue(monitoring.is_approved_for_execution(approved, "personal-primary"))
        self.assertFalse(monitoring.is_approved_for_execution(audit, "other-account"))

        # A manually approved live audit is executable through the live broker route.
        route = OrderRouter().route(Order(symbol="AAPL", side="BUY", quantity=5, price=150.0), mode="live")
        route.update({"account_id": "personal-primary", "audit": approved})
        fill = ExecutionService().execute(route)
        self.assertEqual(fill["status"], "filled")
        self.assertEqual(fill["route"], "live_broker")

        # An audit that is still pending cannot execute, live or paper.
        pending_live = monitoring.build_decision_audit(
            {"signal": "SELL", "confidence": 0.75, "reason": "trend=-1.00"},
            risk,
            {"account_id": "personal-primary", "mode": "live", "manual_approval": False},
        )
        pending_route = OrderRouter().route(
            Order(symbol="AAPL", side="SELL", quantity=5, price=150.0), mode="live"
        )
        pending_route.update({"account_id": "personal-primary", "audit": pending_live})
        with self.assertRaisesRegex(ValueError, "completed approval"):
            ExecutionService().execute(pending_route)

        # Paper audits are approved by the paper policy itself and stay on the paper route.
        paper_audit = monitoring.build_decision_audit(
            signal,
            risk,
            {"account_id": "local-paper", "mode": "paper", "manual_approval": False},
        )
        self.assertEqual(paper_audit["approval_status"], "approved")
        self.assertEqual(paper_audit["approved_by"], "paper_policy")
        paper_route = OrderRouter().route(Order(symbol="AAPL", side="BUY", quantity=5, price=120.0))
        paper_route.update({"account_id": "local-paper", "audit": paper_audit})
        self.assertEqual(ExecutionService().execute(paper_route)["route"], "paper_broker")

    def test_backtester_returns_metrics(self):
        provider = CSVMarketDataProvider()
        backtester = Backtester(provider)
        report = backtester.run(100_000.0, 5_000.0)

        self.assertIn("total_return", report)
        self.assertIn("net_profit", report)
        self.assertIn("win_rate", report)
        self.assertIn("profit_factor", report)
        self.assertIn("max_drawdown", report)
        self.assertIn("paper_ready", report)
        self.assertIn("trades", report)

    def test_backtester_accounts_for_direction_and_costs(self):
        market_data = pd.DataFrame({"close": np.linspace(100.0, 80.0, 50)})

        class BuyStrategy:
            def generate(self, _market_data):
                return {"signal": "BUY"}

        class Provider:
            def get_market_data(self):
                return market_data

        report = Backtester(Provider(), strategy=BuyStrategy(), fee_bps=10.0, slippage_bps=10.0).run(
            100_000.0, 5_000.0
        )

        self.assertGreater(report["trades"], 0)
        self.assertLess(report["total_return"], 0.0)
        self.assertGreater(report["costs"], 0.0)
        self.assertFalse(report["paper_ready"])

    def test_cross_cutting_services_and_events(self):
        market_event = MarketDataEvent(symbol="AAPL", payload={"rows": 40})
        signal_event = SignalEvent(symbol="AAPL", signal="BUY", confidence=0.8)
        risk_event = RiskEvent(symbol="AAPL", approved=True)

        security = SecurityManager()
        security_result = security.evaluate("BUY", 0.8, 100_000.0, 5_000.0)

        monitor = MonitoringService()
        log = monitor.build_log({"signal": "BUY"}, {"approved": True})

        storage = RunStorage()
        storage_path = storage.store({"signal": "BUY", "status": "ok"})

        self.assertEqual(market_event.symbol, "AAPL")
        self.assertEqual(signal_event.signal, "BUY")
        self.assertTrue(risk_event.approved)
        self.assertTrue(security_result["approved"])
        self.assertIn("signal", log)
        self.assertTrue(storage_path.endswith(".json"))

    def test_run_storage_keeps_history_for_learning_loop(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = RunStorage(directory=tmpdir)
            storage.store({"signal": "BUY", "status": "ok"})
            storage.store({"signal": "SELL", "status": "closed"})

            history = storage.load_history()
            self.assertGreaterEqual(len(history), 2)
            self.assertEqual(history[-1]["signal"], "SELL")
            self.assertEqual(history[-1]["status"], "closed")

    def test_approval_and_execution_audits_survive_restart(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = RunStorage(directory=tmpdir)
            monitoring = MonitoringService(storage=storage)
            audit = monitoring.build_decision_audit(
                {"signal": "BUY", "confidence": 0.8, "reason": "test"},
                {"approved": True, "position_size": 750.0, "reason": "test"},
                {"account_id": "personal-primary", "mode": "paper", "manual_approval": True},
            )
            approved = monitoring.approve_decision(audit, "personal-primary", approver="owner")

            route = OrderRouter().route(Order(symbol="AAPL", side="BUY", quantity=5, price=150.0))
            route.update({"account_id": "personal-primary", "audit": approved})
            ExecutionService(storage=storage).execute(route)

            restarted_storage = RunStorage(directory=tmpdir)
            audit_history = restarted_storage.load_audit_history()
            self.assertEqual([event["event_type"] for event in audit_history], ["decision", "approval", "execution"])
            self.assertEqual(audit_history[-1]["fill"]["account_id"], "personal-primary")

    def test_regime_detector_and_alpha_registry(self):
        provider = CSVMarketDataProvider()
        data = provider.get_market_data()

        regime = RegimeDetector().detect(data)
        self.assertIn("label", regime)
        self.assertIn("confidence", regime)

        alpha = AlphaAgentRegistry().run(data)
        self.assertIn("signals", alpha)
        self.assertIn("aggregated_signal", alpha)

    def test_advisor_filter_turns_alpha_into_decision(self):
        alpha = AlphaAgentRegistry().run(CSVMarketDataProvider().get_market_data())
        filtered = AdvisorFilter().filter(alpha)

        self.assertIn("approved", filtered)
        self.assertIn("aggregated_signal", filtered)
        self.assertIn("reasons", filtered)

    def test_market_scanner_hands_ranked_candidates_to_advisor(self):
        scan = MarketScanner(symbols=["AAPL", "BTC-USD"]).scan()

        self.assertEqual(scan["scanned_symbols"], ["AAPL", "BTC-USD"])
        self.assertEqual(len(scan["candidates"]), 2)
        self.assertEqual(scan["candidates"][0]["confidence"], 0.95)
        selected = AdvisorFilter().filter_candidates(scan)
        self.assertTrue(selected["approved"])
        self.assertIn(selected["decision"], {"BUY", "SELL"})
        self.assertEqual(selected["candidate"], scan["candidates"][0])

    def test_intelligence_model_runs_research_before_risk_decisions(self):
        result = IntelligenceModel().evaluate()

        self.assertIn("research", result)
        self.assertIn("reports", result["research"])
        self.assertIn("qualified", result["research"])
        self.assertIsInstance(result["research"]["reports"], list)

    def test_intelligence_model_applies_research_qualified_candidates_to_portfolio_and_risk(self):
        result = IntelligenceModel().evaluate()

        self.assertIn("portfolio", result)
        self.assertIn("risk", result)
        self.assertIn("decision", result)
        self.assertIn("selected_symbol", result["decision"])
        self.assertIn("positions", result["portfolio"])
        self.assertGreaterEqual(result["portfolio"]["cash_remaining"], 0.0)

    def test_order_and_execution_services_drive_a_trade(self):
        order = Order(symbol="AAPL", side="BUY", quantity=5, price=150.0)
        route = OrderRouter().route(order)
        route["account_id"] = "personal-primary"
        route["audit"] = MonitoringService().build_decision_audit(
            {"signal": "BUY", "confidence": 0.8, "reason": "test"},
            {"approved": True, "position_size": 750.0, "reason": "test"},
            {"account_id": "personal-primary", "mode": "paper", "manual_approval": False},
        )
        execution = ExecutionService().execute(route)

        self.assertEqual(route["symbol"], "AAPL")
        self.assertEqual(route["side"], "BUY")
        self.assertEqual(route["quantity"], 5)
        self.assertEqual(execution["status"], "filled")
        self.assertEqual(execution["symbol"], "AAPL")

    def test_execution_service_includes_costs_and_slippage_contract(self):
        order = Order(symbol="AAPL", side="BUY", quantity=10, price=150.0)
        route = OrderRouter().route(order)
        route["account_id"] = "personal-primary"
        route["audit"] = MonitoringService().build_decision_audit(
            {"signal": "BUY", "confidence": 0.8, "reason": "test"},
            {"approved": True, "position_size": 1500.0, "reason": "test"},
            {"account_id": "personal-primary", "mode": "paper", "manual_approval": False},
        )
        route["estimated_fee"] = 0.25
        route["estimated_slippage"] = 0.20
        execution = ExecutionService().execute(route)

        self.assertIn("estimated_fee", execution)
        self.assertIn("estimated_slippage", execution)
        self.assertGreaterEqual(execution["estimated_fee"], 0.0)
        self.assertGreaterEqual(execution["estimated_slippage"], 0.0)
        self.assertEqual(execution["status"], "filled")

    def test_execution_service_rejects_unapproved_and_duplicate_orders(self):
        order = Order(symbol="AAPL", side="BUY", quantity=5, price=150.0)
        route = OrderRouter().route(order)
        route["account_id"] = "personal-primary"

        with self.assertRaises(ValueError):
            ExecutionService().execute(route)

        monitoring = MonitoringService()
        rejected = dict(route)
        rejected["audit"] = monitoring.build_decision_audit(
            {"signal": "BUY", "confidence": 0.8, "reason": "test"},
            {"approved": False, "position_size": 0.0, "reason": "risk rejected"},
            {"account_id": "personal-primary", "mode": "paper", "manual_approval": False},
        )
        with self.assertRaises(ValueError):
            ExecutionService().execute(rejected)

        approved = dict(route)
        approved["audit"] = monitoring.build_decision_audit(
            {"signal": "BUY", "confidence": 0.8, "reason": "test"},
            {"approved": True, "position_size": 750.0, "reason": "test"},
            {"account_id": "personal-primary", "mode": "paper", "manual_approval": False},
        )
        execution = ExecutionService()
        execution.execute(approved)
        with self.assertRaises(ValueError):
            execution.execute(approved)

    def test_market_data_service_and_arg_parser(self):
        service = MarketDataService()
        data = service.fetch("AAPL")
        self.assertIn("symbol", data.columns)

        args = parse_args(["--symbol", "MSFT", "--mode", "paper", "--strategy", "trend"])
        self.assertEqual(args.symbol, "MSFT")
        self.assertEqual(args.mode, "paper")
        self.assertEqual(args.strategy, "trend")

    def test_trade_decision_audit_records_signal_risk_and_account_context(self):
        signal = {"signal": "BUY", "confidence": 0.75, "reason": "trend=1.00"}
        risk = {"approved": True, "position_size": 5000.0, "reason": "Risk constraints passed"}
        account = {"account_id": "personal-primary", "mode": "paper", "manual_approval": True}

        trace = MonitoringService().build_decision_audit(signal, risk, account)

        self.assertEqual(trace["signal"], "BUY")
        self.assertEqual(trace["account_id"], "personal-primary")
        self.assertTrue(trace["risk_approved"])
        self.assertIn("manual_approval", trace)
        self.assertIn("reason", trace)

    def test_report_and_frontend_adapter(self):
        report = AuditReportService().write({"signal": "BUY", "trade": "filled"})
        self.assertTrue(report.endswith(".json"))

        frontend = FrontendAdapter()
        dashboard = frontend.dashboard_snapshot()
        self.assertIn("status", dashboard)
        self.assertIn("market_data", dashboard)

        api = DashboardAPI()
        payload = api.dashboard_payload()
        self.assertIn("market_data", payload)
        self.assertIn("status", payload)

    def test_broker_adapter_and_paper_execution(self):
        broker = PaperBrokerAdapter()
        order = Order(symbol="AAPL", side="BUY", quantity=5, price=150.0)
        routed = broker.place(order)

        self.assertEqual(routed["symbol"], "AAPL")
        self.assertEqual(routed["side"], "BUY")
        self.assertEqual(routed["status"], "paper_filled")
        self.assertTrue(hasattr(BrokerAdapter, "place"))

    def test_alpaca_paper_adapter_uses_paper_contract_without_network(self):
        class LocalAlpacaAdapter(AlpacaPaperBrokerAdapter):
            def __init__(self):
                super().__init__(base_url="https://paper-api.alpaca.markets/v2")
                self.requests = []

            def _request(self, path, method="GET", payload=None):
                self.requests.append((path, method, payload))
                if path == "account":
                    return {"status": "ACTIVE", "buying_power": "100000"}
                if path == "positions":
                    return []
                return {"id": "paper-order", "status": "accepted"}

        adapter = LocalAlpacaAdapter()
        account = adapter.account()
        positions = adapter.positions()
        order = adapter.place(Order(symbol="AAPL", side="BUY", quantity=5, price=150.0))

        self.assertEqual(account["status"], "ACTIVE")
        self.assertEqual(positions, [])
        self.assertEqual(order["status"], "accepted")
        self.assertEqual(adapter.requests[-1], ("orders", "POST", {
            "symbol": "AAPL",
            "qty": "5",
            "side": "buy",
            "type": "market",
            "time_in_force": "day",
        }))

    def test_secure_live_broker_and_free_public_data_provider_contract(self):
        config = AgentConfig()
        self.assertEqual(config.mode, "paper")
        self.assertFalse(config.allow_live)

        live_broker = LiveBrokerAdapter(mode="live")
        order = Order(symbol="AAPL", side="BUY", quantity=5, price=150.0)
        with self.assertRaises(ValueError):
            live_broker.place(order)

        provider = FreePublicMarketDataProvider(symbol="AAPL")
        data = provider.get_market_data()
        self.assertIn("symbol", data.columns)
        self.assertIn("close", data.columns)
        self.assertEqual(provider.source, "sample_csv")

    def test_source_aware_market_data_provider_requires_explicit_source_contract(self):
        provider = SourceAwareMarketDataProvider(symbol="AAPL", source="sample_csv")
        data = provider.get_market_data()
        self.assertIn("symbol", data.columns)
        self.assertEqual(provider.source, "sample_csv")

        with self.assertRaises(ValueError):
            SourceAwareMarketDataProvider(symbol="AAPL", source="").get_market_data()

    def test_real_market_data_provider_uses_explicit_contract_without_live_triggers(self):
        provider = RealMarketDataProvider(symbol="AAPL", source="sample_csv")
        data = provider.get_market_data()
        self.assertIn("symbol", data.columns)
        self.assertEqual(provider.source, "sample_csv")

        with self.assertRaises(ValueError):
            RealMarketDataProvider(symbol="AAPL", source="").get_market_data()

    def test_knowledge_graph_tracks_entities_and_relationships(self):
        graph = KnowledgeGraph()
        graph.add_entity("AAPL", {"asset_class": "stock"})
        graph.add_entity("NASDAQ", {"asset_class": "exchange"})
        graph.add_relation("AAPL", "listed_on", "NASDAQ")
        graph.add_relation("AAPL", "asset_class", "stock")

        self.assertIn("AAPL", graph.entities)
        self.assertIn("NASDAQ", graph.entities)
        self.assertEqual(graph.entities["AAPL"]["asset_class"], "stock")
        self.assertIn(("AAPL", "listed_on", "NASDAQ"), graph.relations)
        self.assertIn(("AAPL", "asset_class", "stock"), graph.relations)

    def test_knowledge_graph_records_agent_event_contract(self):
        graph = KnowledgeGraph()
        event = AgentEvent(
            source="strategy_agent",
            event_type="signal",
            symbol="AAPL",
            confidence=0.82,
            evidence={"trend": 1.1, "volatility": 0.015},
            assumptions=["price momentum remains positive"],
            payload={"signal": "BUY"},
        )

        stored = graph.record_event(event)
        snapshot = graph.snapshot()

        self.assertEqual(stored["symbol"], "AAPL")
        self.assertEqual(stored["event_type"], "signal")
        self.assertEqual(stored["confidence"], 0.82)
        self.assertIn("AAPL", snapshot["entities"])
        self.assertIn("events", snapshot)
        self.assertEqual(snapshot["events"][-1]["source"], "strategy_agent")

    def test_agent_team_enforces_parent_child_communication_boundary(self):
        team = AgentTeam(
            [
                AgentProfile("scanner", "market", "observant", "Find candidates"),
                AgentProfile("risk", "risk", "skeptical", "Reject unsafe proposals"),
            ]
        )
        child = team.create_child("scanner", "news", "fast researcher", "Summarize catalysts")

        team.send(AgentMessage("scanner", child.agent_id, "work", {"symbol": "AAPL"}))
        team.send(AgentMessage(child.agent_id, "scanner", "findings", {"signal": "BUY"}))
        with self.assertRaises(ValueError):
            team.send(AgentMessage(child.agent_id, "risk", "direct", {}))

        self.assertEqual(len(team.messages_for("scanner")), 1)

    def test_learning_journal_records_decision_outcome_and_lesson(self):
        journal = LearningJournal()
        entry = journal.record(
            "strategy",
            "AAPL",
            {"signal": "BUY", "confidence": 0.8},
            {"pnl": -12.50, "exit_reason": "stop_loss"},
            "The entry failed after volatility expanded beyond the regime filter.",
        )

        self.assertEqual(entry["agent_id"], "strategy")
        self.assertEqual(entry["outcome"]["pnl"], -12.50)
        self.assertEqual(len(journal.for_agent("strategy")), 1)

    def test_intelligence_model_records_persistent_paper_review_entries(self):
        result = IntelligenceModel().evaluate()

        self.assertIn("review", result)
        self.assertIn("entries", result["review"])
        self.assertIn("paper_mode", result["review"])
        self.assertTrue(result["review"]["paper_mode"])
        self.assertIsInstance(result["review"]["entries"], list)

    def test_review_agent_feedback_uses_paper_budget_and_candidate_tuning(self):
        review = ReviewAgent()
        portfolio = {
            "positions": {
                "AAPL": {"signal": "BUY", "confidence": 0.88, "cash_used": 20_000.0, "risk_weight": 0.88},
                "MSFT": {"signal": "BUY", "confidence": 0.82, "cash_used": 15_000.0, "risk_weight": 0.82},
                "BTC-USD": {"signal": "BUY", "confidence": 0.91, "cash_used": 10_000.0, "risk_weight": 0.91},
            },
            "total_cash_used": 45_000.0,
            "risk_budget_used": 1.0,
            "cash_remaining": 55_000.0,
        }
        risk = {"approved": True, "position_size": 45_000.0, "symbols": ["AAPL", "MSFT", "BTC-USD"]}
        decision = {"approved": True, "signal": "BUY", "confidence": 0.9, "selected_symbol": "BTC-USD"}

        result = review.evaluate(portfolio, risk, decision)

        self.assertIn("paper_mode", result)
        self.assertTrue(result["paper_mode"])
        self.assertIn("budget_exceeded", result)
        self.assertIn("priority_order", result)
        self.assertIn("reduction_plan", result)
        self.assertFalse(result["allow_live"])

    def test_review_agent_feeds_tuned_next_cycle_candidates(self):
        review = ReviewAgent()
        candidates = [
            {"symbol": "AAPL", "confidence": 0.92, "risk_weight": 0.9},
            {"symbol": "MSFT", "confidence": 0.87, "risk_weight": 0.82},
            {"symbol": "BTC-USD", "confidence": 0.76, "risk_weight": 0.45},
        ]

        result = review.next_cycle_candidates(candidates, risk_budget_used=1.0, risk_budget_limit=0.95)

        self.assertFalse(result["allow_live"])
        self.assertIn("next_cycle_candidates", result)
        self.assertIn("down_ranked", result)
        self.assertTrue(result["budget_exceeded"])
        self.assertLess(result["next_cycle_candidates"][0]["confidence"], 0.92)

    def test_default_team_has_specialized_roles_for_trade_workflow(self):
        team = build_default_team()
        roles = {profile.role for profile in team.profiles.values()}

        self.assertGreaterEqual(len(team.profiles), 10)
        self.assertTrue({
            "market scanner",
            "alpha researcher",
            "regime analyst",
            "risk chief",
            "portfolio manager",
            "execution steward",
            "execution simulator",
            "performance reviewer",
            "data curator",
            "strategy architect",
            "policy guard",
            "learning reviewer",
        }.issubset(roles))

    def test_specialist_agents_support_data_strategy_and_policy_flow(self):
        data_agent = DataAgent(symbol="AAPL", periods=60)
        market = data_agent.collect()

        self.assertIn("close", market.columns)
        self.assertGreater(len(market), 0)

        strategy_agent = StrategyAgent()
        decision = strategy_agent.evaluate(market)
        self.assertIn("signal", decision)
        self.assertIn("confidence", decision)
        self.assertIn("reason", decision)

        policy_agent = PolicyAgent(mode="paper", allow_live=False)
        self.assertTrue(policy_agent.evaluate("paper")["allowed"])
        with self.assertRaises(ValueError):
            policy_agent.evaluate("live")

    def test_execution_simulation_is_paper_only_and_requires_policy_gate(self):
        execution_agent = ExecutionSimulationAgent()

        with self.assertRaises(ValueError):
            execution_agent.execute(
                "BUY", 100.0, 150.0, mode="live",
                policy_gate={"allowed": True}, risk_decision={"approved": True},
            )
        with self.assertRaises(ValueError):
            execution_agent.execute(
                "BUY", 100.0, 150.0, mode="paper",
                policy_gate={"allowed": False}, risk_decision={"approved": True},
            )

        result = execution_agent.execute(
            "BUY",
            100.0,
            150.0,
            mode="paper",
            policy_gate={"allowed": True, "approval_status": "paper"},
            risk_decision={"approved": True},
            portfolio_decision={"approved": True},
        )
        self.assertEqual(result["status"], "filled")
        self.assertTrue(result["simulated"])
        self.assertFalse(result["allow_live"])
        self.assertEqual(result["estimated_fee"], 7.5)
        self.assertEqual(result["estimated_slippage"], 7.5)

    def test_learning_agent_records_simulated_execution_outcome(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = RunStorage(directory=tmpdir)
            journal = LearningJournal(storage=storage)
            learning_agent = LearningAgent(journal=journal)
            portfolio = {
                "positions": {"AAPL": {"confidence": 0.8, "risk_weight": 0.25, "cash_used": 1000.0}},
                "risk_budget_used": 0.25,
            }

            result = learning_agent.review_cycle(
                portfolio,
                {"approved": True},
                {"signal": "BUY", "confidence": 0.8, "selected_symbol": "AAPL"},
                {"mode": "paper", "simulated": True, "status": "filled", "estimated_fee": 0.1},
            )

            self.assertTrue(result["paper_mode"])
            self.assertFalse(result["allow_live"])
            self.assertEqual(result["learning_entries"][0]["outcome"]["execution_status"], "filled")
            self.assertEqual(journal.for_agent("execution_learning_agent")[0]["symbol"], "AAPL")
            persisted = RunStorage(directory=tmpdir).load_history()
            self.assertEqual(persisted[-1]["learning_entry"]["outcome"]["execution_status"], "filled")

    def test_production_readiness_gate_requires_paper_mode_before_live_execution(self):
        gate = ProductionReadinessGate(mode="paper", allow_live=False)
        gate_run = gate.validate()
        self.assertTrue(gate_run["paper_mode"])
        self.assertFalse(gate_run["allow_live"])
        self.assertEqual(gate_run["status"], "paper_ready")

        live_gate = ProductionReadinessGate(mode="live", allow_live=False)
        with self.assertRaises(ValueError):
            live_gate.validate()

    def test_config_can_load_secure_environment_contract(self):
        os.environ["TRADE_AGENT_MODE"] = "paper"
        os.environ["TRADE_AGENT_ALLOW_LIVE"] = "false"
        cfg = AgentConfig.from_env()
        self.assertEqual(cfg.mode, "paper")
        self.assertFalse(cfg.allow_live)
        self.assertTrue(cfg.paper_only)

    def test_environment_configuration_defaults_to_paper_and_parses_strictly(self):
        with patch.dict(os.environ, {}, clear=True):
            config = AgentConfig.from_env()
            environment = EnvironmentPolicy()

        self.assertEqual(config.mode, "paper")
        self.assertFalse(config.allow_live)
        self.assertTrue(config.paper_only)
        self.assertEqual(environment.summary()["mode"], "paper")
        self.assertTrue(environment.summary()["require_manual_approval"])

        for values, expected_error in (
            ({"TRADE_AGENT_ALLOW_LIVE": "sometimes"}, "TRADE_AGENT_ALLOW_LIVE"),
            ({"TRADE_AGENT_MODE": "production"}, "TRADE_AGENT_MODE"),
            ({"TRADE_AGENT_ACCOUNT_EQUITY": "nan"}, "TRADE_AGENT_ACCOUNT_EQUITY"),
        ):
            with self.subTest(values=values), patch.dict(os.environ, values, clear=True):
                with self.assertRaisesRegex(ValueError, expected_error):
                    AgentConfig.from_env()

    def test_agent_config_rejects_unsafe_live_combinations(self):
        with self.assertRaisesRegex(ValueError, "mode"):
            AgentConfig(mode="production")
        with self.assertRaisesRegex(ValueError, "paper_only"):
            AgentConfig(mode="live", allow_live=True, account_id="personal-primary", paper_only=True)
        with self.assertRaisesRegex(ValueError, "account_id"):
            AgentConfig(mode="live", allow_live=True, account_id="", paper_only=False)
        with self.assertRaisesRegex(ValueError, "manual approval"):
            AgentConfig(
                mode="live",
                allow_live=True,
                account_id="personal-primary",
                manual_approval_required=False,
                paper_only=False,
            )

    def test_live_policy_requires_per_action_account_approval_and_nonblank_credentials(self):
        order = Order(symbol="AAPL", side="BUY", quantity=5, price=150.0)
        with patch.dict(os.environ, {"TEST_API_KEY": "key", "TEST_SECRET_KEY": "secret"}, clear=True):
            policy = ProductionPolicy(
                mode="live",
                allow_live=True,
                broker="alpaca",
                account_id="personal-primary",
                api_key_env="TEST_API_KEY",
                secret_key_env="TEST_SECRET_KEY",
            )
            with self.assertRaisesRegex(ValueError, "explicit account_id"):
                policy.execution_gate("live", manual_approval=True)
            with self.assertRaisesRegex(ValueError, "manual approval"):
                policy.execution_gate("live", account_id="personal-primary", manual_approval=False)
            self.assertTrue(policy.execution_gate(
                "live", account_id="personal-primary", manual_approval=True
            )["allowed"])

            whitespace_policy = ProductionPolicy(
                mode="live",
                allow_live=True,
                account_id="personal-primary",
                api_key_env="TEST_API_KEY",
                secret_key_env="TEST_SECRET_KEY",
            )
            with patch.dict(os.environ, {"TEST_API_KEY": "  ", "TEST_SECRET_KEY": "secret"}, clear=True):
                with self.assertRaisesRegex(ValueError, "TEST_API_KEY"):
                    whitespace_policy.execution_gate(
                        "live", account_id="personal-primary", manual_approval=True
                    )

            class StubLiveAdapter(AlpacaLiveBrokerAdapter):
                """Live adapter with the HTTP transport replaced by an in-memory stub."""

                def __init__(self):
                    super().__init__(api_key_env="TEST_API_KEY", secret_key_env="TEST_SECRET_KEY")
                    self.requests = []

                def _request(self, path, method="GET", payload=None):
                    self.requests.append({"path": path, "method": method, "payload": payload})
                    return {"id": "order-1", "symbol": payload["symbol"], "status": "accepted"}

            stub = StubLiveAdapter()
            adapter = LiveBrokerAdapter(policy=policy)
            with patch("trade_agent.broker.AlpacaLiveBrokerAdapter", return_value=stub):
                result = adapter.place(
                    order,
                    account_id="personal-primary",
                    manual_approval=True,
                    risk_approved=True,
                )
            self.assertEqual(
                stub.requests,
                [
                    {
                        "path": "orders",
                        "method": "POST",
                        "payload": {
                            "symbol": "AAPL",
                            "qty": "5",
                            "side": "buy",
                            "type": "market",
                            "time_in_force": "day",
                        },
                    }
                ],
            )
            self.assertEqual(result["route"], "live_broker")
            self.assertEqual(result["mode"], "live")
            self.assertEqual(adapter.history[0]["route"], "live_broker")
            with self.assertRaisesRegex(ValueError, "approved risk decision"):
                adapter.place(order, account_id="personal-primary", manual_approval=True)

    def test_institutional_policy_requires_manual_approval_by_default(self):
        policy = ProductionPolicy(mode="paper", allow_live=True, broker="alpaca", account_id="institutional-primary")
        self.assertTrue(policy.require_manual_approval)
        self.assertTrue(policy.execution_gate("paper")["manual_approval"])

        with self.assertRaises(ValueError):
            policy.execution_gate("live", account_id="institutional-primary", manual_approval=False)

        os.environ["ALPACA_API_KEY"] = "demo-key"
        os.environ["ALPACA_SECRET_KEY"] = "demo-secret"
        gate = policy.execution_gate("live", account_id="institutional-primary", manual_approval=True)
        self.assertTrue(gate["allowed"])
        self.assertTrue(gate["manual_approval"])

    def test_personal_account_contract_requires_explicit_account_without_manual_gate(self):
        original_account_id = os.environ.get("TRADE_AGENT_ACCOUNT_ID")
        original_key = os.environ.get("ALPACA_API_KEY")
        original_secret = os.environ.get("ALPACA_SECRET_KEY")

        try:
            os.environ.pop("TRADE_AGENT_ACCOUNT_ID", None)
            os.environ.pop("ALPACA_API_KEY", None)
            os.environ.pop("ALPACA_SECRET_KEY", None)

            with self.assertRaises(ValueError):
                ProductionPolicy(mode="live", allow_live=True, account_id="", broker="alpaca").execution_gate("live")

            os.environ["ALPACA_API_KEY"] = "demo-key"
            os.environ["ALPACA_SECRET_KEY"] = "demo-secret"
            os.environ["TRADE_AGENT_ACCOUNT_ID"] = "personal-primary"
            policy = ProductionPolicy(mode="live", allow_live=True, account_id="personal-primary", broker="alpaca")
            gate = policy.execution_gate(
                "live", account_id="personal-primary", manual_approval=True
            )
            self.assertEqual(gate["account_id"], "personal-primary")
            self.assertTrue(gate["manual_approval"])
            self.assertTrue(gate["allowed"])
            self.assertEqual(gate["approval_status"], "approved")
            self.assertLessEqual(gate["per_account_risk_budget"], 1.0)
        finally:
            if original_account_id is None:
                os.environ.pop("TRADE_AGENT_ACCOUNT_ID", None)
            else:
                os.environ["TRADE_AGENT_ACCOUNT_ID"] = original_account_id
            if original_key is None:
                os.environ.pop("ALPACA_API_KEY", None)
            else:
                os.environ["ALPACA_API_KEY"] = original_key
            if original_secret is None:
                os.environ.pop("ALPACA_SECRET_KEY", None)
            else:
                os.environ["ALPACA_SECRET_KEY"] = original_secret

    def test_live_execution_gate_requires_explicit_alpaca_approval_and_credentials(self):
        current_key = os.environ.get("ALPACA_API_KEY")
        current_secret = os.environ.get("ALPACA_SECRET_KEY")
        try:
            os.environ.pop("ALPACA_API_KEY", None)
            os.environ.pop("ALPACA_SECRET_KEY", None)
            policy = ProductionPolicy(mode="paper", allow_live=False, broker="alpaca")
            with self.assertRaises(ValueError):
                policy.execution_gate("live")

            os.environ["ALPACA_API_KEY"] = "demo-key"
            os.environ["ALPACA_SECRET_KEY"] = "demo-secret"
            approved_policy = ProductionPolicy(mode="paper", allow_live=True, broker="alpaca", account_id="personal-primary")
            gate = approved_policy.execution_gate("live", account_id="personal-primary", manual_approval=True)
            self.assertTrue(gate["allowed"])
            self.assertEqual(gate["broker"], "alpaca")
            self.assertEqual(gate["account_id"], "personal-primary")
            self.assertTrue(gate["manual_approval"])

            with self.assertRaises(ValueError):
                approved_policy.execution_gate("live", account_id="other-account", manual_approval=False)
        finally:
            if current_key is None:
                os.environ.pop("ALPACA_API_KEY", None)
            else:
                os.environ["ALPACA_API_KEY"] = current_key
            if current_secret is None:
                os.environ.pop("ALPACA_SECRET_KEY", None)
            else:
                os.environ["ALPACA_SECRET_KEY"] = current_secret

    def test_intelligence_and_safety_model_contract(self):
        intelligence = IntelligenceModel()
        result = intelligence.evaluate()
        self.assertIn("signal", result)
        self.assertIn("alpha", result)
        self.assertIn("regime", result)
        self.assertIn("advice", result)
        self.assertIn("policy", result)
        self.assertIn("market_scan", result)
        self.assertIn("scan_advice", result)
        self.assertEqual(len(result["team"]["agents"]), 12)

    def test_order_book_matching_contract(self):
        book = OrderBook()
        order = Order(symbol="AAPL", side="BUY", quantity=5, price=150.0)
        matched = book.match(order)
        self.assertEqual(matched["symbol"], "AAPL")
        self.assertEqual(matched["side"], "BUY")
        self.assertEqual(matched["status"], "matched")
        self.assertEqual(len(book.trades), 1)

    def test_performance_service_reports_metrics(self):
        event = ExecutionEvent(symbol="AAPL", side="BUY", quantity=5, price=150.0, route="paper_broker")
        performance = PerformanceService().report(event, account_equity=100_000.0)

        self.assertIn("pnl", performance)
        self.assertIn("exposure", performance)
        self.assertIn("drawdown", performance)
        self.assertIn("attribution", performance)

    def test_orchestrator_handles_run_flow(self):
        orchestrator = AgentOrchestrator()
        outcome = orchestrator.run()
        self.assertIn("trade", outcome)
        self.assertIn("metrics", outcome)
        self.assertIn("team_messages", outcome)
        self.assertIn("team_snapshot", outcome)
        self.assertTrue(outcome["team_messages"])
        self.assertIn("message_type", outcome["team_messages"][0])

    def test_production_policy_and_execution_gate(self):
        policy = ProductionPolicy()
        self.assertEqual(policy.mode, "paper")
        self.assertFalse(policy.allow_live)
        self.assertTrue(policy.require_manual_approval)
        self.assertIn("manual_approval", policy.as_dict())

        gate = policy.execution_gate("paper")
        self.assertTrue(gate["allowed"])
        with self.assertRaises(ValueError):
            policy.execution_gate("live")

    def test_dashboard_server_can_serve_api_and_static_payload(self):
        server = DashboardServer()
        payload = server.dashboard_payload()
        self.assertIn("market_data", payload)
        self.assertIn("status", payload)
        self.assertIn("generated_by", payload)
        self.assertEqual(server.api_route(), "/api/dashboard")
        self.assertTrue(server.static_index_exists())
        self.assertTrue((Path(server.static_root) / "favicon.svg").is_file())
        self.assertTrue(server.static_root.endswith("frontend"))

    def test_dashboard_health_endpoint_reports_state_store_readiness(self):
        server = DashboardServer()
        self.assertEqual(server.health_route(), "/api/health")
        httpd = server.create_server(host="127.0.0.1", port=0, logger=logging.getLogger("trade_agent.tests"))
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{httpd.server_address[1]}/api/health"
            with urllib.request.urlopen(url, timeout=5) as response:
                payload = json.loads(response.read().decode("utf-8"))
                self.assertEqual(response.status, 200)
        finally:
            httpd.shutdown()
            httpd.server_close()
            thread.join(timeout=5)
        self.assertEqual(payload["status"], "ready")
        self.assertTrue(payload["storage"]["ready"])
        self.assertIn("uptime_seconds", payload)

    def test_startup_retry_recovers_transient_errors_and_then_fails_cleanly(self):
        logger = logging.getLogger("trade_agent.tests.startup")
        attempts = {"count": 0}

        def flaky():
            attempts["count"] += 1
            if attempts["count"] < 3:
                raise OSError("state store not ready")
            return "ready"

        self.assertEqual(
            retry_call(flaky, label="state store", logger=logger, attempts=5, delay=0, timeout=5),
            "ready",
        )
        self.assertEqual(attempts["count"], 3)

        def broken():
            raise OSError("state store locked")

        with self.assertRaises(StartupError):
            retry_call(broken, label="state store", logger=logger, attempts=2, delay=0, timeout=5)

    def test_public_market_data_provider_handles_missing_symbol_column(self):
        market_df = MarketDataProvider(symbol="MSFT", periods=12).get_market_data().drop(columns=["symbol"])
        csv_path = os.path.join(os.getcwd(), "tmp_missing_symbol.csv")
        market_df.to_csv(csv_path, index=False)
        try:
            data = FreePublicMarketDataProvider(symbol="TSLA", csv_path=csv_path).get_market_data()
            self.assertIn("symbol", data.columns)
            self.assertTrue((data["symbol"] == "TSLA").all())
            self.assertIn("close", data.columns)
        finally:
            if os.path.exists(csv_path):
                os.remove(csv_path)

    def test_multi_layer_agent_run_returns_documented_layers(self):
        agent = MultiLayerTradeAgent(account_equity=100_000, proposal_capital=5_000)
        result = agent.run()

        self.assertIn("market_data_rows", result)
        self.assertIn("signal", result)
        self.assertIn("risk", result)
        self.assertIn("trade", result)
        self.assertTrue(result["execution_simulation"]["simulated"])
        self.assertFalse(result["execution_simulation"]["allow_live"])
        self.assertIn("learning_entries", result["review"])

    def test_multi_layer_agent_refuses_live_mode_without_policy_approval(self):
        config = AgentConfig(
            mode="live",
            allow_live=True,
            account_id="personal-primary",
            paper_only=False,
        )
        with patch.dict(os.environ, {}, clear=True):
            agent = MultiLayerTradeAgent(config=config)
            with self.assertRaisesRegex(ValueError, "broker credentials"):
                agent.run()

    def test_environment_policy_rejects_invalid_switch_and_conflicting_approval_flags(self):
        with self.assertRaisesRegex(ValueError, "TRADE_AGENT_KILL_SWITCH"):
            EnvironmentPolicy({"TRADE_AGENT_KILL_SWITCH": "enabled"})
        with self.assertRaisesRegex(ValueError, "conflicts"):
            AgentConfig.from_env({
                "TRADE_AGENT_REQUIRE_MANUAL_APPROVAL": "true",
                "TRADE_AGENT_MANUAL_APPROVAL": "false",
            })

    def test_production_readiness_gate_requires_explicit_live_action_context(self):
        gate = ProductionReadinessGate(
            mode="live",
            allow_live=True,
            account_id="personal-primary",
            api_key_env="TEST_API_KEY",
            secret_key_env="TEST_SECRET_KEY",
        )
        with patch.dict(os.environ, {"TEST_API_KEY": "key", "TEST_SECRET_KEY": "secret"}, clear=True):
            with self.assertRaisesRegex(ValueError, "explicit account_id on each action"):
                gate.validate(manual_approval=True)
            result = gate.validate(account_id="personal-primary", manual_approval=True)
        self.assertEqual(result["status"], "live_ready")
        self.assertTrue(result["live_execution_available"])
        self.assertEqual(result["account_id"], "personal-primary")

    def test_cli_requires_account_id_and_credentials_before_live_execution(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "explicit account_id"):
                run_cli(["--mode", "live"])
            with self.assertRaisesRegex(ValueError, "backtest mode is not implemented"):
                run_cli(["--mode", "backtest"])

        # A fully configured live run fails closed while broker credentials are absent.
        live_environment = {
            "TRADE_AGENT_MODE": "live",
            "TRADE_AGENT_ALLOW_LIVE": "true",
            "TRADE_AGENT_ACCOUNT_ID": "personal-primary",
            "TRADE_AGENT_REQUIRE_MANUAL_APPROVAL": "true",
        }
        with patch.dict(os.environ, live_environment, clear=True):
            with self.assertRaisesRegex(ValueError, "broker credentials"):
                run_cli([])

    def test_dashboard_switches_workflow_to_live_only_with_confirmed_settings(self):
        api = DashboardAPI()
        live_environment = {
            "TRADE_AGENT_MODE": "paper",
            "TRADE_AGENT_ALLOW_LIVE": "true",
            "TRADE_AGENT_ACCOUNT_ID": "personal-primary",
            "TRADE_AGENT_REQUIRE_MANUAL_APPROVAL": "true",
            "ALPACA_API_KEY": "paper-key",
            "ALPACA_SECRET_KEY": "paper-secret",
        }
        with patch.dict(os.environ, live_environment, clear=True):
            settings = api.update_settings({"mode": "live", "require_manual_approval": True})
            self.assertEqual(settings["mode"], "live")
            self.assertEqual(api.orchestrator.agent.config.mode, "live")
            self.assertFalse(api.orchestrator.agent.config.paper_only)
            self.assertIsInstance(api.orchestrator.agent.execution_agent, LiveExecutionAgent)
            with self.assertRaisesRegex(ValueError, "manual approval"):
                api.update_settings({"mode": "live", "require_manual_approval": False})
            with self.assertRaisesRegex(ValueError, "JSON booleans"):
                api.update_settings({"mode": "paper", "kill_switch": "false"})

        # Live mode is refused outright when the environment does not allow it.
        with patch.dict(os.environ, {**live_environment, "TRADE_AGENT_ALLOW_LIVE": "false"}, clear=True):
            with self.assertRaisesRegex(ValueError, "TRADE_AGENT_ALLOW_LIVE"):
                api.update_settings({"mode": "live", "require_manual_approval": True})

    def test_paper_broker_and_live_adapter_fail_closed(self):
        with self.assertRaisesRegex(ValueError, "only supports paper mode"):
            PaperBrokerAdapter(mode="live")
        adapter = LiveBrokerAdapter()
        order = Order(symbol="AAPL", side="BUY", quantity=1, price=100.0)
        with self.assertRaises(ValueError):
            adapter.place(order, risk_approved=True, account_id="personal-primary", manual_approval=True)


if __name__ == "__main__":
    unittest.main()
