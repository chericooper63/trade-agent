from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(frozen=True)
class AgentResult:
    """Normalized, serializable output from one specialist in a decision cycle."""

    agent_name: str
    role: str
    status: str
    confidence: float
    payload: dict[str, Any]
    evidence: dict[str, Any]
    reason: str
    timestamp: str
    run_id: str

    @classmethod
    def create(
        cls,
        *,
        agent_name: str,
        role: str,
        status: str,
        confidence: float,
        payload: dict[str, Any],
        evidence: dict[str, Any],
        reason: str = "",
        run_id: str,
    ) -> "AgentResult":
        return cls(
            agent_name=agent_name,
            role=role,
            status=status,
            confidence=float(confidence),
            payload=payload,
            evidence=evidence,
            reason=reason,
            timestamp=datetime.now(timezone.utc).isoformat(),
            run_id=run_id,
        )

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class AgentEvent:
    source: str
    event_type: str
    symbol: str
    confidence: float
    evidence: dict[str, Any] = field(default_factory=dict)
    assumptions: list[str] = field(default_factory=list)
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class MarketDataEvent:
    symbol: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class SignalEvent:
    symbol: str
    signal: str
    confidence: float


@dataclass
class RiskEvent:
    symbol: str
    approved: bool
    reason: str = ""


@dataclass
class OrderEvent:
    symbol: str
    side: str
    quantity: int
    price: float
    route: str = "paper_broker"
    status: str = "queued"


@dataclass
class ExecutionEvent:
    symbol: str
    side: str
    quantity: int
    price: float
    route: str = "paper_broker"
    status: str = "filled"
