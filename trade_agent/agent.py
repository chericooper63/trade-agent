from __future__ import annotations

from .agents import DataAgent, ExecutionSimulationAgent, LearningAgent, PolicyAgent, StrategyAgent
from .config import AgentConfig
from .data import MarketDataProvider
from .research import ResearchAgent
from .scanner import MarketScanner
from .strategy import TechnicalSignalGenerator
from .risk import RiskManager
from .execution import SimulatedBroker
from .portfolio import PortfolioManager


class MultiLayerTradeAgent:
    """Coordinates data ingestion, signal generation, risk gating, portfolio planning, and execution."""

    def __init__(
        self,
        symbol: str = "AAPL",
        account_equity: float = 100_000.0,
        proposal_capital: float = 5_000.0,
        config: AgentConfig | None = None,
    ):
        self.config = config or AgentConfig(
            symbol=symbol,
            account_equity=account_equity,
            proposal_capital=proposal_capital,
        )
        self.symbol = self.config.symbol
        self.account_equity = self.config.account_equity
        self.proposal_capital = self.config.proposal_capital
        self.data_agent = DataAgent(symbol=self.symbol)
        self.market_data_provider = MarketDataProvider(symbol=self.symbol)
        self.signal_generator = TechnicalSignalGenerator()
        self.strategy_agent = StrategyAgent(self.signal_generator)
        self.scanner = MarketScanner(symbols=[self.symbol])
        self.research_agent = ResearchAgent(self.scanner)
        self.policy_agent = PolicyAgent(
            mode=self.config.mode,
            allow_live=self.config.allow_live,
            require_manual_approval=self.config.manual_approval_required,
            api_key_env=self.config.api_key_env,
            secret_key_env=self.config.secret_key_env,
            broker=self.config.broker,
            account_id=self.config.account_id,
            per_account_risk_budget=self.config.per_account_risk_budget,
        )
        self.risk_manager = RiskManager(
            max_position_size=self.config.max_position_size,
            max_daily_loss=self.config.max_daily_loss,
        )
        self.portfolio_manager = PortfolioManager()
        self.broker = SimulatedBroker(symbol=self.symbol)
        self.execution_agent = ExecutionSimulationAgent(self.broker)
        self.learning_agent = LearningAgent()

    def run(self) -> dict:
        from .orchestration import AgentOrchestrator

        return AgentOrchestrator(agent=self).run()
