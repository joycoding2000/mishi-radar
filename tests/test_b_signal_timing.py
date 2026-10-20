from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from mishi_radar.cash_backtest.engine import run_backtest

from tests.b_fixtures import bar, config, make_input, market_day, signal, trading_dates


class SignalOpenTimingTests(unittest.TestCase):
    dates = trading_dates(2, end=date(2026, 10, 19))
    signal_day, trade_day = dates

    def _run(self, available_at: str):
        days = [
            market_day(self.signal_day, {"SH:600001": bar(self.signal_day, 5, 5)}),
            market_day(self.trade_day, {"SH:600001": bar(self.trade_day, 5, 5)}),
        ]
        item = signal(
            "SH:600001",
            self.signal_day,
            strategy_id="S02",
            candidate_rank=1,
            pool_rank=1,
            available_at=available_at,
        )
        return run_backtest(
            make_input(self.dates, days, signals_by_signal_date={self.signal_day: (item,)}),
            config(
                strategy_id="S02",
                initial_cash=Decimal(1005),
                top_n=1,
                start_date=self.trade_day,
                stop_loss=None,
            ),
        )

    def test_signal_known_before_next_open_executes_at_next_open(self) -> None:
        result = self._run(f"{self.trade_day}T09:00:00")
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(
            [(fill.date, fill.quantity, fill.price) for fill in result.fills],
            [(self.trade_day, 200, Decimal(5))],
        )
        self.assertEqual(result.nav_points[-1].cash, Decimal(0))
        self.assertEqual(result.nav_points[-1].equity, Decimal(1000))

    def test_signal_known_just_before_open_executes_at_next_open(self) -> None:
        result = self._run(f"{self.trade_day}T09:29:59")
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(len(result.fills), 1)
        self.assertEqual(result.fills[0].date, self.trade_day)

    def test_signal_known_after_open_is_not_executed_at_that_open(self) -> None:
        result = self._run(f"{self.trade_day}T09:30:01")
        self.assertEqual(result.fills, [])
        expired = [order for order in result.orders if order.status == "EXPIRED"]
        self.assertEqual(len(expired), 1)
        self.assertEqual(expired[0].reason, "EXPIRED_INPUT_WINDOW")

    def test_previous_day_evening_timestamp_is_before_next_open(self) -> None:
        result = self._run(f"{self.signal_day}T23:59:59")
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(len(result.fills), 1)
        self.assertEqual(result.fills[0].date, self.trade_day)


if __name__ == "__main__":
    unittest.main()
