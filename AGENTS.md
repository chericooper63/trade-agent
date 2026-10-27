# Repository notes

## Running here (Base44 sandbox)

- `docker compose -f docker-compose.base44.yml up -d` is the only supported boot path.
  The API listens on container port 8000, published on host port 3000 (the preview port).
- `./` is bind-mounted at `/app`, so `uvicorn --reload` picks up edits without a rebuild.
  `requirements.txt` changes DO need a rebuild (`up -d --build`).
- No database, cache or queue: nothing to migrate or seed. The app serves real content
  immediately, so healthcheck success on `/health` is enough.

## Gotchas

- The agent is deliberately a dry-run placeholder; `/api/agent/orders` returns
  `simulated: true` and never contacts a broker. Do not describe it as live trading.
- `BROKER_API_KEY` / `BROKER_API_SECRET` are optional. If real broker credentials are
  ever required, declare them with `set_secrets` and add `/run/base44/app.env` as the
  LAST `env_file:` entry for the `api` service — never inline the values under
  `environment:`.

## Checks

```bash
docker compose -f docker-compose.base44.yml exec -T api pytest -q
docker compose -f docker-compose.base44.yml exec -T api python -c "from app.main import app; print(app.title)"
```
