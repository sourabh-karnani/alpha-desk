"""Zerodha Kite adapter — interface stub.

Deliberately NOT implemented. Live order routing needs an authenticated session
(API key/secret + daily access token) and real-money safeguards that are out of
scope for a paper-only v1. This file pins the contract so a real adapter is a
drop-in for `PaperBroker`: implement `place()` against the Kite Connect SDK and
wire it wherever a `Broker` is constructed.
"""
from __future__ import annotations

from trading.brokers.base import Broker, Fill, Order


class KiteBroker(Broker):
    def __init__(self, api_key: str | None = None, access_token: str | None = None):
        self.api_key = api_key
        self.access_token = access_token

    def name(self) -> str:
        return "kite"

    def place(self, order: Order) -> Fill:  # pragma: no cover - stub
        raise NotImplementedError(
            "Live Kite order routing is not implemented in v1 (paper-only). "
            "Use PaperBroker, or implement this against the Kite Connect SDK."
        )
