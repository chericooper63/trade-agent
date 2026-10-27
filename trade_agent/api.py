from __future__ import annotations

from .agent import MultiLayerTradeAgent
from .config import AgentConfig
from .env import EnvironmentPolicy
from .frontend import FrontendAdapter
from .orchestration import AgentOrchestrator


class DashboardAPI:
    """Provides a dashboard-ready JSON payload for a local UI or web frontend."""

    def __init__(self):
        self.frontend = FrontendAdapter()
        config = AgentConfig.from_env()
        self.orchestrator = AgentOrchestrator(agent=MultiLayerTradeAgent(config=config))
        self.last_run = None
        environment = EnvironmentPolicy()
        self.settings = {
            "mode": environment.mode,
            "require_manual_approval": environment.require_manual_approval,
            "kill_switch": environment.kill_switch,
        }

    def update_credentials(self, api_key: str, secret_key: str) -> dict:
        raise ValueError(
            "Credential upload is unavailable. Configure broker secrets in the local environment or secret manager."
        )

    def update_settings(self, requested: dict) -> dict:
        if not isinstance(requested, dict):
            raise ValueError("Settings must be supplied as a JSON object.")
        environment = EnvironmentPolicy()
        mode = requested.get("mode", self.settings["mode"])
        if not isinstance(mode, str):
            raise ValueError("mode must be either paper or live")
        mode = mode.strip().lower()
        if mode not in {"paper", "live"}:
            raise ValueError("mode must be paper or live")
        manual_approval = requested.get("require_manual_approval", self.settings["require_manual_approval"])
        kill_switch = requested.get("kill_switch", self.settings["kill_switch"])
        if type(manual_approval) is not bool or type(kill_switch) is not bool:
            raise ValueError("require_manual_approval and kill_switch must be JSON booleans.")
        if mode == "live":
            if not environment.allow_live:
                raise ValueError("Live mode is disabled by TRADE_AGENT_ALLOW_LIVE=false.")
            if not environment.account_id:
                raise ValueError("Live mode requires an explicit TRADE_AGENT_ACCOUNT_ID.")
            if not manual_approval:
                raise ValueError("Live mode requires manual approval to remain enabled.")
            raise ValueError("Live dashboard execution is unavailable; no order was sent.")
        self.settings = {
            "mode": mode,
            "require_manual_approval": manual_approval,
            "kill_switch": kill_switch,
        }
        self.orchestrator.agent.config.kill_switch = kill_switch
        return self.settings.copy()

    def run_workflow(self) -> dict:
        if self.settings["mode"] != "paper":
            raise ValueError("Dashboard workflows are paper-only; live execution is unavailable.")
        if self.settings["kill_switch"]:
            raise ValueError("The kill switch is active; disable it before running a workflow.")
        result = self.orchestrator.run()
        self.last_run = result
        return self.last_run

    def _persisted_runs(self) -> list[dict]:
        try:
            return self.orchestrator.storage.load_history()
        except (OSError, ValueError):
            return []

    @staticmethod
    def _run_summary(run: dict) -> dict:
        summary = dict(run.get("final_summary") or {})
        summary["run_id"] = summary.get("run_id") or run.get("run_id")
        summary["completed_at"] = run.get("completed_at")
        return summary

    def dashboard_payload(self) -> dict:
        snapshot = self.frontend.dashboard_snapshot()
        connection = dict(snapshot["connection"])
        connection.update(self.settings)
        connection["account_data_available"] = False
        persisted = self._persisted_runs()
        last_run = self.last_run or (persisted[-1] if persisted else None)
        market_data = dict(snapshot["market_data"])
        if last_run:
            market_data["last_run"] = last_run
        return {
            "status": snapshot["status"],
            "mode": self.settings["mode"],
            "last_run": last_run,
            "run_history": [self._run_summary(run) for run in persisted[-20:]],
            "account_state": {"available": False, "source": None, "reason": "No live account connection is used."},
            "market_data": market_data,
            "connection": connection,
            "agent_workspace": snapshot["agent_workspace"],
            "generated_by": "trade_agent.api.DashboardAPI",
        }
