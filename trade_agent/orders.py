from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Order:
    symbol: str
    side: str
    quantity: int
    price: float
    order_type: str = "market"


class OrderRouter:
    """Very small routing abstraction for a simplified execution path."""

    def route(self, order: Order) -> dict:
        return {
            "symbol": order.symbol,
            "side": order.side,
            "quantity": order.quantity,
            "price": order.price,
            "order_type": order.order_type,
            "route": "paper_broker",
            "status": "queued",
        }


class OrderBook:
    """A tiny in-repo matching-book abstraction for paper flows.

    This does not produce a production exchange engine, but it provides a
    clear order-book object that can layer into a future matching engine.
    """

    def __init__(self):
        self.buy_orders = []
        self.sell_orders = []
        self.trades = []

    def add(self, order: Order) -> dict:
        if order.side == "BUY":
            self.buy_orders.append(order)
        elif order.side == "SELL":
            self.sell_orders.append(order)
        else:
            raise ValueError("side must be BUY or SELL")

        return {"symbol": order.symbol, "side": order.side, "quantity": order.quantity, "status": "queued"}

    def match(self, order: Order) -> dict:
        self.add(order)
        pair = {"symbol": order.symbol, "side": order.side, "quantity": order.quantity, "price": order.price, "status": "matched"}
        self.trades.append(pair)
        return pair
