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
    synthetic_fees,
    synthetic_rule,
    trading_dates,
)


class S06ReplacementTests(unittest.TestCase):
    def _signals(self, date):
        return {
            date: (
                signal("SH:600001", date, strategy_id="S06", candidate_rank=1, pool_rank=1, industry_id="G", industry_trigger_rank=1),
                signal("SH:600002", date, strategy_id="S06", candidate_rank=2, pool_rank=2, industry_id="G", industry_trigger_rank=2),
                signal(
                    "SH:600003",
                    date,
                    strategy_id="S06",
                    candidate_rank=None,
                    pool_rank=3,
                    industry_id="G",
                    industry_trigger_rank=3,
                    formal_candidate=False,
                    execution_replacement_order=1,
                    signal_status="FALSE",
                    signal_state="CONCENTRATION_EXCLUDED",
                ),
                signal(
                    "SH:600004",
                    date,
                    strategy_id="S06",
                    candidate_rank=None,
                    pool_rank=4,
                    industry_id="G",
                    industry_trigger_rank=4,
                    formal_candidate=False,
                    execution_replacement_order=2,
                    signal_status="FALSE",
                    signal_state="CONCENTRATION_EXCLUDED",
                ),
            )
        }

    def _days(self, dates, *, blocked, c_blocked=False):
        days = []
        for day in dates:
            bars = {
                "SH:600001": bar(day, 10, 10, suspended=blocked.get(day, False)),
                "SH:600002": bar(day, 10, 10),
                "SH:600003": bar(day, 10, 10, suspended=c_blocked and day == dates[1]),
                "SH:600004": bar(day, 10, 10),
            }
            days.append(market_day(day, bars))
        return days

    def test_formal_candidate_blocked_uses_same_industry_prior_order(self) -> None:
        dates = trading_dates(3)
        data = make_input(
            dates,
            self._days(dates, blocked={dates[1]: True}),
            signals_by_signal_date=self._signals(dates[0]),
        )
        result = run_backtest(
            data,
            config(strategy_id="S06", initial_cash=Decimal(100000), top_n=2, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        positions = {p.security_id: p.quantity for p in result.position_history if p.date == dates[1]}
        self.assertEqual(positions, {"SH:600002": 4900, "SH:600003": 4900})
        replacement = [o for o in result.orders if o.security_id == "SH:600003" and o.side == "BUY"][0]
        self.assertEqual(replacement.replacement_for, "SH:600001")
        self.assertEqual(replacement.replacement_reason, "SUSPENDED")
        self.assertEqual(replacement.original_candidate_rank, 1)
        self.assertFalse(replacement.formal_candidate)
        self.assertEqual(replacement.industry_trigger_rank, 3)
        self.assertEqual(
            [o.status for o in result.orders if o.security_id == "SH:600001" and o.side == "BUY"],
            ["UNFILLED"],
        )
        self.assertNotIn("SH:600004", positions)

    def test_first_replacement_blocked_falls_through_to_next(self) -> None:
        dates = trading_dates(3)
        data = make_input(
            dates,
            self._days(dates, blocked={dates[1]: True}, c_blocked=True),
            signals_by_signal_date=self._signals(dates[0]),
        )
        result = run_backtest(
            data,
            config(strategy_id="S06", initial_cash=Decimal(100000), top_n=2, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        positions = {p.security_id: p.quantity for p in result.position_history if p.date == dates[1]}
        self.assertEqual(positions, {"SH:600002": 4900, "SH:600004": 4900})
        self.assertEqual(
            [o.status for o in result.orders if o.security_id == "SH:600003" and o.side == "BUY"],
            ["UNFILLED"],
        )
        replacement = [o for o in result.orders if o.security_id == "SH:600004" and o.side == "BUY"][0]
        self.assertEqual(replacement.replacement_for, "SH:600001")
        self.assertEqual(replacement.industry_trigger_rank, 4)


class IndustryCapTests(unittest.TestCase):
    def test_s06_industry_cap_prevents_second_position(self) -> None:
        dates = trading_dates(3)
        days = [
            market_day(
                day,
                {
                    "SH:600001": bar(day, 10, 10),
                    "SH:600002": bar(day, 10, 10),
                    "SH:600003": bar(day, 10, 10),
                },
            )
            for day in dates
        ]
        signals = {
            dates[0]: (
                signal("SH:600001", dates[0], strategy_id="S06", candidate_rank=1, pool_rank=1, industry_id="G", industry_trigger_rank=1),
                signal("SH:600002", dates[0], strategy_id="S06", candidate_rank=2, pool_rank=2, industry_id="G", industry_trigger_rank=2),
                signal(
                    "SH:600003",
                    dates[0],
                    strategy_id="S06",
                    candidate_rank=None,
                    pool_rank=3,
                    industry_id="G",
                    industry_trigger_rank=3,
                    formal_candidate=False,
                    execution_replacement_order=1,
                    signal_status="FALSE",
                    signal_state="CONCENTRATION_EXCLUDED",
                ),
            )
        }
        result = run_backtest(
            make_input(dates, days, signals_by_signal_date=signals),
            config(
                strategy_id="S06",
                initial_cash=Decimal(100000),
                top_n=2,
                start_date=dates[1],
                s06_industry_cap=1,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        positions = {p.security_id for p in result.position_history if p.date == dates[1]}
        self.assertEqual(positions, {"SH:600001"})
        blocked = [o for o in result.orders if o.security_id in {"SH:600002", "SH:600003"} and o.side == "BUY"]
        self.assertTrue(blocked)
        self.assertTrue(all(order.status == "UNFILLED" and order.reason == "INDUSTRY_CAP" for order in blocked))


class InsufficientCashTests(unittest.TestCase):
    def test_cash_below_one_lot_does_not_create_position(self) -> None:
        dates = trading_dates(3)
        days = [market_day(day, {"SH:600001": bar(day, 10, 10)}) for day in dates]
        result = run_backtest(
            make_input(dates, days, signals_by_signal_date={dates[0]: (signal("SH:600001", dates[0]),)}),
            config(initial_cash=Decimal(50), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(result.fills, [])
        self.assertEqual(result.nav_points[-1].cash, Decimal(50))
        self.assertEqual(result.position_history, [])
        order = [o for o in result.orders if o.side == "BUY"][0]
        self.assertEqual(order.status, "UNFILLED")
        self.assertEqual(order.reason, "INSUFFICIENT_CASH")


class UnknownSignalTests(unittest.TestCase):
    def _data(self, dates, signal_item):
        days = [market_day(day, {"SH:600001": bar(day, 10, 10)}) for day in dates]
        return make_input(dates, days, signals_by_signal_date={dates[0]: (signal_item,)})

    def test_incomplete_pool_blocks_instead_of_trading_partial_rank(self) -> None:
        dates = trading_dates(3)
        item = signal("SH:600001", dates[0], pool_complete=False)
        result = run_backtest(
            self._data(dates, item),
            config(initial_cash=Decimal(100000), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("SIGNAL_POOL_INCOMPLETE" in item for item in result.blockers))

    def test_missing_candidate_rank_blocks(self) -> None:
        dates = trading_dates(3)
        item = signal("SH:600001", dates[0], candidate_rank=None)
        result = run_backtest(
            self._data(dates, item),
            config(initial_cash=Decimal(100000), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("CANDIDATE_RANK_MISSING" in item for item in result.blockers))

    def test_unknown_entry_conflict_blocks(self) -> None:
        dates = trading_dates(3)
        item = signal("SH:600001", dates[0], entry_conflict_exit="UNKNOWN")
        result = run_backtest(
            self._data(dates, item),
            config(initial_cash=Decimal(100000), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("ENTRY_CONFLICT_UNKNOWN" in item for item in result.blockers))


class OccupiedPositionTests(unittest.TestCase):
    def test_unsold_position_occupies_slot_and_cash_is_not_released(self) -> None:
        dates = trading_dates(4)
        days = []
        for day in dates:
            if day == dates[2]:
                bars = {
                    "SH:600001": bar(day, 10, 10),
                    "SH:600002": bar(day, 9, 9, limit_down=9),
                    "SH:600003": bar(day, 10, 10),
                    "SH:600004": bar(day, 10, 10),
                }
            else:
                bars = {sid: bar(day, 10, 10) for sid in ("SH:600001", "SH:600002", "SH:600003", "SH:600004")}
            days.append(market_day(day, bars))
        signals = {
            dates[0]: (
                signal("SH:600001", dates[0], candidate_rank=1, pool_rank=1),
                signal("SH:600002", dates[0], candidate_rank=2, pool_rank=2),
            ),
            dates[1]: (
                signal("SH:600003", dates[1], candidate_rank=1, pool_rank=1),
                signal("SH:600004", dates[1], candidate_rank=2, pool_rank=2),
            ),
        }
        result = run_backtest(
            make_input(dates, days, signals_by_signal_date=signals),
            config(initial_cash=Decimal(100000), top_n=2, rebalance_days=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        day2_positions = {
            p.security_id: p.quantity for p in result.position_history if p.date == dates[2]
        }
        self.assertEqual(set(day2_positions), {"SH:600002", "SH:600003"})
        failed_sell = [
            o for o in result.orders if o.security_id == "SH:600002" and o.side == "SELL" and o.attempt_date == dates[2]
        ][0]
        self.assertEqual(failed_sell.status, "UNFILLED")
        self.assertEqual(failed_sell.reason, "LIMIT_DOWN")
        self.assertNotIn("SH:600004", day2_positions)
        self.assertLess(result.nav_points[1].cash, Decimal(50000))


class S04NoAddTests(unittest.TestCase):
    def test_existing_s04_position_is_not_augmented(self) -> None:
        dates = trading_dates(3)
        days = []
        for day in dates:
            a = Decimal(10) if day == dates[1] else Decimal(5) if day == dates[2] else Decimal(10)
            bars = {"SH:600001": bar(day, a, a), "SH:600002": bar(day, 10, 10)}
            days.append(market_day(day, bars))
        signals = {
            dates[0]: (
                signal("SH:600001", dates[0], strategy_id="S04", candidate_rank=1, pool_rank=1),
                signal("SH:600002", dates[0], strategy_id="S04", candidate_rank=2, pool_rank=2),
            ),
            dates[1]: (
                signal("SH:600001", dates[1], strategy_id="S04", candidate_rank=1, pool_rank=1),
                signal("SH:600002", dates[1], strategy_id="S04", candidate_rank=2, pool_rank=2),
            ),
        }
        result = run_backtest(
            make_input(dates, days, signals_by_signal_date=signals),
            config(
                strategy_id="S04",
                initial_cash=Decimal(3000),
                top_n=2,
                rebalance_days=1,
                start_date=dates[1],
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        fills_on_day2 = [f for f in result.fills if f.date == dates[2]]
        self.assertEqual(fills_on_day2, [])


class FeesAndSlippageTests(unittest.TestCase):
    def test_buy_and_sell_fees_and_slippage(self) -> None:
        dates = trading_dates(3)
        days = [market_day(day, {"SH:600001": bar(day, 10, 10)}) for day in dates]
        signals = {dates[0]: (signal("SH:600001", dates[0]),)}
        exits = {dates[1]: (exit_request("SH:600001", dates[1]),)}
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date=signals,
                exit_requests_by_signal_date=exits,
                fees=synthetic_fees(
                    commission_rate=0,
                    min_commission=5,
                    slippage_rate="0.0005",
                    sell_tax_rate=0,
                    transfer_fee_rate=0,
                ),
            ),
            config(initial_cash=Decimal(1006), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        buy = [o for o in result.orders if o.side == "BUY"][0]
        sell = [o for o in result.orders if o.side == "SELL"][0]
        self.assertEqual(buy.price, Decimal("10.01"))
        self.assertEqual(buy.commission, Decimal(5))
        self.assertEqual(sell.price, Decimal("9.99"))
        self.assertEqual(sell.commission, Decimal(5))
        self.assertEqual(result.nav_points[-1].cash, Decimal("994.00"))

    def test_sell_tax_and_transfer_are_itemized(self) -> None:
        dates = trading_dates(3)
        days = [market_day(day, {"SH:600001": bar(day, 10, 10)}) for day in dates]
        signals = {dates[0]: (signal("SH:600001", dates[0]),)}
        exits = {dates[1]: (exit_request("SH:600001", dates[1]),)}
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date=signals,
                exit_requests_by_signal_date=exits,
                fees=synthetic_fees(
                    commission_rate=0,
                    min_commission=5,
                    slippage_rate=0,
                    sell_tax_rate="0.001",
                    transfer_fee_rate="0.00002",
                ),
            ),
            config(initial_cash=Decimal(1006), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        buy = [o for o in result.orders if o.side == "BUY"][0]
        sell = [o for o in result.orders if o.side == "SELL"][0]
        self.assertEqual(buy.commission, Decimal(5))
        self.assertEqual(buy.other_fees, Decimal("0.02"))
        self.assertEqual(sell.commission, Decimal(5))
        self.assertEqual(sell.other_fees, Decimal("1.02"))
        self.assertEqual(result.nav_points[-1].cash, Decimal("994.96"))
        self.assertTrue(all(item["cash_ok"] for item in result.reconciliation))
        self.assertTrue(all(item["equity_ok"] for item in result.reconciliation))


class SuspensionValuationTests(unittest.TestCase):
    def test_confirmed_suspension_uses_stale_mark_and_is_labeled(self) -> None:
        dates = trading_dates(4)
        days = []
        for index, day in enumerate(dates):
            if index >= 2:
                bars = {"SH:600001": bar(day, None, None, suspended=True)}
            else:
                bars = {"SH:600001": bar(day, 10, 10)}
            days.append(market_day(day, bars))
        result = run_backtest(
            make_input(dates, days, signals_by_signal_date={dates[0]: (signal("SH:600001", dates[0]),)}),
            config(initial_cash=Decimal(1005), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        suspended = [p for p in result.position_history if p.date == dates[2]][0]
        self.assertEqual(suspended.market_value, Decimal(1000))
        self.assertEqual(suspended.mark_status, "STALE_MARK_CONFIRMED_SUSPENSION")
        self.assertEqual(result.nav_points[-1].equity, Decimal(1000))


class RestrictionTests(unittest.TestCase):
    def test_buy_at_limit_up_is_unfilled(self) -> None:
        dates = trading_dates(3)
        days = []
        for day in dates:
            days.append(
                market_day(
                    day,
                    {"SH:600001": bar(day, 10, 10, limit_up=10 if day == dates[1] else None)},
                )
            )
        result = run_backtest(
            make_input(dates, days, signals_by_signal_date={dates[0]: (signal("SH:600001", dates[0]),)}),
            config(initial_cash=Decimal(100000), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        buy = [o for o in result.orders if o.side == "BUY"][0]
        self.assertEqual(buy.status, "UNFILLED")
        self.assertEqual(buy.reason, "LIMIT_UP")
        self.assertEqual(result.nav_points[-1].cash, Decimal(100000))

    def test_sell_delay_keeps_position_until_sellable(self) -> None:
        dates = trading_dates(4)
        days = [market_day(day, {"SH:600001": bar(day, 10, 10)}) for day in dates]
        signals = {dates[0]: (signal("SH:600001", dates[0]),)}
        exits = {dates[1]: (exit_request("SH:600001", dates[1]),)}
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date=signals,
                exit_requests_by_signal_date=exits,
                rules=(synthetic_rule(sell_delay_days=2),),
            ),
            config(initial_cash=Decimal(1005), top_n=1, start_date=dates[1], stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        day2_sell = [o for o in result.orders if o.side == "SELL" and o.attempt_date == dates[2]][0]
        self.assertEqual(day2_sell.status, "UNFILLED")
        self.assertEqual(day2_sell.reason, "T_SELL_RESTRICTED")
        day3_sell = [o for o in result.orders if o.side == "SELL" and o.attempt_date == dates[3]][0]
        self.assertEqual(day3_sell.status, "FILLED")


class DeterminismTests(unittest.TestCase):
    def test_same_input_twice_gives_identical_orders_positions_cash_and_nav(self) -> None:
        dates = trading_dates(5)
        days = []
        for index, day in enumerate(dates):
            c_price = Decimal("9") if index == 2 else Decimal("10")
            days.append(
                market_day(
                    day,
                    {
                        "SH:600001": bar(day, 10, 10, suspended=index == 1),
                        "SH:600002": bar(day, 10, 10),
                        "SH:600003": bar(day, c_price, c_price, limit_down=Decimal(9) if index == 2 else None),
                    },
                )
            )
        signals = {
            dates[0]: (
                signal("SH:600001", dates[0], candidate_rank=1, pool_rank=1),
                signal("SH:600002", dates[0], candidate_rank=2, pool_rank=2),
                signal("SH:600003", dates[0], candidate_rank=3, pool_rank=3),
            )
        }
        exits = {dates[1]: (exit_request("SH:600003", dates[1]),)}
        data = make_input(dates, days, signals_by_signal_date=signals, exit_requests_by_signal_date=exits)
        cfg = config(start_date=dates[1], top_n=2, stop_loss=None)
        first = run_backtest(data, cfg)
        second = run_backtest(data, cfg)
        self.assertEqual(first.status, second.status)
        self.assertEqual(first.orders, second.orders)
        self.assertEqual(first.fills, second.fills)
        self.assertEqual(first.nav_points, second.nav_points)
        self.assertEqual(first.position_history, second.position_history)
        self.assertEqual(first.closed_cycles, second.closed_cycles)
        self.assertEqual(first.metrics, second.metrics)


if __name__ == "__main__":
    unittest.main()
