from __future__ import annotations

import argparse
import json
import os
import signal
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .api import DashboardAPI
from .startup import StartupError, configure_logging, retry_call

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}


class DashboardHTTPServer(ThreadingHTTPServer):
    """Threaded server that tolerates restarts and slow clients."""

    allow_reuse_address = True
    daemon_threads = True
    request_queue_size = 64


class DashboardServer:
    """Serve the static dashboard and expose a clean dashboard JSON API endpoint."""

    def __init__(self, static_root: str | Path | None = None):
        self.static_root = str(static_root or Path(__file__).resolve().parents[1] / "frontend")
        self.api = DashboardAPI()
        self.started_at: float | None = None
        self._boot_started = time.monotonic()

    def dashboard_payload(self) -> dict:
        return self.api.dashboard_payload()

    def index_path(self) -> str:
        return str(Path(self.static_root) / "index.html")

    def static_index_exists(self) -> bool:
        return Path(self.index_path()).exists()

    def api_route(self) -> str:
        return "/api/dashboard"

    def health_route(self) -> str:
        return "/api/health"

    def state_store_probe(self) -> dict:
        """Readiness of the persisted run store (the app's storage dependency)."""
        try:
            return self.api.orchestrator.storage.probe()
        except (OSError, ValueError) as exc:
            return {"ready": False, "error": str(exc)}

    def health_payload(self) -> tuple[int, dict]:
        """Return the HTTP status and body describing server readiness."""
        probe = self.state_store_probe()
        status = 200 if probe.get("ready") else 503
        uptime = round(time.monotonic() - self.started_at, 3) if self.started_at else 0.0
        return status, {
            "status": "ready" if probe.get("ready") else "degraded",
            "uptime_seconds": uptime,
            "storage": probe,
            "mode": self.api.settings.get("mode"),
        }

    def _serve_file(self, handler: BaseHTTPRequestHandler, file_path: Path, content_type: str):
        body = file_path.read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def route_handler(self, logger=None, request_timeout: float = 30.0):
        server_logger = logger or configure_logging()
        serve_file = self._serve_file

        class Handler(BaseHTTPRequestHandler):
            # Bounds a stalled client so a thread is never held open forever.
            timeout = request_timeout

            def _send_json(self, status: int, payload: dict) -> None:
                body = json.dumps(payload).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                try:
                    self._handle_get()
                except (BrokenPipeError, ConnectionResetError):
                    return
                except Exception as exc:  # handler failures must not kill the server
                    server_logger.exception("Unhandled error while serving %s", self.path)
                    self._send_json(500, {"error": f"Internal server error: {exc}"})

            def _handle_get(self):
                request_path = self.path.split("?", 1)[0]
                if request_path == self.server.health_route:
                    status, payload = self.server.dashboard_server.health_payload()
                    self._send_json(status, payload)
                    return

                if request_path == self.server.dashboard_route:
                    self._send_json(200, self.server.dashboard_server.dashboard_payload())
                    return

                if request_path in {"/", "/frontend", "/frontend/"}:
                    serve_file(self, Path(self.server.static_root) / "index.html", CONTENT_TYPES[".html"])
                    return

                if request_path.startswith("/frontend/"):
                    target = Path(self.server.static_root) / request_path.replace("/frontend/", "", 1)
                    if target.exists() and target.is_file():
                        mime = CONTENT_TYPES.get(target.suffix, "application/octet-stream")
                        serve_file(self, target, mime)
                        return

                self.send_response(404)
                self.end_headers()

            def do_POST(self):
                try:
                    self._handle_post()
                except (BrokenPipeError, ConnectionResetError):
                    return
                except Exception as exc:
                    server_logger.exception("Unhandled error while serving %s", self.path)
                    self._send_json(500, {"error": f"Internal server error: {exc}"})

            def _handle_post(self):
                request_path = self.path.split("?", 1)[0]
                if request_path not in {self.server.settings_route, self.server.run_route}:
                    self.send_response(404)
                    self.end_headers()
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    raw = self.rfile.read(length).decode("utf-8") if length else ""
                    requested = json.loads(raw) if raw.strip() else {}
                    if request_path == self.server.settings_route:
                        result = {"settings": self.server.dashboard_server.api.update_settings(requested)}
                    else:
                        result = {"run": self.server.dashboard_server.api.run_workflow()}
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    self._send_json(400, {"error": str(exc)})
                except OSError as exc:
                    server_logger.error("Persistent run storage failed: %s", exc)
                    self._send_json(500, {"error": f"Persistent run storage failed: {exc}"})
                else:
                    self._send_json(200, result)

            def log_message(self, format, *args):
                return

            def log_error(self, format, *args):
                server_logger.warning("%s - %s", self.address_string(), format % args)

        return Handler

    def create_server(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        *,
        bind_attempts: int = 5,
        startup_timeout: float = 30.0,
        request_timeout: float = 30.0,
        logger=None,
    ) -> DashboardHTTPServer:
        """Bind the listening socket with retries and wire up the routes."""
        log = logger or configure_logging()
        handler = self.route_handler(logger=log, request_timeout=request_timeout)
        server = retry_call(
            lambda: DashboardHTTPServer((host, port), handler),
            label=f"Binding {host}:{port}",
            logger=log,
            attempts=bind_attempts,
            timeout=startup_timeout,
        )
        server.dashboard_server = self
        server.dashboard_route = self.api_route()
        server.health_route = self.health_route()
        server.settings_route = "/api/settings"
        server.run_route = "/api/run"
        server.static_root = self.static_root
        self.started_at = time.monotonic()
        return server

    def start(
        self,
        host: str = "127.0.0.1",
        port: int = 8000,
        *,
        bind_attempts: int = 5,
        startup_timeout: float = 30.0,
        request_timeout: float = 30.0,
        logger=None,
    ):
        log = logger or configure_logging()
        log.info(
            "Starting dashboard server on %s:%s (state store: %s, mode: %s)",
            host,
            port,
            self.state_store_probe().get("directory"),
            self.api.settings.get("mode"),
        )
        server = self.create_server(
            host=host,
            port=port,
            bind_attempts=bind_attempts,
            startup_timeout=startup_timeout,
            request_timeout=request_timeout,
            logger=log,
        )
        try:
            log.info(
                "Dashboard server ready on http://%s:%s/ (startup took %d ms)",
                host,
                port,
                int((time.monotonic() - self._boot_started) * 1000),
            )
            server.serve_forever()
        except KeyboardInterrupt:
            log.info("Dashboard server shutdown requested")
        finally:
            server.server_close()
            log.info("Dashboard server stopped")


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    try:
        return float(raw) if raw is not None else default
    except ValueError as exc:
        raise ValueError(f"{name} must be a number; received {raw!r}.") from exc


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    try:
        return int(raw) if raw is not None else default
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer; received {raw!r}.") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the local trade-agent dashboard")
    parser.add_argument("--host", default=os.getenv("TRADE_AGENT_HOST", "127.0.0.1"))
    parser.add_argument("--port", default=_env_int("TRADE_AGENT_PORT", 8000), type=int)
    parser.add_argument("--log-level", default=os.getenv("TRADE_AGENT_LOG_LEVEL", "INFO"))
    parser.add_argument(
        "--startup-timeout",
        default=_env_float("TRADE_AGENT_STARTUP_TIMEOUT", 30.0),
        type=float,
        help="Total seconds to wait for the state store and for binding the port.",
    )
    parser.add_argument(
        "--bind-attempts",
        default=_env_int("TRADE_AGENT_BIND_ATTEMPTS", 5),
        type=int,
        help="How many times to retry binding the listening socket.",
    )
    parser.add_argument(
        "--storage-attempts",
        default=_env_int("TRADE_AGENT_STORAGE_ATTEMPTS", 3),
        type=int,
        help="How many times to retry the persisted run store (startup 'database').",
    )
    parser.add_argument(
        "--request-timeout",
        default=_env_float("TRADE_AGENT_REQUEST_TIMEOUT", 30.0),
        type=float,
        help="Seconds before a stalled client connection is closed.",
    )
    args = parser.parse_args(argv)

    logger = configure_logging(args.log_level)
    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    print(f"Trade-agent dashboard: http://{display_host}:{args.port}/")

    def _stop_on_signal(signum, _frame):
        logger.info("Received %s", signal.Signals(signum).name)
        raise KeyboardInterrupt

    for signal_name in ("SIGINT", "SIGTERM"):
        if hasattr(signal, signal_name):
            signal.signal(getattr(signal, signal_name), _stop_on_signal)

    try:
        server = retry_call(
            DashboardServer,
            label="Dashboard API and state store initialisation",
            logger=logger,
            attempts=args.storage_attempts,
            timeout=args.startup_timeout,
        )
        probe = server.state_store_probe()
        logger.info(
            "State store ready at %s (%s persisted run(s))",
            probe.get("directory"),
            probe.get("history_entries", 0),
        )
        server.start(
            host=args.host,
            port=args.port,
            bind_attempts=args.bind_attempts,
            startup_timeout=args.startup_timeout,
            request_timeout=args.request_timeout,
            logger=logger,
        )
    except StartupError as exc:
        logger.error("Startup failed: %s", exc)
        return 1
    except ValueError as exc:
        logger.error("Invalid startup configuration: %s", exc)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
