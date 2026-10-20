from __future__ import annotations

import unittest
from decimal import Decimal

from mishi_radar.cash_backtest.model import Signal


class SignalContractTests(unittest.TestCase):
    def test_from_dict_accepts_od1_signal_record_shape(self) -> None:
        payload = {
            "signal_id": "S02:SH:600001:2026-10-16:S02_DEFAULT/R3.2-2026-10-19-OD1-v1",
            "security_id": "SH:600001",
            "strategy_id": "S02",
            "config_id": "S02_DEFAULT",
            "config_version": "S02_DEFAULT/R3.2-2026-10-19-OD1-v1",
            "signal_date": "2026-10-16",
            "input_version": "SYNTHETIC-A-1",
            "qualification_status": "SCORABLE",
            "signal_state": "CANDIDATE",
            "signal_status": "TRUE",
            "observation_status": "TRUE",
            "confirmation_status": "TRUE",
            "pool_rank": 1,
            "sample_pool_rank": 1,
            "candidate_rank": 1,
            "sample_candidate_rank": 1,
            "pool_size": 3,
            "candidate_size": 1,
            "pool_complete": True,
            "industry_id": None,
            "industry_pool_rank": None,
            "industry_trigger_rank": None,
            "industry_total_rank": None,
            "formal_candidate": True,
            "replacement_eligible": False,
            "execution_replacement_order": None,
            "entry_conflict_exit": "FALSE",
            "entry_platform_upper": "10",
            "available_at": "UNKNOWN",
            "bound_s01_config_version": None,
            "reasons": [],
            "metrics": {"u20": "10"},
            "conditions": {},
            "sort_key": [],
        }
        signal = Signal.from_dict(payload)
        self.assertEqual(signal.security_id, "SH:600001")
        self.assertEqual(signal.strategy_id, "S02")
        self.assertEqual(signal.entry_platform_upper, Decimal(10))
        self.assertIsNone(signal.available_at)
        self.assertTrue(signal.formal_candidate)


if __name__ == "__main__":
    unittest.main()
