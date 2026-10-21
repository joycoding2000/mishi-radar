from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

from mishi_radar.cash_backtest.engine import _Engine, run_backtest
from mishi_radar.cash_backtest.model import BacktestConfig, CorporateAction

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

SID = "SH:600001"
IDS = [SID, "SH:600002", "SH:600003"]


class ExecutionDefectTests(unittest.TestCase):
    def test_full_slots_still_allow_existing_position_topup(self) -> None:
        dates = trading_dates(3)
        days = []
        for index, day in enumerate(dates):
            days.append(
                market_day(
                    day,
                    {
                        SID: bar(day, 20 if index == 2 else 10, 20 if index == 2 else 10),
                        IDS[1]: bar(day, 10, 10),
                    },
                )
            )
        signals = {
            dates[index]: (
                signal(SID, dates[index], candidate_rank=1),
                signal(IDS[1], dates[index], candidate_rank=2),
            )
            for index in (0, 1)
        }
        result = run_backtest(
            make_input(dates, days, signals_by_signal_date=signals, fees=synthetic_fees(min_commission=0)),
            config(
                start_date=dates[1],
                rebalance_days=1,
                top_n=2,
                initial_cash=Decimal(100000),
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        positions = {item.security_id: item.quantity for item in result.final_positions}
        self.assertEqual(positions, {SID: 3750, IDS[1]: 7500})
        self.assertEqual(result.nav_points[-1].cash, Decimal(0))

    def test_partial_target_reduction_respects_sell_lot_size(self) -> None:
        dates = trading_dates(3)
        days = []
        for index, day in enumerate(dates):
            days.append(
                market_day(
                    day,
                    {
                        SID: bar(day, 20 if index == 2 else 10, 20 if index == 2 else 10),
                        IDS[1]: bar(day, 10, 10),
                    },
                )
            )
        signals = {
            dates[index]: (
                signal(SID, dates[index], candidate_rank=1),
                signal(IDS[1], dates[index], candidate_rank=2),
            )
            for index in (0, 1)
        }
        rule = replace(synthetic_rule(lot_size=100), sell_lot_size=100)
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date=signals,
                rules=(rule,),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=dates[1],
                rebalance_days=1,
                top_n=2,
                initial_cash=Decimal(10000),
                stop_loss=None,
            ),
        )
        sells = [fill.quantity for fill in result.fills if fill.side == "SELL"]
        self.assertTrue(sells)
        self.assertTrue(all(quantity % 100 == 0 for quantity in sells))

    def test_failed_rank_removal_retries_next_open(self) -> None:
        dates = trading_dates(5)
        days = []
        for index, day in enumerate(dates):
            days.append(
                market_day(
                    day,
                    {
                        SID: bar(
                            day,
                            9 if index == 3 else 10,
                            9 if index == 3 else 10,
                            limit_down=9 if index == 3 else None,
                        )
                    },
                )
            )
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]),)},
                fees=synthetic_fees(min_commission=0),
            ),
            config(start_date=dates[1], rebalance_days=2, top_n=1, initial_cash=Decimal(1000), stop_loss=None),
        )
        sell_orders = [(order.attempt_date, order.status) for order in result.orders if order.side == "SELL"]
        self.assertIn((dates[4], "FILLED"), sell_orders)
        self.assertEqual(result.final_positions, [])

    def test_locked_exits_sort_by_first_trigger_date(self) -> None:
        dates = trading_dates(6)

        def bars(index, day):
            return {
                SID: bar(day, 10, 10, suspended=index == 3),
                IDS[1]: bar(day, 10, 10, suspended=index in (2, 3)),
            }

        days = [market_day(day, bars(index, day)) for index, day in enumerate(dates)]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]), signal(IDS[1], dates[0], candidate_rank=2))},
                exit_requests_by_signal_date={
                    dates[1]: (exit_request(IDS[1], dates[1]),),
                    dates[2]: (exit_request(SID, dates[2]),),
                },
                fees=synthetic_fees(min_commission=0),
            ),
            config(start_date=dates[1], rebalance_days=20, top_n=2, initial_cash=Decimal(2000), stop_loss=None),
        )
        filled = [fill.security_id for fill in result.fills if fill.side == "SELL" and fill.date == dates[4]]
        self.assertEqual(filled, [IDS[1], SID])

    def test_slipped_sell_exactly_at_limit_down_is_legal(self) -> None:
        dates = trading_dates(3)
        days = [
            market_day(dates[0], {SID: bar(dates[0], 10, 10)}),
            market_day(dates[1], {SID: bar(dates[1], 10, 10)}),
            market_day(
                dates[2],
                {
                    SID: bar(
                        dates[2],
                        Decimal("10.01"),
                        Decimal("10.01"),
                        high=Decimal("10.01"),
                        low=Decimal("9.99"),
                        limit_down=Decimal("9.99"),
                    )
                },
            ),
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]),)},
                exit_requests_by_signal_date={dates[1]: (exit_request(SID, dates[1]),)},
                fees=synthetic_fees(min_commission=0, slippage_rate=Decimal("0.001")),
            ),
            config(start_date=dates[1], top_n=1, initial_cash=Decimal(1001), stop_loss=None),
        )
        sells = [order for order in result.orders if order.side == "SELL"]
        self.assertTrue(sells)
        self.assertEqual(sells[0].status, "FILLED")
        self.assertEqual(sells[0].price, Decimal("9.99"))

    def test_blocked_prefix_with_unreached_segment_returns_result(self) -> None:
        dates = trading_dates(5)
        days = [
            market_day(dates[0], {SID: bar(dates[0], 10, 10)}),
            market_day(dates[1], {SID: bar(dates[1], 10, 10)}),
            market_day(dates[2], {SID: bar(dates[2], 10, None)}),
            market_day(dates[3], {SID: bar(dates[3], 10, 10)}),
            market_day(dates[4], {SID: bar(dates[4], 10, 10)}),
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]),)},
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=dates[1],
                top_n=1,
                initial_cash=Decimal(1000),
                stop_loss=None,
                segment_boundaries=(dates[3],),
            ),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(len(result.nav_points), 1)
        self.assertIsInstance(result.fixed_segment_returns, dict)

    def test_bar_business_date_mismatch_blocks(self) -> None:
        dates = trading_dates(2)
        mismatched = replace(bar(dates[1], 10, 10), date=dates[0])
        days = [
            market_day(dates[0], {SID: bar(dates[0], 10, 10)}),
            market_day(dates[1], {SID: mismatched}),
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]),)},
                fees=synthetic_fees(min_commission=0),
            ),
            config(start_date=dates[1], top_n=1, initial_cash=Decimal(1000), stop_loss=None),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("BAR_BUSINESS_DATE_MISMATCH" in item for item in result.blockers))

    def test_negative_bar_amount_blocks(self) -> None:
        dates = trading_dates(2)
        days = [
            market_day(dates[0], {SID: bar(dates[0], 10, 10)}),
            market_day(dates[1], {SID: bar(dates[1], 10, 10, amount=-1)}),
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]),)},
                fees=synthetic_fees(min_commission=0),
            ),
            config(start_date=dates[1], top_n=1, initial_cash=Decimal(1000), stop_loss=None),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("NEGATIVE_BAR_AMOUNT" in item for item in result.blockers))

    def test_s07_default_rebalance_is_twenty_days(self) -> None:
        self.assertEqual(BacktestConfig(strategy_id="S07").rebalance_days, 20)
        self.assertEqual(BacktestConfig(strategy_id="S01").rebalance_days, 5)


class CorporateActionDefectTests(unittest.TestCase):
    def test_multiple_dividend_layers_use_old_share_entitlement(self) -> None:
        dates = trading_dates(5)
        ca1 = CorporateAction(SID, "CASH_DIVIDEND", dates[2], record_date=dates[1], pay_date=dates[2], cash_per_share=Decimal(1), dividend_tax_rate=Decimal(0))
        ca2 = CorporateAction(SID, "CASH_DIVIDEND", dates[3], record_date=dates[2], pay_date=dates[3], cash_per_share=Decimal(1), dividend_tax_rate=Decimal(0))
        prices = [10, 10, 9, 8, 20]
        days = [
            market_day(
                day,
                {SID: bar(day, prices[index], prices[index])},
                corporate_actions=(ca1,) if index == 2 else (ca2,) if index == 3 else (),
            )
            for index, day in enumerate(dates)
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[index]: (signal(SID, dates[index]),) for index in range(4)},
                rules=(synthetic_rule(lot_size=1),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(start_date=dates[1], rebalance_days=1, top_n=2, initial_cash=Decimal(2000), stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual([fill.quantity for fill in result.fills if fill.side == "SELL"], [37])
        self.assertEqual(result.final_positions[0].dividend_open, Decimal(137))

    def test_dividend_then_split_partial_sale_keeps_dividend_attribution(self) -> None:
        dates = trading_dates(5)
        dividend = CorporateAction(
            SID,
            "CASH_DIVIDEND",
            dates[2],
            record_date=dates[1],
            pay_date=dates[2],
            cash_per_share=Decimal(1),
            dividend_tax_rate=Decimal(0),
        )
        split = CorporateAction(
            SID,
            "BONUS_SHARES",
            dates[3],
            record_date=dates[2],
            share_multiplier=Decimal(2),
            new_share_sellable_date=dates[3],
        )
        prices = [Decimal(10), Decimal(10), Decimal(9), Decimal("4.5"), Decimal(20)]
        days = [
            market_day(
                day,
                {SID: bar(day, prices[index], prices[index])},
                corporate_actions=(dividend,) if index == 2 else (split,) if index == 3 else (),
            )
            for index, day in enumerate(dates)
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={
                    dates[0]: (signal(SID, dates[0]),),
                    dates[3]: (signal(SID, dates[3]),),
                },
                rules=(synthetic_rule(lot_size=1),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=dates[1],
                initial_cash=Decimal(10000),
                top_n=10,
                rebalance_days=3,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual([fill.quantity for fill in result.fills if fill.side == "SELL"], [134])
        position = result.final_positions[0]
        self.assertEqual(position.quantity, 66)
        self.assertEqual(position.dividend_open, Decimal(33))
        self.assertEqual(position.dividend_open, Decimal(100) * Decimal(position.quantity) / Decimal(200))

    def test_cancelled_corporate_action_does_not_block_record_date(self) -> None:
        dates = trading_dates(4)
        action = CorporateAction(
            SID,
            "CASH_DIVIDEND",
            dates[3],
            status="CANCELLED",
            record_date=dates[2],
            cash_per_share=Decimal(1),
            dividend_tax_rate=Decimal(0),
        )
        days = [
            market_day(day, {SID: bar(day, 10, 10)}, corporate_actions=(action,) if index == 3 else ())
            for index, day in enumerate(dates)
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]),)},
                fees=synthetic_fees(min_commission=0),
            ),
            config(start_date=dates[1], top_n=1, initial_cash=Decimal(1000), stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)

    def test_mixed_dividends_feed_open_position_stop(self) -> None:
        dates = trading_dates(6)
        ca1 = CorporateAction(SID, "CASH_DIVIDEND", dates[2], record_date=dates[1], pay_date=dates[2], cash_per_share=Decimal(1), dividend_tax_rate=Decimal(0))
        ca2 = CorporateAction(SID, "CASH_DIVIDEND", dates[3], record_date=dates[2], pay_date=dates[3], cash_per_share=Decimal(1), dividend_tax_rate=Decimal(0))
        prices = [10, 10, 9, 8, 7, 7]
        days = [
            market_day(
                day,
                {SID: bar(day, prices[index], prices[index])},
                corporate_actions=(ca1,) if index == 2 else (ca2,) if index == 3 else (),
            )
            for index, day in enumerate(dates)
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]),)},
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=dates[1],
                top_n=1,
                initial_cash=Decimal(1000),
                stop_loss=Decimal("0.08"),
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        stop_orders = [
            order for order in result.orders if order.side == "SELL" and order.reason == "STOP_LOSS"
        ]
        self.assertEqual(len(stop_orders), 1)
        self.assertEqual(stop_orders[0].attempt_date, dates[5])
        self.assertEqual(stop_orders[0].status, "FILLED")
        self.assertEqual(result.final_positions, [])
        self.assertEqual(result.closed_cycles[0].total_pnl, Decimal("-100"))

    def test_sold_bonus_rights_stay_in_one_original_cycle(self) -> None:
        dates = trading_dates(5)
        action = CorporateAction(
            SID,
            "BONUS_SHARES",
            dates[3],
            record_date=dates[1],
            share_multiplier=Decimal(2),
            new_share_sellable_date=dates[3],
        )
        prices = [Decimal(10), Decimal(10), Decimal(5), Decimal(5), Decimal(6)]
        days = [
            market_day(
                day,
                {SID: bar(day, prices[index], prices[index])},
                corporate_actions=(action,) if index == 3 else (),
            )
            for index, day in enumerate(dates)
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]),)},
                exit_requests_by_signal_date={
                    dates[1]: (exit_request(SID, dates[1]),),
                    dates[3]: (exit_request(SID, dates[3]),),
                },
                rules=(synthetic_rule(lot_size=1),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(start_date=dates[1], top_n=1, initial_cash=Decimal(1000), stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(result.final_positions, [])
        self.assertEqual(len(result.closed_cycles), 1)
        self.assertEqual(result.closed_cycles[0].total_pnl, Decimal(100))
        self.assertEqual(result.nav_points[-1].cash, Decimal(1100))

    def test_fractional_cash_enters_original_cycle(self) -> None:
        dates = trading_dates(4)
        action = CorporateAction(
            SID,
            "MERGE",
            dates[2],
            record_date=dates[1],
            share_multiplier=Decimal("0.5"),
            cash_in_lieu=Decimal(10),
        )
        days = []
        for index, day in enumerate(dates):
            price = Decimal(10) if index < 2 else Decimal(20)
            days.append(
                market_day(
                    day,
                    {SID: bar(day, price, price)},
                    corporate_actions=(action,) if index == 2 else (),
                )
            )
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]),)},
                exit_requests_by_signal_date={dates[2]: (exit_request(SID, dates[2]),)},
                rules=(synthetic_rule(lot_size=1),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(start_date=dates[1], top_n=1, initial_cash=Decimal(30), stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(result.nav_points[-1].cash, Decimal(30))
        self.assertEqual(result.nav_points[-1].nav, Decimal(1))
        self.assertEqual(result.closed_cycles[0].total_pnl, Decimal(0))

    def test_bonus_delivery_with_default_stop_does_not_block(self) -> None:
        dates = trading_dates(5)
        action = CorporateAction(
            SID,
            "BONUS_SHARES",
            dates[3],
            record_date=dates[1],
            share_multiplier=Decimal(2),
            new_share_sellable_date=dates[3],
        )
        prices = [Decimal(10), Decimal(10), Decimal(5), Decimal(5), Decimal(5)]
        days = [
            market_day(
                day,
                {SID: bar(day, prices[index], prices[index])},
                corporate_actions=(action,) if index == 3 else (),
            )
            for index, day in enumerate(dates)
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]),)},
                exit_requests_by_signal_date={dates[1]: (exit_request(SID, dates[1]),)},
                rules=(synthetic_rule(lot_size=1),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=dates[1],
                top_n=1,
                initial_cash=Decimal(1000),
                rebalance_days=20,
                stop_loss=Decimal("0.08"),
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual([position.quantity for position in result.final_positions], [100])
        self.assertEqual(result.nav_points[-1].equity, Decimal(1000))

    def test_bonus_delivery_after_reentry_preserves_both_quantities(self) -> None:
        dates = trading_dates(5)
        action = CorporateAction(
            SID,
            "BONUS_SHARES",
            dates[4],
            record_date=dates[1],
            share_multiplier=Decimal(2),
            new_share_sellable_date=dates[4],
        )
        prices = [Decimal(10), Decimal(10), Decimal(5), Decimal(5), Decimal(5)]
        days = [
            market_day(
                day,
                {SID: bar(day, prices[index], prices[index])},
                corporate_actions=(action,) if index == 4 else (),
            )
            for index, day in enumerate(dates)
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={
                    dates[0]: (signal(SID, dates[0]),),
                    dates[2]: (signal(SID, dates[2]),),
                },
                exit_requests_by_signal_date={dates[1]: (exit_request(SID, dates[1]),)},
                rules=(synthetic_rule(lot_size=1),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=dates[1],
                top_n=1,
                initial_cash=Decimal(1000),
                rebalance_days=2,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(sum(position.quantity for position in result.final_positions), 200)
        self.assertEqual(result.nav_points[-1].equity, Decimal(1000))

    def test_bonus_delivery_after_reentry_keeps_separate_cycle_attribution(self) -> None:
        dates = trading_dates(6)
        action = CorporateAction(
            SID,
            "BONUS_SHARES",
            dates[4],
            record_date=dates[1],
            share_multiplier=Decimal(2),
            new_share_sellable_date=dates[4],
        )
        prices = [
            Decimal(10),
            Decimal(10),
            Decimal(5),
            Decimal(5),
            Decimal(5),
            Decimal(6),
        ]
        days = [
            market_day(
                day,
                {SID: bar(day, prices[index], prices[index])},
                corporate_actions=(action,) if index == 4 else (),
            )
            for index, day in enumerate(dates)
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={
                    dates[0]: (signal(SID, dates[0]),),
                    dates[2]: (signal(SID, dates[2]),),
                },
                exit_requests_by_signal_date={
                    dates[1]: (exit_request(SID, dates[1]),),
                    dates[4]: (exit_request(SID, dates[4]),),
                },
                rules=(synthetic_rule(lot_size=1),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=dates[1],
                top_n=1,
                initial_cash=Decimal(1000),
                rebalance_days=2,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(result.nav_points[-1].cash, Decimal(1200))
        self.assertEqual(result.metrics["closed_cycle_count"], Decimal(2))
        self.assertFalse(
            any(warning.startswith("PENDING_CYCLE_MERGED_REENTRY") for warning in result.warnings)
        )
        cycles = sorted(
            (cycle.opened_on, cycle.closed_on, cycle.total_pnl)
            for cycle in result.closed_cycles
        )
        self.assertEqual(
            cycles,
            [
                (dates[1], dates[5], Decimal(100)),
                (dates[3], dates[5], Decimal(100)),
            ],
        )

    def test_parallel_holding_same_day_sell_combines_minimum_commission(self) -> None:
        dates = trading_dates(6)
        action = CorporateAction(
            SID,
            "BONUS_SHARES",
            dates[4],
            record_date=dates[1],
            share_multiplier=Decimal(2),
            new_share_sellable_date=dates[4],
        )
        prices = [
            Decimal(10),
            Decimal(10),
            Decimal(5),
            Decimal(5),
            Decimal(5),
            Decimal(6),
        ]
        days = [
            market_day(
                day,
                {SID: bar(day, prices[index], prices[index])},
                corporate_actions=(action,) if index == 4 else (),
            )
            for index, day in enumerate(dates)
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={
                    dates[0]: (signal(SID, dates[0]),),
                    dates[2]: (signal(SID, dates[2]),),
                },
                exit_requests_by_signal_date={
                    dates[1]: (exit_request(SID, dates[1]),),
                    dates[4]: (exit_request(SID, dates[4]),),
                },
                rules=(synthetic_rule(lot_size=1),),
                fees=synthetic_fees(commission_rate=Decimal("0.0003"), min_commission=5),
            ),
            config(
                start_date=dates[1],
                top_n=1,
                initial_cash=Decimal(1010),
                rebalance_days=2,
                stop_loss=None,
            ),
        )
        same_day_sells = [
            fill for fill in result.fills if fill.side == "SELL" and fill.date == dates[5]
        ]
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(sum(fill.quantity for fill in same_day_sells), 199)
        self.assertEqual(sum(fill.gross for fill in same_day_sells), Decimal(1194))
        self.assertEqual(sum(fill.commission for fill in same_day_sells), Decimal(5))
        self.assertEqual(result.nav_points[-1].cash, Decimal(1189))

    def test_locked_exit_retries_legacy_holding_after_main_position_closes(self) -> None:
        dates = trading_dates(7)
        action = CorporateAction(
            SID,
            "BONUS_SHARES",
            dates[4],
            record_date=dates[1],
            share_multiplier=Decimal(2),
            new_share_sellable_date=dates[6],
        )
        prices = [
            Decimal(10),
            Decimal(10),
            Decimal(5),
            Decimal(5),
            Decimal(5),
            Decimal(6),
            Decimal(6),
        ]
        days = [
            market_day(
                day,
                {SID: bar(day, prices[index], prices[index])},
                corporate_actions=(action,) if index == 4 else (),
            )
            for index, day in enumerate(dates)
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={
                    dates[0]: (signal(SID, dates[0]),),
                    dates[2]: (signal(SID, dates[2]),),
                },
                exit_requests_by_signal_date={
                    dates[1]: (exit_request(SID, dates[1]),),
                    dates[4]: (exit_request(SID, dates[4]),),
                },
                rules=(synthetic_rule(lot_size=1),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=dates[1],
                top_n=1,
                initial_cash=Decimal(1000),
                rebalance_days=2,
                stop_loss=None,
            ),
        )
        first_attempt = [
            fill for fill in result.fills if fill.side == "SELL" and fill.date == dates[5]
        ]
        retry = [
            fill for fill in result.fills if fill.side == "SELL" and fill.date == dates[6]
        ]
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(sum(fill.quantity for fill in first_attempt), 100)
        self.assertEqual(sum(fill.quantity for fill in retry), 100)
        self.assertEqual(sum(position.quantity for position in result.final_positions), 0)
        self.assertEqual(result.nav_points[-1].cash, Decimal(1200))

    def test_external_fractional_cash_stays_in_original_cycle(self) -> None:
        dates = trading_dates(5)
        action = CorporateAction(
            SID,
            "BONUS_SHARES",
            dates[3],
            record_date=dates[1],
            share_multiplier=Decimal("1.5"),
            new_share_sellable_date=dates[3],
            cash_in_lieu=Decimal(3),
        )
        prices = [Decimal(10), Decimal(10), Decimal(6), Decimal(6), Decimal(6)]
        days = [
            market_day(
                day,
                {SID: bar(day, prices[index], prices[index])},
                corporate_actions=(action,) if index == 3 else (),
            )
            for index, day in enumerate(dates)
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]),)},
                exit_requests_by_signal_date={
                    dates[1]: (exit_request(SID, dates[1]),),
                    dates[3]: (exit_request(SID, dates[3]),),
                },
                rules=(synthetic_rule(lot_size=1),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(start_date=dates[1], top_n=1, initial_cash=Decimal(30), stop_loss=None),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(result.nav_points[-1].cash, Decimal(27))
        self.assertEqual(len(result.closed_cycles), 1)
        self.assertEqual(result.closed_cycles[0].total_pnl, Decimal(-3))
        self.assertEqual(sum((cycle.total_pnl for cycle in result.closed_cycles), Decimal(0)), Decimal(-3))

    def test_bonus_adjusts_fixed_s02_platform(self) -> None:
        dates = trading_dates(3)
        action = CorporateAction(
            SID,
            "BONUS_SHARES",
            dates[2],
            record_date=dates[1],
            share_multiplier=Decimal(2),
            new_share_sellable_date=dates[2],
        )
        days = [
            market_day(dates[0], {SID: bar(dates[0], 10, 10)}),
            market_day(dates[1], {SID: bar(dates[1], 10, 10)}),
            market_day(
                dates[2],
                {SID: bar(dates[2], 5, 5)},
                corporate_actions=(action,),
            ),
        ]
        data = make_input(
            dates,
            days,
            signals_by_signal_date={
                dates[0]: (signal(SID, dates[0], strategy_id="S02", entry_platform_upper=10),)
            },
            fees=synthetic_fees(min_commission=0),
        )
        engine = _Engine(
            data,
            config(
                strategy_id="S02",
                start_date=dates[1],
                top_n=1,
                initial_cash=Decimal(1000),
                stop_loss=None,
            ),
        )
        engine._prepare()
        engine._run_day(dates[1], 0)
        engine._run_day(dates[2], 1)
        position = engine.positions[SID]
        self.assertEqual(position.quantity, 200)
        self.assertEqual(position.cost_open, Decimal(1000))
        self.assertEqual(position.entry_platform_upper, Decimal(5))


if __name__ == "__main__":
    unittest.main()
