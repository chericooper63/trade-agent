from __future__ import annotations

import pandas as pd

from .strategy import TechnicalSignalGenerator


class Backtester:
    """Evaluate one-bar strategy trades with conservative execution costs."""

    def __init__(
        self,
        provider,
        strategy=None,
        fee_bps: float = 5.0,
        slippage_bps: float = 5.0,
        min_trades: int = 5,
        max_drawdown_pct: float = 10.0,
    ):
        self.provider = provider
        self.strategy = strategy or TechnicalSignalGenerator()
        self.fee_bps = float(fee_bps)
        self.slippage_bps = float(slippage_bps)
        self.min_trades = int(min_trades)
        self.max_drawdown_pct = float(max_drawdown_pct)

    def run(self, account_equity: float, proposed_capital: float) -> dict:
        if account_equity <= 0 or proposed_capital <= 0:
            raise ValueError("Account equity and proposed capital must be positive.")
        if self.fee_bps < 0 or self.slippage_bps < 0 or self.min_trades < 1 or self.max_drawdown_pct < 0:
            raise ValueError("Backtest costs, trade minimum, and drawdown limit must be valid.")

        market_data = self.provider.get_market_data()
        if not isinstance(market_data, pd.DataFrame) or market_data.empty:
            return self._empty_report()

        closes = market_data["close"].astype(float).reset_index(drop=True)
        if len(closes) < 2:
            return self._empty_report(len(closes))

        cost_rate = 2.0 * (self.fee_bps + self.slippage_bps) / 10_000.0
        trade_pnl = []
        for entry_index in range(1, len(closes) - 1):
            signal = self.strategy.generate(market_data.iloc[: entry_index + 1])
            side = signal.get("signal")
            if side not in {"BUY", "SELL"}:
                continue

            direction = 1.0 if side == "BUY" else -1.0
            gross_return = direction * (closes.iloc[entry_index + 1] / closes.iloc[entry_index] - 1.0)
            trade_pnl.append(float(proposed_capital * (gross_return - cost_rate)))

        equity_curve = [float(account_equity)]
        for pnl in trade_pnl:
            equity_curve.append(equity_curve[-1] + pnl)

        curve = pd.Series(equity_curve, dtype=float)
        drawdown = curve / curve.cummax() - 1.0
        winning = [pnl for pnl in trade_pnl if pnl > 0]
        losing = [pnl for pnl in trade_pnl if pnl < 0]
        gross_profit = sum(winning)
        gross_loss = abs(sum(losing))
        final_equity = equity_curve[-1]
        profit_factor = float(gross_profit / gross_loss) if gross_loss else None
        report = {
            "total_return": float((final_equity / account_equity - 1.0) * 100),
            "net_profit": float(final_equity - account_equity),
            "win_rate": float(len(winning) / len(trade_pnl)) if trade_pnl else 0.0,
            "profit_factor": profit_factor,
            "max_drawdown": float(abs(drawdown.min()) * 100),
            "trades": len(trade_pnl),
            "costs": float(proposed_capital * cost_rate * len(trade_pnl)),
            "market_rows": len(market_data),
        }
        report["paper_ready"] = bool(
            report["trades"] >= self.min_trades
            and report["total_return"] > 0.0
            and report["max_drawdown"] <= self.max_drawdown_pct
        )
        return report

    @staticmethod
    def _empty_report(market_rows: int = 0) -> dict:
        return {
            "total_return": 0.0,
            "net_profit": 0.0,
            "win_rate": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "trades": 0,
            "costs": 0.0,
            "market_rows": market_rows,
            "paper_ready": False,
        }
