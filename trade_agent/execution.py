from __future__ import annotations

from .orders import Order


class SimulatedBroker:
    """A simple simulated execution layer that logs orders and prints outcomes."""

    def __init__(self, symbol: str = "AAPL"):
        self.symbol = symbol
        self.orders = []

    def execute(self, signal: str, order_size: float, price: float) -> dict:
        if signal == "HOLD" or order_size <= 0:
            return {"status": "skipped", "reason": "No trade executed"}

        order = {
            "symbol": self.symbol,
            "side": "BUY" if signal == "BUY" else "SELL",
            "size": order_size,
            "price": price,
            "status": "filled",
        }
        self.orders.append(order)
        return order


class ExecutionService:
    """Accepts only account-approved routed orders and turns them into fills."""

    def __init__(self, storage=None):
        self.fills = []
        self.executed_orders = set()
        self.storage = storage

    def execute(self, routed_order: dict) -> dict:
        audit = routed_order.get("audit")
        account_id = routed_order.get("account_id")
        if not isinstance(audit, dict):
            raise ValueError("Execution requires an audited trade decision.")
        if not account_id or audit.get("account_id") != account_id:
            raise ValueError("Execution account does not match the audited decision account.")
        if audit.get("approval_status") != "approved" or not audit.get("risk_approved", False):
            raise ValueError("Execution requires a risk-approved decision with completed approval.")
        execution_mode = audit.get("mode", "paper")
        if execution_mode not in {"paper", "live"}:
            raise ValueError(f"Unsupported execution mode: {execution_mode!r}.")
        route = routed_order.get("route", "paper_broker")
        if route not in {"paper_broker", "live_broker"}:
            raise ValueError(f"ExecutionService only accepts paper_broker or live_broker routes; got {route!r}.")

        expected_signal = "BUY" if routed_order.get("side") == "BUY" else "SELL"
        if audit.get("signal") != expected_signal:
            raise ValueError("Order side does not match the audited decision signal.")

        fingerprint = routed_order.get("order_id") or (
            account_id,
            routed_order.get("symbol"),
            routed_order.get("side"),
            routed_order.get("quantity"),
            routed_order.get("price"),
        )
        if fingerprint in self.executed_orders:
            raise ValueError("Duplicate order rejected: this order was already executed.")

        fill = {
            "symbol": routed_order["symbol"],
            "side": routed_order["side"],
            "quantity": routed_order["quantity"],
            "price": routed_order["price"],
            "route": routed_order.get("route", "paper_broker"),
            "status": "filled",
            "estimated_fee": float(routed_order.get("estimated_fee", 0.0)),
            "estimated_slippage": float(routed_order.get("estimated_slippage", 0.0)),
            "account_id": account_id,
            "approval_status": audit["approval_status"],
        }
        self.executed_orders.add(fingerprint)
        self.fills.append(fill)
        if self.storage is not None:
            self.storage.store_audit_event(
                {"event_type": "execution", "audit": dict(audit), "fill": dict(fill)}
            )
        return fill
