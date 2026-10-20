from __future__ import annotations

import unittest
from decimal import Decimal

from mishi_radar.cash_backtest.accounting import (
    allocate_sale_cost,
    cycle_economic_pnl,
    remaining_open_stop_ratio,
    split_dividend_entitlement,
)
from mishi_radar.cash_backtest.engine import run_backtest

from tests.b_fixtures import bar, config, make_input, market_day, signal, trading_dates


class PartialSaleAccountingTests(unittest.TestCase):
    def test_owner_counterexample_without_fees(self) -> None:
        cost_sold, cost_open = allocate_sale_cost(Decimal(2000), 100, 200)
        self.assertEqual(cost_sold, Decimal(1000))
        self.assertEqual(cost_open, Decimal(1000))
        r_open = remaining_open_stop_ratio(Decimal(200), Decimal(0), cost_open)
        self.assertEqual(r_open, Decimal("-0.8"))
        self.assertLessEqual(r_open, Decimal("-0.08"))
        total = cycle_economic_pnl(Decimal(1000), Decimal(0), Decimal(200), Decimal(0), cost_open)
        self.assertEqual(total, Decimal(200))
        self.assertEqual(total / Decimal(2000), Decimal("0.10"))

    def test_owner_counterexample_with_buy_and_sell_fees(self) -> None:
        cost_before = Decimal(2005)
        cost_sold, cost_open = allocate_sale_cost(cost_before, 100, 200)
        self.assertEqual(cost_sold, Decimal("1002.50"))
        self.assertEqual(cost_open, Decimal("1002.50"))
        realized = Decimal(2000) - Decimal(5) - cost_sold
        self.assertEqual(realized, Decimal("992.50"))
        open_pnl = Decimal(200) - cost_open
        self.assertEqual(open_pnl, Decimal("-802.50"))
        self.assertEqual(realized + open_pnl, Decimal(190))
        self.assertAlmostEqual(
            float(remaining_open_stop_ratio(Decimal(200), Decimal(0), cost_open)),
            -0.8004987531,
            places=9,
        )

    def test_dividend_entitlement_splits_with_partial_sale(self) -> None:
        sold, remaining, units = split_dividend_entitlement(Decimal(100), 100, 50)
        self.assertEqual(sold, Decimal(50))
        self.assertEqual(remaining, Decimal(50))
        self.assertEqual(units, 50)
        cost_sold, cost_open = allocate_sale_cost(Decimal(1000), 50, 100)
        self.assertEqual(cost_sold, Decimal(500))
        realized_trade = Decimal(450) - cost_sold
        self.assertEqual(realized_trade + sold, Decimal(0))
        self.assertEqual(Decimal(450) + remaining - cost_open, Decimal(0))


class PartialSaleBacktestTests(unittest.TestCase):
    def test_partial_sale_then_remaining_position_stop_triggers(self) -> None:
        dates = trading_dates(6)
        prices = {
            dates[1]: {"SH:600001": 10, "SH:600002": 10},
            dates[2]: {"SH:600001": 20, "SH:600002": 10},
            dates[3]: {"SH:600001": 2, "SH:600002": 10},
            dates[4]: {"SH:600001": 2, "SH:600002": 10},
            dates[5]: {"SH:600001": 2, "SH:600002": 10},
        }
        bars = {}
        for day in dates:
            if day in prices:
                bars[day] = market_day(
                    day,
                    {sid: bar(day, price, price) for sid, price in prices[day].items()},
                )
            else:
                bars[day] = market_day(day, {"SH:600001": bar(day, 10, 10), "SH:600002": bar(day, 10, 10)})
        signals = {
            dates[0]: (
                signal("SH:600001", dates[0], strategy_id="S04", candidate_rank=1, pool_rank=1),
                signal("SH:600002", dates[0], strategy_id="S04", candidate_rank=2, pool_rank=2),
            ),
            dates[1]: (
                signal("SH:600001", dates[1], strategy_id="S04", candidate_rank=1, pool_rank=1),
                signal("SH:600002", dates[1], strategy_id="S04", candidate_rank=2, pool_rank=2),
            ),
            dates[2]: (
                signal("SH:600001", dates[2], strategy_id="S04", candidate_rank=1, pool_rank=1),
                signal("SH:600002", dates[2], strategy_id="S04", candidate_rank=2, pool_rank=2),
            ),
            dates[3]: (
                signal("SH:600001", dates[3], strategy_id="S04", candidate_rank=1, pool_rank=1),
                signal("SH:600002", dates[3], strategy_id="S04", candidate_rank=2, pool_rank=2),
            ),
        }
        result = run_backtest(
            make_input(dates, list(bars.values()), signals_by_signal_date=signals),
            config(
                strategy_id="S04",
                initial_cash=Decimal(4010),
                top_n=2,
                rebalance_days=1,
                stop_loss=Decimal("0.08"),
                start_date=dates[1],
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        day2_positions = [p for p in result.position_history if p.date == dates[2] and p.security_id == "SH:600001"]
        self.assertEqual(len(day2_positions), 1)
        self.assertEqual(day2_positions[0].quantity, 150)
        self.assertEqual(day2_positions[0].cost_open, Decimal("1503.75"))
        day3 = [p for p in result.position_history if p.date == dates[3] and p.security_id == "SH:600001"][0]
        self.assertLessEqual(day3.r_open, Decimal("-0.08"))
        stop_orders = [
            order
            for order in result.orders
            if order.security_id == "SH:600001" and order.side == "SELL" and order.reason == "STOP_LOSS"
        ]
        self.assertEqual(len(stop_orders), 1)
        self.assertEqual(stop_orders[0].attempt_date, dates[4])
        self.assertEqual(stop_orders[0].status, "FILLED")
        cycle = [item for item in result.closed_cycles if item.security_id == "SH:600001"][0]
        self.assertEqual(cycle.total_pnl, Decimal("-715.00"))


if __name__ == "__main__":
    unittest.main()
