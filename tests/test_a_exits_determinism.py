from __future__ import annotations

import unittest
from decimal import Decimal

from mishi_radar.strategy_core.config import S01Config, default_configs
from mishi_radar.strategy_core.engine import compute_all, compute_strategy, evaluate_exit, signal_records
from mishi_radar.strategy_core.model import (
    ConditionStatus,
    ExitContext,
    confirmed_zero,
    num,
    raw_zero_unknown,
)
from mishi_radar.strategy_core.strategies import ma_value

from tests.a_fixtures import default_financial, flat, make_snapshot, trading_dates, trend


def _snapshot_with_last_close(last: Decimal, *, dates=None):
    dates = dates or trading_dates(70)
    closes = [Decimal(10)] * 69 + [last]
    return make_snapshot(dates, {"SH:600001": closes}, benchmark_closes=[100] * 70)


class ExitTests(unittest.TestCase):
    def test_no_position_and_common_stop_semantics(self) -> None:
        snapshot = _snapshot_with_last_close(Decimal(10))
        no_position = evaluate_exit(snapshot, "S01", "SH:600001", ExitContext(holding_days=0, has_position=False))
        self.assertEqual(no_position.status, ConditionStatus.FALSE)
        stopped = evaluate_exit(
            snapshot,
            "S01",
            "SH:600001",
            ExitContext(holding_days=0, common_stop_triggered=True),
        )
        self.assertEqual(stopped.status, ConditionStatus.TRUE)
        self.assertIn("STOP_LOSS", stopped.reasons)
        unknown = evaluate_exit(
            snapshot,
            "S01",
            "SH:600001",
            ExitContext(holding_days=0, common_stop_unknown=True),
        )
        self.assertEqual(unknown.status, ConditionStatus.UNKNOWN)

    @staticmethod
    def _personal_ma10():
        return default_configs().with_s01(
            S01Config(ma_short=10, config_id="S01_PERSONAL", config_version="S01_PERSONAL/v1")
        )

    def test_personal_s01_ma10_exit_uses_configured_short_ma(self) -> None:
        dates = trading_dates(20)
        closes = [Decimal("8.0")] * 10 + [Decimal("12.0")] * 9 + [Decimal("11.0")]
        snapshot = make_snapshot(dates, {"SH:600001": closes}, benchmark_closes=[100] * 20)
        self.assertEqual(ma_value(snapshot, "SH:600001", 10).value, Decimal("11.9"))
        self.assertEqual(ma_value(snapshot, "SH:600001", 20).value, Decimal("9.95"))
        personal = self._personal_ma10()
        decision = evaluate_exit(
            snapshot,
            "S01",
            "SH:600001",
            ExitContext(holding_days=0),
            personal,
        )
        self.assertEqual(decision.status, ConditionStatus.TRUE)
        self.assertIn("STRATEGY_EXIT:S01_BELOW_MA20", decision.reasons)

    def test_default_s01_ma20_does_not_exit_on_same_input(self) -> None:
        dates = trading_dates(20)
        closes = [Decimal("8.0")] * 10 + [Decimal("12.0")] * 9 + [Decimal("11.0")]
        snapshot = make_snapshot(dates, {"SH:600001": closes}, benchmark_closes=[100] * 20)
        decision = evaluate_exit(
            snapshot,
            "S01",
            "SH:600001",
            ExitContext(holding_days=0),
            default_configs(),
        )
        self.assertEqual(decision.status, ConditionStatus.FALSE)

    def test_s06_exit_keeps_default_when_personal_ma10_would_exit(self) -> None:
        dates = trading_dates(20)
        closes = [Decimal("8.0")] * 10 + [Decimal("12.0")] * 9 + [Decimal("11.0")]
        snapshot = make_snapshot(dates, {"SH:600001": closes}, benchmark_closes=[100] * 20)
        personal = self._personal_ma10()
        personal_s01 = evaluate_exit(
            snapshot, "S01", "SH:600001", ExitContext(holding_days=0), personal
        )
        s06 = evaluate_exit(
            snapshot,
            "S06",
            "SH:600001",
            ExitContext(holding_days=0, industry_rank_history=(1, 1)),
            personal,
        )
        self.assertEqual(personal_s01.status, ConditionStatus.TRUE)
        self.assertEqual(s06.status, ConditionStatus.FALSE)

    def test_s02_exit_uses_mechanically_adjusted_platform(self) -> None:
        dates = trading_dates(20)
        snapshot = make_snapshot(
            dates,
            {"SH:600001": [Decimal("4.90")] * 20},
            benchmark_closes=[100] * 20,
        )
        decision = evaluate_exit(
            snapshot,
            "S02",
            "SH:600001",
            ExitContext(holding_days=0, entry_platform_upper=Decimal(5)),
            default_configs(),
        )
        self.assertEqual(decision.status, ConditionStatus.TRUE)
        self.assertIn("STRATEGY_EXIT:S02_BELOW_PLATFORM", decision.reasons)

    def test_s06_exit_keeps_default_when_personal_ma10_would_not_exit(self) -> None:
        dates = trading_dates(20)
        closes = [Decimal("9.4")] * 10 + [Decimal("8.8")] * 9 + [Decimal("9.0")]
        snapshot = make_snapshot(dates, {"SH:600001": closes}, benchmark_closes=[100] * 20)
        self.assertEqual(ma_value(snapshot, "SH:600001", 10).value, Decimal("8.82"))
        self.assertEqual(ma_value(snapshot, "SH:600001", 20).value, Decimal("9.11"))
        personal = self._personal_ma10()
        personal_s01 = evaluate_exit(
            snapshot, "S01", "SH:600001", ExitContext(holding_days=0), personal
        )
        default_s01 = evaluate_exit(
            snapshot, "S01", "SH:600001", ExitContext(holding_days=0), default_configs()
        )
        s06 = evaluate_exit(
            snapshot,
            "S06",
            "SH:600001",
            ExitContext(holding_days=0, industry_rank_history=(1, 1)),
            personal,
        )
        self.assertEqual(personal_s01.status, ConditionStatus.FALSE)
        self.assertEqual(default_s01.status, ConditionStatus.TRUE)
        self.assertEqual(s06.status, ConditionStatus.TRUE)

    def test_strategy_specific_exits(self) -> None:
        below = _snapshot_with_last_close(Decimal(5))
        above = _snapshot_with_last_close(Decimal(10))
        cases = [
            ("S01", below, ExitContext(holding_days=0), "S01_BELOW_MA20"),
            ("S02", above, ExitContext(holding_days=0, entry_platform_upper=Decimal(11)), "S02_BELOW_PLATFORM"),
            ("S03", below, ExitContext(holding_days=0), "S03_BELOW_MA60"),
            ("S04", above, ExitContext(holding_days=0), "S04_REACHED_MA20"),
            ("S05", below, ExitContext(holding_days=0), "S05_BELOW_MA60"),
            ("S06", below, ExitContext(holding_days=0, industry_rank_history=(1, 1)), "S06_BELOW_BOUND_MA20"),
            ("S08", below, ExitContext(holding_days=0), "S08_BELOW_MA20"),
        ]
        for strategy_id, snapshot, context, reason in cases:
            with self.subTest(strategy=strategy_id):
                decision = evaluate_exit(snapshot, strategy_id, "SH:600001", context)
                self.assertEqual(decision.status, ConditionStatus.TRUE)
                self.assertTrue(any(reason in item for item in decision.reasons))

    def test_s06_industry_exit_and_max_holding(self) -> None:
        snapshot = _snapshot_with_last_close(Decimal(10))
        industry_exit = evaluate_exit(
            snapshot,
            "S06",
            "SH:600001",
            ExitContext(holding_days=0, industry_rank_history=(11, 11)),
        )
        self.assertEqual(industry_exit.status, ConditionStatus.TRUE)
        max_holding = evaluate_exit(
            snapshot,
            "S01",
            "SH:600001",
            ExitContext(holding_days=20),
        )
        self.assertEqual(max_holding.status, ConditionStatus.TRUE)
        self.assertIn("MAX_HOLDING", max_holding.reasons)

    def test_s07_condition_exit_and_s08_three_day_outflow(self) -> None:
        dates = trading_dates(70)
        snapshot = make_snapshot(
            dates,
            {"SH:600001": trend(70, 10, "0.002")},
            benchmark_closes=[100] * 70,
            financials={
                "SH:600001": default_financial(
                    "IND_A", dates[-1], pe=10, np_ttm=5, ocf_ttm=5, equity_average=100
                )
            },
        )
        s07 = evaluate_exit(snapshot, "S07", "SH:600001", ExitContext(holding_days=0))
        self.assertEqual(s07.status, ConditionStatus.TRUE)
        self.assertTrue(any("S07_CONDITION_FAILED" in item for item in s07.reasons))
        flows = {day: num(1) for day in dates}
        for day in dates[-3:]:
            flows[day] = num(-1)
        snapshot = snapshot.__class__(
            **{
                **snapshot.__dict__,
                "fund_flows": {"SH:600001": flows},
            }
        )
        s08 = evaluate_exit(snapshot, "S08", "SH:600001", ExitContext(holding_days=0))
        self.assertEqual(s08.status, ConditionStatus.TRUE)
        self.assertTrue(any("S08_THREE_DAY_OUTFLOW" in item for item in s08.reasons))


class S08ExitAvailabilityTests(unittest.TestCase):
    @staticmethod
    def _snapshot(dates, last_five):
        flows = {day: num(1) for day in dates[:-5]}
        for day, value in zip(dates[-5:], last_five):
            flows[day] = value
        return make_snapshot(
            dates,
            {"SH:600001": [Decimal(10)] * 20},
            benchmark_closes=[100] * 20,
            fund_flows={"SH:600001": flows},
        )

    def test_d2_after_close_three_day_outflow_is_unknown(self) -> None:
        dates = trading_dates(20)
        snapshot = self._snapshot(
            dates,
            [
                num(1),
                num(1),
                num(-1, available_at=f"{dates[-1]}T23:59:59"),
                num(-1, available_at=f"{dates[-1]}T23:59:59"),
                num(-1, available_at=f"{dates[-1]}T23:59:59"),
            ]
        )
        decision = evaluate_exit(snapshot, "S08", "SH:600001", ExitContext(holding_days=0))
        self.assertEqual(decision.status, ConditionStatus.UNKNOWN)
        self.assertIn("S08_LAST_THREE_FLOWS_UNKNOWN", decision.reasons)

    def test_before_close_three_day_outflow_still_exits(self) -> None:
        dates = trading_dates(20)
        snapshot = self._snapshot(
            dates,
            [
                num(1),
                num(1),
                num(-1, available_at=f"{dates[-1]}T14:59:59"),
                num(-1, available_at=f"{dates[-1]}T14:59:59"),
                num(-1, available_at=f"{dates[-1]}T14:59:59"),
            ]
        )
        decision = evaluate_exit(snapshot, "S08", "SH:600001", ExitContext(holding_days=0))
        self.assertEqual(decision.status, ConditionStatus.TRUE)
        self.assertIn("STRATEGY_EXIT:S08_THREE_DAY_OUTFLOW", decision.reasons)

    def test_partially_unavailable_flow_is_not_a_confirmed_exit(self) -> None:
        dates = trading_dates(20)
        snapshot = self._snapshot(
            dates,
            [
                num(1),
                num(1),
                num(-1, available_at=f"{dates[-1]}T14:00:00"),
                num(-1, available_at=f"{dates[-1]}T23:59:59"),
                num(-1, available_at=f"{dates[-1]}T14:00:00"),
            ]
        )
        decision = evaluate_exit(snapshot, "S08", "SH:600001", ExitContext(holding_days=0))
        self.assertEqual(decision.status, ConditionStatus.UNKNOWN)
        self.assertNotEqual(decision.status, ConditionStatus.TRUE)

    def test_confirmed_zero_is_not_unknown_and_not_a_negative_day(self) -> None:
        dates = trading_dates(20)
        snapshot = self._snapshot(
            dates,
            [
                num(1),
                num(1),
                num(-1, available_at=f"{dates[-1]}T14:00:00"),
                confirmed_zero(available_at=f"{dates[-1]}T14:00:00"),
                num(-1, available_at=f"{dates[-1]}T14:00:00"),
            ]
        )
        decision = evaluate_exit(snapshot, "S08", "SH:600001", ExitContext(holding_days=0))
        self.assertEqual(decision.status, ConditionStatus.FALSE)
        self.assertNotEqual(decision.status, ConditionStatus.UNKNOWN)

    def test_raw_zero_remains_unknown(self) -> None:
        dates = trading_dates(20)
        snapshot = self._snapshot(
            dates,
            [
                num(1),
                num(1),
                num(-1, available_at=f"{dates[-1]}T14:00:00"),
                raw_zero_unknown(available_at=f"{dates[-1]}T14:00:00", reason="RAW_ZERO_UNCERTIFIED"),
                num(-1, available_at=f"{dates[-1]}T14:00:00"),
            ]
        )
        decision = evaluate_exit(snapshot, "S08", "SH:600001", ExitContext(holding_days=0))
        self.assertEqual(decision.status, ConditionStatus.UNKNOWN)
        self.assertIn("S08_LAST_THREE_FLOWS_UNKNOWN", decision.reasons)

    def test_s08_entry_path_keeps_availability_unknown(self) -> None:
        dates = trading_dates(20)
        flows = {day: num(1) for day in dates[:-5]}
        for day in dates[-3:]:
            flows[day] = num(-1, available_at=f"{dates[-1]}T23:59:59")
        snapshot = make_snapshot(
            dates,
            {"SH:600001": trend(20, 10, "0.002")},
            benchmark_closes=[100] * 20,
            fund_flows={"SH:600001": flows},
        )
        result = compute_strategy(snapshot, "S08", default_configs())
        self.assertEqual(result.rows["SH:600001"].signal_status, ConditionStatus.UNKNOWN)


class DeterminismTests(unittest.TestCase):
    def test_repeated_and_shuffled_inputs_match(self) -> None:
        dates = trading_dates(70)
        closes = {
            "SH:600003": trend(70, 10, "0.001"),
            "SH:600001": trend(70, 10, "0.002"),
            "SH:600002": flat(70, 10),
        }
        snapshot_a = make_snapshot(dates, closes, benchmark_closes=[100] * 70)
        snapshot_b = make_snapshot(
            dates,
            {"SH:600001": closes["SH:600001"], "SH:600003": closes["SH:600003"], "SH:600002": closes["SH:600002"]},
            benchmark_closes=[100] * 70,
        )
        first = signal_records(compute_all(snapshot_a, default_configs()))
        second = signal_records(compute_all(snapshot_a, default_configs()))
        shuffled = signal_records(compute_all(snapshot_b, default_configs()))
        self.assertEqual(first, second)
        self.assertEqual(first, shuffled)


if __name__ == "__main__":
    unittest.main()
