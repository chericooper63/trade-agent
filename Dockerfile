# Development image for the Trade Agent dashboard.
# The repository is bind-mounted at /app by docker-compose.base44.yml, so the
# dashboard reads frontend files live and watchfiles restarts the server when
# the Python package changes. Only dependencies live in the image.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt ./
RUN pip install --upgrade pip && pip install -r requirements.txt watchfiles pytest

EXPOSE 8000

CMD ["python", "-m", "trade_agent.server", "--host", "0.0.0.0", "--port", "8000"]
