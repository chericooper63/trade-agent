from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_index_page_renders():
    response = client.get("/")
    assert response.status_code == 200
    assert "Trade Agent" in response.text


def test_agent_status():
    response = client.get("/api/agent/status")
    assert response.status_code == 200
    body = response.json()
    assert body["agent"] == "baseline"
    assert body["broker_configured"] is False


def test_analyze_symbol():
    response = client.get("/api/agent/analyze/aapl")
    assert response.status_code == 200
    assert response.json()["symbol"] == "AAPL"


def test_order_proposal_is_simulated():
    response = client.post("/api/agent/orders", json={"symbol": "AAPL", "quantity": 3})
    assert response.status_code == 200
    assert response.json()["simulated"] is True


def test_order_rejects_non_positive_quantity():
    response = client.post("/api/agent/orders", json={"symbol": "AAPL", "quantity": 0})
    assert response.status_code == 422
