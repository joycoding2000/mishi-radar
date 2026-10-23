from __future__ import annotations

import unittest
from decimal import Decimal

from mishi_radar.cash_backtest.engine import run_backtest
from mishi_radar.cash_backtest.model import CorporateAction

from tests.b_fixtures import bar, config, exit_request, make_input, market_day, signal, trading_dates


class CorporateActionTests(unittest.TestCase):
    def _base_days(self, dates, actions=None):
        actions_by_date = actions or {}
        days = []
        for day in dates:
            price = Decimal("10") if day < dates[2] else Decimal("9.9")
            bars = {"SH:600001": bar(day, price, price)}
            days.append(
                market_day(
                    day,
                    bars,
                    corporate_actions=actions_by_date.get(day, ()),
                )
            )
        return days

    def _buy_signal(self, dates):
        return {dates[0]: (signal("SH:600001", dates[0]),)}

    def test_cash_dividend_receivable_and_payment_do_not_double_count(self) -> None:
        dates = trading_dates(5)
        action = CorporateAction(
            security_id="SH:600001",
            action_type="CASH_DIVIDEND",
            effective_date=dates[2],
            record_date=dates[1],
            pay_date=dates[3],
            cash_per_share=Decimal("0.1"),
            dividend_tax_rate=Decimal("0"),
            source="SYNTHETIC",
            version="SYNTHETIC-CA-1",
        )
        days = self._base_days(dates, {dates[2]: (action,)})
        result = run_backtest(
            make_input(dates, days, signals_by_signal_date=self._buy_signal(dates)),
            config(initial_cash=Decimal(1005), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        ex_date = result.nav_points[1]
        self.assertEqual(ex_date.cash, Decimal(0))
        self.assertEqual(ex_date.receivables, Decimal(10))
        self.assertEqual(ex_date.market_value, Decimal(990))
        self.assertEqual(ex_date.equity, Decimal(1000))
        pay_date = result.nav_points[2]
        self.assertEqual(pay_date.cash, Decimal(10))
        self.assertEqual(pay_date.receivables, Decimal(0))
        self.assertEqual(pay_date.market_value, Decimal(990))
        self.assertEqual(pay_date.equity, Decimal(1000))
        self.assertEqual(result.nav_points[-1].equity, Decimal(1000))
        self.assertTrue(all(item["cash_ok"] for item in result.reconciliation))
        self.assertTrue(all(item["equity_ok"] for item in result.reconciliation))

    def test_bonus_shares_adjust_quantity_cost_and_sellable_date(self) -> None:
        dates = trading_dates(5)
        action = CorporateAction(
            security_id="SH:600001",
            action_type="BONUS_SHARES",
            effective_date=dates[2],
            record_date=dates[1],
            share_multiplier=Decimal(2),
            new_share_sellable_date=dates[3],
            source="SYNTHETIC",
            version="SYNTHETIC-CA-1",
        )
        days = []
        for day in dates:
            price = Decimal("10") if day < dates[2] else Decimal("5")
            days.append(
                market_day(
                    day,
                    {"SH:600001": bar(day, price, price)},
                    corporate_actions=(action,) if day == dates[2] else (),
                )
            )
        result = run_backtest(
            make_input(dates, days, signals_by_signal_date=self._buy_signal(dates)),
            config(initial_cash=Decimal(1005), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        ex_date = [p for p in result.position_history if p.date == dates[2]][0]
        self.assertEqual(ex_date.quantity, 200)
        self.assertEqual(ex_date.sellable_quantity, 100)
        self.assertEqual(ex_date.cost_open, Decimal(1005))
        self.assertEqual(ex_date.market_value, Decimal(1000))
        next_date = [p for p in result.position_history if p.date == dates[3]][0]
        self.assertEqual(next_date.sellable_quantity, 200)
        self.assertEqual(next_date.cost_open, Decimal(1005))
        self.assertTrue(all(item["cash_ok"] for item in result.reconciliation))
        self.assertTrue(all(item["equity_ok"] for item in result.reconciliation))

    def test_sale_between_record_and_ex_date_keeps_dividend_claim(self) -> None:
        dates = trading_dates(6)
        action = CorporateAction(
            security_id="SH:600001",
            action_type="CASH_DIVIDEND",
            effective_date=dates[3],
            record_date=dates[1],
            pay_date=dates[4],
            cash_per_share=Decimal("0.1"),
            dividend_tax_rate=Decimal("0"),
            source="SYNTHETIC",
            version="SYNTHETIC-CA-1",
        )
        days = []
        for index, day in enumerate(dates):
            price = Decimal("9.9") if index >= 3 else Decimal("10")
            days.append(
                market_day(
                    day,
                    {"SH:600001": bar(day, price, price)},
                    corporate_actions=(action,) if day == dates[3] else (),
                )
            )
        signals = {dates[0]: (signal("SH:600001", dates[0]),)}
        exits = {dates[1]: (exit_request("SH:600001", dates[1]),)}
        result = run_backtest(
            make_input(dates, days, signals_by_signal_date=signals, exit_requests_by_signal_date=exits),
            config(initial_cash=Decimal(1005), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(len(result.closed_cycles), 1)
        cycle = result.closed_cycles[0]
        self.assertEqual(cycle.realized_trading_pnl, Decimal("-10.00"))
        self.assertEqual(cycle.realized_dividend, Decimal("10.00"))
        self.assertEqual(cycle.total_pnl, Decimal("0.00"))
        ex_date = result.nav_points[2]
        self.assertEqual(ex_date.cash, Decimal("995.00"))
        self.assertEqual(ex_date.receivables, Decimal("10.00"))
        self.assertEqual(ex_date.equity, Decimal("1005.00"))
        pay_date = result.nav_points[3]
        self.assertEqual(pay_date.cash, Decimal("1005.00"))
        self.assertEqual(pay_date.receivables, Decimal("0.00"))
        self.assertEqual(pay_date.equity, Decimal("1005.00"))
        self.assertTrue(all(item["cash_ok"] for item in result.reconciliation))

    def test_unknown_corporate_action_blocks_held_security(self) -> None:
        dates = trading_dates(4)
        action = CorporateAction(
            security_id="SH:600001",
            action_type="CASH_DIVIDEND",
            effective_date=dates[2],
            status="UNKNOWN",
            cash_per_share=Decimal("0.1"),
        )
        days = self._base_days(dates, {dates[2]: (action,)})
        result = run_backtest(
            make_input(dates, days, signals_by_signal_date=self._buy_signal(dates)),
            config(initial_cash=Decimal(1005), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("CORPORATE_ACTION_UNKNOWN" in item for item in result.blockers))

    def test_unknown_corporate_action_blocks_buy_candidate(self) -> None:
        dates = trading_dates(3)
        action = CorporateAction(
            security_id="SH:600001",
            action_type="CASH_DIVIDEND",
            effective_date=dates[1],
            status="UNKNOWN",
            cash_per_share=Decimal("0.1"),
        )
        days = []
        for day in dates:
            days.append(
                market_day(
                    day,
                    {"SH:600001": bar(day, 10, 10)},
                    corporate_actions=(action,) if day == dates[1] else (),
                )
            )
        result = run_backtest(
            make_input(dates, days, signals_by_signal_date={dates[0]: (signal("SH:600001", dates[0]),)}),
            config(initial_cash=Decimal(1005), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("CORPORATE_ACTION_UNKNOWN" in item for item in result.blockers))

    def test_incomplete_corporate_action_coverage_blocks_candidate_before_buy(self) -> None:
        dates = trading_dates(3)
        days = []
        for day in dates:
            days.append(
                market_day(
                    day,
                    {"SH:600001": bar(day, 10, 10)},
                    corporate_actions_complete=day != dates[1],
                )
            )
        result = run_backtest(
            make_input(dates, days, signals_by_signal_date={dates[0]: (signal("SH:600001", dates[0]),)}),
            config(initial_cash=Decimal(1005), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("CORPORATE_ACTION_COVERAGE_INCOMPLETE" in item for item in result.blockers))

    def test_incomplete_corporate_action_coverage_blocks_held_security(self) -> None:
        dates = trading_dates(4)
        days = []
        for day in dates:
            days.append(
                market_day(
                    day,
                    {"SH:600001": bar(day, 10, 10)},
                    corporate_actions_complete=day != dates[2],
                )
            )
        result = run_backtest(
            make_input(dates, days, signals_by_signal_date=self._buy_signal(dates)),
            config(initial_cash=Decimal(1005), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("CORPORATE_ACTION_COVERAGE_INCOMPLETE" in item for item in result.blockers))


if __name__ == "__main__":
    unittest.main()
