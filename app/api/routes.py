"""Agent endpoints. Mounted under /api by app.main."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agents.trading_agent import agent
from app.core.config import settings

router = APIRouter(prefix="/api", tags=["agent"])


class OrderProposal(BaseModel):
    symbol: str = Field(..., min_length=1, max_length=16)
    quantity: float = Field(..., gt=0)


@router.get("/agent/status")
def agent_status() -> dict:
    """Current agent state, including the broker connection flag."""
    return {**agent.status(), "broker_configured": settings.broker_configured}


@router.get("/agent/analyze/{symbol}")
def analyze_symbol(symbol: str) -> dict:
    """Market analysis for one symbol (placeholder: neutral)."""
    if not symbol.strip():
        raise HTTPException(status_code=400, detail="symbol must not be empty")
    return agent.analyze(symbol)


@router.post("/agent/orders")
def propose_order(order: OrderProposal) -> dict:
    """Return an order proposal. Simulated only - never sent to a broker."""
    return agent.propose_order(order.symbol, order.quantity)
