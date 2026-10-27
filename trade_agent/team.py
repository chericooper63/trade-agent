from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class AgentProfile:
    """Identity and operating brief for a main agent or private child agent."""

    agent_id: str
    role: str
    persona: str
    mandate: str
    parent_id: str | None = None
    capabilities: tuple[str, ...] = ()


@dataclass(frozen=True)
class AgentMessage:
    """A routed work product exchanged between agents in one reporting chain."""

    sender_id: str
    recipient_id: str
    message_type: str
    payload: dict[str, Any] = field(default_factory=dict)
    message_id: str = field(default_factory=lambda: uuid4().hex)
    run_id: str = ""
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


class AgentTeam:
    """Manage role ownership, private child agents, and controlled handoffs."""

    def __init__(self, profiles: list[AgentProfile] | None = None):
        self.profiles = {profile.agent_id: profile for profile in profiles or []}
        self.messages: list[AgentMessage] = []

    def register(self, profile: AgentProfile) -> None:
        if profile.agent_id in self.profiles:
            raise ValueError(f"Agent already registered: {profile.agent_id}")
        if profile.parent_id is not None and profile.parent_id not in self.profiles:
            raise ValueError("A child agent must be registered after its parent agent.")
        self.profiles[profile.agent_id] = profile

    def create_child(
        self,
        parent_id: str,
        role: str,
        persona: str,
        mandate: str,
        capabilities: tuple[str, ...] = (),
    ) -> AgentProfile:
        parent = self.profiles.get(parent_id)
        if parent is None:
            raise ValueError(f"Unknown parent agent: {parent_id}")
        child = AgentProfile(
            agent_id=f"{parent_id}.{role}.{uuid4().hex[:8]}",
            role=role,
            persona=persona,
            mandate=mandate,
            parent_id=parent.agent_id,
            capabilities=capabilities,
        )
        self.profiles[child.agent_id] = child
        return child

    def send(self, message: AgentMessage) -> None:
        sender = self.profiles.get(message.sender_id)
        recipient = self.profiles.get(message.recipient_id)
        if sender is None or recipient is None:
            raise ValueError("Both message sender and recipient must be registered agents.")
        if not self._is_allowed(sender, recipient):
            raise ValueError("Agent communication must stay within the main-agent reporting chain.")
        self.messages.append(message)

    def messages_for(self, agent_id: str) -> list[AgentMessage]:
        return [message for message in self.messages if message.recipient_id == agent_id]

    def snapshot(self) -> dict[str, Any]:
        return {
            "agents": [asdict(profile) for profile in self.profiles.values()],
            "messages": [asdict(message) for message in self.messages],
        }

    @staticmethod
    def _is_allowed(sender: AgentProfile, recipient: AgentProfile) -> bool:
        if sender.parent_id == recipient.agent_id or recipient.parent_id == sender.agent_id:
            return True
        return sender.parent_id is None and recipient.parent_id is None


class LearningJournal:
    """Record decision outcomes as durable training evidence, never as silent mutation."""

    def __init__(self, storage=None, path: str | Path | None = None):
        self.entries: list[dict[str, Any]] = []
        self.storage = storage
        self.path = Path(path) if path is not None else None

    def _persist(self, entry: dict[str, Any]) -> None:
        if self.storage is not None:
            self.storage.store_learning_entry(entry)

        if self.path is not None:
            records = []
            if self.path.exists():
                try:
                    payload = json.loads(self.path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError) as exc:
                    raise ValueError(f"Unable to read learning history at {self.path}.") from exc
                if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
                    raise ValueError(f"Learning history at {self.path} has an invalid format.")
                records = payload
            records.append(entry)
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(records, indent=2, sort_keys=True), encoding="utf-8")

    def record(
        self,
        agent_id: str,
        symbol: str,
        decision: dict[str, Any],
        outcome: dict[str, Any],
        lesson: str,
    ) -> dict[str, Any]:
        if not agent_id or not symbol or not lesson.strip():
            raise ValueError("Learning records require an agent, symbol, and non-empty lesson.")
        entry = {
            "entry_id": uuid4().hex,
            "recorded_at": datetime.now(timezone.utc).isoformat(),
            "agent_id": agent_id,
            "symbol": symbol,
            "decision": dict(decision),
            "outcome": dict(outcome),
            "lesson": lesson.strip(),
        }
        self._persist(entry)
        self.entries.append(entry)
        return entry

    def for_agent(self, agent_id: str) -> list[dict[str, Any]]:
        return [entry for entry in self.entries if entry["agent_id"] == agent_id]

    def snapshot(self) -> dict[str, Any]:
        return {
            "entries": [dict(entry) for entry in self.entries],
            "count": len(self.entries),
        }


def build_default_team() -> AgentTeam:
    """Build the default specialized team for market scanning, research, risk, portfolio, execution, and review."""
    profiles = [
        AgentProfile(
            "data_curator",
            "data curator",
            "Methodical and detail-oriented.",
            "Collect, normalize, and validate market data before any signal or portfolio decision is considered.",
            capabilities=("data_collection", "source_validation", "quality_checks"),
        ),
        AgentProfile(
            "market_scanner",
            "market scanner",
            "Observant and relentlessly evidence-driven.",
            "Scan the market universe, rank candidates, and surface trade-worthy opportunities.",
            capabilities=("market_data", "screening", "candidate_ranking"),
        ),
        AgentProfile(
            "alpha_researcher",
            "alpha researcher",
            "Analytical and skeptical of weak samples.",
            "Validate signals with feature checks, historical context, and evidence-backed alpha hypotheses.",
            capabilities=("alpha_generation", "feature_testing", "signal_validation"),
        ),
        AgentProfile(
            "strategy_architect",
            "strategy architect",
            "Rational and adaptive under market change.",
            "Design and tune the logic that transforms market structure into a trade decision and confidence estimate.",
            capabilities=("signal_design", "regime_logic", "strategy_tuning"),
        ),
        AgentProfile(
            "regime_analyst",
            "regime analyst",
            "Calm under changing market conditions.",
            "Detect macro and regime context that can amplify or suppress the current signal quality.",
            capabilities=("regime_detection", "macro_context", "signal_adjustment"),
        ),
        AgentProfile(
            "risk_chief",
            "risk chief",
            "Conservative, precise, and mathematically disciplined.",
            "Reject unsafe proposals that violate account limits, drawdown rules, and concentration constraints.",
            capabilities=("risk_checks", "drawdown_control", "position_limits"),
        ),
        AgentProfile(
            "portfolio_manager",
            "portfolio manager",
            "Deliberate about concentration and exposure.",
            "Allocate approved risk across symbols and accounts while respecting budget and liquidity constraints.",
            capabilities=("allocation", "exposure_management", "multi_asset_budget"),
        ),
        AgentProfile(
            "execution_steward",
            "execution steward",
            "Auditable, precise, and explicit about approval.",
            "Route only approved, account-bound orders through paper or explicitly gated live broker adapters.",
            capabilities=("orders", "audit_trail", "routing"),
        ),
        AgentProfile(
            "execution_simulator",
            "execution simulator",
            "Skeptical of idealized fills and attentive to transaction costs.",
            "Simulate approved paper orders and report modeled execution outcomes without accessing live brokers.",
            capabilities=("paper_fills", "cost_modeling", "execution_review"),
        ),
        AgentProfile(
            "policy_guard",
            "policy guard",
            "Disciplined and compliance-minded.",
            "Enforce paper-only defaults, explicit credentials, and manual approval gates before any live path can open.",
            capabilities=("approval_gate", "execution_policy", "compliance"),
        ),
        AgentProfile(
            "learning_reviewer",
            "learning reviewer",
            "Evidence-led and careful not to confuse correlation with causation.",
            "Review paper outcomes, persist lessons, and rank future candidates without changing execution permissions.",
            capabilities=("paper_review", "outcome_journal", "candidate_feedback"),
        ),
        AgentProfile(
            "performance_reviewer",
            "performance reviewer",
            "Focused on measurable outcomes and learning loops.",
            "Compare fills to expectations, record lessons, and create evidence for later strategy or policy updates.",
            capabilities=("attribution", "post_trade_review", "learning_journal"),
        ),
    ]
    return AgentTeam(profiles)
