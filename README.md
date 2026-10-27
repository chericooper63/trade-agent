# trade-agent

A ready-to-go autonomous trading agent with market analysis and execution capabilities.

This repository currently holds a **working boilerplate**: a FastAPI service with a
placeholder trading agent, a health endpoint and a small status page. The agent is a
dry run — it never contacts a broker and never submits an order.

## Layout

```
.
├── app/
│   ├── main.py              # main entry file (FastAPI app, / and /health)
│   ├── core/config.py       # settings read from environment variables
│   ├── agents/
│   │   └── trading_agent.py # agent skeleton: analyze() + propose_order() + status()
│   └── api/routes.py        # /api endpoints
├── tests/test_api.py        # API tests
├── requirements.txt
├── Dockerfile
├── docker-compose.base44.yml
├── .env.example
└── README.md
```

## Run it

With Docker (what the preview uses):

```bash
docker compose -f docker-compose.base44.yml up -d --build
```

Locally, without Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open <http://localhost:3000> (Docker) or <http://localhost:8000> (local).

## Endpoints

| Method | Path                        | Purpose                              |
| ------ | --------------------------- | ------------------------------------ |
| GET    | `/`                         | Status page                          |
| GET    | `/health`                   | Liveness probe                       |
| GET    | `/docs`                     | Interactive API docs                 |
| GET    | `/api/agent/status`         | Agent state + broker configured flag |
| GET    | `/api/agent/analyze/{sym}`  | Market analysis for one symbol       |
| POST   | `/api/agent/orders`         | Simulated order proposal             |

```bash
curl -s localhost:3000/api/agent/status
curl -s localhost:3000/api/agent/analyze/AAPL
curl -s -X POST localhost:3000/api/agent/orders \
  -H 'content-type: application/json' -d '{"symbol":"AAPL","quantity":3}'
```

## Configuration

| Variable            | Default        | Notes                                     |
| ------------------- | -------------- | ----------------------------------------- |
| `APP_NAME`          | `Trade Agent`  | Page title / API title                    |
| `ENVIRONMENT`       | `development`  | Free-form environment label               |
| `PAPER_TRADING`     | `true`         | Keep `true` until a broker is wired       |
| `BROKER_API_KEY`    | *(empty)*      | Optional; dry-run while empty             |
| `BROKER_API_SECRET` | *(empty)*      | Optional; dry-run while empty             |

Nothing is required to boot. Broker credentials are not stored in the repo.

## Tests

```bash
docker compose -f docker-compose.base44.yml exec -T api pytest -q
```

## Next steps

1. Replace `TradingAgent.analyze` with real market analysis.
2. Implement `propose_order` against a broker client, gated on `settings.broker_configured`.
3. Add persistence for positions and an order/audit log.
