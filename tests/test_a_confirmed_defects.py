from __future__ import annotations

import unittest
from dataclasses import replace
from decimal import Decimal

from mishi_radar.strategy_core.config import (
    S02Config,
    S03Config,
    S04Config,
    S05Config,
    S06Config,
    S07Config,
    S08Config,
    default_configs,
)
from mishi_radar.strategy_core.diagnostics import compute_diagnostics
from mishi_radar.strategy_core.engine import compute_strategy, evaluate_exit, signal_records
from mishi_radar.strategy_core.model import (
    ConditionStatus,
    Eligibility,
    ExitContext,
    Numeric,
    ValueStatus,
    num,
    raw_zero_unknown,
)

from tests.a_fixtures import default_financial, make_snapshot, trading_dates, trend


class ConfigIdentityTests(unittest.TestCase):
    def test_replace_and_common_config_changes_keep_distinct_identity(self) -> None:
        dates = trading_dates(70)
        sid = "SH:600001"
        snapshot = make_snapshot(dates, {sid: trend(70, 10, "0.002")})
        base = default_configs()
        edited = replace(base, s02=replace(base.s02, platform_width=Decimal("0.10")))
        common = replace(base, common=replace(base.common, min_avg_amount_20=Decimal("50000000")))
        records = []
        for bundle in (base, edited, common):
            records.append(
                signal_records({"S02": compute_strategy(snapshot, "S02", bundle)})[0]
            )
        keys = [
            (record["config_id"], record["config_version"], record["signal_id"])
            for record in records
        ]
        self.assertNotEqual(keys[0], keys[1])
        self.assertNotEqual(keys[0], keys[2])
        self.assertNotEqual(keys[1], keys[2])

    def test_personal_configurations_keep_distinct_identity(self) -> None:
        dates = trading_dates(70)
        sid = "SH:600001"
        snapshot = make_snapshot(dates, {sid: trend(70, 10, "0.002")})
        changes = [
            ("S02", "s02", S02Config(platform_width=Decimal("0.10"))),
            ("S03", "s03", S03Config(ma_distance=Decimal("0.02"))),
            ("S04", "s04", S04Config(prior_drop_threshold=Decimal("-0.05"))),
            ("S05", "s05", S05Config(low_vol_percentile=Decimal("0.20"))),
            ("S06", "s06", S06Config(max_per_industry=1)),
            ("S07", "s07", S07Config(roe_threshold=Decimal("0.08"))),
            ("S08", "s08", S08Config(positive_days_required=4)),
        ]
        for strategy_id, key, changed_config in changes:
            with self.subTest(strategy=strategy_id):
                baseline = compute_strategy(snapshot, strategy_id, default_configs())
                changed = compute_strategy(
                    snapshot, strategy_id, replace(default_configs(), **{key: changed_config})
                )
                r0 = signal_records({strategy_id: baseline})[0]
                r1 = signal_records({strategy_id: changed})[0]
                self.assertNotEqual(
                    (r0["config_id"], r0["config_version"], r0["signal_id"]),
                    (r1["config_id"], r1["config_version"], r1["signal_id"]),
                )
                self.assertEqual(changed.config_id, r1["config_id"])
                self.assertEqual(changed.config_version, r1["config_version"])


class DiagnosticPoolTests(unittest.TestCase):
    def test_single_comparable_member_has_no_relative_score(self) -> None:
        dates = trading_dates(70)
        sid = "SH:600001"
        snapshot = make_snapshot(dates, {sid: trend(70, 10, "0.002")})
        result = compute_diagnostics(snapshot)
        for name, dimension in result.rows[sid].items():
            with self.subTest(dimension=name):
                self.assertIsNone(dimension.score)
                self.assertLess(dimension.pool_size, 2)

    def test_unknown_competitor_invalidates_pool_and_is_unknown(self) -> None:
        dates = trading_dates(70)
        ids = ["SH:600001", "SH:600002", "SH:600003"]
        snapshot = make_snapshot(dates, {sid: trend(70, 10, "0.002") for sid in ids})
        securities = dict(snapshot.securities)
        securities[ids[2]] = replace(securities[ids[2]], is_st=None)
        snapshot = replace(snapshot, securities=securities)
        result = compute_diagnostics(snapshot)
        for name, dimension in result.rows[ids[0]].items():
            with self.subTest(dimension=name):
                self.assertIsNone(dimension.score)
                self.assertFalse(dimension.pool_complete)
        for name, dimension in result.rows[ids[2]].items():
            with self.subTest(dimension=name, member=ids[2]):
                self.assertEqual(dimension.status, ValueStatus.UNKNOWN)

    def test_incomplete_universe_invalidates_financial_scores(self) -> None:
        dates = trading_dates(70)
        sid = "SH:600001"
        snapshot = make_snapshot(dates, {sid: trend(70, 10, "0.002")}, universe_complete=False)
        result = compute_diagnostics(snapshot)
        for name in ("value", "quality"):
            dimension = result.rows[sid][name]
            self.assertIsNone(dimension.score)
            self.assertFalse(dimension.pool_complete)


class InvalidInputTests(unittest.TestCase):
    def _snapshot(self):
        dates = trading_dates(70)
        sid = "SH:600001"
        return sid, dates, make_snapshot(dates, {sid: trend(70, 10, "0.002")})

    def test_contradictory_ohlc_is_invalid(self) -> None:
        sid, dates, snapshot = self._snapshot()
        bars = {sid: dict(snapshot.bars[sid])}
        bars[sid][dates[-1]] = replace(bars[sid][dates[-1]], high=num(1))
        result = compute_strategy(replace(snapshot, bars=bars), "S01", default_configs())
        self.assertEqual(result.rows[sid].eligibility, Eligibility.INVALID)

    def test_negative_traded_amount_is_invalid(self) -> None:
        sid, dates, snapshot = self._snapshot()
        bars = {sid: dict(snapshot.bars[sid])}
        bars[sid][dates[-2]] = replace(bars[sid][dates[-2]], amount=num(-1))
        result = compute_strategy(replace(snapshot, bars=bars), "S01", default_configs())
        self.assertEqual(result.rows[sid].eligibility, Eligibility.INVALID)

    def test_bar_business_date_mismatch_is_invalid(self) -> None:
        sid, dates, snapshot = self._snapshot()
        bars = {sid: dict(snapshot.bars[sid])}
        bars[sid][dates[-2]] = replace(bars[sid][dates[-2]], date=dates[-1])
        result = compute_strategy(replace(snapshot, bars=bars), "S01", default_configs())
        self.assertEqual(result.rows[sid].eligibility, Eligibility.INVALID)


class S07FinancialTests(unittest.TestCase):
    def test_future_financial_component_is_unknown(self) -> None:
        dates = trading_dates(70)
        sid = "SH:600001"
        snapshot = make_snapshot(dates, {sid: trend(70, 10, "0.002")})
        base_fin = default_financial("IND_A", dates[-1])
        for component in ("pe_ttm", "np_ytd"):
            with self.subTest(component=component):
                value = getattr(base_fin, component)
                fin = replace(
                    base_fin,
                    **{component: replace(value, available_at=f"{dates[-1]}T23:59:59")},
                )
                local = replace(snapshot, financials={sid: fin})
                result = compute_strategy(local, "S07", default_configs())
                self.assertEqual(result.rows[sid].signal_status, ConditionStatus.UNKNOWN)

    def test_known_false_component_dominates_future_component(self) -> None:
        dates = trading_dates(70)
        sid = "SH:600001"
        snapshot = make_snapshot(dates, {sid: trend(70, 10, "0.002")})
        base_fin = default_financial("IND_A", dates[-1])
        cases = {
            "negative_pe": replace(
                base_fin,
                pe_ttm=num(-1),
                np_ytd=num(-10),
                ocf_ytd=replace(base_fin.ocf_ytd, available_at=f"{dates[-1]}T23:59:59"),
            ),
            "negative_ocf": replace(
                base_fin,
                pe_ttm=num(10),
                np_ytd=replace(base_fin.np_ytd, available_at=f"{dates[-1]}T23:59:59"),
                ocf_ytd=num(-10),
            ),
        }
        for name, fin in cases.items():
            with self.subTest(case=name):
                local = replace(snapshot, financials={sid: fin})
                decision = evaluate_exit(local, "S07", sid, ExitContext(holding_days=1))
                self.assertEqual(decision.status, ConditionStatus.TRUE)
                self.assertIn("STRATEGY_EXIT:S07_CONDITION_FAILED", decision.reasons)
                stop = evaluate_exit(
                    local,
                    "S07",
                    sid,
                    ExitContext(holding_days=1, common_stop_triggered=True),
                )
                self.assertEqual(stop.status, ConditionStatus.TRUE)
                self.assertIn("STOP_LOSS", stop.reasons)

    def test_known_negative_ocf_dominates_missing_profit(self) -> None:
        dates = trading_dates(70)
        sid = "SH:600001"
        snapshot = make_snapshot(dates, {sid: trend(70, 10, "0.002")})
        fin = replace(
            default_financial("IND_A", dates[-1]),
            pe_ttm=num(10),
            np_ytd=Numeric(None, ValueStatus.MISSING, "NP_MISSING"),
            ocf_ytd=num(-10),
        )
        snapshot = replace(snapshot, financials={sid: fin})
        decision = evaluate_exit(snapshot, "S07", sid, ExitContext(holding_days=1))
        self.assertEqual(decision.status, ConditionStatus.TRUE)
        self.assertIn("STRATEGY_EXIT:S07_CONDITION_FAILED", decision.reasons)

    def test_known_nonpositive_pe_exits_s07(self) -> None:
        dates = trading_dates(70)
        sid = "SH:600001"
        snapshot = make_snapshot(dates, {sid: trend(70, 10, "0.002")})
        fin = replace(
            default_financial("IND_A", dates[-1]),
            pe_ttm=num(-1),
            np_ytd=num(-10),
        )
        snapshot = replace(snapshot, financials={sid: fin})
        decision = evaluate_exit(snapshot, "S07", sid, ExitContext(holding_days=1))
        self.assertEqual(decision.status, ConditionStatus.TRUE)
        self.assertIn("STRATEGY_EXIT:S07_CONDITION_FAILED", decision.reasons)


class IncompletePoolTriggerTests(unittest.TestCase):
    def test_s05_incomplete_pool_does_not_confirm_low_vol(self) -> None:
        dates = trading_dates(70)
        ids = ["SH:600001", "SH:600002", "SH:600003"]
        snapshot = make_snapshot(
            dates,
            {
                ids[0]: trend(70, 10, "0.002"),
                ids[1]: trend(70, 10, "0.0018"),
                ids[2]: trend(70, 10, "0.0016"),
            },
        )
        bars = {sid: dict(snapshot.bars[sid]) for sid in ids}
        bars[ids[2]][dates[-30]] = replace(
            bars[ids[2]][dates[-30]], amount=Numeric(None, ValueStatus.MISSING, "AMOUNT_MISSING")
        )
        snapshot = replace(snapshot, bars=bars)
        result = compute_strategy(snapshot, "S05", default_configs())
        row = result.rows[ids[0]]
        self.assertFalse(result.pool_complete)
        self.assertEqual(row.signal_status, ConditionStatus.UNKNOWN)
        self.assertEqual(row.conditions["low_vol_percentile"], ConditionStatus.UNKNOWN)
        self.assertIsNone(row.pool_rank)
        self.assertIsNotNone(row.metrics["q_sigma60"])

    def test_s06_incomplete_industry_section_does_not_confirm_top5(self) -> None:
        dates = trading_dates(70)
        ids = [f"SH:{600001 + index}" for index in range(7)]
        snapshot = make_snapshot(
            dates,
            {sid: trend(70, 10, str(Decimal(".007") - index * Decimal(".001"))) for index, sid in enumerate(ids)},
            industry_by_id={sid: f"G{index}" for index, sid in enumerate(ids)},
        )
        bars = {sid: dict(snapshot.bars[sid]) for sid in ids}
        del bars[ids[0]][dates[-1]]
        snapshot = replace(snapshot, bars=bars)
        result = compute_strategy(snapshot, "S06", default_configs())
        row = result.rows[ids[5]]
        self.assertFalse(result.pool_complete)
        self.assertEqual(row.signal_status, ConditionStatus.UNKNOWN)
        self.assertIsNone(row.industry_total_rank)
        self.assertFalse(result.industries["G5"].strong)


class ThreeValuedLogicTests(unittest.TestCase):
    def test_s08_known_false_price_survives_missing_flow(self) -> None:
        dates = trading_dates(70)
        sid = "SH:600001"
        snapshot = make_snapshot(dates, {sid: [Decimal(10)] * 69 + [Decimal(9)]})
        flows = dict(snapshot.fund_flows[sid])
        flows[dates[-1]] = Numeric(None, ValueStatus.MISSING, "FLOW_MISSING")
        snapshot = replace(snapshot, fund_flows={sid: flows})
        result = compute_strategy(snapshot, "S08", default_configs())
        row = result.rows[sid]
        self.assertEqual(row.signal_status, ConditionStatus.FALSE)
        self.assertTrue(row.reasons)
        self.assertEqual(row.conditions["price_above_ma20"], ConditionStatus.FALSE)

    def test_s08_known_false_flow_survives_missing_price(self) -> None:
        dates = trading_dates(70)
        sid = "SH:600001"
        snapshot = make_snapshot(dates, {sid: trend(70, 10, "0.002")})
        flows = {day: num(-1) for day in dates}
        bars = {sid: dict(snapshot.bars[sid])}
        bars[sid][dates[-1]] = replace(
            bars[sid][dates[-1]],
            close=Numeric(None, ValueStatus.MISSING, "CLOSE_MISSING"),
        )
        snapshot = replace(snapshot, bars=bars, fund_flows={sid: flows})
        result = compute_strategy(snapshot, "S08", default_configs())
        row = result.rows[sid]
        self.assertEqual(row.signal_status, ConditionStatus.FALSE)
        self.assertTrue(row.reasons)
        self.assertNotEqual(row.conditions["price_above_ma20"], ConditionStatus.TRUE)


if __name__ == "__main__":
    unittest.main()
