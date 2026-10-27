from __future__ import annotations

import json
from pathlib import Path
from tempfile import gettempdir


class AuditReportService:
    """Persist a simple structured run report or audit artifact as JSON."""

    def __init__(self, directory: str | Path | None = None):
        self.directory = Path(directory or gettempdir()) / "trade_agent_reports"
        self.directory.mkdir(parents=True, exist_ok=True)

    def write(self, payload: dict) -> str:
        output_path = self.directory / "latest_report.json"
        output_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        return str(output_path)
