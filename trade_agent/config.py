from __future__ import annotations

import math
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass


def parse_environment_bool(environ: Mapping[str, str], name: str, default: bool) -> bool:
    raw = environ.get(name)
    if raw is None:
        return default
    value = raw.strip().lower()
    if value == "true":
        return True
    if value == "false":
        return False
    raise ValueError(f"{name} must be either 'true' or 'false'; received {raw!r}.")


def _parse_environment_float(environ: Mapping[str, str], name: str, default: float) -> float:
    raw = environ.get(name)
    try:
        value = float(raw) if raw is not None else float(default)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite number; received {raw!r}.") from exc
    if not math.isfinite(value):
        raise ValueError(f"{name} must be a finite number; received {raw!r}.")
    return value


def _validate_environment_name(name: str, field_name: str) -> str:
    if not isinstance(name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name.strip()):
        raise ValueError(f"{field_name} must be a valid environment variable name.")
    return name.strip()


@dataclass
class AgentConfig:
    """Static project configuration values for the demo agent.

    The software is intentionally configured toward a paper-first default to
    keep the repository safe and testable. Real live execution is represented
    by an explicit opt-in path that must not be enabled by default.
    """

    symbol: str = "AAPL"
    account_equity: float = 100_000.0
    proposal_capital: float = 5_000.0
    max_position_size: float = 1.0
    max_daily_loss: float = 0.02
    lookback_fast: int = 12
    lookback_slow: int = 30
    volatility_window: int = 24
    mode: str = "paper"
    allow_live: bool = False
    broker: str = "alpaca"
    api_key_env: str = "ALPACA_API_KEY"
    secret_key_env: str = "ALPACA_SECRET_KEY"
    account_id: str = ""
    manual_approval_required: bool = True
    per_account_risk_budget: float = 1.0
    paper_only: bool | None = None
    kill_switch: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.mode, str):
            raise ValueError("mode (TRADE_AGENT_MODE) must be either 'paper' or 'live'.")
        self.mode = self.mode.strip().lower()
        if self.mode not in {"paper", "live"}:
            raise ValueError("mode (TRADE_AGENT_MODE) must be either 'paper' or 'live'; unsupported execution mode.")
        if type(self.allow_live) is not bool:
            raise ValueError("allow_live must be a boolean; use explicit true or false configuration.")
        if type(self.manual_approval_required) is not bool:
            raise ValueError("manual_approval_required must be a boolean.")
        if type(self.kill_switch) is not bool:
            raise ValueError("kill_switch must be a boolean.")

        if not isinstance(self.symbol, str) or not self.symbol.strip():
            raise ValueError("symbol must be a non-empty string.")
        self.symbol = self.symbol.strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{1,10}(?:-[A-Z0-9]{1,10})?", self.symbol):
            raise ValueError(f"Unsupported symbol format: {self.symbol!r}.")
        self.broker = str(self.broker).strip().lower()
        if not self.broker:
            raise ValueError("broker must be a non-empty identifier.")
        self.api_key_env = _validate_environment_name(self.api_key_env, "api_key_env")
        self.secret_key_env = _validate_environment_name(self.secret_key_env, "secret_key_env")
        if not isinstance(self.account_id, str):
            raise ValueError("account_id must be a string.")
        self.account_id = self.account_id.strip()

        numeric_limits = {
            "account_equity": (self.account_equity, 0.0, None, False),
            "proposal_capital": (self.proposal_capital, 0.0, None, False),
            "max_position_size": (self.max_position_size, 0.0, 1.0, True),
            "max_daily_loss": (self.max_daily_loss, 0.0, 1.0, True),
            "per_account_risk_budget": (self.per_account_risk_budget, 0.0, 1.0, True),
        }
        for name, (raw_value, minimum, maximum, inclusive_minimum) in numeric_limits.items():
            try:
                value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be a finite number within its allowed range.") from exc
            below_minimum = value < minimum or (value == minimum and not inclusive_minimum)
            if not math.isfinite(value) or below_minimum or (maximum is not None and value > maximum):
                comparator = "greater than zero" if not inclusive_minimum else f"at least {minimum}"
                if maximum is not None:
                    comparator += f" and at most {maximum}"
                raise ValueError(f"{name} must be finite, {comparator}.")
            setattr(self, name, value)

        for name in ("lookback_fast", "lookback_slow", "volatility_window"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer.")

        if self.paper_only is None:
            self.paper_only = self.mode == "paper"
        elif type(self.paper_only) is not bool:
            raise ValueError("paper_only must be a boolean.")
        if self.mode == "paper" and not self.paper_only:
            raise ValueError("paper mode must keep paper_only enabled.")
        if self.mode == "live":
            if not self.allow_live:
                raise ValueError("Live mode requires explicit opt-in with TRADE_AGENT_ALLOW_LIVE=true.")
            if self.paper_only:
                raise ValueError("Live mode conflicts with paper_only=true; explicitly configure a live policy.")
            if not self.account_id:
                raise ValueError("Live mode requires an explicit account_id (TRADE_AGENT_ACCOUNT_ID).")
            if not self.manual_approval_required:
                raise ValueError("Live mode requires manual approval to remain enabled.")
            if self.broker != "alpaca":
                raise ValueError(f"Live execution is unsupported for broker {self.broker!r}.")

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "AgentConfig":
        source = os.environ if environ is None else environ
        mode = source.get("TRADE_AGENT_MODE", "paper").strip().lower()
        allow_live = parse_environment_bool(source, "TRADE_AGENT_ALLOW_LIVE", False)
        broker = source.get("TRADE_AGENT_BROKER", "alpaca").strip().lower()
        api_key_env = source.get("TRADE_AGENT_API_KEY_ENV", "ALPACA_API_KEY")
        secret_key_env = source.get("TRADE_AGENT_SECRET_KEY_ENV", "ALPACA_SECRET_KEY")
        account_id = source.get("TRADE_AGENT_ACCOUNT_ID", "")

        approval_name = "TRADE_AGENT_REQUIRE_MANUAL_APPROVAL"
        legacy_approval_name = "TRADE_AGENT_MANUAL_APPROVAL"
        if approval_name in source and legacy_approval_name in source:
            canonical_approval = parse_environment_bool(source, approval_name, True)
            legacy_approval = parse_environment_bool(source, legacy_approval_name, True)
            if canonical_approval != legacy_approval:
                raise ValueError(
                    f"{approval_name} conflicts with legacy {legacy_approval_name}; remove the conflicting setting."
                )
        manual_approval_required = parse_environment_bool(
            source,
            approval_name if approval_name in source else legacy_approval_name,
            True,
        )
        return cls(
            mode=mode,
            allow_live=allow_live,
            broker=broker,
            api_key_env=api_key_env,
            secret_key_env=secret_key_env,
            account_id=account_id,
            manual_approval_required=manual_approval_required,
            per_account_risk_budget=_parse_environment_float(source, "TRADE_AGENT_PER_ACCOUNT_RISK_BUDGET", 1.0),
            account_equity=_parse_environment_float(source, "TRADE_AGENT_ACCOUNT_EQUITY", 100_000.0),
            proposal_capital=_parse_environment_float(source, "TRADE_AGENT_PROPOSAL_CAPITAL", 5_000.0),
            max_position_size=_parse_environment_float(source, "TRADE_AGENT_MAX_POSITION_SIZE", 1.0),
            max_daily_loss=_parse_environment_float(source, "TRADE_AGENT_MAX_DAILY_LOSS", 0.02),
            paper_only=mode == "paper",
            kill_switch=parse_environment_bool(source, "TRADE_AGENT_KILL_SWITCH", False),
        )
