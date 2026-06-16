"""Paper broker: deterministic fills, modelled costs, optional slippage."""
from __future__ import annotations

from trading.brokers.base import BpsFeeModel, Broker, FeeModel, Fill, Order

# Adverse-slippage direction per side: you buy/cover a touch higher, sell/short
# a touch lower than the reference price.
_ADVERSE = {"buy": +1, "cover": +1, "sell": -1, "short": -1}


class PaperBroker(Broker):
    """Fills every order at its reference price, nudged by `slippage_bps` in the
    adverse direction and charged `fee_model`. No network, no real money."""

    def __init__(self, fee_model: FeeModel | None = None, slippage_bps: float = 0.0):
        self.fee_model = fee_model or BpsFeeModel()
        self.slippage_bps = slippage_bps

    def name(self) -> str:
        return "paper"

    def place(self, order: Order) -> Fill:
        slip = self.slippage_bps / 10_000.0 * _ADVERSE.get(order.side, 0)
        fill_price = order.price * (1.0 + slip)
        fee = self.fee_model.fee(fill_price * order.qty, order.side)
        return Fill(
            ticker=order.ticker,
            side=order.side,
            qty=order.qty,
            price=fill_price,
            fee=fee,
            ts=order.ts,
        )
