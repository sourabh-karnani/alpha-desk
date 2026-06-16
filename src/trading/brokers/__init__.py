"""Broker abstraction.

v1 ships a fully-functional `PaperBroker` (no real money, no network) plus the
abstract `Broker` interface and order/fill types. A real broker adapter (e.g.
Zerodha Kite) implements the same interface; a stub lives in `kite.py` to pin
the contract without bundling credentials or live order routing.
"""
from trading.brokers.base import BpsFeeModel, Broker, FeeModel, Fill, Order
from trading.brokers.paper import PaperBroker

__all__ = ["BpsFeeModel", "Broker", "FeeModel", "Fill", "Order", "PaperBroker"]
