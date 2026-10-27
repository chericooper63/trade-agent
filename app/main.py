"""Main entry point for the Trade Agent API.

Run locally:     uvicorn app.main:app --reload
In the sandbox:  docker compose -f docker-compose.base44.yml up -d
"""

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from app.agents.trading_agent import agent
from app.api.routes import router
from app.core.config import settings

app = FastAPI(title=settings.app_name, version="0.1.0")
app.include_router(router)


@app.get("/health", tags=["system"])
def health() -> dict:
    """Liveness probe used by Docker/compose healthchecks."""
    return {"status": "ok"}


_INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>{{title}}</title>
  <style>
    :root { color-scheme: dark; }
    body {
      margin: 0; min-height: 100vh; display: grid; place-items: center;
      font-family: ui-sans-serif, system-ui, -apple-system, sans-serif;
      background: #0b1020; color: #e6ebf5;
    }
    main {
      box-sizing: border-box; width: min(680px, 92vw); padding: 40px; border-radius: 16px;
      background: #121a30; border: 1px solid #24304f;
    }
    h1 { margin: 0 0 6px; font-size: 28px; letter-spacing: -0.01em; }
    p.lead { margin: 0 0 24px; color: #97a3bd; line-height: 1.5; }
    dl {
      display: grid; grid-template-columns: 170px 1fr; gap: 10px 16px;
      margin: 0 0 26px; font-size: 14px;
    }
    dt { color: #7d8aa8; }
    dd { margin: 0; }
    h2 { font-size: 13px; text-transform: uppercase; letter-spacing: 0.08em; color: #7d8aa8; margin: 0 0 10px; }
    ul { margin: 0; padding-left: 18px; font-size: 14px; line-height: 1.9; }
    code { background: #0b1020; padding: 2px 6px; border-radius: 6px; font-size: 13px; }
  </style>
</head>
<body>
  <main>
    <h1>{{title}}</h1>
    <p class="lead">The boilerplate API is running. The agent below is a dry-run
    placeholder: it does not contact a broker and never submits an order.</p>
    <dl>
      <dt>Environment</dt><dd>{{environment}}</dd>
      <dt>Paper trading</dt><dd>{{paper_trading}}</dd>
      <dt>Agent</dt><dd>{{agent}} ({{positions}} open position(s))</dd>
    </dl>
    <h2>Endpoints</h2>
    <ul>
      <li><code>GET /health</code> — liveness probe</li>
      <li><code>GET /api/agent/status</code> — agent state</li>
      <li><code>GET /api/agent/analyze/{symbol}</code> — market analysis</li>
      <li><code>POST /api/agent/orders</code> — simulated order proposal</li>
      <li><code>GET /docs</code> — interactive API docs</li>
    </ul>
  </main>
</body>
</html>
"""


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index() -> str:
    """Minimal status page so the running service is visible in the browser."""
    status = agent.status()
    return (
        _INDEX_HTML.replace("{{title}}", settings.app_name)
        .replace("{{environment}}", settings.environment)
        .replace("{{paper_trading}}", "on" if settings.paper_trading else "off")
        .replace("{{agent}}", status["agent"])
        .replace("{{positions}}", str(len(status["positions"])))
    )
