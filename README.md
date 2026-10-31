# Trade Agent

A high-level institutional trading architecture prototype built in Python for experimentation, signal generation, portfolio planning, execution governance, and audit-ready operations.

This repository is intentionally structured as a safe, reviewable institutional operating model rather than a casual bot wrapper. The default setup is designed to run in paper mode and to block live execution unless opt-in safeguards, explicit account assignment, and governance approvals are in place.

## Project framing: UAEP and ORACLE

At the highest level, this project sits inside a broader operating architecture:

- UAEP (Universal AI Executive Operating Protocol) is the generalized framework for building reliable AI systems as operating processes rather than one-off chat responses.
- ORACLE is the concrete, personal-account implementation of that framework in the domain of autonomous trading.

The relationship is:

```text
                   UAEP
       Universal AI Operating Architecture
                         │
                         ▼
             General AI operating model
                         │
                         ├── objective setting
                         ├── context assembly
                         ├── expert coordination
                         ├── reasoning
                         ├── planning
                         ├── decision making
                         ├── execution
                         ├── validation
                         ├── improvement
                         └── delivery
                         │
                         ▼
                       ORACLE
      Institutional-grade multi-agent trading operating system
```

In other words, UAEP answers the architectural question: how should an AI system function as a governed, repeatable, auditable operating layer? ORACLE is a domain-specific application of that idea, focused on institutional-grade trading operations under explicit risk control, account governance, and execution constraints.

The system is intentionally designed to move away from the simplistic pattern of:

```text
User asks → AI answers
```

and toward a more structured loop:

```text
Objective → Context → Expertise → Reasoning → Planning → Decision → Execution → Validation → Improvement → Delivery
```

This is an operational architecture for intelligence, not just a prompt or a model wrapper.

## What this project includes

- Synthetic OHLCV market-data generation and CSV-backed data access
- Trend and volatility signal generation using simple technical heuristics
- Risk checks, position sizing, and portfolio allocation logic
- Paper execution simulation with broker abstraction patterns
- Backtesting and performance reporting
- Monitoring, decision auditing, and approval-state tracking
- A lightweight dashboard front end served locally
- Safety-focused configuration that keeps live trading disabled by default

## Current status

This is best described as an institutional operating architecture scaffold and paper-trading prototype. It includes the core layers of a trading system, but it is not a complete live broker-connected production engine and should not be treated as a ready-to-deploy investment system without further operational hardening.

## Architecture overview

The project follows a layered design:

1. Configuration and environment contract
   - `trade_agent/config.py`
   - Paper-first values and explicit live-mode gate checks

2. Market data layer
   - `trade_agent/data.py`
   - Generates synthetic price data or loads CSV market data

3. Signal generation layer
   - `trade_agent/strategy.py`
   - Produces `BUY`, `SELL`, or `HOLD` signals using trend and volatility heuristics

4. Portfolio and risk layer
   - `trade_agent/portfolio.py`
   - `trade_agent/risk.py`
   - `trade_agent/security.py`
   - Validates signal quality, exposure, and account limits

5. Execution layer
   - `trade_agent/broker.py`
   - `trade_agent/execution.py`
   - `trade_agent/orders.py`
   - Simulates order routing and paper fills

6. Observability and review layer
   - `trade_agent/monitoring.py`
   - `trade_agent/report.py`
   - `trade_agent/backtest.py`
   - Stores audit records, decision logs, and trade performance summaries

7. Dashboard and web UI
   - `frontend/`
   - `trade_agent/server.py`
   - `trade_agent/api.py`
   - Serves a local dashboard that reflects the current paper-trading snapshot

## Main project modules

- `trade_agent/agent.py` — main multi-layer orchestration agent
- `trade_agent/cli.py` — CLI entry point and demo runner
- `trade_agent/config.py` — configuration defaults and environment-based overrides
- `trade_agent/data.py` — providers for synthetic and CSV data
- `trade_agent/strategy.py` — signal generation and research scoring engine
- `trade_agent/risk.py` — risk gating and position sizing
- `trade_agent/portfolio.py` — capital allocation and multi-symbol budget logic
- `trade_agent/broker.py` — abstract broker contract with paper and live adapters
- `trade_agent/execution.py` — order execution service and simulation logic
- `trade_agent/backtest.py` — simple fairness-focused backtester
- `trade_agent/monitoring.py` — decision and approval workflows
- `trade_agent/team.py` — agent profile and learning journal scaffolding
- `trade_agent/security.py` — production readiness and safety gate checks
- `trade_agent/server.py` — local dashboard HTTP server
- `tests/test_trade_agent.py` — validation suite covering the trading workflow

## Repository structure

```text
trade-agent/
├── README.md
├── pyproject.toml
├── requirements.txt
├── docs/
│   ├── multi_layer_team_architecture.md
│   └── project_oracle_gap_analysis.md
├── frontend/
│   ├── app.js
│   ├── index.html
│   └── styles.css
├── tests/
│   └── test_trade_agent.py
├── trade_agent/
│   ├── __init__.py
│   ├── advisor.py
│   ├── agent.py
│   ├── alpha.py
│   ├── api.py
│   ├── backtest.py
│   ├── broker.py
│   ├── cli.py
│   ├── config.py
│   ├── data.py
│   ├── env.py
│   ├── events.py
│   ├── execution.py
│   ├── frontend.py
│   ├── intelligence.py
│   ├── knowledge_graph.py
│   ├── market_service.py
│   ├── monitoring.py
│   ├── orchestration.py
│   ├── orders.py
│   ├── performance.py
│   ├── policy.py
│   ├── portfolio.py
│   ├── regime.py
│   ├── report.py
│   ├── research.py
│   ├── risk.py
│   ├── sample_market_data.csv
│   ├── scanner.py
│   ├── security.py
│   ├── server.py
│   ├── storage.py
│   ├── strategy.py
│   └── team.py
└── trade_agent.egg-info/
```

## Prerequisites

- Python 3.10 or newer
- A virtual environment is recommended
- Internet access is only needed if you later add live provider or broker integrations

## Installation

From the project root:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m pip install -e .
```

## Quick start

### Run the CLI demo

```bash
python -m trade_agent.cli
```

Optional arguments:

```bash
python -m trade_agent.cli --symbol AAPL --mode paper --strategy trend --equity 100000 --capital 5000
```

The CLI prints a summary that includes:

- market data row count
- signal and confidence
- portfolio allocation summary
- risk approval result
- simulated execution result

Example output:

```text
Trade agent run summary
==================================================
Mode: paper
Strategy: trend
Symbol: AAPL
Rows of market data: 200
Signal: BUY
Confidence: 0.735
Signal reason: trend=1.00, volatility=0.0120, latest_return=0.0042
Portfolio: {'side': 'BUY', 'cash_used': 5000.0, 'cash_remaining': 95000.0, 'confidence': 0.735}
Risk: {'approved': True, 'reason': 'Risk constraints passed', 'position_size': 5000.0}
Trade: {'symbol': 'AAPL', 'side': 'BUY', 'quantity': 5000, 'price': 154.32, 'status': 'filled'}
```

## Run the local dashboard

The repository includes a lightweight HTTP dashboard and a local front-end shell.

```bash
python - <<'PY'
from trade_agent.server import DashboardServer
DashboardServer().start(host='127.0.0.1', port=8000)
PY
```

Then open http://127.0.0.1:8000 in a browser.

## Backtesting and evaluation

The project includes a backtester that evaluates simulated trade outcomes over generated or CSV-loaded market history.

```bash
python - <<'PY'
from trade_agent.backtest import Backtester
from trade_agent.data import CSVMarketDataProvider

report = Backtester(CSVMarketDataProvider()).run(100_000.0, 5_000.0)
print(report)
PY
```

Backtest output includes:

- total return
- net profit
- win rate
- profit factor
- max drawdown
- trade count
- paper readiness flag

## Safety model and gating

The repository intentionally enforces a safe default:

- live execution is disabled unless an explicit opt-in is set
- configuration defaults to paper mode and validates boolean/numeric environment values strictly
- live policy checks require explicit opt-in, account identity, both configured credentials, and per-action manual approval
- paper execution is supported; live broker submission is not implemented and fails closed
- the CLI and dashboard reject live execution instead of silently changing modes

Key configuration values are defined in `trade_agent/config.py` and can be overridden through environment variables.

### Environment variables

```bash
TRADE_AGENT_MODE=paper
TRADE_AGENT_ALLOW_LIVE=false
TRADE_AGENT_BROKER=alpaca
TRADE_AGENT_REQUIRE_MANUAL_APPROVAL=true
TRADE_AGENT_API_KEY_ENV=ALPACA_API_KEY
TRADE_AGENT_SECRET_KEY_ENV=ALPACA_SECRET_KEY
TRADE_AGENT_ACCOUNT_ID=
TRADE_AGENT_PER_ACCOUNT_RISK_BUDGET=1.0
TRADE_AGENT_ACCOUNT_EQUITY=100000.0
TRADE_AGENT_PROPOSAL_CAPITAL=5000.0
TRADE_AGENT_MAX_POSITION_SIZE=1.0
TRADE_AGENT_MAX_DAILY_LOSS=0.02
```

Boolean environment values must be the literal `true` or `false` (case-insensitive). `TRADE_AGENT_MODE` accepts `paper` or `live`; selecting `live` is not sufficient to execute: live policy validation also requires `TRADE_AGENT_ALLOW_LIVE=true`, `TRADE_AGENT_BROKER=alpaca`, an explicit account ID, non-empty API key and secret values in the configured variables, and manual approval on each action. The live adapter currently refuses submission even after policy validation, so no live orders can be placed by this application.

## Testing

Run the repository test suite:

```bash
pytest -q
```

The current test suite covers:

- market data generation
- signal generation validity
- researcher scoring outputs
- risk approval and rejection behavior
- portfolio sizing and budget enforcement
- backtest result structure
- monitoring and decision audit flows
- storage history persistence
- paper-first safety gates

## Data sources and limitations

This project currently uses:

- synthetic OHLCV generation for demo runs
- a bundled sample CSV file for reproducible local experiments
- a free/public-provider abstraction that falls back to local data unless configured otherwise

It does not yet include:

- real broker connectivity
- live market-data subscriptions
- news or sentiment ingestion
- persistent knowledge graphs or long-term memory
- a full multi-agent team doing structured transitive decision handoffs
- enterprise-grade production deployment or compliance controls

## Documentation

Additional project documentation lives in the `docs/` directory:

- `docs/multi_layer_team_architecture.md` — intended multi-agent architecture and role boundaries
- `docs/project_oracle_gap_analysis.md` — roadmap and gap analysis between the scaffold and a more advanced oracle-style system
- `docs/architecture_baseline.md` — evidence-based implementation baseline and staged roadmap

## Typical development workflow

1. Create a virtual environment.
2. Install the project dependencies.
3. Run the CLI demo to inspect a sample decision.
4. Review the portfolio and risk summary.
5. Run the backtester on CSV or generated market data.
6. Inspect the dashboard payload and audit logs.
7. Add or modify strategy logic while keeping the paper-first safety model intact.

## Recommended next steps

If you want to evolve this repository beyond the prototype stage, the natural next steps are:

- add a real market-data provider
- wire a broker integration behind explicit credentials
- replace heuristic signals with a data-driven or ML-based model
- add persistent storage and learning loops
- define stronger risk and operational controls for live execution
- expand the agent team into specialized roles with formal handoff contracts

## License

This project is provided as a local research and demo repository. Review the repository’s licensing details before production or commercial use.

## Summary

Trade Agent is a safe-by-default research prototype for exploring multi-layer algorithmic trading decisions in a controlled environment. It is designed to be extended, audited, and improved without exposing the system to accidental live execution.
