"""Startup helpers for the dashboard server.

Logging setup, bounded retries and readiness reporting live here so
``trade_agent.server`` stays a thin HTTP layer.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from typing import Any

LOGGER_NAME = "trade_agent.startup"


class StartupError(RuntimeError):
    """Raised when a startup step cannot succeed within its retry budget."""


def configure_logging(level: str = "INFO") -> logging.Logger:
    """Return the startup logger with a single timestamped stream handler."""
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(str(level).upper())
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s")
        )
        logger.addHandler(handler)
    logger.propagate = False
    return logger


def log_orchestrator_readiness(server, logger: logging.Logger) -> None:
    """Log clear, per-component status updates for orchestrator readiness.

    Called during dashboard startup after the orchestrator is initialised so
    operators can see exactly which sub-systems came up and in what mode.
    """
    orchestrator = server.api.orchestrator
    config = orchestrator.agent.config

    logger.info(
        "Orchestrator agent initialised (symbol=%s, mode=%s, paper_only=%s, "
        "equity=%s, proposal_capital=%s)",
        config.symbol,
        config.mode,
        config.paper_only,
        config.account_equity,
        config.proposal_capital,
    )

    probe = orchestrator.storage.probe()
    storage_state = "ready" if probe.get("ready") else "degraded"
    logger.info(
        "Orchestrator storage %s — directory=%s, persisted_runs=%s, writable=%s",
        storage_state,
        probe.get("directory"),
        probe.get("history_entries", 0),
        probe.get("writable"),
    )

    agent_count = len(orchestrator.team.profiles)
    logger.info(
        "Orchestrator team assembled (%d specialist agents online)",
        agent_count,
    )

    logger.info(
        "Orchestrator monitoring ready — audit store=%s",
        type(orchestrator.monitor.storage).__name__,
    )

    logger.info(
        "Orchestrator ready for dashboard (mode=%s, allow_live=%s, kill_switch=%s)",
        config.mode,
        config.allow_live,
        getattr(config, "kill_switch", False),
    )


def retry_call(
    operation: Callable[[], Any],
    *,
    label: str,
    logger: logging.Logger,
    attempts: int = 3,
    delay: float = 0.5,
    timeout: float = 15.0,
) -> Any:
    """Run ``operation`` until it succeeds or its attempt/time budget runs out.

    Transient environment failures (``OSError`` for ports and files,
    ``ValueError`` for unreadable persisted state) are retried; the total wait is
    bounded by ``timeout`` seconds so startup can never hang indefinitely.
    """
    attempts = max(int(attempts), 1)
    deadline = time.monotonic() + max(float(timeout), 0.0)
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        try:
            result = operation()
        except (OSError, ValueError) as exc:
            last_error = exc
            remaining = deadline - time.monotonic()
            logger.warning(
                "%s failed (attempt %s/%s, %.1fs left): %s",
                label,
                attempt,
                attempts,
                max(remaining, 0.0),
                exc,
            )
            if attempt >= attempts or remaining <= 0:
                break
            time.sleep(min(delay, remaining))
        else:
            if attempt > 1:
                logger.info("%s succeeded after %s attempt(s)", label, attempt)
            return result
    raise StartupError(f"{label} failed after {attempts} attempt(s): {last_error}") from last_error
