from __future__ import annotations

import unittest
from datetime import date
from decimal import Decimal

from mishi_radar.cash_backtest.engine import run_backtest
from mishi_radar.cash_backtest.model import (
    CorporateAction,
    DividendTaxBinding,
    EligibilityRecord,
    EligibilitySnapshot,
    SignalBatch,
)

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
A = "SH:600001"
B = "SH:600002"
H = "SH:600003"


def _batch(
    *,
    strategy_id: str = "S01",
    config_id: str = "S01_DEFAULT",
    config_version: str = "S01_DEFAULT/SYNTHETIC",
    signal_date: str,
    available_at: str,
    status: str = "COMPLETE",
    signals: tuple = (),
    coverage_until: str | None = None,
) -> SignalBatch:
    return SignalBatch(
        strategy_id=strategy_id,
        config_id=config_id,
        config_version=config_version,
        signal_date=signal_date,
        available_at=available_at,
        status=status,
        signals=signals,
        coverage_until=coverage_until,
    )


class X01BatchWindowTests(unittest.TestCase):
    def test_late_rebalance_proposal_gets_one_deferred_attempt_r1(self) -> None:
        dates = trading_dates(3, end=date(2026, 10, 14))
        signal_date, anchor, attempt = dates[0], dates[1], dates[2]
        days = [market_day(day, {A: bar(day, 5, 5)}) for day in dates]
        item = signal(A, signal_date)
        batch = _batch(
            signal_date=signal_date,
            available_at=f"{anchor}T09:30:01",
            signals=(item,),
            coverage_until=f"{attempt}T09:30:00",
        )
        result = run_backtest(
            make_input(
                dates,
                days,
                signal_batches=(batch,),
                rules=(synthetic_rule(lot_size=100),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=anchor,
                initial_cash=Decimal(1005),
                top_n=1,
                rebalance_days=1,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(
            [(fill.date, fill.quantity, fill.price) for fill in result.fills],
            [(attempt, 200, Decimal(5))],
        )
        statuses = [entry["status"] for entry in result.proposal_entries]
        self.assertIn("PENDING", statuses)
        self.assertIn("FILLED", statuses)

    def test_published_time_after_necessary_info_controls_window(self) -> None:
        dates = trading_dates(4, end=date(2026, 10, 15))
        signal_date, anchor, attempt = dates[0], dates[1], dates[2]
        days = [market_day(day, {A: bar(day, 5, 5)}) for day in dates]
        batch = _batch(
            signal_date=signal_date,
            available_at=f"{anchor}T09:00:00",
            signals=(signal(A, signal_date),),
            coverage_until=f"{attempt}T09:30:00",
        )
        batch = SignalBatch(
            strategy_id=batch.strategy_id,
            config_id=batch.config_id,
            config_version=batch.config_version,
            signal_date=batch.signal_date,
            available_at=batch.available_at,
            status=batch.status,
            signals=batch.signals,
            coverage_until=batch.coverage_until,
            published_at=f"{anchor}T09:30:01",
        )
        result = run_backtest(
            make_input(
                dates,
                days,
                signal_batches=(batch,),
                rules=(synthetic_rule(lot_size=100),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=anchor,
                initial_cash=Decimal(1005),
                top_n=1,
                rebalance_days=5,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual([(fill.date, fill.quantity) for fill in result.fills], [(attempt, 200)])

    def test_late_proposal_can_use_non_rebalance_open_once_r5(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        signal_date, anchor, attempt = dates[0], dates[1], dates[2]
        days = [market_day(day, {A: bar(day, 5, 5)}) for day in dates]
        batch = _batch(
            signal_date=signal_date,
            available_at=f"{anchor}T09:30:01",
            signals=(signal(A, signal_date),),
            coverage_until=f"{attempt}T09:30:00",
        )
        result = run_backtest(
            make_input(
                dates,
                days,
                signal_batches=(batch,),
                rules=(synthetic_rule(lot_size=100),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=anchor,
                initial_cash=Decimal(1005),
                top_n=1,
                rebalance_days=5,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(len(result.fills), 1)
        self.assertEqual(result.fills[0].date, attempt)
        self.assertEqual(result.fills[0].quantity, 200)
        self.assertTrue(
            any(
                entry["status"] == "ATTEMPTING" and entry["reason"] == "DEFERRED_ATTEMPT"
                for entry in result.proposal_entries
            )
        )

    def _replacement_case(self, status: str, signals: tuple = ()) -> object:
        dates = trading_dates(5, end=date(2026, 10, 16))
        signal_date, anchor, replacement_date = dates[0], dates[1], dates[2]
        days = [market_day(day, {A: bar(day, 5, 5), B: bar(day, 5, 5)}) for day in dates]
        old = _batch(
            signal_date=signal_date,
            available_at=f"{anchor}T09:30:01",
            signals=(signal(A, signal_date),),
            coverage_until=f"{dates[3]}T09:30:00",
        )
        new = _batch(
            signal_date=anchor,
            available_at=f"{anchor}T15:00:00",
            status=status,
            signals=signals,
            coverage_until=f"{dates[3]}T09:30:00",
        )
        return run_backtest(
            make_input(
                dates,
                days,
                signal_batches=(old, new),
                rules=(synthetic_rule(lot_size=100),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=anchor,
                initial_cash=Decimal(1005),
                top_n=1,
                rebalance_days=5,
                stop_loss=None,
            ),
        )

    def test_complete_new_batch_replaces_old_without_non_rebalance_buy(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        signal_date, anchor = dates[0], dates[1]
        result = self._replacement_case(
            "COMPLETE",
            (signal(B, anchor),),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(result.fills, [])
        self.assertTrue(any(entry["status"] == "REPLACED" for entry in result.proposal_entries))
        self.assertTrue(any(entry["status"] == "IGNORED" for entry in result.proposal_entries))

    def test_complete_empty_batch_replaces_old(self) -> None:
        result = self._replacement_case("COMPLETE_EMPTY")
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(result.fills, [])
        self.assertTrue(any(entry["status"] == "REPLACED" for entry in result.proposal_entries))
        self.assertTrue(any(entry["status"] == "EMPTY" for entry in result.proposal_entries))

    def test_missing_coverage_evidence_blocks_deferred_attempt(self) -> None:
        dates = trading_dates(4, end=date(2026, 10, 15))
        signal_date, anchor = dates[0], dates[1]
        days = [market_day(day, {A: bar(day, 5, 5)}) for day in dates]
        batch = _batch(
            signal_date=signal_date,
            available_at=f"{anchor}T09:30:01",
            signals=(signal(A, signal_date),),
            coverage_until=None,
        )
        result = run_backtest(
            make_input(
                dates,
                days,
                signal_batches=(batch,),
                rules=(synthetic_rule(lot_size=100),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=anchor,
                initial_cash=Decimal(1005),
                top_n=1,
                rebalance_days=5,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("SIGNAL_BATCH_COVERAGE_UNKNOWN" in blocker for blocker in result.blockers))

    def test_unknown_replacement_blocks(self) -> None:
        result = self._replacement_case("UNKNOWN")
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("SIGNAL_BATCH_UNKNOWN" in blocker for blocker in result.blockers))
        self.assertEqual(result.fills, [])

    def test_failed_deferred_attempt_is_not_retried(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        signal_date, anchor, attempt, next_day = dates[0], dates[1], dates[2], dates[3]
        days = [
            market_day(
                day,
                {A: bar(day, 5, 5, suspended=(day == attempt))},
            )
            for day in dates
        ]
        batch = _batch(
            signal_date=signal_date,
            available_at=f"{anchor}T09:30:01",
            signals=(signal(A, signal_date),),
            coverage_until=f"{next_day}T09:30:00",
        )
        result = run_backtest(
            make_input(
                dates,
                days,
                signal_batches=(batch,),
                rules=(synthetic_rule(lot_size=100),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=anchor,
                initial_cash=Decimal(1005),
                top_n=1,
                rebalance_days=5,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(result.fills, [])
        attempts = [order for order in result.orders if order.attempt_date == attempt]
        self.assertEqual(len(attempts), 1)
        self.assertEqual(attempts[0].reason, "SUSPENDED")
        self.assertFalse(any(order.attempt_date == next_day for order in result.orders))


class U1TimeContractTests(unittest.TestCase):
    def test_offset_signal_is_rejected_at_consumption_boundary(self) -> None:
        day = trading_dates(1)[0]
        with self.assertRaises(ValueError):
            signal(A, day, available_at=f"{day}T02:00:00Z")
        with self.assertRaises(ValueError):
            _batch(
                signal_date=day,
                available_at=f"{day}T10:00:00+08:00",
                coverage_until=f"{day}T15:00:00",
            )

    def test_normalized_after_open_time_does_not_fill_same_open(self) -> None:
        dates = trading_dates(2, end=date(2026, 10, 15))
        signal_day, trade_day = dates
        days = [market_day(day, {A: bar(day, 5, 5)}) for day in dates]
        item = signal(A, signal_day, available_at=f"{trade_day}T10:00:00")
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={signal_day: (item,)},
                rules=(synthetic_rule(lot_size=100),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=trade_day,
                initial_cash=Decimal(1005),
                top_n=1,
                rebalance_days=1,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(result.fills, [])


class U2EligibilityTests(unittest.TestCase):
    def _eligibility(self, dates):
        return {
            dates[0]: EligibilitySnapshot(
                date=dates[0],
                records=tuple(
                    EligibilityRecord(sid, "ELIGIBLE", dates[0], f"{dates[0]}T08:00:00")
                    for sid in (A, B, H)
                ),
            ),
            dates[1]: EligibilitySnapshot(
                date=dates[1],
                records=tuple(
                    EligibilityRecord(sid, "ELIGIBLE", dates[0], f"{dates[0]}T08:00:00")
                    for sid in (A, B, H)
                ),
            ),
            dates[2]: EligibilitySnapshot(
                date=dates[2],
                records=(
                    EligibilityRecord(
                        A,
                        "INELIGIBLE",
                        dates[2],
                        f"{dates[2]}T08:00:00",
                        effective_to=dates[2],
                        reason="ST",
                    ),
                    EligibilityRecord(B, "ELIGIBLE", dates[0], f"{dates[1]}T08:00:00"),
                    EligibilityRecord(
                        H,
                        "INELIGIBLE",
                        dates[2],
                        f"{dates[2]}T08:00:00",
                        effective_to=dates[2],
                        reason="ST",
                    ),
                ),
            ),
            dates[3]: EligibilitySnapshot(
                date=dates[3],
                records=tuple(
                    EligibilityRecord(sid, "ELIGIBLE", dates[0], f"{dates[3]}T08:00:00")
                    for sid in (A, B, H)
                ),
            ),
            dates[4]: EligibilitySnapshot(
                date=dates[4],
                records=tuple(
                    EligibilityRecord(sid, "ELIGIBLE", dates[0], f"{dates[4]}T08:00:00")
                    for sid in (A, B, H)
                ),
            ),
        }

    def test_ineligible_candidate_is_replaced_and_held_lock_retries(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        days = []
        for index, day in enumerate(dates):
            bars = {
                A: bar(day, 5, 5),
                B: bar(day, 5, 5),
                H: bar(day, 10, 10, suspended=(index == 2)),
            }
            days.append(market_day(day, bars))
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={
                    dates[0]: (signal(H, dates[0], candidate_rank=1),),
                    dates[1]: (
                        signal(A, dates[1], candidate_rank=1),
                        signal(B, dates[1], candidate_rank=2),
                    ),
                },
                exit_requests_by_signal_date={},
                eligibility_by_date=self._eligibility(dates),
                rules=(synthetic_rule(lot_size=100),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=dates[1],
                initial_cash=Decimal(2000),
                top_n=2,
                rebalance_days=1,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        fills = [(fill.side, fill.security_id, fill.date, fill.quantity) for fill in result.fills]
        self.assertIn(("BUY", H, dates[1], 100), fills)
        self.assertTrue(
            any(fill[0] == "BUY" and fill[1] == B and fill[2] == dates[2] for fill in fills)
        )
        self.assertFalse(
            any(fill[0] == "BUY" and fill[1] == A and fill[2] == dates[2] for fill in fills)
        )
        self.assertIn(("SELL", H, dates[3], 100), fills)
        self.assertTrue(
            any(
                order.security_id == A
                and order.attempt_date == dates[2]
                and order.reason == "ELIGIBILITY_INELIGIBLE"
                for order in result.orders
            )
        )
        self.assertTrue(
            any(
                entry["security_id"] == H and entry["status"] == "INELIGIBLE"
                for entry in result.eligibility_entries
            )
        )
        self.assertTrue(
            any(
                order.security_id == H
                and order.attempt_date == dates[3]
                and order.reason == "ELIGIBILITY_RISK"
                for order in result.orders
            )
        )

    def test_eligibility_lock_retries_on_non_rebalance_day_after_recovery(self) -> None:
        dates = trading_dates(4, end=date(2026, 10, 15))
        days = [
            market_day(
                day,
                {H: bar(day, 10, 10, suspended=(index == 2))},
            )
            for index, day in enumerate(dates)
        ]
        eligibility = {
            dates[0]: EligibilitySnapshot(
                date=dates[0],
                records=(EligibilityRecord(H, "ELIGIBLE", dates[0], f"{dates[0]}T08:00:00"),),
            ),
            dates[1]: EligibilitySnapshot(
                date=dates[1],
                records=(EligibilityRecord(H, "ELIGIBLE", dates[0], f"{dates[1]}T08:00:00"),),
            ),
            dates[2]: EligibilitySnapshot(
                date=dates[2],
                records=(
                    EligibilityRecord(
                        H,
                        "INELIGIBLE",
                        dates[2],
                        f"{dates[2]}T08:00:00",
                        effective_to=dates[2],
                        reason="ST",
                    ),
                ),
            ),
            dates[3]: EligibilitySnapshot(
                date=dates[3],
                records=(EligibilityRecord(H, "ELIGIBLE", dates[0], f"{dates[3]}T08:00:00"),),
            ),
        }
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(H, dates[0]),)},
                eligibility_by_date=eligibility,
                rules=(synthetic_rule(lot_size=100),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=dates[1],
                initial_cash=Decimal(1005),
                top_n=1,
                rebalance_days=5,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(
            [(fill.side, fill.security_id, fill.date) for fill in result.fills],
            [("BUY", H, dates[1]), ("SELL", H, dates[3])],
        )

    def test_missing_execution_day_snapshot_blocks(self) -> None:
        dates = trading_dates(2, end=date(2026, 10, 14))
        days = [market_day(day, {A: bar(day, 5, 5)}) for day in dates]
        eligibility = {
            dates[0]: EligibilitySnapshot(
                date=dates[0],
                records=(EligibilityRecord(A, "ELIGIBLE", dates[0], f"{dates[0]}T08:00:00"),),
            )
        }
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(A, dates[0]),)},
                eligibility_by_date=eligibility,
                rules=(synthetic_rule(lot_size=100),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=dates[1],
                initial_cash=Decimal(1005),
                top_n=1,
                rebalance_days=1,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("ELIGIBILITY_COVERAGE_MISSING" in blocker for blocker in result.blockers))

    def test_known_after_open_is_not_backfilled(self) -> None:
        dates = trading_dates(3, end=date(2026, 10, 15))
        eligibility = {
            dates[0]: EligibilitySnapshot(
                date=dates[0],
                records=tuple(
                    EligibilityRecord(sid, "ELIGIBLE", dates[0], f"{dates[0]}T08:00:00")
                    for sid in (A, B, H)
                ),
            ),
            dates[1]: EligibilitySnapshot(
                date=dates[1],
                records=tuple(
                    EligibilityRecord(sid, "ELIGIBLE", dates[0], f"{dates[1]}T08:00:00")
                    for sid in (A, B, H)
                ),
            ),
            dates[2]: EligibilitySnapshot(
                date=dates[2],
                records=(
                    EligibilityRecord(A, "INELIGIBLE", dates[2], f"{dates[2]}T10:00:00", reason="ST"),
                    EligibilityRecord(B, "ELIGIBLE", dates[0], f"{dates[1]}T08:00:00"),
                    EligibilityRecord(H, "ELIGIBLE", dates[0], f"{dates[1]}T08:00:00"),
                ),
            ),
        }
        days = [market_day(day, {A: bar(day, 5, 5), B: bar(day, 5, 5)}) for day in dates]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[1]: (signal(A, dates[1]),)},
                eligibility_by_date=eligibility,
                rules=(synthetic_rule(lot_size=100),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=dates[1],
                initial_cash=Decimal(1005),
                top_n=1,
                rebalance_days=1,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("ELIGIBILITY_NOT_KNOWN_AT_OPEN" in blocker for blocker in result.blockers))


class U3FeeTaxTests(unittest.TestCase):
    def test_overlapping_fee_versions_block_instead_of_choosing_latest(self) -> None:
        dates = trading_dates(2, end=date(2026, 10, 14))
        days = [market_day(day, {SID: bar(day, 5, 5)}) for day in dates]
        first = synthetic_fees(
            effective_from=dates[1],
            effective_to=dates[1],
            known_at=f"{dates[0]}T15:00:00",
            version="F1",
        )
        second = synthetic_fees(
            effective_from=dates[1],
            effective_to=dates[1],
            known_at=f"{dates[0]}T16:00:00",
            version="F2",
        )
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]),)},
                rules=(synthetic_rule(lot_size=100),),
                fees=first,
                fee_schedules=(first, second),
            ),
            config(
                start_date=dates[1],
                initial_cash=Decimal(1005),
                top_n=1,
                rebalance_days=1,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("FEE_SCHEDULE_CONFLICT" in blocker for blocker in result.blockers))

    def test_tax_known_after_ex_date_is_not_backfilled(self) -> None:
        dates = trading_dates(3, end=date(2026, 10, 15))
        action = CorporateAction(
            SID,
            "CASH_DIVIDEND",
            dates[2],
            record_date=dates[1],
            pay_date=dates[2],
            cash_per_share=Decimal(1),
            dividend_tax_bindings=(
                DividendTaxBinding(
                    acquisition_from=dates[1],
                    acquisition_to=dates[1],
                    tax_rate=Decimal("0.20"),
                    known_at=f"{dates[2]}T10:00:00",
                    rule_version="TAX-LATE",
                ),
            ),
        )
        days = [
            market_day(
                day,
                {SID: bar(day, 10, 10)},
                corporate_actions=(action,) if index == 2 else (),
            )
            for index, day in enumerate(dates)
        ]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]),)},
                rules=(synthetic_rule(lot_size=100),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(
                start_date=dates[1],
                initial_cash=Decimal(1005),
                top_n=1,
                rebalance_days=1,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("DIVIDEND_TAX" in blocker for blocker in result.blockers))

    def test_versioned_fees_and_per_lot_tax_match_approved_fixture(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        prices = [Decimal(10), Decimal(10), Decimal(6), Decimal(5), Decimal(5)]
        dividend = CorporateAction(
            SID,
            "CASH_DIVIDEND",
            dates[3],
            record_date=dates[2],
            pay_date=dates[4],
            cash_per_share=Decimal(1),
            dividend_tax_bindings=(
                DividendTaxBinding(
                    acquisition_from=dates[1],
                    acquisition_to=dates[1],
                    tax_rate=Decimal(0),
                    known_at=f"{dates[1]}T15:00:00",
                    rule_version="TAX-D1",
                ),
                DividendTaxBinding(
                    acquisition_from=dates[2],
                    acquisition_to=dates[2],
                    tax_rate=Decimal("0.20"),
                    known_at=f"{dates[1]}T15:00:00",
                    rule_version="TAX-D2",
                ),
            ),
        )
        days = [
            market_day(
                day,
                {SID: bar(day, prices[index], prices[index])},
                corporate_actions=(dividend,) if index == 3 else (),
            )
            for index, day in enumerate(dates)
        ]
        f1 = synthetic_fees(
            effective_from=dates[1],
            effective_to=dates[1],
            buy_tax_rate=Decimal(0),
            known_at=f"{dates[0]}T15:00:00",
            version="F1",
        )
        f2 = synthetic_fees(
            effective_from=dates[2],
            effective_to=dates[4],
            buy_tax_rate=Decimal("0.001"),
            known_at=f"{dates[1]}T15:00:00",
            version="F2",
        )
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={
                    dates[0]: (signal(SID, dates[0]),),
                    dates[1]: (signal(SID, dates[1]),),
                },
                exit_requests_by_signal_date={dates[2]: (exit_request(SID, dates[2]),)},
                rules=(synthetic_rule(lot_size=100),),
                fees=f1,
                fee_schedules=(f1, f2),
            ),
            config(
                start_date=dates[1],
                initial_cash=Decimal(4000),
                top_n=2,
                rebalance_days=1,
                stop_loss=None,
            ),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(result.nav_points[0].cash, Decimal("2995.00"))
        self.assertEqual(result.nav_points[0].equity, Decimal("3995.00"))
        self.assertEqual(result.nav_points[1].cash, Decimal("2389.40"))
        self.assertEqual(result.nav_points[1].equity, Decimal("3589.40"))
        self.assertEqual(result.nav_points[2].cash, Decimal("3384.40"))
        self.assertEqual(result.nav_points[2].equity, Decimal("3564.40"))
        self.assertEqual(result.nav_points[-1].cash, Decimal("3564.40"))
        self.assertEqual(result.nav_points[-1].equity, Decimal("3564.40"))
        self.assertEqual(len(result.closed_cycles), 1)
        cycle = result.closed_cycles[0]
        self.assertEqual(cycle.realized_trading_pnl, Decimal("-615.60"))
        self.assertEqual(cycle.realized_dividend, Decimal("180.00"))
        self.assertEqual(cycle.total_pnl, Decimal("-435.60"))
        taxes = sorted(entry["tax"] for entry in result.dividend_tax_entries)
        self.assertEqual(taxes, [Decimal(0), Decimal(20)])
        self.assertEqual([entry["version"] for entry in result.fee_entries], ["F1", "F2", "F2"])
        self.assertEqual([entry["commission"] for entry in result.fee_entries], [Decimal(5), Decimal(5), Decimal(5)])


if __name__ == "__main__":
    unittest.main()
