from __future__ import annotations

import os
from collections.abc import Mapping

from .config import AgentConfig, parse_environment_bool


class EnvironmentPolicy:
    """Read environment-driven defaults for a production-safe execution config.

    This loader is intentionally passive. It never writes live credentials.
    It simply reads a safe environment contract already declared in .env.example
    and gives the package a single, testable configuration boundary.
    """

    def __init__(self, environ: Mapping[str, str] | None = None):
        source = os.environ if environ is None else environ
        config = AgentConfig.from_env(source)
        self.mode = config.mode
        self.allow_live = config.allow_live
        self.broker = config.broker
        self.api_key_env = config.api_key_env
        self.secret_key_env = config.secret_key_env
        self.account_id = config.account_id
        self.account_equity = config.account_equity
        self.proposal_capital = config.proposal_capital
        self.max_position_size = config.max_position_size
        self.max_daily_loss = config.max_daily_loss
        self.require_manual_approval = config.manual_approval_required
        self.kill_switch = parse_environment_bool(source, "TRADE_AGENT_KILL_SWITCH", False)

    def summary(self) -> dict:
        return {
            "mode": self.mode,
            "allow_live": self.allow_live,
            "broker": self.broker,
            "api_key_env": self.api_key_env,
            "secret_key_env": self.secret_key_env,
            "account_id_set": bool(self.account_id),
            "account_equity": self.account_equity,
            "proposal_capital": self.proposal_capital,
            "max_position_size": self.max_position_size,
            "max_daily_loss": self.max_daily_loss,
            "require_manual_approval": self.require_manual_approval,
            "kill_switch": self.kill_switch,
        }
