from __future__ import annotations

from .data import CSVMarketDataProvider
from .env import EnvironmentPolicy
from .team import build_default_team


class FrontendAdapter:
    """A simple adapter that provides data in a shape suitable for a local dashboard or UI."""

    def __init__(self):
        self.provider = CSVMarketDataProvider()
        self.team = build_default_team()
        self.environment = EnvironmentPolicy()

    def dashboard_snapshot(self) -> dict:
        data = self.provider.get_market_data()
        return {
            "status": "ready",
            "market_data": {
                "rows": len(data),
                "symbol": data["symbol"].iloc[0] if "symbol" in data.columns else "UNKNOWN",
            },
            "mode": "paper",
            "connection": self.environment.summary(),
            "agent_workspace": [
                {
                    "agent_id": profile.agent_id,
                    "role": profile.role,
                    "mandate": profile.mandate,
                    "capabilities": list(profile.capabilities),
                    "status": "ready",
                    "work_state": "Awaiting run",
                }
                for profile in self.team.profiles.values()
            ],
        }
