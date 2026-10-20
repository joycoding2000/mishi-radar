from __future__ import annotations

import unittest
from decimal import Decimal

from mishi_radar.cash_backtest.engine import run_backtest

from tests.b_fixtures import (
    bar,
    config,
    exit_request,
    make_input,
    market_day,
    signal,
    trading_dates,
)


class CashModelSpecExampleTests(unittest.TestCase):
    def test_spec_c_buy_failure_replacement_sell_failure_and_recovery(self) -> None:
        dates = trading_dates(5)
        start = dates[1]
        bars = {}
        for index, day in enumerate(dates):
            a_suspended = index == 1
            c_limit = Decimal(9) if index == 2 else None
            bars[day] = market_day(
                day,
                {
                    "SH:600001": bar(day, 10, 10, suspended=a_suspended),
                    "SH:600002": bar(day, 10, 10),
                    "SH:600003": bar(
                        day,
                        Decimal(9) if index >= 2 else 10,
                        Decimal(9) if index >= 2 else 10,
                        limit_down=c_limit,
                    ),
                },
            )
        signals = {
            dates[0]: (
                signal("SH:600001", dates[0], candidate_rank=1, pool_rank=1),
                signal("SH:600002", dates[0], candidate_rank=2, pool_rank=2),
                signal("SH:600003", dates[0], candidate_rank=3, pool_rank=3),
            )
        }
        exits = {dates[1]: (exit_request("SH:600003", dates[1]),)}
        data = make_input(dates, list(bars.values()), signals_by_signal_date=signals, exit_requests_by_signal_date=exits)
        result = run_backtest(
            data,
            config(start_date=start, top_n=2, rebalance_days=5, stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertTrue(result.synthetic)
        day1 = result.nav_points[0]
        self.assertEqual(day1.date, dates[1])
        self.assertEqual(day1.cash, Decimal(1990))
        self.assertEqual(day1.market_value, Decimal(98000))
        self.assertEqual(day1.equity, Decimal(99990))
        positions_day1 = [p for p in result.position_history if p.date == dates[1]]
        self.assertEqual({p.security_id: p.quantity for p in positions_day1}, {"SH:600002": 4900, "SH:600003": 4900})
        blocked_a = [o for o in result.orders if o.security_id == "SH:600001" and o.attempt_date == dates[1]]
        self.assertEqual(len(blocked_a), 1)
        self.assertEqual(blocked_a[0].status, "UNFILLED")
        self.assertEqual(blocked_a[0].reason, "SUSPENDED")
        self.assertEqual(blocked_a[0].commission, Decimal(0))

        day2 = result.nav_points[1]
        self.assertEqual(day2.cash, Decimal(1990))
        self.assertEqual(day2.equity, Decimal(95090))
        self.assertEqual(
            [p.quantity for p in result.position_history if p.date == dates[2] and p.security_id == "SH:600003"],
            [4900],
        )
        failed_sell = [
            o
            for o in result.orders
            if o.security_id == "SH:600003" and o.side == "SELL" and o.attempt_date == dates[2]
        ]
        self.assertEqual(failed_sell[0].status, "UNFILLED")
        self.assertEqual(failed_sell[0].reason, "LIMIT_DOWN")
        self.assertEqual(failed_sell[0].commission, Decimal(0))
        self.assertEqual(failed_sell[0].signal_date, dates[1])

        day3 = result.nav_points[2]
        self.assertEqual(day3.cash, Decimal(46085))
        self.assertEqual(day3.equity, Decimal(95085))
        self.assertNotIn("SH:600003", {p.security_id for p in result.position_history if p.date == dates[3]})
        self.assertEqual(result.metrics["sell_count"], Decimal(1))
        self.assertEqual(sum((o.commission for o in result.orders), Decimal(0)), Decimal(15))
        self.assertEqual(len(result.closed_cycles), 1)
        self.assertEqual(result.closed_cycles[0].security_id, "SH:600003")
        self.assertEqual(result.closed_cycles[0].total_pnl, Decimal("-4910"))
        self.assertTrue(all(item["cash_ok"] for item in result.reconciliation))
        self.assertTrue(all(item["equity_ok"] for item in result.reconciliation))

    def test_no_signal_keeps_cash_and_nav_one(self) -> None:
        dates = trading_dates(30)
        days = [
            market_day(day, {"SH:600001": bar(day, 10, 10)})
            for day in dates
        ]
        result = run_backtest(make_input(dates, days), config(top_n=2, stop_loss=None))
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(result.nav_points[-1].cash, Decimal(100000))
        self.assertEqual(result.nav_points[-1].equity, Decimal(100000))
        self.assertEqual(result.nav_points[-1].nav, Decimal(1))
        self.assertEqual(result.fills, [])
        self.assertIsNone(result.metrics["win_rate"])
        self.assertIn("2026-09", result.monthly_returns)
        self.assertIn("2026-10", result.monthly_returns)
        self.assertEqual(result.monthly_returns["2026-10"], Decimal(0))
        self.assertEqual(result.yearly_returns["2026"], Decimal(0))

    def test_unknown_signal_availability_blocks(self) -> None:
        dates = trading_dates(3)
        days = [market_day(day, {"SH:600001": bar(day, 10, 10)}) for day in dates]
        signals = {
            dates[0]: (
                signal("SH:600001", dates[0], available_at="UNKNOWN"),
            )
        }
        result = run_backtest(
            make_input(dates, days, signals_by_signal_date=signals),
            config(start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("SIGNAL_AVAILABILITY_UNKNOWN" in item for item in result.blockers))


if __name__ == "__main__":
    unittest.main()
