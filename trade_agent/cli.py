from __future__ import annotations

import argparse
from dataclasses import replace
import json

from .agent import MultiLayerTradeAgent
from .config import AgentConfig
from .orchestration import AgentOrchestrator


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Multi-layer trade agent")
    parser.add_argument("--symbol", default="AAPL")
    parser.add_argument("--mode", default=None, choices=["paper", "backtest", "live"])
    parser.add_argument("--strategy", default="trend")
    parser.add_argument("--equity", type=float, default=100_000.0)
    parser.add_argument("--capital", type=float, default=5_000.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)
    config = AgentConfig.from_env()
    requested_mode = args.mode or config.mode
    if requested_mode == "backtest":
        raise ValueError("The CLI backtest mode is not implemented; use Backtester directly.")
    if args.strategy != "trend":
        raise ValueError(f"Unsupported CLI strategy {args.strategy!r}; only 'trend' is available.")
    if requested_mode == "live":
        config = replace(
            config,
            mode="live",
            paper_only=False,
            allow_live=True,
            symbol=args.symbol or config.symbol,
            account_equity=config.account_equity if args.equity is None else args.equity,
            proposal_capital=config.proposal_capital if args.capital is None else args.capital,
        )
    else:
        config = replace(
            config,
            mode="paper",
            paper_only=True,
            symbol=args.symbol or config.symbol,
            account_equity=config.account_equity if args.equity is None else args.equity,
            proposal_capital=config.proposal_capital if args.capital is None else args.capital,
        )
    result = AgentOrchestrator(agent=MultiLayerTradeAgent(config=config)).run()
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
