from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

from mishi_radar.strategy_core.config import S01Config, default_configs
from mishi_radar.strategy_core.engine import compute_diagnostics, compute_strategy, signal_records, style_view
from mishi_radar.strategy_core.model import (
    ConditionStatus,
    Eligibility,
    FinancialSnapshot,
    Numeric,
    SecurityInfo,
    ValueStatus,
    num,
    raw_zero_unknown,
)
from mishi_radar.strategy_core.strategies import _ttm_metrics

from tests.a_fixtures import (
    BASE_AMOUNT,
    default_financial,
    flat,
    make_bar,
    make_snapshot,
    trading_dates,
    trend,
)


class S05Tests(unittest.TestCase):
    def test_low_vol_percentile_and_not_applicable_zero_amount(self) -> None:
        dates = trading_dates(70)
        noise = Decimal("0.001")

        def series(base: Decimal, slope: Decimal, scale: int) -> list[Decimal]:
            return [
                base + slope * index + (noise * scale if index % 2 else -noise * scale)
                for index in range(70)
            ]

        zero_day = dates[-30]
        snapshot = make_snapshot(
            dates,
            {
                "SH:600001": series(Decimal(10), Decimal("0.02"), 1),
                "SH:600002": series(Decimal(10), Decimal("0.015"), 2),
                "SH:600003": series(Decimal(10), Decimal("0.01"), 3),
                "SH:600004": trend(70, 10, "0.001"),
            },
            benchmark_closes=[100] * 70,
        )
        # Replace the zero-day amount with a confirmed zero on the fourth security.
        bars = dict(snapshot.bars["SH:600004"])
        original = bars[zero_day]
        from mishi_radar.strategy_core.model import confirmed_zero

        bars[zero_day] = original.__class__(
            date=original.date,
            open=original.open,
            high=original.high,
            low=original.low,
            close=original.close,
            volume=original.volume,
            amount=confirmed_zero(),
            adjustment_factor=original.adjustment_factor,
            volume_factor=original.volume_factor,
        )
        snapshot = snapshot.__class__(
            **{**snapshot.__dict__, "bars": {**snapshot.bars, "SH:600004": bars}}
        )
        result = compute_strategy(snapshot, "S05", default_configs())
        a = result.rows["SH:600001"]
        self.assertEqual(a.signal_status, ConditionStatus.TRUE)
        self.assertEqual(a.conditions["low_vol_percentile"], ConditionStatus.TRUE)
        self.assertEqual(result.rows["SH:600002"].signal_status, ConditionStatus.FALSE)
        self.assertEqual(result.rows["SH:600003"].signal_status, ConditionStatus.FALSE)
        self.assertEqual(result.rows["SH:600004"].eligibility, Eligibility.STRATEGY_NOT_APPLICABLE)
        self.assertIsNone(result.rows["SH:600004"].pool_rank)
        self.assertTrue(result.pool_complete)

    def test_missing_amount_makes_pool_local_only(self) -> None:
        dates = trading_dates(70)
        snapshot = make_snapshot(
            dates,
            {
                "SH:600001": trend(70, 10, "0.002"),
                "SH:600002": trend(70, 10, "0.001"),
            },
            benchmark_closes=[100] * 70,
        )
        bars = dict(snapshot.bars["SH:600002"])
        day = dates[-30]
        original = bars[day]
        bars[day] = original.__class__(
            date=original.date,
            open=original.open,
            high=original.high,
            low=original.low,
            close=original.close,
            volume=original.volume,
            amount=Numeric(None, ValueStatus.MISSING, "AMOUNT_MISSING"),
            adjustment_factor=original.adjustment_factor,
            volume_factor=original.volume_factor,
        )
        snapshot = snapshot.__class__(
            **{**snapshot.__dict__, "bars": {**snapshot.bars, "SH:600002": bars}}
        )
        result = compute_strategy(snapshot, "S05", default_configs())
        self.assertFalse(result.pool_complete)
        self.assertIsNone(result.rows["SH:600001"].pool_rank)
        self.assertIsNotNone(result.rows["SH:600001"].sample_pool_rank)


class S06Tests(unittest.TestCase):
    def _snapshot(self):
        dates = trading_dates(70)
        strong = {
            "SH:600001": trend(70, 10, "0.002"),
            "SH:600002": trend(70, 10, "0.0018"),
            "SH:600003": trend(70, 10, "0.0016"),
        }
        special = [Decimal(11)] * 60 + [Decimal("12.5")] * 9 + [Decimal(12)]
        strong["SH:600004"] = special
        weak = {sid: flat(70, 10) for sid in ("SH:600005", "SH:600006", "SH:600007", "SH:600008")}
        return make_snapshot(
            dates,
            {**strong, **weak},
            benchmark_closes=[100] * 70,
            industry_by_id={
                "SH:600001": "IND_STRONG",
                "SH:600002": "IND_STRONG",
                "SH:600003": "IND_STRONG",
                "SH:600004": "IND_STRONG",
                "SH:600005": "IND_WEAK",
                "SH:600006": "IND_WEAK",
                "SH:600007": "IND_WEAK",
                "SH:600008": "IND_WEAK",
            },
            industry_members={
                "IND_STRONG": ("SH:600001", "SH:600002", "SH:600003", "SH:600004"),
                "IND_WEAK": ("SH:600005", "SH:600006", "SH:600007", "SH:600008"),
            },
        )

    def test_industry_pool_and_trigger_ranks(self) -> None:
        snapshot = self._snapshot()
        result = compute_strategy(snapshot, "S06", default_configs())
        strong = result.industries["IND_STRONG"]
        weak = result.industries["IND_WEAK"]
        self.assertTrue(strong.strong)
        self.assertEqual(strong.breadth, Decimal(1))
        self.assertFalse(weak.strong)
        self.assertEqual(result.pool_size, 8)
        self.assertTrue(result.pool_complete)
        strong_ids = ["SH:600001", "SH:600002", "SH:600003", "SH:600004"]
        for sid in strong_ids:
            row = result.rows[sid]
            self.assertEqual(row.industry_id, "IND_STRONG")
            self.assertIsNotNone(row.pool_rank)
            self.assertIsNotNone(row.industry_pool_rank)
            self.assertIsNotNone(row.industry_trigger_rank)
        formal = [sid for sid in strong_ids if result.rows[sid].formal_candidate]
        self.assertEqual(len(formal), 2)
        excluded = [sid for sid in strong_ids if not result.rows[sid].formal_candidate]
        self.assertEqual(len(excluded), 2)
        for sid in excluded:
            self.assertEqual(result.rows[sid].signal_state.value, "CONCENTRATION_EXCLUDED")
            self.assertIsNone(result.rows[sid].candidate_rank)
            self.assertIsNotNone(result.rows[sid].execution_replacement_order)
        replacement_rows = sorted(
            (result.rows[sid] for sid in excluded), key=lambda row: row.industry_trigger_rank
        )
        self.assertEqual([row.execution_replacement_order for row in replacement_rows], [1, 2])
        for sid in ("SH:600005", "SH:600006", "SH:600007", "SH:600008"):
            row = result.rows[sid]
            self.assertEqual(row.signal_state.value, "ELIGIBLE_NOT_TRIGGERED")
            self.assertIsNotNone(row.pool_rank)

    def test_missing_member_value_makes_industry_unknown(self) -> None:
        snapshot = self._snapshot()
        business_date = snapshot.business_date
        bars = {
            sid: {
                day: bar
                for day, bar in security_bars.items()
                if not (sid == "SH:600002" and day == business_date)
            }
            for sid, security_bars in snapshot.bars.items()
        }
        snapshot = snapshot.__class__(**{**snapshot.__dict__, "bars": bars})
        result = compute_strategy(snapshot, "S06", default_configs())
        self.assertEqual(result.industries["IND_STRONG"].status, "UNKNOWN")
        self.assertFalse(result.pool_complete)
        self.assertEqual(result.rows["SH:600001"].eligibility, Eligibility.INPUT_UNKNOWN)
        self.assertIsNone(result.rows["SH:600001"].pool_rank)

    def test_s06_binding_ignores_personal_s01_config(self) -> None:
        snapshot = self._snapshot()
        personal = S01Config(ma_short=10, config_id="S01_PERSONAL", config_version="S01_PERSONAL/v1")
        bundle_default = default_configs()
        bundle_personal = default_configs().with_s01(personal)
        s01_default = compute_strategy(snapshot, "S01", bundle_default)
        s01_personal = compute_strategy(snapshot, "S01", bundle_personal)
        self.assertEqual(s01_default.rows["SH:600004"].signal_status, ConditionStatus.TRUE)
        self.assertEqual(s01_personal.rows["SH:600004"].signal_status, ConditionStatus.FALSE)
        s06_default = compute_strategy(snapshot, "S06", bundle_default)
        s06_personal = compute_strategy(snapshot, "S06", bundle_personal)
        for sid in s06_default.rows:
            a = s06_default.rows[sid]
            b = s06_personal.rows[sid]
            self.assertEqual(a.signal_status, b.signal_status)
            self.assertEqual(a.pool_rank, b.pool_rank)
            self.assertEqual(a.candidate_rank, b.candidate_rank)
            self.assertEqual(a.industry_trigger_rank, b.industry_trigger_rank)


class S07Tests(unittest.TestCase):
    def _financials(self, dates):
        d = dates[-1]
        return {
            "SH:600001": default_financial("IND_VAL", d, pe=10, np_ttm=10, ocf_ttm=12, equity_average=100),
            "SH:600002": default_financial("IND_VAL", d, pe=20, np_ttm=15, ocf_ttm=15, equity_average=100),
            "SH:600003": default_financial("IND_VAL", d, pe=30, np_ttm=5, ocf_ttm=5, equity_average=100),
            "SH:600004": default_financial("IND_VAL", d, pe=8, np_ttm=10, ocf_ttm=12, equity_average=100, is_financial=True),
            "SH:600005": default_financial("IND_VAL", d, pe=-5, np_ttm=10, ocf_ttm=12, equity_average=100),
            "SH:600006": default_financial("IND_VAL", d, pe=30, np_ttm=10, ocf_ttm=12, equity_average=-100),
        }

    def _snapshot(self, dates=None):
        dates = dates or trading_dates(30)
        return make_snapshot(
            dates,
            {sid: trend(30, 10, "0.001") for sid in (
                "SH:600001", "SH:600002", "SH:600003", "SH:600004", "SH:600005", "SH:600006"
            )},
            benchmark_closes=[100] * 30,
            industry_by_id={sid: "IND_VAL" for sid in (
                "SH:600001", "SH:600002", "SH:600003", "SH:600004", "SH:600005", "SH:600006"
            )},
            financials=self._financials(dates),
        )

    def test_industry_value_quality_and_not_applicable(self) -> None:
        snapshot = self._snapshot()
        result = compute_strategy(snapshot, "S07", default_configs())
        self.assertTrue(result.pool_complete)
        a = result.rows["SH:600001"]
        b = result.rows["SH:600002"]
        c = result.rows["SH:600003"]
        self.assertEqual(a.metrics["q_pe_ttm"], Decimal(Decimal(5) / Decimal(6)))
        self.assertEqual(a.metrics["q_roe_ttm"], Decimal("0.5"))
        self.assertEqual(b.metrics["q_pe_ttm"], Decimal("0.5"))
        self.assertEqual(b.metrics["q_roe_ttm"], Decimal(Decimal(5) / Decimal(6)))
        self.assertEqual(a.signal_status, ConditionStatus.TRUE)
        self.assertEqual(b.signal_status, ConditionStatus.TRUE)
        self.assertEqual(c.signal_status, ConditionStatus.FALSE)
        self.assertEqual(b.candidate_rank, 1)
        self.assertEqual(a.candidate_rank, 2)
        self.assertIsNotNone(c.pool_rank)
        for sid in ("SH:600004", "SH:600005", "SH:600006"):
            row = result.rows[sid]
            self.assertEqual(row.eligibility, Eligibility.STRATEGY_NOT_APPLICABLE)
            self.assertIsNone(row.pool_rank)

    def test_ttm_formula_and_average_equity(self) -> None:
        fin = FinancialSnapshot(
            report_period="2026-06-30",
            is_year_end=False,
            np_ytd=num(6),
            ocf_ytd=num(7),
            equity=num(100),
            np_fy_prior=num(10),
            ocf_fy_prior=num(11),
            np_ytd_prior_same=num(4),
            ocf_ytd_prior_same=num(5),
            equity_prior_same=num(80),
            pe_ttm=num(10),
            pe_business_date="2026-10-16",
            is_financial=False,
            industry_id="IND_VAL",
            available_at="2026-10-16",
        )
        metrics, blocker = _ttm_metrics(fin)
        self.assertIsNone(blocker)
        self.assertEqual(metrics["np_ttm"], Decimal(12))
        self.assertEqual(metrics["ocf_ttm"], Decimal(13))
        self.assertEqual(metrics["equity_average"], Decimal(90))
        self.assertEqual(metrics["roe_ttm"], Decimal(12) / Decimal(90))

    def test_financial_not_available_until_next_day_is_unknown(self) -> None:
        dates = trading_dates(30)
        financials = self._financials(dates)
        financials["SH:600001"] = default_financial(
            "IND_VAL", dates[-1], pe=10, np_ttm=10, ocf_ttm=12, equity_average=100, available_at=dates[-1] + "T23:59:59"
        )
        snapshot = make_snapshot(
            dates,
            {"SH:600001": trend(30, 10, "0.001")},
            benchmark_closes=[100] * 30,
            financials={"SH:600001": financials["SH:600001"]},
        )
        result = compute_strategy(snapshot, "S07", default_configs())
        row = result.rows["SH:600001"]
        self.assertEqual(row.signal_status, ConditionStatus.UNKNOWN)
        self.assertFalse(result.pool_complete)
        self.assertIsNone(row.pool_rank)

    def test_raw_announcement_date_maps_to_next_close_but_normalized_date_does_not_shift(self) -> None:
        dates = trading_dates(30)
        announcement_day, business_day = dates[-2], dates[-1]
        base = default_financial("IND_VAL", business_day)
        raw = replace(base, available_at=None, announced_on=announcement_day)
        normalized = replace(base, available_at=business_day, announced_on=announcement_day)
        same_day_announcement = replace(base, available_at=None, announced_on=business_day)
        for financial, expected in (
            (raw, ConditionStatus.TRUE),
            (normalized, ConditionStatus.TRUE),
            (same_day_announcement, ConditionStatus.UNKNOWN),
        ):
            snapshot = make_snapshot(
                dates,
                {"SH:600001": trend(30, 10, "0.001")},
                benchmark_closes=[100] * 30,
                financials={"SH:600001": financial},
            )
            result = compute_strategy(snapshot, "S07", default_configs())
            self.assertEqual(result.rows["SH:600001"].signal_status, expected)

    def test_offset_availability_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            default_financial(
                "IND_VAL",
                "2026-10-16",
                available_at="2026-10-16T10:00:00+08:00",
            )


class S08Tests(unittest.TestCase):
    def test_five_day_flow_and_positive_day_ranking(self) -> None:
        dates = trading_dates(30)
        flows = {}
        for sid in ("SH:600001", "SH:600002", "SH:600003"):
            values = {day: num(1) for day in dates}
            flows[sid] = values
        for day, value in zip(dates[-5:], (1, 1, 1, -1, -1)):
            flows["SH:600001"][day] = num(value)
        for day, value in zip(dates[-5:], (1, 1, 1, 1, -1)):
            flows["SH:600002"][day] = num(value)
        for day, value in zip(dates[-5:], (1, 1, 1, 1, 1)):
            flows["SH:600003"][day] = num(value)
        snapshot = make_snapshot(
            dates,
            {
                "SH:600001": trend(30, 10, "0.002"),
                "SH:600002": trend(30, 10, "0.002"),
                "SH:600003": [Decimal(10) * (Decimal("0.998") ** i) for i in range(30)],
            },
            benchmark_closes=[100] * 30,
            fund_flows=flows,
        )
        result = compute_strategy(snapshot, "S08", default_configs())
        a = result.rows["SH:600001"]
        b = result.rows["SH:600002"]
        c = result.rows["SH:600003"]
        self.assertEqual(a.metrics["net_sum"], Decimal(1))
        self.assertEqual(a.metrics["positive_days"], Decimal(3))
        self.assertEqual(b.metrics["positive_days"], Decimal(4))
        self.assertEqual(a.signal_status, ConditionStatus.TRUE)
        self.assertEqual(b.signal_status, ConditionStatus.TRUE)
        self.assertEqual(b.candidate_rank, 1)
        self.assertEqual(a.candidate_rank, 2)
        self.assertEqual(c.signal_status, ConditionStatus.FALSE)
        self.assertIsNotNone(c.pool_rank)

    def test_raw_zero_and_missing_day_are_unknown(self) -> None:
        dates = trading_dates(30)
        flows = {}
        for sid in ("SH:600001", "SH:600002"):
            values = {day: num(1) for day in dates}
            for day, value in zip(dates[-5:], (1, 1, 1, -1, -1)):
                values[day] = num(value)
            flows[sid] = values
        flows["SH:600002"][dates[-2]] = raw_zero_unknown(reason="RAW_ZERO_UNCERTIFIED")
        snapshot = make_snapshot(
            dates,
            {"SH:600001": trend(30, 10, "0.002"), "SH:600002": trend(30, 10, "0.002")},
            benchmark_closes=[100] * 30,
            fund_flows=flows,
        )
        result = compute_strategy(snapshot, "S08", default_configs())
        self.assertEqual(result.rows["SH:600002"].signal_status, ConditionStatus.UNKNOWN)
        self.assertFalse(result.pool_complete)
        self.assertIsNone(result.rows["SH:600001"].pool_rank)

    def test_zero_amount_denominator_not_applicable(self) -> None:
        dates = trading_dates(30)
        snapshot = make_snapshot(
            dates,
            {"SH:600001": trend(30, 10, "0.002")},
            benchmark_closes=[100] * 30,
        )
        bars = {}
        for day in dates[-5:]:
            original = snapshot.bars["SH:600001"][day]
            bars[day] = original.__class__(
                date=original.date,
                open=original.open,
                high=original.high,
                low=original.low,
                close=original.close,
                volume=original.volume,
                amount=Numeric(Decimal(0), ValueStatus.CONFIRMED_ZERO),
                adjustment_factor=original.adjustment_factor,
                volume_factor=original.volume_factor,
            )
        snapshot = snapshot.__class__(
            **{**snapshot.__dict__, "bars": {**snapshot.bars, "SH:600001": {**snapshot.bars["SH:600001"], **bars}}}
        )
        result = compute_strategy(snapshot, "S08", default_configs())
        self.assertEqual(result.rows["SH:600001"].eligibility, Eligibility.STRATEGY_NOT_APPLICABLE)
        self.assertIsNone(result.rows["SH:600001"].pool_rank)


class DiagnosticsAndStyleTests(unittest.TestCase):
    def test_six_dimensions_and_missing_is_not_zero_or_fifty(self) -> None:
        dates = trading_dates(70)
        snapshot = make_snapshot(
            dates,
            {"SH:600001": trend(70, 10, "0.002"), "SH:600002": trend(70, 10, "0.001")},
            benchmark_closes=[100] * 70,
        )
        financials = {"SH:600001": default_financial("IND_A", dates[-1])}
        snapshot = snapshot.__class__(
            **{**snapshot.__dict__, "financials": financials}
        )
        diagnostics = compute_diagnostics(snapshot, default_configs())
        row = diagnostics.rows["SH:600001"]
        self.assertEqual(set(row), {"momentum", "reversal", "value", "quality", "low_volatility", "liquidity"})
        self.assertEqual(row["value"].raw_value, Decimal(10))
        self.assertIsNone(row["value"].score)
        self.assertFalse(row["value"].pool_complete)
        self.assertNotEqual(row["value"].score, Decimal(0))
        self.assertNotEqual(row["quality"].score, Decimal(50))
        missing = diagnostics.rows["SH:600002"]
        self.assertIsNone(missing["value"].raw_value)
        self.assertIsNone(missing["value"].score)
        self.assertEqual(missing["value"].status, ValueStatus.MISSING)
        self.assertIsNone(missing["quality"].score)

    def test_styles_change_order_only(self) -> None:
        dates = trading_dates(70)
        snapshot = make_snapshot(
            dates,
            {"SH:600001": trend(70, 10, "0.002"), "SH:600002": trend(70, 10, "0.001")},
            benchmark_closes=[100] * 70,
        )
        from mishi_radar.strategy_core.engine import compute_all

        results = compute_all(snapshot, default_configs())
        before = signal_records(results)
        balanced = style_view("BALANCED/1")
        attack = style_view("ATTACK/1")
        defensive = style_view("DEFENSIVE/1")
        self.assertEqual(balanced.strategy_order[0], "S01")
        self.assertEqual(attack.strategy_order[0], "S02")
        self.assertEqual(defensive.strategy_order[0], "S05")
        self.assertEqual(attack.diagnostic_priority, ("volume_price", "momentum", "fund_flow"))
        self.assertEqual(signal_records(results), before)


if __name__ == "__main__":
    unittest.main()
