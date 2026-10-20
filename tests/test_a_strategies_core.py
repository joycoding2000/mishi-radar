from __future__ import annotations

import unittest
from decimal import Decimal

from mishi_radar.strategy_core.config import default_configs
from mishi_radar.strategy_core.engine import compute_strategy
from mishi_radar.strategy_core.model import ConditionStatus, SignalState

from tests.a_fixtures import (
    BASE_AMOUNT,
    flat,
    make_bar,
    make_snapshot,
    trading_dates,
    trend,
)


class S01Tests(unittest.TestCase):
    def test_trend_hit_and_non_hits(self) -> None:
        dates = trading_dates(70)
        snapshot = make_snapshot(
            dates,
            {
                "SH:600001": trend(70, 10, "0.002"),
                "SH:600002": flat(70, 10),
                "SH:600003": [Decimal(10) * (Decimal("0.998") ** i) for i in range(70)],
            },
            benchmark_closes=[100] * 70,
        )
        result = compute_strategy(snapshot, "S01", default_configs())
        self.assertEqual(result.rows["SH:600001"].signal_status, ConditionStatus.TRUE)
        self.assertEqual(result.rows["SH:600001"].candidate_rank, 1)
        self.assertEqual(result.rows["SH:600002"].signal_status, ConditionStatus.FALSE)
        self.assertEqual(result.rows["SH:600003"].signal_status, ConditionStatus.FALSE)
        self.assertTrue(result.pool_complete)
        self.assertEqual(result.pool_size, 3)

    def test_er20_zero_is_false_even_when_trend_is_positive(self) -> None:
        dates = trading_dates(70)
        closes = [Decimal("8.5")] * 70
        closes[49] = Decimal(10)
        for index in range(50, 69):
            closes[index] = Decimal(9)
        closes[69] = Decimal(10)
        snapshot = make_snapshot(
            dates,
            {"SH:600001": closes},
            benchmark_closes=[100] * 70,
        )
        result = compute_strategy(snapshot, "S01", default_configs())
        row = result.rows["SH:600001"]
        self.assertEqual(row.metrics["er20"], Decimal(0))
        self.assertEqual(row.conditions["trend"], ConditionStatus.TRUE)
        self.assertEqual(row.signal_status, ConditionStatus.FALSE)


class S02Tests(unittest.TestCase):
    def _bars(self, dates, *, d_close, d_volume, d_high=12):
        bars = {}
        for index, day in enumerate(dates):
            if index < 9:
                bars[day] = make_bar(day, 10)
            elif index <= 28:
                volume = Decimal(1000) if index < 24 else Decimal(200)
                bars[day] = make_bar(day, "9.5", high=10, low=9, volume=volume)
            else:
                bars[day] = make_bar(
                    day,
                    d_close,
                    high=d_high,
                    low="9.9",
                    volume=d_volume,
                    amount=BASE_AMOUNT,
                )
        return bars

    def test_platform_window_excludes_breakout_day_and_volume_boundary(self) -> None:
        dates = trading_dates(30)
        snapshot = make_snapshot(
            dates,
            {
                "SH:600001": flat(30, "9.5"),
                "SH:600002": flat(30, "9.5"),
                "SH:600003": flat(30, "9.5"),
            },
            benchmark_closes=[100] * 30,
            bars_override={
                "SH:600001": self._bars(dates, d_close="10.1", d_volume=1200),
                "SH:600002": self._bars(dates, d_close="10.1", d_volume=1199),
                "SH:600003": self._bars(dates, d_close="10.0", d_volume=1200),
            },
        )
        result = compute_strategy(snapshot, "S02", default_configs())
        a = result.rows["SH:600001"]
        self.assertEqual(a.metrics["u20"], Decimal(10))
        self.assertEqual(a.metrics["v20"], Decimal(800))
        self.assertEqual(a.metrics["v5"], Decimal(200))
        self.assertEqual(a.observation_status, ConditionStatus.TRUE)
        self.assertEqual(a.signal_status, ConditionStatus.TRUE)
        self.assertEqual(result.rows["SH:600002"].signal_status, ConditionStatus.FALSE)
        self.assertEqual(result.rows["SH:600003"].signal_status, ConditionStatus.FALSE)

    def test_unknown_volume_is_unknown_not_false(self) -> None:
        dates = trading_dates(30)
        bars = self._bars(dates, d_close="10.1", d_volume=1200)
        bars[dates[-1]] = make_bar(dates[-1], "10.1", high=12, low="9.9", volume=1200, amount=BASE_AMOUNT)
        snapshot = make_snapshot(
            dates,
            {"SH:600001": flat(30, "9.5")},
            benchmark_closes=[100] * 30,
            bars_override={"SH:600001": bars},
        )
        # Remove the raw volume while keeping the bar otherwise valid.
        snapshot = snapshot.__class__(
            **{
                **snapshot.__dict__,
                "bars": {
                    "SH:600001": {
                        day: (
                            bar.__class__(
                                date=bar.date,
                                open=bar.open,
                                high=bar.high,
                                low=bar.low,
                                close=bar.close,
                                volume=bar.volume.__class__(None, bar.volume.status.MISSING, "VOLUME_MISSING"),
                                amount=bar.amount,
                                adjustment_factor=bar.adjustment_factor,
                                volume_factor=bar.volume_factor,
                            )
                            if day == dates[-1]
                            else bar
                        )
                        for day, bar in snapshot.bars["SH:600001"].items()
                    }
                },
            }
        )
        result = compute_strategy(snapshot, "S02", default_configs())
        self.assertEqual(result.rows["SH:600001"].signal_status, ConditionStatus.UNKNOWN)
        self.assertIsNone(result.rows["SH:600001"].pool_rank)


class S03Tests(unittest.TestCase):
    def _closes(self, last_close: Decimal = Decimal("12.5")) -> list[Decimal]:
        closes = [Decimal(10) + Decimal("0.06") * index for index in range(56)]
        closes.extend([Decimal("13.0"), Decimal("12.8"), Decimal("12.6"), Decimal("12.4"), last_close])
        return closes

    def test_pullback_confirmation_and_failed_confirmation(self) -> None:
        dates = trading_dates(61)
        snapshot = make_snapshot(
            dates,
            {
                "SH:600001": self._closes(Decimal("12.5")),
                "SH:600002": self._closes(Decimal("12.45")),
            },
            benchmark_closes=[100] * 61,
        )
        result = compute_strategy(snapshot, "S03", default_configs())
        self.assertEqual(result.rows["SH:600001"].observation_status, ConditionStatus.TRUE)
        self.assertEqual(result.rows["SH:600001"].confirmation_status, ConditionStatus.TRUE)
        self.assertEqual(result.rows["SH:600001"].signal_status, ConditionStatus.TRUE)
        self.assertEqual(result.rows["SH:600002"].observation_status, ConditionStatus.TRUE)
        self.assertEqual(result.rows["SH:600002"].confirmation_status, ConditionStatus.FALSE)
        self.assertEqual(result.rows["SH:600002"].signal_status, ConditionStatus.FALSE)

    def test_missing_yesterday_high_is_unknown(self) -> None:
        dates = trading_dates(61)
        closes = self._closes(Decimal("12.5"))
        bad = make_bar(dates[-2], closes[-2], high=Decimal("12.5"))
        snapshot = make_snapshot(
            dates,
            {"SH:600001": closes},
            benchmark_closes=[100] * 61,
            bars_override={"SH:600001": {dates[-2]: bad}},
        )
        from mishi_radar.strategy_core.model import Numeric, ValueStatus

        bars = dict(snapshot.bars["SH:600001"])
        original = bars[dates[-2]]
        bars[dates[-2]] = original.__class__(
            date=original.date,
            open=original.open,
            high=Numeric(None, ValueStatus.MISSING, "HIGH_MISSING"),
            low=original.low,
            close=original.close,
            volume=original.volume,
            amount=original.amount,
            adjustment_factor=original.adjustment_factor,
            volume_factor=original.volume_factor,
        )
        snapshot = snapshot.__class__(
            **{**snapshot.__dict__, "bars": {**snapshot.bars, "SH:600001": bars}}
        )
        result = compute_strategy(snapshot, "S03", default_configs())
        self.assertEqual(result.rows["SH:600001"].signal_status, ConditionStatus.UNKNOWN)


class S04Tests(unittest.TestCase):
    def _closes(self, *, base: Decimal = Decimal(10), d_minus_1: Decimal = Decimal("9.2")) -> list[Decimal]:
        closes = [base] * 23
        closes.extend([Decimal(10), Decimal("9.8"), Decimal("9.3"), Decimal("9.3"), Decimal("9.2"), d_minus_1, Decimal("9.5")])
        return closes

    def test_prior_drop_and_repair(self) -> None:
        dates = trading_dates(30)
        snapshot = make_snapshot(
            dates,
            {
                "SH:600001": self._closes(),
                "SH:600002": self._closes(d_minus_1=Decimal("9.21")),
            },
            benchmark_closes=[100] * 30,
        )
        result = compute_strategy(snapshot, "S04", default_configs())
        a = result.rows["SH:600001"]
        self.assertEqual(a.metrics["prior_drop5"], Decimal("-0.08"))
        self.assertEqual(a.observation_status, ConditionStatus.TRUE)
        self.assertEqual(a.signal_status, ConditionStatus.TRUE)
        self.assertEqual(a.entry_conflict_exit, ConditionStatus.FALSE)
        b = result.rows["SH:600002"]
        self.assertEqual(b.observation_status, ConditionStatus.FALSE)
        self.assertEqual(b.signal_status, ConditionStatus.FALSE)

    def test_entry_conflict_exit_is_flagged(self) -> None:
        dates = trading_dates(30)
        snapshot = make_snapshot(
            dates,
            {"SH:600001": self._closes(base=Decimal("9.2"))},
            benchmark_closes=[100] * 30,
        )
        result = compute_strategy(snapshot, "S04", default_configs())
        row = result.rows["SH:600001"]
        self.assertEqual(row.signal_status, ConditionStatus.TRUE)
        self.assertEqual(row.entry_conflict_exit, ConditionStatus.TRUE)

    def test_missing_d_minus_6_is_unknown(self) -> None:
        dates = trading_dates(30)
        closes = self._closes()
        snapshot = make_snapshot(
            dates,
            {"SH:600001": closes},
            benchmark_closes=[100] * 30,
            bars_override={"SH:600001": {dates[-7]: make_bar(dates[-7], None)}},
        )
        result = compute_strategy(snapshot, "S04", default_configs())
        self.assertEqual(result.rows["SH:600001"].signal_status, ConditionStatus.UNKNOWN)

    def test_prior_drop_window_ends_at_d_minus_1_and_uses_d_minus_6(self) -> None:
        dates = trading_dates(30)
        first = self._closes()
        second = list(first)
        second[22] = Decimal("8.0")  # D-7, not part of the approved 5-day return
        snapshot_a = make_snapshot(dates, {"SH:600001": first}, benchmark_closes=[100] * 30)
        snapshot_b = make_snapshot(dates, {"SH:600001": second}, benchmark_closes=[100] * 30)
        row_a = compute_strategy(snapshot_a, "S04", default_configs()).rows["SH:600001"]
        row_b = compute_strategy(snapshot_b, "S04", default_configs()).rows["SH:600001"]
        self.assertEqual(row_a.metrics["prior_drop5"], row_b.metrics["prior_drop5"])
        self.assertEqual(row_a.signal_status, row_b.signal_status)


if __name__ == "__main__":
    unittest.main()
