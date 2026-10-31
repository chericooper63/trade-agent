from __future__ import annotations

from datetime import datetime, timezone


class MonitoringService:
    """Produce a structured monitoring log for agent decisions and audit records."""

    def __init__(self, storage=None):
        self.events = []
        self.storage = storage

    def _persist_audit_event(self, event_type: str, payload: dict) -> None:
        if self.storage is not None:
            self.storage.store_audit_event({"event_type": event_type, **payload})

    def build_log(self, signal: dict, risk: dict) -> dict:
        log = {
            "signal": signal.get("signal") if isinstance(signal, dict) else signal,
            "risk_approved": bool(risk.get("approved", False)) if isinstance(risk, dict) else bool(risk),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
        self.events.append(log)
        return log

    def build_decision_audit(self, signal: dict, risk: dict, account: dict | None = None) -> dict:
        manual_approval = account.get("manual_approval", False) if isinstance(account, dict) else False
        if type(manual_approval) is not bool:
            raise ValueError("manual_approval must be a boolean value.")
        mode = account.get("mode") if isinstance(account, dict) else None
        if mode is not None:
            if not isinstance(mode, str) or mode.strip().lower() not in {"paper", "live"}:
                raise ValueError("Execution audit mode must be either 'paper' or 'live'.")
            mode = mode.strip().lower()
        live_action = mode == "live"
        risk_approved = bool(risk.get("approved", False)) if isinstance(risk, dict) else bool(risk)
        portfolio_approved = bool(account.get("portfolio_approved", risk_approved)) if isinstance(account, dict) else risk_approved
        policy_approved = bool(account.get("policy_approved", True)) if isinstance(account, dict) else True
        approved = risk_approved and portfolio_approved and policy_approved
        approval_status = "pending" if manual_approval or live_action else "approved" if approved else "rejected"
        audit = {
            "signal": signal.get("signal") if isinstance(signal, dict) else signal,
            "confidence": float(signal.get("confidence", 0.0)) if isinstance(signal, dict) else 0.0,
            "reason": signal.get("reason") if isinstance(signal, dict) else "",
            "risk_approved": risk_approved,
            "portfolio_approved": portfolio_approved,
            "policy_approved": policy_approved,
            "position_size": float(risk.get("position_size", 0.0)) if isinstance(risk, dict) else 0.0,
            "risk_reason": risk.get("reason") if isinstance(risk, dict) else "",
            "account_id": account.get("account_id") if isinstance(account, dict) else None,
            "mode": mode,
            "manual_approval": manual_approval,
            "approval_status": approval_status,
            "approved_by": "paper_policy" if approval_status == "approved" and mode == "paper" else None,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "run_id": account.get("run_id") if isinstance(account, dict) else None,
        }
        self.events.append(audit)
        self._persist_audit_event("decision", {"audit": audit})
        return audit

    def approve_decision(self, audit: dict, account_id: str, approver: str) -> dict:
        if not account_id or not account_id.strip():
            raise ValueError("Approval requires an explicit account_id.")
        if audit.get("account_id") != account_id:
            raise ValueError("Approval account does not match the audited decision account.")
        if not approver or not approver.strip():
            raise ValueError("A non-empty approver is required.")
        if not audit.get("risk_approved", False):
            raise ValueError("A risk-rejected decision cannot be approved for execution.")
        if audit.get("mode") == "live" and audit.get("manual_approval") is not True:
            raise ValueError("Live execution requires explicit manual approval on the audited action.")
        if audit.get("approval_status") != "pending":
            raise ValueError("Only pending decisions can be approved.")

        approved = dict(audit)
        approved["approval_status"] = "approved"
        approved["approved_by"] = approver
        approved["timestamp"] = datetime.now(timezone.utc).isoformat()
        self.events.append(approved)
        self._persist_audit_event("approval", {"audit": approved})
        return approved

    def is_approved_for_execution(self, audit: dict, account_id: str) -> bool:
        return (
            audit.get("approval_status") == "approved"
            and audit.get("account_id") == account_id
            and bool(audit.get("risk_approved", False))
            and bool(audit.get("portfolio_approved", True))
            and bool(audit.get("policy_approved", True))
            and audit.get("signal") in {"BUY", "SELL"}
            and (
                audit.get("mode") == "paper"
                or (
                    audit.get("mode") == "live"
                    and audit.get("manual_approval") is True
                    and bool(audit.get("approved_by"))
                )
            )
        )
