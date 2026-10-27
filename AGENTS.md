# Repository notes

## What this is

`trade_agent/` is the trading engine (paper-only by design: no live order adapter exists and
`DashboardAPI` refuses live settings). `frontend/` is the operations dashboard, served by a
stdlib `http.server` in `trade_agent/server.py` — no JS build step.

## Running here (Base44 sandbox)

- `docker compose -f docker-compose.base44.yml up -d` starts the single `dashboard` service:
  container port 8000 → host port 3000 (the preview port).
- `./` is bind-mounted at `/app`. Frontend files (`index.html`, `app.js`, `styles.css`) are read
  from disk per request, so UI edits need only a browser refresh. Python edits are picked up by
  `watchfiles`, which restarts `python -m trade_agent.server`. `requirements.txt` changes need
  `up -d --build`. The server traps the reloader's SIGINT so reloads exit quietly instead of
  logging a `KeyboardInterrupt` traceback.
- Run state (`history.json`, `latest_run.json`, audit log) is written to
  `~/.local/state/trade-agent/`, mapped to the named volume `trade_agent_state` so cycles
  survive container recreation. Reset it with
  `exec -T dashboard rm -f /root/.local/state/trade-agent/runs/*.json`.
- No database, cache or seed step. Market data comes from `trade_agent/sample_market_data.csv`
  (40 AAPL rows) via `CSVMarketDataProvider`.

## Dashboard contract (do not change casually)

- `GET /` → `frontend/index.html`; assets under `/frontend/*`.
- `GET /api/dashboard` → status, mode, `last_run` (in-memory, falling back to the latest
  persisted run), `run_history` (last 20 summaries), `connection` safety flags, `agent_workspace`.
  The `run_history` field and the persisted-run fallback were added for the dashboard.
- `POST /api/run` → runs one paper cycle (400 if the kill switch is on).
- `POST /api/settings` → `{mode, require_manual_approval, kill_switch}`; live mode always raises.

## Checks

```bash
docker compose -f docker-compose.base44.yml exec -T dashboard python -m pytest -q
```

62 of 64 tests pass. Two failures are pre-existing in the imported snapshot and unrelated to the
dashboard: `test_multi_layer_agent_run_returns_documented_layers` and
`test_learning_agent_records_simulated_execution_outcome` expect a simulated fill, but the sample
data yields a HOLD signal, so the cycle is (correctly) rejected.

## Credentials

None required. `TRADE_AGENT_*` / `ALPACA_*` variables exist for the live path, which is
unavailable in this build; the engine runs against a local virtual budget.
