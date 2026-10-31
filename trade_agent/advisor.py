from __future__ import annotations


class AdvisorFilter:
    """Advisor layer that screens the alpha registry output and returns a decision summary."""

    def __init__(self, agreement_threshold: int = 2):
        self.agreement_threshold = agreement_threshold

    def filter(self, alpha_result: dict) -> dict:
        signals = alpha_result.get("signals", {})
        aggregated_signal = alpha_result.get("aggregated_signal", "HOLD")

        buy_votes = sum(1 for value in signals.values() if value == "BUY")
        sell_votes = sum(1 for value in signals.values() if value == "SELL")

        if buy_votes >= self.agreement_threshold:
            approved = True
            decision = "BUY"
            reasons = ["momentum agreement"]
        elif sell_votes >= self.agreement_threshold:
            approved = True
            decision = "SELL"
            reasons = ["mean reversion or volatility agreement"]
        else:
            approved = False
            decision = "HOLD"
            reasons = ["alpha agreement below threshold"]

        return {
            "approved": approved,
            "decision": decision,
            "aggregated_signal": aggregated_signal,
            "signals": signals,
            "reasons": reasons,
        }

    def filter_candidates(self, scan_result: dict) -> dict:
        """Select the highest-confidence actionable candidate from a market scan."""
        candidates = scan_result.get("actionable", []) if isinstance(scan_result, dict) else []
        if not candidates:
            return {
                "approved": False,
                "decision": "HOLD",
                "candidate": None,
                "candidates": [],
                "reasons": ["no actionable market candidates"],
            }

        candidate = candidates[0]
        return {
            "approved": True,
            "decision": candidate["signal"],
            "candidate": candidate,
            "candidates": candidates,
            "reasons": ["highest-confidence actionable candidate"],
        }
