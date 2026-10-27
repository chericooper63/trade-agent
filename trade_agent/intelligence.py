from __future__ import annotations

from .advisor import AdvisorFilter
from .alpha import AlphaAgentRegistry
from .data import CSVMarketDataProvider
from .policy import ProductionPolicy
from .portfolio import PortfolioManager
from .regime import RegimeDetector
from .research import ResearchAgent
from .review import ReviewAgent
from .risk import RiskManager
from .scanner import MarketScanner
from .strategy import TechnicalSignalGenerator
from .storage import RunStorage
from .team import LearningJournal, build_default_team


class IntelligenceModel:
    """Compose the internal intelligence and safety model as one repository contract.

    This model intentionally keeps the project’s intelligence in-repo:
    - market data to signal generation
    - alpha registry to aggregate signals
    - regime detector for macro context
    - advisor filter for the decision summary
    - research validation for candidate quality before risk decisions
    - production policy layer for safe execution gating
    """

    def __init__(
        self,
        provider=None,
        policy=None,
        scanner=None,
        account_equity: float = 100_000.0,
        proposal_capital: float = 5_000.0,
    ):
        self.provider = provider or CSVMarketDataProvider()
        self.policy = policy or ProductionPolicy()
        self.account_equity = float(account_equity)
        self.proposal_capital = float(proposal_capital)
        self.signal_generator = TechnicalSignalGenerator()
        self.alpha_registry = AlphaAgentRegistry()
        self.regime_detector = RegimeDetector()
        self.advisor_filter = AdvisorFilter()
        self.scanner = scanner or MarketScanner()
        self.research_agent = ResearchAgent(self.scanner)
        self.portfolio_manager = PortfolioManager()
        self.risk_manager = RiskManager(max_position_size=1.0, max_daily_loss=self.policy.max_daily_loss)
        self.learning_journal = LearningJournal(storage=RunStorage())
        self.review_agent = ReviewAgent(journal=self.learning_journal)
        self.team = build_default_team()

    def evaluate(self) -> dict:
        market_data = self.provider.get_market_data()
        signal = self.signal_generator.generate(market_data)
        alpha = self.alpha_registry.run(market_data)
        regime = self.regime_detector.detect(market_data)
        advice = self.advisor_filter.filter(alpha)
        market_scan = self.scanner.scan()
        scan_advice = self.advisor_filter.filter_candidates(market_scan)
        research = self.research_agent.evaluate(market_scan, self.account_equity, self.proposal_capital)

        decision_candidate = None
        if research.get("qualified"):
            decision_candidate = max(research["qualified"], key=lambda item: float(item.get("confidence", 0.0)))
        else:
            decision_candidate = scan_advice.get("candidate") or max(
                market_scan.get("actionable", []) or market_scan.get("candidates", []),
                key=lambda item: float(item.get("confidence", 0.0)),
                default=None,
            )

        if decision_candidate is None:
            portfolio = {
                "positions": {},
                "total_cash_used": 0.0,
                "risk_budget_used": 0.0,
                "cash_remaining": float(self.account_equity),
                "side": "HOLD",
                "cash_used": 0.0,
                "confidence": 0.0,
            }
            risk = {"approved": False, "reason": "No actionable research or market candidate", "position_size": 0.0}
            decision = {
                "approved": False,
                "reason": "No candidate passed research validation.",
                "selected_symbol": None,
                "signal": "HOLD",
                "confidence": 0.0,
            }
        else:
            candidate_pool = research.get("qualified") or market_scan.get("actionable") or market_scan.get("candidates") or []
            signals = {item["symbol"]: item.get("signal", "HOLD") for item in candidate_pool}
            confidences = {item["symbol"]: float(item.get("confidence", 0.0)) for item in candidate_pool}
            capital_map = {item["symbol"]: float(self.proposal_capital) for item in candidate_pool}

            if signals:
                portfolio = self.portfolio_manager.plan_portfolio(
                    signals,
                    confidences,
                    float(self.account_equity),
                    capital_map,
                )
                top_symbol = max(candidate_pool, key=lambda item: float(item.get("confidence", 0.0)))["symbol"]
                portfolio["side"] = str(portfolio["positions"].get(top_symbol, {}).get("signal", "HOLD"))
                portfolio["cash_used"] = float(portfolio.get("total_cash_used", 0.0))
                portfolio["cash_remaining"] = float(portfolio.get("cash_remaining", self.account_equity))
                portfolio["confidence"] = float(portfolio["positions"].get(top_symbol, {}).get("confidence", 0.0))
            else:
                portfolio = self.portfolio_manager.plan(
                    str(decision_candidate.get("signal", "HOLD")),
                    float(decision_candidate.get("confidence", 0.0)),
                    float(self.account_equity),
                    float(self.proposal_capital),
                )

            risk = self.risk_manager.evaluate(
                str(decision_candidate.get("signal", "HOLD")),
                float(decision_candidate.get("confidence", 0.0)),
                float(self.account_equity),
                float(self.proposal_capital),
            )
            risk["symbols"] = sorted(portfolio.get("positions", {}).keys())
            risk["budget_used"] = float(portfolio.get("risk_budget_used", 0.0))
            approved = bool(risk.get("approved")) and bool(research.get("qualified") or candidate_pool)
            decision = {
                "approved": approved,
                "reason": "Research-qualified candidates were used to drive the portfolio and risk check."
                if research.get("qualified")
                else "The highest-confidence actionable candidate was evaluated and allocated through the paper portfolio gate.",
                "selected_symbol": decision_candidate.get("symbol"),
                "signal": str(decision_candidate.get("signal", "HOLD")),
                "confidence": float(decision_candidate.get("confidence", 0.0)),
            }

        review_entries = []
        candidate_symbols = list(portfolio.get("positions", {}).keys()) or [decision.get("selected_symbol")] if decision.get("selected_symbol") else []
        for symbol in candidate_symbols:
            if not symbol:
                continue
            lesson = (
                "The paper review confirmed the selected candidate remained within the portfolio risk budget and execution safeguards."
                if risk.get("approved")
                else "The paper review identified that the decision should be skipped or re-scored before any next cycle."
            )
            outcome = {
                "status": "paper_reviewed",
                "approved": bool(risk.get("approved", False)),
                "cash_used": float(portfolio.get("cash_used", 0.0)),
                "symbol": symbol,
                "risk_budget_used": float(portfolio.get("risk_budget_used", 0.0)),
            }
            review_entries.append(
                self.learning_journal.record(
                    "portfolio_manager",
                    str(symbol),
                    {
                        "signal": dict(decision).get("signal", "HOLD"),
                        "confidence": float(dict(decision).get("confidence", 0.0)),
                        "approved": bool(decision.get("approved", False)),
                    },
                    outcome,
                    lesson,
                )
            )

        review_payload = {
            "entries": review_entries,
            "paper_mode": self.policy.mode == "paper",
            "allow_live": bool(self.policy.allow_live),
            "persisted": True,
        }

        review_feedback = self.review_agent.evaluate(portfolio, risk, decision)
        review_payload["risk_feedback"] = review_feedback
        review_payload["budget_exceeded"] = bool(review_feedback.get("budget_exceeded", False))
        review_payload["next_cycle_candidates"] = review_feedback.get("next_cycle_candidates", [])
        review_payload["down_ranked"] = review_feedback.get("down_ranked", [])

        return {
            "signal": signal,
            "alpha": alpha,
            "regime": regime,
            "advice": advice,
            "market_scan": market_scan,
            "scan_advice": scan_advice,
            "research": research,
            "portfolio": portfolio,
            "risk": risk,
            "decision": decision,
            "review": review_payload,
            "review_agent": review_feedback,
            "team": self.team.snapshot(),
            "policy": self.policy.as_dict(),
        }
