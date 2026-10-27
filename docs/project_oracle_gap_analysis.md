# Project Oracle Gap Analysis

## UAEP-to-ORACLE context

This repository is not just a trading assistant. It is a scaffold for a broader institutional operating architecture that mirrors the UAEP concept:

- objective and execution gates
- specialized expert roles
- structured reasoning and planning
- delegated work products and handoffs
- validation and learning loops
- governance, authority, and auditability

ORACLE is the concrete institutional implementation of that architecture, with finance and trading as the first proving ground. The immediate codebase is deliberately narrow and safe, but the conceptual design reaches much farther: a governed multi-agent operating system that can reason, decide, act, validate, and improve within an explicit account and policy boundary over time.

## What the repository already has

The workspace already contains the early foundations for a multi-layer trading system:

- configuration and environment contract in `trade_agent/config.py`
- broker abstraction with paper and live adapters in `trade_agent/broker.py`
- risk, security, and production-readiness gates in `trade_agent/security.py`
- synthetic and CSV OHLCV data providers in `trade_agent/data.py`
- a market service wrapper in `trade_agent/market_service.py`
- a simulator and strategy/risk/portfoliopattern in `trade_agent/agent.py`, `trade_agent/risk.py`, `trade_agent/portfolio.py`, and `trade_agent/strategy.py`

This means the repo is already organized around the same architectural idea used in the system image: market data, strategy, risk, portfolio, and execution.

## What is still missing from the image-level Oracle architecture

The current codebase does not yet implement the full image-style Oracle architecture:

1. Seven-agent role network
   - There is no real seven-agent pipeline with distinct specialists and event handoff.
   - The code has services and adapters, but not a coordinated agent mesh.

2. News, social, and event intelligence
   - The data layer is price and OHLCV-only, with a sample CSV path and a free public provider abstraction.
   - There is no news, social, earnings, macro, or sentiment intelligence feed.

3. Knowledge graph and memory
   - No persistent graph of entities, relationships, and learned trade-relevant links exists.
   - No long-term memory model for learned strategies or event associations.

4. Research and strategy generation engine
   - Strategy generation is simple and deterministic from technical signal rules.
   - There is no explicit research agent, signal ranking engine, or multi-factor scoring framework.

5. Adaptive learning loop
   - The code has testing, backtesting, and report services, but no real adaptive policy memory loop.
   - There is no training feedback mechanism that updates signal weights, watchlist priorities, or risk thresholds over time.

6. Production execution integration
   - The code has a `LiveBrokerAdapter` contract and a readiness gate, but no real configured broker adapter with Alpaca, Coinbase, or an exchange exchange contract.
   - No live data or broker credential contract has been integrated.

7. Full portfolio intelligence
   - The repo has portfolio planning, risk, security, and monitoring services, but no full cross-market asset class orchestration for stocks and crypto under a common objective.

8. Agent-to-agent output contract
   - There is no formal shared event schema that every agent writes to and every downstream agent reads, with confidence, assumptions, and evidence attached.

## What still needs to be chosen before live execution

The repository is an architecture scaffold, not a live-ready trading engine. The next requirements that are still needed are:

1. Broker/exchange target
   - Choose the real broker or exchange, such as Alpaca for equities and a compatible crypto venue.

2. Credential environment contract
   - Decide the credential mapping, such as `TRADE_AGENT_API_KEY` and `TRADE_AGENT_API_KEY_ENV` or a broker-specific mapping.

3. Stock and crypto market-data source
   - Choose a real stock data provider and a real crypto data provider.

4. Execution routing and order model
   - Decide how equity orders and crypto orders are placed and how fees, spreads, and slippage are represented.

5. Real safety and policy rules
   - Define max drawdown, max loss, max position size, fees, slippage, and kill-switch rules.

6. Live gate approval path
   - Confirm the environment contract for `TRADE_AGENT_MODE`, `TRADE_AGENT_ALLOW_LIVE`, and the broker credential variable.

7. Performance and learning store
   - Choose a persistent log and knowledge store for the agent network to improve over time.

8. Success target
   - Decide the portfolio return target after fees, such as a 20% monthly aspiration or a lower confidence target.

## Recommended next architecture step

Build the repo toward a seven-agent moat:

1. Data Layer Agent
2. Stock Opening Movement Agent
3. Stock Continuation Agent
4. Crypto 24/7 Agent
5. News/Social/Event Agent
6. Risk and Portfolio Agent
7. Execution and Learning Agent

Each agent should emit a standardized event, and the Risk and Portfolio Agent should be the hard gate for whether an event reaches the Execution Agent.

## Next prompt

Choose a real broker or exchange and provide the corresponding credential variable naming and environment contract.
