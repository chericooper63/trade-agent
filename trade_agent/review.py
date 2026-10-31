from __future__ import annotations

from typing import Any

from .storage import RunStorage
from .team import LearningJournal


class ReviewAgent:
    """Paper-only review loop that checks risk-budget fit and tunes future candidate selection.

    This agent exists to improve the decision process without ever permitting a live
    execution path. It scores the current paper allocation against the allowed risk
    budget and returns a concrete reduction plan plus a priority ordering for the
    next cycle.
    """

    def __init__(self, journal: LearningJournal | None = None):
        self.journal = journal or LearningJournal(storage=RunStorage())
        self.allow_live = False

    def next_cycle_candidates(
        self,
        candidates: list[dict[str, Any]],
        *,
        risk_budget_used: float = 0.0,
        risk_budget_limit: float = 1.0,
    ) -> dict[str, Any]:
        if self.allow_live:
            raise ValueError("ReviewAgent is intentionally paper-only and cannot enable live execution.")

        budget_exceeded = bool(float(risk_budget_used) > float(risk_budget_limit))
        ranked = []
        down_ranked = []

        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            symbol = str(candidate.get("symbol", "unknown"))
            confidence = float(candidate.get("confidence", 0.0))
            risk_weight = float(candidate.get("risk_weight", 0.0))
            adjusted_confidence = confidence * max(0.0, 1.0 - min(risk_weight, 1.0) * 0.5)
            if budget_exceeded and risk_weight > 0.0:
                adjusted_confidence *= max(0.0, 1.0 - (max(risk_budget_used - risk_budget_limit, 0.0) / max(risk_weight, 1e-9)))
                down_ranked.append({"symbol": symbol, "confidence": confidence, "risk_weight": risk_weight, "adjusted_confidence": adjusted_confidence})
            ranked.append({
                "symbol": symbol,
                "confidence": confidence,
                "risk_weight": risk_weight,
                "adjusted_confidence": adjusted_confidence,
            })

        ranked.sort(key=lambda item: item["adjusted_confidence"], reverse=True)
        return {
            "paper_mode": True,
            "allow_live": False,
            "budget_exceeded": budget_exceeded,
            "risk_budget_used": float(risk_budget_used),
            "risk_budget_limit": float(risk_budget_limit),
            "next_cycle_candidates": ranked,
            "down_ranked": down_ranked,
            "review_status": "needs_reduction" if budget_exceeded else "approved",
        }

    def evaluate(
        self,
        portfolio: dict[str, Any],
        risk: dict[str, Any],
        decision: dict[str, Any],
        *,
        risk_budget_limit: float = 1.0,
    ) -> dict[str, Any]:
        if self.allow_live:
            raise ValueError("ReviewAgent is intentionally paper-only and cannot enable live execution.")

        positions = portfolio.get("positions", {}) if isinstance(portfolio, dict) else {}
        risk_budget_used = float(portfolio.get("risk_budget_used", 0.0)) if isinstance(portfolio, dict) else 0.0
        if not positions:
            risk_budget_used = 0.0

        if positions and risk_budget_used <= 0.0:
            risk_budget_used = sum(
                float(position.get("risk_weight", 0.0))
                for position in positions.values()
                if isinstance(position, dict)
            )

        budget_exceeded = bool(risk_budget_used > float(risk_budget_limit))
        priority_order = sorted(
            positions,
            key=lambda symbol: float(positions[symbol].get("confidence", 0.0)) if isinstance(positions[symbol], dict) else 0.0,
            reverse=True,
        )

        reduction_plan: list[dict[str, Any]] = []
        if budget_exceeded:
            overage = max(risk_budget_used - float(risk_budget_limit), 0.0)
            for symbol in priority_order:
                position = positions.get(symbol, {}) if isinstance(positions.get(symbol), dict) else {}
                if not position:
                    continue
                current_cash = float(position.get("cash_used", 0.0))
                current_weight = float(position.get("risk_weight", 0.0))
                if current_weight <= 0.0:
                    continue
                scale = min(max(1.0 - (overage / max(current_weight, 1e-9)), 0.0), 1.0)
                reduced_cash = current_cash * scale
                reduction_plan.append(
                    {
                        "symbol": symbol,
                        "current_cash_used": current_cash,
                        "new_cash_used": reduced_cash,
                        "cash_reduction": current_cash - reduced_cash,
                        "risk_weight": current_weight,
                    }
                )
                overage = max(overage - current_weight, 0.0)
                if overage <= 0.0:
                    break

        for symbol in priority_order:
            position = positions.get(symbol, {}) if isinstance(positions.get(symbol), dict) else {}
            if not position:
                continue
            self.journal.record(
                "risk_review_agent",
                symbol,
                {
                    "signal": decision.get("signal", "HOLD"),
                    "confidence": float(decision.get("confidence", 0.0)),
                    "approved": bool(decision.get("approved", False)),
                },
                {
                    "status": "paper_reviewed",
                    "risk_budget_used": risk_budget_used,
                    "risk_budget_limit": float(risk_budget_limit),
                    "budget_exceeded": budget_exceeded,
                    "symbol": symbol,
                },
                (
                    "The paper review stayed inside the risk budget and should keep the symbol in the next candidate list."
                    if not budget_exceeded
                    else "The paper review exceeded the risk budget, so the symbol should be down-weighted before the next cycle."
                ),
            )

        candidate_order = [
            {
                "symbol": symbol,
                "confidence": float(positions[symbol].get("confidence", 0.0)) if isinstance(positions[symbol], dict) else 0.0,
                "risk_weight": float(positions[symbol].get("risk_weight", 0.0)) if isinstance(positions[symbol], dict) else 0.0,
            }
            for symbol in priority_order
        ]
        next_cycle = self.next_cycle_candidates(
            candidate_order,
            risk_budget_used=risk_budget_used,
            risk_budget_limit=risk_budget_limit,
        )

        result = {
            "paper_mode": True,
            "allow_live": False,
            "budget_exceeded": budget_exceeded,
            "risk_budget_used": risk_budget_used,
            "risk_budget_limit": float(risk_budget_limit),
            "priority_order": priority_order,
            "reduction_plan": reduction_plan,
            "review_status": "needs_reduction" if budget_exceeded else "approved",
            "recommended_symbols": priority_order,
            "next_cycle_candidates": next_cycle["next_cycle_candidates"],
            "down_ranked": next_cycle["down_ranked"],
        }
        return result
