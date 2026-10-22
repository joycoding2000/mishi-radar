"""Permanent regressions for the G01-G07 gate findings and legacy boundary."""

from __future__ import annotations

import unittest
from dataclasses import replace
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
OTHER = "SH:600002"


def _eligibility(dates, status: str = "ELIGIBLE"):
    return {
        day: EligibilitySnapshot(
            day,
            (
                EligibilityRecord(SID, status, dates[0], f"{dates[0]}T08:00:00"),
                EligibilityRecord(OTHER, "ELIGIBLE", dates[0], f"{dates[0]}T08:00:00"),
            ),
        )
        for day in dates
    }


def _batch(
    *,
    signal_date: str,
    available_at: str,
    signals: tuple = (),
    coverage_until: str | None = None,
    status: str = "COMPLETE",
) -> SignalBatch:
    return SignalBatch(
        "S01",
        "S01_DEFAULT",
        "S01_DEFAULT/SYNTHETIC",
        signal_date,
        available_at,
        status=status,
        signals=signals,
        coverage_until=coverage_until,
    )


class GateBatchCoverageTests(unittest.TestCase):
    def test_g01_normal_batch_without_coverage_is_blocked(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        days = [market_day(day, {SID: bar(day, 5, 5)}) for day in dates]
        batch = _batch(
            signal_date=dates[0],
            available_at=f"{dates[0]}T15:00:00",
            signals=(signal(SID, dates[0]),),
            coverage_until=None,
        )
        result = run_backtest(
            make_input(dates, days, signal_batches=(batch,)),
            config(start_date=dates[1], initial_cash=Decimal(1005), top_n=1, rebalance_days=5),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("SIGNAL_BATCH_COVERAGE_UNKNOWN" in item for item in result.blockers))
        self.assertEqual(result.fills, [])

    def test_g01_coverage_that_ends_before_open_is_blocked(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        days = [market_day(day, {SID: bar(day, 5, 5)}) for day in dates]
        batch = _batch(
            signal_date=dates[0],
            available_at=f"{dates[0]}T15:00:00",
            signals=(signal(SID, dates[0]),),
            coverage_until=f"{dates[0]}T15:00:00",
        )
        result = run_backtest(
            make_input(dates, days, signal_batches=(batch,)),
            config(start_date=dates[1], initial_cash=Decimal(1005), top_n=1, rebalance_days=5),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("SIGNAL_BATCH_COVERAGE_INCOMPLETE" in item for item in result.blockers))


class GateBatchMemberTests(unittest.TestCase):
    def test_g02_member_not_available_at_anchor_open_is_deferred(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        days = [market_day(day, {SID: bar(day, 5, 5)}) for day in dates]
        late = signal(SID, dates[0], available_at=f"{dates[1]}T10:00:00")
        batch = _batch(
            signal_date=dates[0],
            available_at=f"{dates[0]}T15:00:00",
            signals=(late,),
            coverage_until=f"{dates[4]}T15:00:00",
        )
        result = run_backtest(
            make_input(dates, days, signal_batches=(batch,)),
            config(start_date=dates[1], initial_cash=Decimal(1005), top_n=1, rebalance_days=5),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertFalse(any(fill.date == dates[1] for fill in result.fills))
        self.assertEqual([(fill.date, fill.quantity) for fill in result.fills], [(dates[2], 200)])

    def test_g02_incomplete_pool_member_blocks(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        days = [market_day(day, {SID: bar(day, 5, 5)}) for day in dates]
        incomplete = replace(signal(SID, dates[0]), pool_complete=False)
        batch = _batch(
            signal_date=dates[0],
            available_at=f"{dates[0]}T15:00:00",
            signals=(incomplete,),
            coverage_until=f"{dates[4]}T15:00:00",
        )
        result = run_backtest(
            make_input(dates, days, signal_batches=(batch,)),
            config(start_date=dates[1], initial_cash=Decimal(1005), top_n=1, rebalance_days=5),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("SIGNAL_POOL_INCOMPLETE" in item for item in result.blockers))
        self.assertEqual(result.fills, [])

    def test_g02_unknown_member_availability_blocks(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        days = [market_day(day, {SID: bar(day, 5, 5)}) for day in dates]
        unknown = replace(
            signal(SID, dates[0]),
            available_at=None,
            available_at_kind="UNKNOWN",
        )
        batch = _batch(
            signal_date=dates[0],
            available_at=f"{dates[0]}T15:00:00",
            signals=(unknown,),
            coverage_until=f"{dates[4]}T15:00:00",
        )
        result = run_backtest(
            make_input(dates, days, signal_batches=(batch,)),
            config(start_date=dates[1], initial_cash=Decimal(1005), top_n=1, rebalance_days=5),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("SIGNAL_AVAILABILITY_UNKNOWN" in item for item in result.blockers))
        self.assertEqual(result.fills, [])


class GateIntervalEndTests(unittest.TestCase):
    def test_g03_replay_end_keeps_pending_instead_of_expiring(self) -> None:
        dates = trading_dates(2, end=date(2026, 10, 13))
        days = [market_day(day, {SID: bar(day, 5, 5)}) for day in dates]
        batch = _batch(
            signal_date=dates[0],
            available_at=f"{dates[1]}T10:00:00",
            signals=(signal(SID, dates[0]),),
            coverage_until=f"{dates[1]}T15:00:00",
        )
        result = run_backtest(
            make_input(dates, days, signal_batches=(batch,)),
            config(start_date=dates[1], initial_cash=Decimal(1005), top_n=1, rebalance_days=5),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertFalse(any(entry["status"] == "EXPIRED" for entry in result.proposal_entries))
        self.assertTrue(any(entry["status"] == "PENDING" for entry in result.proposal_entries))
        self.assertTrue(any("PENDING_PROPOSAL_OUTSIDE_RANGE" in item for item in result.warnings))

    def test_g03_unproven_coverage_at_replay_end_blocks(self) -> None:
        dates = trading_dates(2, end=date(2026, 10, 13))
        days = [market_day(day, {SID: bar(day, 5, 5)}) for day in dates]
        batch = _batch(
            signal_date=dates[0],
            available_at=f"{dates[1]}T10:00:00",
            signals=(signal(SID, dates[0]),),
            coverage_until=None,
        )
        result = run_backtest(
            make_input(dates, days, signal_batches=(batch,)),
            config(start_date=dates[1], initial_cash=Decimal(1005), top_n=1, rebalance_days=5),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("SIGNAL_BATCH_COVERAGE_UNKNOWN" in item for item in result.blockers))


class GateAvailabilitySemanticsTests(unittest.TestCase):
    def test_g04_normalized_date_is_usable_at_that_close_not_that_open(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        days = [market_day(day, {SID: bar(day, 5, 5)}) for day in dates]
        normalized = replace(
            signal(SID, dates[0]),
            available_at=dates[1],
            available_at_kind="NORMALIZED_AVAILABLE_DATE",
        )
        batch = _batch(
            signal_date=dates[0],
            available_at=f"{dates[0]}T15:00:00",
            signals=(normalized,),
            coverage_until=f"{dates[4]}T15:00:00",
        )
        result = run_backtest(
            make_input(dates, days, signal_batches=(batch,)),
            config(start_date=dates[1], initial_cash=Decimal(1005), top_n=1, rebalance_days=5),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertFalse(any(fill.date == dates[1] for fill in result.fills))
        self.assertEqual([(fill.date, fill.quantity) for fill in result.fills], [(dates[2], 200)])

    def test_g04_untyped_date_only_signal_is_rejected_by_consumer(self) -> None:
        payload = {
            "security_id": SID,
            "strategy_id": "S01",
            "config_version": "S01_DEFAULT/REAL",
            "signal_date": "2026-10-12",
            "input_version": "REAL-1",
            "qualification_status": "SCORABLE",
            "signal_status": "TRUE",
            "available_at": "2026-10-13",
        }
        from mishi_radar.cash_backtest.model import Signal

        with self.assertRaises(ValueError):
            Signal.from_dict(payload)
        typed = Signal.from_dict({**payload, "available_at_kind": "NORMALIZED_AVAILABLE_DATE"})
        self.assertEqual(typed.available_at_kind, "NORMALIZED_AVAILABLE_DATE")


class GateEligibilityTests(unittest.TestCase):
    def test_g05_production_batch_without_eligibility_coverage_blocks(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        days = [market_day(day, {SID: bar(day, 5, 5)}) for day in dates]
        batch = _batch(
            signal_date=dates[0],
            available_at=f"{dates[0]}T15:00:00",
            signals=(signal(SID, dates[0]),),
            coverage_until=f"{dates[4]}T15:00:00",
        )
        result = run_backtest(
            make_input(dates, days, signal_batches=(batch,)),
            config(
                start_date=dates[1],
                initial_cash=Decimal(1005),
                top_n=1,
                rebalance_days=5,
                synthetic=False,
            ),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("ELIGIBILITY_COVERAGE_MISSING" in item for item in result.blockers))
        self.assertEqual(result.fills, [])

    def test_g05_unknown_ranked_candidate_blocks_instead_of_substitution(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        days = [market_day(day, {SID: bar(day, 5, 5), OTHER: bar(day, 5, 5)}) for day in dates]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={
                    dates[0]: (
                        signal(SID, dates[0], candidate_rank=1),
                        signal(OTHER, dates[0], candidate_rank=2),
                    )
                },
                eligibility_by_date=_eligibility(dates, "UNKNOWN"),
                rules=(synthetic_rule(lot_size=100),),
                fees=synthetic_fees(min_commission=0),
            ),
            config(start_date=dates[1], initial_cash=Decimal(1005), top_n=1, rebalance_days=1),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("ELIGIBILITY_UNKNOWN" in item for item in result.blockers))
        self.assertEqual(result.fills, [])


class GateFeeKeyTests(unittest.TestCase):
    def _run(self, fees, fee_schedules=(), rebalance_days=1):
        dates = trading_dates(3, end=date(2026, 10, 15))
        days = [market_day(day, {SID: bar(day, 5, 5)}) for day in dates]
        return run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]),)},
                rules=(synthetic_rule(lot_size=100),),
                fees=fees,
                fee_schedules=fee_schedules,
            ),
            config(
                start_date=dates[1],
                initial_cash=Decimal(1005),
                top_n=1,
                rebalance_days=rebalance_days,
            ),
        )

    def test_g06_non_synthetic_version_without_known_at_blocks(self) -> None:
        fees = replace(
            synthetic_fees(min_commission=0),
            known_at=None,
            synthetic=False,
            source="TEST-EXPLICIT",
            version="NO-KNOWN-TIME",
        )
        result = self._run(fees, (fees,))
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("FEE_SCHEDULE_KNOWN_AT_MISSING" in item for item in result.blockers))

    def test_g06_single_table_wrong_key_and_future_known_at_blocks(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        fees = replace(
            synthetic_fees(min_commission=0),
            known_at=f"{dates[3]}T10:00:00",
            side="SELL",
            market="SZ",
            synthetic=False,
        )
        result = self._run(fees)
        self.assertEqual(result.status, "BLOCKED")
        self.assertEqual(result.fills, [])

    def test_g06_non_synthetic_table_without_complete_key_blocks(self) -> None:
        dates = trading_dates(3, end=date(2026, 10, 15))
        fees = replace(
            synthetic_fees(min_commission=0),
            known_at=f"{dates[0]}T15:00:00",
            synthetic=False,
            version="UNBOUND",
        )
        result = self._run(fees)
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("FEE_SCHEDULE_KEY_INCOMPLETE" in item for item in result.blockers))

    def test_g06_bound_non_synthetic_table_with_known_at_is_accepted(self) -> None:
        dates = trading_dates(3, end=date(2026, 10, 15))
        fees = replace(
            synthetic_fees(min_commission=0),
            known_at=f"{dates[0]}T15:00:00",
            market="SH",
            security_id=SID,
            side="BUY",
            synthetic=False,
            version="BOUND-BUY",
        )
        result = self._run(fees, rebalance_days=5)
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual([entry["version"] for entry in result.fee_entries], ["BOUND-BUY"])


class GateLotSourceTests(unittest.TestCase):
    def test_g07_bonus_keeps_source_acquisition_for_tax_binding(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        split = CorporateAction(
            SID,
            "BONUS_SHARES",
            dates[2],
            record_date=dates[1],
            share_multiplier=Decimal(2),
        )
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
                    tax_rate=Decimal("0.20"),
                    known_at=f"{dates[0]}T15:00:00",
                ),
            ),
        )
        days = [
            market_day(
                day,
                {SID: bar(day, Decimal(10 if index < 2 else 5), Decimal(10 if index < 2 else 5))},
                corporate_actions=(split,) if index == 2 else (dividend,) if index == 3 else (),
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
            config(start_date=dates[1], initial_cash=Decimal(1000), top_n=1, rebalance_days=5),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertEqual(len(result.dividend_tax_entries), 2)
        self.assertEqual(
            sorted(
                (entry["acquired_date"], entry["quantity"], entry["tax"])
                for entry in result.dividend_tax_entries
            ),
            [(dates[1], 100, Decimal("20.00")), (dates[1], 100, Decimal("20.00"))],
        )

    def test_g07_post_sale_delivery_keeps_source_lot_acquisition(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        bonus = CorporateAction(
            SID,
            "BONUS_SHARES",
            dates[3],
            record_date=dates[1],
            share_multiplier=Decimal(2),
        )
        dividend = CorporateAction(
            SID,
            "CASH_DIVIDEND",
            dates[4],
            record_date=dates[3],
            pay_date=dates[4],
            cash_per_share=Decimal(1),
            dividend_tax_bindings=(
                DividendTaxBinding(
                    acquisition_from=dates[1],
                    acquisition_to=dates[1],
                    tax_rate=Decimal("0.20"),
                    known_at=f"{dates[0]}T15:00:00",
                ),
            ),
        )
        days = [
            market_day(
                day,
                {SID: bar(day, 10, 10)},
                corporate_actions=(bonus,) if index == 3 else (dividend,) if index == 4 else (),
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
            config(start_date=dates[1], initial_cash=Decimal(1000), top_n=1, rebalance_days=20),
        )
        self.assertEqual(result.status, "SUCCEEDED", result.blockers)
        self.assertTrue(any(fill.side == "SELL" and fill.date == dates[2] for fill in result.fills))
        self.assertEqual(len(result.dividend_tax_entries), 1)
        entry = result.dividend_tax_entries[0]
        self.assertEqual(entry["acquired_date"], dates[1])
        self.assertEqual(entry["quantity"], 100)
        self.assertEqual(entry["tax"], Decimal("20.00"))


class GateLegacyBoundaryTests(unittest.TestCase):
    def test_legacy_late_signal_requires_batch_instead_of_expiring(self) -> None:
        dates = trading_dates(5, end=date(2026, 10, 16))
        days = [market_day(day, {SID: bar(day, 5, 5)}) for day in dates]
        late = signal(SID, dates[0], available_at=f"{dates[1]}T09:30:01")
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (late,), dates[1]: ()},
            ),
            config(start_date=dates[1], initial_cash=Decimal(1005), top_n=1, rebalance_days=5),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(any("LEGACY_SIGNAL_REQUIRES_BATCH" in item for item in result.blockers))
        self.assertFalse(any(entry.status == "EXPIRED" for entry in result.orders))

    def test_non_synthetic_legacy_signal_is_rejected(self) -> None:
        dates = trading_dates(3, end=date(2026, 10, 15))
        days = [market_day(day, {SID: bar(day, 5, 5)}) for day in dates]
        result = run_backtest(
            make_input(
                dates,
                days,
                signals_by_signal_date={dates[0]: (signal(SID, dates[0]),)},
                eligibility_by_date=_eligibility(dates),
            ),
            config(
                start_date=dates[1],
                initial_cash=Decimal(1005),
                top_n=1,
                rebalance_days=1,
                synthetic=False,
            ),
        )
        self.assertEqual(result.status, "BLOCKED")
        self.assertTrue(
            any("LEGACY_SIGNAL_ROUTE_REQUIRES_SYNTHETIC_COMPAT" in item for item in result.blockers)
        )
        self.assertEqual(result.fills, [])


if __name__ == "__main__":
    unittest.main()
