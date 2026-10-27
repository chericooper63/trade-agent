from __future__ import annotations

from .policy import ProductionPolicy


class SecurityManager:
    """Applies placeholder security and circuit-breaker checks before trading."""

    def __init__(self, max_position_size: float = 1.0):
        self.max_position_size = max_position_size

    def evaluate(self, signal: str, confidence: float, account_equity: float, proposed_capital: float) -> dict:
        if signal == "HOLD":
            return {"approved": False, "reason": "No trade signal", "halted": True}
        if confidence < 0.45:
            return {"approved": False, "reason": "Low confidence", "halted": False}
        if proposed_capital > account_equity * self.max_position_size:
            return {"approved": False, "reason": "Position exceeds security limit", "halted": False}
        return {"approved": True, "reason": "Security checks passed", "halted": False}


class ProductionReadinessGate:
    """Release gate enforcing a safe paper-first operating model.

    This repository is intentionally structured to keep real live execution
    behind an approval gate. The gate belongs in the security layer because
    it is a production control, not a trading signal.
    """

    def __init__(
        self,
        mode: str = "paper",
        allow_live: bool = False,
        *,
        policy: ProductionPolicy | None = None,
        account_id: str = "",
        manual_approval_required: bool = True,
        broker: str = "alpaca",
        api_key_env: str = "ALPACA_API_KEY",
        secret_key_env: str = "ALPACA_SECRET_KEY",
    ):
        self.policy = policy or ProductionPolicy(
            mode=mode,
            allow_live=allow_live,
            require_manual_approval=manual_approval_required,
            broker=broker,
            account_id=account_id,
            api_key_env=api_key_env,
            secret_key_env=secret_key_env,
        )
        self.mode = self.policy.mode
        self.allow_live = self.policy.allow_live

    def validate(self, account_id: str | None = None, manual_approval: bool = False) -> dict:
        gate = self.policy.execution_gate(
            self.mode,
            account_id=account_id,
            manual_approval=manual_approval,
        )
        if self.mode == "paper":
            return {
                "paper_mode": True,
                "allow_live": False,
                "status": "paper_ready",
                **gate,
            }
        return {
            "paper_mode": False,
            "allow_live": True,
            "status": "live_policy_validated_execution_unavailable",
            "live_execution_available": False,
            **gate,
        }
