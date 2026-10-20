from __future__ import annotations

import unittest
from decimal import Decimal

from mishi_radar.strategy_core.config import (
    S01Config,
    S02Config,
    S06Config,
    S01_DEFAULT_CONFIG_VERSION,
    default_configs,
)
from mishi_radar.strategy_core.engine import compute_strategy
from mishi_radar.strategy_core.mathx import percentile_high, percentile_low
from mishi_radar.strategy_core.model import ConditionStatus, ValueStatus
from mishi_radar.strategy_core.strategies import ma_value, return_value

from tests.a_fixtures import flat, make_bar, make_snapshot, trading_dates, trend


class MathAndRankingTests(unittest.TestCase):
    def test_percentile_uses_midrank_and_handles_singleton(self) -> None:
        population = [Decimal(1), Decimal(2), Decimal(2), Decimal(3)]
        self.assertEqual(percentile_high(Decimal(2), population), Decimal("0.5"))
        self.assertEqual(percentile_high(Decimal(1), population), Decimal("0.125"))
        self.assertEqual(percentile_high(Decimal(3), population), Decimal("0.875"))
        self.assertEqual(percentile_low(Decimal(2), population), Decimal("0.5"))
        self.assertEqual(percentile_high(Decimal(7), [Decimal(7)]), Decimal("0.5"))
        self.assertIsNone(percentile_high(Decimal(7), []))

    def test_market_day_windows_and_excess_return(self) -> None:
        dates = trading_dates(5)
        snapshot = make_snapshot(
            dates,
            {"SH:600001": [10, 11, 12, 13, 14]},
            benchmark_closes=[100, 100, 100, 100, 100],
        )
        self.assertEqual(ma_value(snapshot, "SH:600001", 3).value, Decimal(13))
        self.assertEqual(return_value(snapshot, "SH:600001", 2).value, Decimal(14) / Decimal(12) - 1)

    def test_raw_and_adjusted_prices_are_separate(self) -> None:
        dates = trading_dates(70)
        factors = [Decimal(1) + Decimal("0.001") * index for index in range(len(dates))]
        bars = {
            day: make_bar(day, 10, adjustment_factor=factors[index])
            for index, day in enumerate(dates)
        }
        snapshot = make_snapshot(
            dates,
            {"SH:600001": flat(70, 10)},
            benchmark_closes=[100] * 70,
            bars_override={"SH:600001": bars},
        )
        result = compute_strategy(snapshot, "S01", default_configs())
        row = result.rows["SH:600001"]
        self.assertEqual(row.signal_status, ConditionStatus.TRUE)
        self.assertEqual(snapshot.bars["SH:600001"][dates[-1]].close.value, Decimal(10))
        self.assertGreater(snapshot.bars["SH:600001"][dates[-1]].adjusted_close().value, Decimal(10))

    def test_equal_scores_break_ties_by_security_id(self) -> None:
        dates = trading_dates(70)
        closes = trend(70)
        snapshot = make_snapshot(
            dates,
            {"SH:600002": closes, "SH:600001": closes},
            benchmark_closes=[100] * 70,
        )
        result = compute_strategy(snapshot, "S01", default_configs())
        self.assertEqual(result.rows["SH:600001"].pool_rank, 1)
        self.assertEqual(result.rows["SH:600002"].pool_rank, 2)
        self.assertTrue(result.pool_complete)

    def test_parameter_whitelist_rejects_unknown_values(self) -> None:
        with self.assertRaises(ValueError):
            S01Config(ma_short=15)
        with self.assertRaises(ValueError):
            S02Config(platform_width=Decimal("0.17"))
        with self.assertRaises(ValueError):
            S06Config(bound_s01_config_version="S01_DEFAULT/OTHER")
        self.assertEqual(S01_DEFAULT_CONFIG_VERSION, "S01_DEFAULT/R3.2-2026-10-19-OD1-v1")

    def test_value_not_available_until_after_close_is_unknown(self) -> None:
        dates = trading_dates(70)
        bars = {
            day: make_bar(day, value)
            for day, value in zip(dates, trend(70))
        }
        last = bars[dates[-1]]
        bars[dates[-1]] = last.__class__(
            date=last.date,
            open=last.open,
            high=last.high,
            low=last.low,
            close=last.close.__class__(
                last.close.value,
                last.close.status,
                last.close.reason,
                available_at=dates[-1] + "T23:59:59",
            ),
            volume=last.volume,
            amount=last.amount,
            adjustment_factor=last.adjustment_factor,
            volume_factor=last.volume_factor,
        )
        snapshot = make_snapshot(
            dates,
            {"SH:600001": trend(70)},
            benchmark_closes=[100] * 70,
            bars_override={"SH:600001": bars},
        )
        result = compute_strategy(snapshot, "S01", default_configs())
        self.assertEqual(result.rows["SH:600001"].signal_status, ConditionStatus.UNKNOWN)
        self.assertFalse(result.pool_complete)

    def test_unknown_bar_is_not_zero_filled(self) -> None:
        dates = trading_dates(70)
        closes = trend(70)
        closes[-1] = None  # type: ignore[index]
        snapshot = make_snapshot(
            dates,
            {"SH:600001": closes, "SH:600002": trend(70)},
            benchmark_closes=[100] * 70,
        )
        result = compute_strategy(snapshot, "S01", default_configs())
        self.assertIsNone(result.rows["SH:600001"].pool_rank)
        self.assertNotEqual(result.rows["SH:600001"].eligibility.value, "SCORABLE")
        self.assertFalse(result.pool_complete)
        self.assertIsNotNone(result.rows["SH:600002"].sample_pool_rank)
        self.assertIsNone(result.rows["SH:600002"].pool_rank)


if __name__ == "__main__":
    unittest.main()
