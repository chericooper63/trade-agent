from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from .api import DashboardAPI


class DashboardServer:
    """Serve the static dashboard and expose a clean dashboard JSON API endpoint."""

    def __init__(self, static_root: str | Path | None = None):
        self.static_root = str(static_root or Path(__file__).resolve().parents[1] / "frontend")
        self.api = DashboardAPI()

    def dashboard_payload(self) -> dict:
        return self.api.dashboard_payload()

    def index_path(self) -> str:
        return str(Path(self.static_root) / "index.html")

    def static_index_exists(self) -> bool:
        return Path(self.index_path()).exists()

    def api_route(self) -> str:
        return "/api/dashboard"

    def _serve_file(self, handler: BaseHTTPRequestHandler, file_path: Path, content_type: str):
        body = file_path.read_bytes()
        handler.send_response(200)
        handler.send_header("Content-Type", content_type)
        handler.send_header("Content-Length", str(len(body)))
        handler.end_headers()
        handler.wfile.write(body)

    def route_handler(self):
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                request_path = self.path.split("?", 1)[0]
                if request_path == self.server.dashboard_route:
                    payload = json.dumps(self.server.dashboard_api.dashboard_payload()).encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(payload)))
                    self.end_headers()
                    self.wfile.write(payload)
                    return

                if request_path in {"/", "/frontend", "/frontend/"}:
                    target = Path(self.server.static_root) / "index.html"
                    self.server._serve_file(self, target, "text/html; charset=utf-8")
                    return

                if request_path.startswith("/frontend/"):
                    target = Path(self.server.static_root) / request_path.replace("/frontend/", "", 1)
                    if target.exists() and target.is_file():
                        mime = "text/html; charset=utf-8" if target.suffix == ".html" else "text/css; charset=utf-8" if target.suffix == ".css" else "application/javascript; charset=utf-8"
                        self.server._serve_file(self, target, mime)
                        return

                self.send_response(404)
                self.end_headers()

            def do_POST(self):
                request_path = self.path.split("?", 1)[0]
                if request_path not in {
                    self.server.settings_route,
                    self.server.run_route,
                }:
                    self.send_response(404)
                    self.end_headers()
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    requested = json.loads(self.rfile.read(length).decode("utf-8"))
                    if request_path == self.server.settings_route:
                        result = {"settings": self.server.dashboard_api.update_settings(requested)}
                    else:
                        result = {"run": self.server.dashboard_api.run_workflow()}
                    body = json.dumps(result).encode("utf-8")
                    self.send_response(200)
                except (ValueError, TypeError, json.JSONDecodeError) as exc:
                    body = json.dumps({"error": str(exc)}).encode("utf-8")
                    self.send_response(400)
                except OSError as exc:
                    body = json.dumps({"error": f"Persistent run storage failed: {exc}"}).encode("utf-8")
                    self.send_response(500)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, format, *args):
                return

        return Handler

    def start(self, host: str = "127.0.0.1", port: int = 8000):
        handler = self.route_handler()
        server = ThreadingHTTPServer((host, port), handler)
        server.dashboard_payload = self.dashboard_payload()
        server.dashboard_route = self.api_route()
        server.settings_route = "/api/settings"
        server.run_route = "/api/run"
        server.dashboard_api = self.api
        server.static_root = self.static_root
        server._serve_file = self._serve_file
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            # watchfiles stops the server with SIGINT on every code change;
            # exit quietly instead of printing a traceback into the logs.
            pass
        finally:
            server.server_close()


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the local trade-agent dashboard")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args(argv)
    display_host = "127.0.0.1" if args.host in {"0.0.0.0", "::"} else args.host
    print(f"Trade-agent dashboard: http://{display_host}:{args.port}/")
    DashboardServer().start(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
