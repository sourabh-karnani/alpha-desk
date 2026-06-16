"""Order/fill types, a cost model, and the abstract Broker interface."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

# Sides are expressed in the broker's vocabulary. A LONG idea opens with "buy"
# and closes with "sell"; a SHORT idea opens with "short" and closes with "cover".
VALID_SIDES = ("buy", "sell", "short", "cover")


@dataclass
class Order:
    ticker: str
    side: str
    qty: int
    price: float            # assumed reference/limit price
    kind: str = "market"
    ts: str | None = None

    def __post_init__(self) -> None:
        if self.side not in VALID_SIDES:
            raise ValueError(f"side must be one of {VALID_SIDES}, got {self.side!r}")
        if self.qty <= 0:
            raise ValueError("qty must be positive")


@dataclass
class Fill:
    ticker: str
    side: str
    qty: int
    price: float            # actual fill price (after slippage)
    fee: float
    ts: str | None = None

    @property
    def value(self) -> float:
        return self.price * self.qty


class FeeModel(ABC):
    @abstractmethod
    def fee(self, value: float, side: str) -> float:
        """Cost in account currency for a trade of the given notional `value`."""


class BpsFeeModel(FeeModel):
    """Flat basis-points-per-side cost.

    Default 7.5 bps/side ≈ 15 bps round-trip, a realistic all-in figure for
    Indian retail equities (brokerage + STT + exchange + stamp + GST).
    """

    def __init__(self, bps_per_side: float = 7.5):
        self.bps_per_side = bps_per_side

    def fee(self, value: float, side: str) -> float:
        return abs(value) * self.bps_per_side / 10_000.0


class Broker(ABC):
    """Minimal synchronous order interface. Implementations fill an order and
    return the resulting `Fill` (raising on rejection)."""

    @abstractmethod
    def place(self, order: Order) -> Fill: ...

    @abstractmethod
    def name(self) -> str: ...
