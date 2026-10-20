from __future__ import annotations

import unittest
from decimal import Decimal

from mishi_radar.strategy_core.config import default_configs
from mishi_radar.strategy_core.engine import compute_strategy, signal_records

from tests.a_fixtures import flat, make_snapshot, trading_dates
from tests.test_a_strategies_core import S02Tests


REQUIRED_FIELDS = {
    "signal_id",
    "security_id",
    "strategy_id",
    "config_id",
    "config_version",
    "signal_date",
    "input_version",
    "qualification_status",
    "signal_state",
    "signal_status",
    "observation_status",
    "confirmation_status",
    "pool_rank",
    "sample_pool_rank",
    "candidate_rank",
    "sample_candidate_rank",
    "pool_size",
    "candidate_size",
    "pool_complete",
    "industry_id",
    "industry_pool_rank",
    "industry_trigger_rank",
    "industry_total_rank",
    "formal_candidate",
    "replacement_eligible",
    "execution_replacement_order",
    "entry_conflict_exit",
    "entry_platform_upper",
    "available_at",
    "bound_s01_config_version",
    "reasons",
    "metrics",
    "conditions",
    "sort_key",
}


class SignalContractTests(unittest.TestCase):
    def test_signal_records_expose_b_consumer_fields(self) -> None:
        dates = trading_dates(30)
        snapshot = make_snapshot(
            dates,
            {"SH:600001": flat(30, "9.5")},
            benchmark_closes=[100] * 30,
            bars_override={"SH:600001": S02Tests()._bars(dates, d_close="10.1", d_volume=1200)},
        )
        result = compute_strategy(snapshot, "S02", default_configs())
        records = signal_records({"S02": result})
        self.assertEqual(len(records), 1)
        record = records[0]
        self.assertTrue(REQUIRED_FIELDS.issubset(record))
        self.assertEqual(record["entry_platform_upper"], "10")
        self.assertEqual(record["available_at"], dates[-1])
        self.assertEqual(record["strategy_id"], "S02")
        self.assertEqual(record["qualification_status"], "SCORABLE")
        self.assertEqual(record["signal_status"], "TRUE")


if __name__ == "__main__":
    unittest.main()
