from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any


class RunStorage:
    """Persist restart-safe run snapshots and append-only audit history."""

    _lock = threading.RLock()

    def __init__(self, directory: str | Path | None = None):
        if directory is None:
            configured_directory = os.getenv("TRADE_AGENT_DATA_DIR")
            state_directory = Path(
                os.getenv("XDG_STATE_HOME", Path.home() / ".local" / "state")
            )
            directory = configured_directory or state_directory / "trade-agent" / "runs"
        self.directory = Path(directory).expanduser()
        self.directory.mkdir(parents=True, exist_ok=True)
        self.history_path = self.directory / "history.json"
        self.latest_path = self.directory / "latest_run.json"
        self.audit_path = self.directory / "audit_history.json"
        self.learning_path = self.directory / "learning_history.json"

    def store(self, payload: dict[str, Any]) -> str:
        with self._lock:
            history = self._read_list(self.history_path)
            history.append(dict(payload))
            self._write_json(self.history_path, history)
            self._write_json(self.latest_path, payload)
        return str(self.latest_path)

    def load_history(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_list(self.history_path)

    def store_audit_event(self, event: dict[str, Any]) -> str:
        with self._lock:
            events = self._read_list(self.audit_path)
            events.append(dict(event))
            self._write_json(self.audit_path, events)
        return str(self.audit_path)

    def load_audit_history(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_list(self.audit_path)

    def store_learning_entry(self, entry: dict[str, Any]) -> str:
        with self._lock:
            entries = self._read_list(self.learning_path)
            entries.append(dict(entry))
            self._write_json(self.learning_path, entries)
        return str(self.learning_path)

    def load_learning_history(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read_list(self.learning_path)

    def probe(self) -> dict[str, Any]:
        """Cheap readiness check for the persisted run store (used by /api/health)."""
        self.directory.mkdir(parents=True, exist_ok=True)
        writable = os.access(self.directory, os.W_OK)
        error: str | None = None
        try:
            entries = len(self._read_list(self.history_path))
        except ValueError as exc:
            entries = 0
            error = str(exc)
        return {
            "ready": writable and error is None,
            "directory": str(self.directory),
            "writable": writable,
            "history_entries": entries,
            "error": error,
        }

    @staticmethod
    def _read_list(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"Unable to read persisted history at {path}.") from exc
        if not isinstance(payload, list) or any(not isinstance(item, dict) for item in payload):
            raise ValueError(f"Persisted history at {path} has an invalid format.")
        return payload

    @staticmethod
    def _write_json(path: Path, payload: Any) -> None:
        text = json.dumps(payload, indent=2, sort_keys=True, allow_nan=False)
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_file.write(text)
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
                temporary_path = Path(temporary_file.name)
            temporary_path.replace(path)
        finally:
            if temporary_path is not None and temporary_path.exists():
                temporary_path.unlink()
