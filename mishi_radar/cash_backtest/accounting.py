"""Pure accounting rules for partial sales, dividends and the open-position stop."""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal("0.01")
ZERO = Decimal("0")


def money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def allocate_sale_cost(cost_before: Decimal, quantity_sold: int, quantity_before: int) -> tuple[Decimal, Decimal]:
    """Return ``(cost_sold, cost_open)`` using the approved proportional rule."""

    if quantity_before <= 0:
        raise ValueError("quantity_before must be positive")
    if quantity_sold < 0 or quantity_sold > quantity_before:
        raise ValueError("quantity_sold outside position")
    if quantity_sold == quantity_before:
        return cost_before, ZERO
    cost_sold = money(cost_before * Decimal(quantity_sold) / Decimal(quantity_before))
    return cost_sold, cost_before - cost_sold


def split_dividend_entitlement(
    dividend_open: Decimal,
    entitled_units: int,
    quantity_sold: int,
) -> tuple[Decimal, Decimal, int]:
    """Split existing net dividend equity between sold and remaining shares."""

    if dividend_open <= 0 or entitled_units <= 0:
        return ZERO, dividend_open, entitled_units
    entitled_sold = min(quantity_sold, entitled_units)
    if entitled_sold >= entitled_units:
        return dividend_open, ZERO, 0
    sold = money(dividend_open * Decimal(entitled_sold) / Decimal(entitled_units))
    return sold, dividend_open - sold, entitled_units - entitled_sold


def remaining_open_stop_ratio(market_value: Decimal, dividend_open: Decimal, cost_open: Decimal) -> Decimal | None:
    if cost_open <= 0:
        return None
    return (market_value + dividend_open - cost_open) / cost_open


def cycle_total_pnl(realized_trading_pnl: Decimal, realized_dividend: Decimal) -> Decimal:
    return realized_trading_pnl + realized_dividend


def cycle_economic_pnl(
    realized_trading_pnl: Decimal,
    realized_dividend: Decimal,
    market_value: Decimal,
    dividend_open: Decimal,
    cost_open: Decimal,
) -> Decimal:
    """Cycle P&L before or after closing, keeping realized and open risk separate."""

    return realized_trading_pnl + realized_dividend + market_value + dividend_open - cost_open
