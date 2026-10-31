from __future__ import annotations

import os
import math
import re


class ProductionPolicy:
    """Production-readiness policy container for the trade agent.

    This enforces an institutional operating model where live execution is
    only permitted under explicit account identity, credentials, and approval
    governance. Manual approval remains a required control for high-level
    operational use, even though the underlying system can still run in paper
    mode for research and validation.
    """

    def __init__(
        self,
        mode: str = "paper",
        allow_live: bool = False,
        require_manual_approval: bool = True,
        max_daily_loss: float = 0.02,
        api_key_env: str = "ALPACA_API_KEY",
        secret_key_env: str = "ALPACA_SECRET_KEY",
        broker: str = "alpaca",
        account_id: str = "",
        per_account_risk_budget: float = 1.0,
    ):
        if not isinstance(mode, str) or mode.strip().lower() not in {"paper", "live"}:
            raise ValueError("mode must be either 'paper' or 'live'.")
        if type(allow_live) is not bool:
            raise ValueError("allow_live must be a boolean; use explicit true or false configuration.")
        if type(require_manual_approval) is not bool:
            raise ValueError("require_manual_approval must be a boolean.")
        if not isinstance(api_key_env, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", api_key_env.strip()):
            raise ValueError("api_key_env must be a valid environment variable name.")
        if not isinstance(secret_key_env, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", secret_key_env.strip()):
            raise ValueError("secret_key_env must be a valid environment variable name.")
        try:
            max_daily_loss = float(max_daily_loss)
            per_account_risk_budget = float(per_account_risk_budget)
        except (TypeError, ValueError) as exc:
            raise ValueError("Risk limits must be finite numbers within their allowed ranges.") from exc
        if not math.isfinite(max_daily_loss) or not 0.0 <= max_daily_loss <= 1.0:
            raise ValueError("max_daily_loss must be finite and between 0.0 and 1.0.")
        if not math.isfinite(per_account_risk_budget) or not 0.0 <= per_account_risk_budget <= 1.0:
            raise ValueError("per_account_risk_budget must be finite and between 0.0 and 1.0.")
        if not isinstance(account_id, str):
            raise ValueError("account_id must be a string.")

        self.mode = mode.strip().lower()
        self.allow_live = allow_live
        self.require_manual_approval = require_manual_approval
        self.max_daily_loss = max_daily_loss
        self.api_key_env = api_key_env.strip()
        self.secret_key_env = secret_key_env.strip()
        self.broker = str(broker).strip().lower()
        if not self.broker:
            raise ValueError("broker must be a non-empty identifier.")
        self.account_id = account_id.strip()
        self.per_account_risk_budget = per_account_risk_budget

    def _check_live_credentials(self) -> None:
        if self.broker != "alpaca":
            raise ValueError(f"Unsupported broker target for live execution: {self.broker}")
        if not self.account_id or not str(self.account_id).strip():
            raise ValueError("Live execution requires an explicit account_id for the personal brokerage account.")
        api_key = os.getenv(self.api_key_env, "").strip()
        secret_key = os.getenv(self.secret_key_env, "").strip()
        missing = [name for name, value in ((self.api_key_env, api_key), (self.secret_key_env, secret_key)) if not value]
        if missing:
            raise ValueError(f"Live execution requires non-empty broker credentials: {', '.join(missing)}.")

    def execution_gate(self, mode: str, account_id: str | None = None, manual_approval: bool = False) -> dict:
        if not isinstance(mode, str):
            raise ValueError("Execution mode must be either 'paper' or 'live'.")
        mode = mode.strip().lower()

        if mode == "paper":
            return {
                "allowed": True,
                "reason": "paper execution is enabled",
                "manual_approval": self.require_manual_approval,
                "approval_status": "paper",
                "broker": self.broker,
                "account_id": self.account_id,
                "per_account_risk_budget": self.per_account_risk_budget,
            }
        if mode == "live":
            if not self.allow_live:
                raise ValueError("Live execution is blocked until the production policy explicitly enables it.")
            self._check_live_credentials()
            if not self.account_id:
                raise ValueError("Live execution requires an explicitly configured account_id.")
            if not isinstance(account_id, str) or not account_id.strip():
                raise ValueError("Live execution requires an explicit account_id on each action.")
            requested_account_id = account_id.strip()
            if requested_account_id != self.account_id:
                raise ValueError("Live execution account does not match the configured personal brokerage account.")
            if manual_approval is not True:
                raise ValueError("Live execution requires an explicit manual approval signal under the institutional policy.")
            return {
                "allowed": True,
                "reason": "live execution gate passed",
                "manual_approval": True,
                "approval_status": "approved",
                "broker": self.broker,
                "account_id": self.account_id,
                "per_account_risk_budget": self.per_account_risk_budget,
            }
        raise ValueError(f"Unsupported execution mode: {mode}")

    def as_dict(self) -> dict:
        return {
            "mode": self.mode,
            "allow_live": self.allow_live,
            "require_manual_approval": self.require_manual_approval,
            "max_daily_loss": self.max_daily_loss,
            "manual_approval": self.require_manual_approval,
            "broker": self.broker,
            "account_id": self.account_id,
            "per_account_risk_budget": self.per_account_risk_budget,
            "api_key_env": self.api_key_env,
            "secret_key_env": self.secret_key_env,
        }
