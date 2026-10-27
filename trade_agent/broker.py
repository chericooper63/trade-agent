from __future__ import annotations

import os
import json
from urllib.request import Request, urlopen
from abc import ABC, abstractmethod
from dataclasses import dataclass
from urllib.parse import urlsplit

from .orders import Order
from .policy import ProductionPolicy


@dataclass(frozen=True)
class BrokerExecutionReceipt:
    """Typed, audit-friendly execution result for broker adapters."""

    symbol: str
    side: str
    quantity: int
    price: float
    route: str
    status: str
    mode: str


class BrokerExecutionError(ValueError):
    """Raised when a broker adapter refuses to execute a request."""

    pass


class BrokerAdapter(ABC):
    """Thin contract for a broker or exchange adapter."""

    @abstractmethod
    def place(self, order: Order) -> dict:
        """Place an order and return the broker result payload."""
        raise NotImplementedError


class PaperBrokerAdapter(BrokerAdapter):
    """A paper mode adapter that supports local simulation without secrets."""

    def __init__(self, mode: str = "paper"):
        if mode != "paper":
            raise BrokerExecutionError("PaperBrokerAdapter only supports paper mode.")
        self.mode = "paper"
        self.history = []

    def place(self, order: Order) -> dict:
        if not order.symbol or not order.side or order.quantity <= 0 or order.price <= 0:
            raise BrokerExecutionError("Paper broker rejected an invalid order payload.")

        result = BrokerExecutionReceipt(
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            price=order.price,
            route="paper_broker",
            status="paper_filled",
            mode=self.mode,
        )
        result_dict = result.__dict__
        self.history.append(result_dict)
        return result_dict


class LiveBrokerAdapter(BrokerAdapter):
    """Fail-closed live adapter contract; actual live submission is unavailable."""

    def __init__(self, mode: str = "live", policy: ProductionPolicy | None = None):
        if mode != "live":
            raise BrokerExecutionError("LiveBrokerAdapter requires explicit live mode.")
        self.mode = "live"
        self.policy = policy or ProductionPolicy(mode="live", allow_live=False)
        self.history = []

    def place(
        self,
        order: Order,
        *,
        account_id: str | None = None,
        manual_approval: bool = False,
        risk_approved: bool = False,
    ) -> dict:
        if not order.symbol or not order.side or order.quantity <= 0 or order.price <= 0:
            raise BrokerExecutionError("Live broker rejected an invalid order payload.")
        if risk_approved is not True:
            raise BrokerExecutionError("Live execution requires an approved risk decision.")
        self.policy.execution_gate(
            "live",
            account_id=account_id,
            manual_approval=manual_approval,
        )
        raise BrokerExecutionError("Live broker submission is not implemented; no order was sent.")


class AlpacaPaperBrokerAdapter(BrokerAdapter):
    """Call Alpaca's paper trading API using credentials held in the environment."""

    def __init__(
        self,
        api_key_env: str = "ALPACA_API_KEY",
        secret_key_env: str = "ALPACA_SECRET_KEY",
        base_url: str = "https://paper-api.alpaca.markets/v2",
    ):
        self.api_key_env = api_key_env
        self.secret_key_env = secret_key_env
        self.base_url = base_url.rstrip("/")
        parsed_url = urlsplit(self.base_url)
        if parsed_url.scheme != "https" or parsed_url.hostname != "paper-api.alpaca.markets" or parsed_url.path != "/v2":
            raise BrokerExecutionError("AlpacaPaperBrokerAdapter only permits the HTTPS Alpaca paper-trading endpoint.")

    def _credentials(self) -> tuple[str, str]:
        api_key = os.getenv(self.api_key_env, "").strip()
        secret_key = os.getenv(self.secret_key_env, "").strip()
        if not api_key or not secret_key:
            raise BrokerExecutionError(
                f"Alpaca paper credentials are missing. Set {self.api_key_env} and "
                f"{self.secret_key_env} outside the repository."
            )
        return api_key, secret_key

    def _request(self, path: str, method: str = "GET", payload: dict | None = None) -> dict | list:
        api_key, secret_key = self._credentials()
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(
            f"{self.base_url}/{path.lstrip('/')}",
            data=body,
            method=method,
            headers={
                "APCA-API-KEY-ID": api_key,
                "APCA-API-SECRET-KEY": secret_key,
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except Exception as exc:
            raise BrokerExecutionError(f"Alpaca paper API request failed: {exc}") from exc

    def account(self) -> dict:
        return self._request("account")

    def clock(self) -> dict:
        return self._request("clock")

    def positions(self) -> list:
        result = self._request("positions")
        if not isinstance(result, list):
            raise BrokerExecutionError("Alpaca positions response was not a list.")
        return result

    def place(self, order: Order) -> dict:
        if not order.symbol or order.side.upper() not in {"BUY", "SELL"} or order.quantity <= 0:
            raise BrokerExecutionError("Alpaca rejected an invalid order payload.")
        payload = {
            "symbol": order.symbol,
            "qty": str(order.quantity),
            "side": order.side.lower(),
            "type": order.order_type,
            "time_in_force": "day",
        }
        result = self._request("orders", method="POST", payload=payload)
        if not isinstance(result, dict):
            raise BrokerExecutionError("Alpaca order response was not an object.")
        return result
