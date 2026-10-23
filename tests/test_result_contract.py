from __future__ import annotations

import json
import unittest

from mishi_radar.result_contract import (
    F1_CONTRACT,
    F3_CONTRACT,
    F7_CONTRACT,
    RESULT_CONTRACT_VERSION,
    build_f1,
    build_f3,
    build_f7,
    build_fixture_snapshot,
    build_result_bundle,
    dumps,
    fixture_metadata,
)
from mishi_radar.strategy_core import compute_all, compute_diagnostics
from mishi_radar.strategy_core.model import SignalState


SIX_DIMENSIONS = (
    "momentum",
    "reversal",
    "value",
    "quality",
    "low_volatility",
    "liquidity",
)


def _kernel(scenario: str):
    snapshot = build_fixture_snapshot(scenario)
    return snapshot, compute_all(snapshot), compute_diagnostics(snapshot)


class ResultContractTests(unittest.TestCase):
    def test_f1_multi_hit_matches_kernel_rows(self) -> None:
        snapshot, results, _diagnostics = _kernel("normal")
        payload = build_f1(
            results,
            snapshot,
            fixture=fixture_metadata("normal"),
            strategy_id="S01",
            top_n=10,
        )
        candidate = next(item for item in payload["candidates"] if item["security_id"] == "SYN:000001")
        kernel_hits = {
            strategy_id: result.rows["SYN:000001"]
            for strategy_id, result in results.items()
            if result.rows["SYN:000001"].signal_state is SignalState.CANDIDATE
        }
        tags = {item["strategy_id"]: item for item in candidate["hit_tags"]}
        self.assertEqual(set(tags), set(kernel_hits))
        self.assertGreaterEqual(len(tags), 2)
        for strategy_id, row in kernel_hits.items():
            tag = tags[strategy_id]
            self.assertEqual(tag["config_id"], row.config_id)
            self.assertEqual(tag["config_version"], row.config_version)
            self.assertEqual(tag["input_version"], row.input_version)
            self.assertEqual(tag["signal_date"], row.signal_date)
            self.assertEqual(tag["signal_state"], row.signal_state.value)
            self.assertEqual(tag["candidate_rank"], row.candidate_rank)
            self.assertEqual(tag["pool_rank"], row.pool_rank)
            self.assertEqual(tag["sample_candidate_rank"], row.sample_candidate_rank)
            self.assertEqual(tag["sample_pool_rank"], row.sample_pool_rank)
            self.assertEqual(
                tag["conditions"],
                {key: value.value for key, value in row.conditions.items()},
            )
            self.assertEqual(tag["reasons"], list(row.reasons))

    def test_f1_top_n_keeps_exact_beyond_rank_and_preview_uses_samples(self) -> None:
        snapshot, results, _diagnostics = _kernel("normal")
        payload = build_f1(
            results,
            snapshot,
            fixture=fixture_metadata("normal"),
            strategy_id="S01",
            top_n=2,
        )
        self.assertEqual(len(payload["candidates"]), 2)
        self.assertEqual(len(payload["beyond_top_n"]), 2)
        self.assertEqual(payload["counts"]["formal_candidates"], 4)
        self.assertEqual(
            [item["candidate_rank"] for item in payload["candidates"]],
            [1, 2],
        )
        self.assertEqual(
            [item["candidate_rank"] for item in payload["beyond_top_n"]],
            [3, 4],
        )
        for item in payload["candidates"]:
            self.assertTrue(item["within_top_n"])
            self.assertEqual(item["rank_scope"], "FIXTURE_BATCH_EXACT")
            kernel_row = results["S01"].rows[item["security_id"]]
            self.assertEqual(item["candidate_rank"], kernel_row.candidate_rank)
            self.assertEqual(item["pool_rank"], kernel_row.pool_rank)
        for item in payload["beyond_top_n"]:
            self.assertFalse(item["within_top_n"])
            self.assertEqual(item["rank_scope"], "FIXTURE_BATCH_EXACT")
            self.assertIsNotNone(item["candidate_rank"])
            self.assertIsNotNone(item["pool_rank"])
            kernel_row = results["S01"].rows[item["security_id"]]
            self.assertEqual(item["candidate_rank"], kernel_row.candidate_rank)
            self.assertEqual(item["pool_rank"], kernel_row.pool_rank)

        unknown_snapshot, unknown_results, _ = _kernel("unknown")
        preview = build_f1(
            unknown_results,
            unknown_snapshot,
            fixture=fixture_metadata("unknown"),
            strategy_id="S01",
            top_n=2,
        )
        self.assertEqual(preview["outcome"]["kind"], "PREVIEW")
        self.assertFalse(preview["outcome"]["formal_identity_available"])
        self.assertTrue(preview["outcome"]["sample_only"])
        self.assertEqual(preview["candidates"], [])
        self.assertEqual(preview["beyond_top_n"], [])
        self.assertGreater(len(preview["preview_candidates"]), 0)
        for item in preview["preview_candidates"]:
            self.assertIsNone(item["candidate_rank"])
            self.assertIsNone(item["pool_rank"])
            self.assertIsNotNone(item["sample_candidate_rank"])
            self.assertIsNotNone(item["sample_pool_rank"])
            self.assertFalse(item["formal_candidate"])
            self.assertEqual(item["rank_scope"], "SAMPLE_ONLY")
            kernel_row = unknown_results["S01"].rows[item["security_id"]]
            self.assertEqual(item["sample_candidate_rank"], kernel_row.sample_candidate_rank)
            self.assertEqual(item["sample_pool_rank"], kernel_row.sample_pool_rank)

    def test_f3_preserves_six_dimensions_units_windows_and_status(self) -> None:
        snapshot, results, diagnostics = _kernel("normal")
        payload = build_f3(
            diagnostics,
            results,
            snapshot,
            fixture=fixture_metadata("normal"),
            security_id="SYN:000001",
            strategy_id="S01",
        )
        self.assertEqual(len(payload["dimensions"]), 6)
        self.assertEqual(
            [item["name"] for item in payload["dimensions"]],
            list(SIX_DIMENSIONS),
        )
        kernel_dimensions = diagnostics.rows["SYN:000001"]
        for item in payload["dimensions"]:
            source = kernel_dimensions[item["name"]]
            expected_raw = format(source.raw_value, "f") if source.raw_value is not None else None
            expected_score = format(source.score, "f") if source.score is not None else None
            self.assertEqual(item["raw_value"], expected_raw)
            self.assertEqual(item["score"], expected_score)
            self.assertEqual(item["unit"], source.unit)
            self.assertEqual(item["window"], source.window)
            self.assertEqual(item["business_date"], source.business_date)
            self.assertEqual(item["status"], source.status.value)
            self.assertEqual(item["explanation"], source.explanation)
            self.assertFalse(item["missing"])
        self.assertIsNone(payload["score_policy"]["cross_strategy_total"])
        self.assertEqual(payload["score_policy"]["rule"], "NO_CROSS_STRATEGY_TOTAL_SCORE")
        text = dumps(payload)
        self.assertNotIn('"total_score"', text)
        self.assertNotIn('"cross_strategy_total": "', text)

        unknown_snapshot, unknown_results, unknown_diagnostics = _kernel("unknown")
        unknown_payload = build_f3(
            unknown_diagnostics,
            unknown_results,
            unknown_snapshot,
            fixture=fixture_metadata("unknown"),
            security_id="SYN:000006",
            strategy_id="S01",
        )
        for item in unknown_payload["dimensions"]:
            self.assertEqual(item["status"], "MISSING")
            self.assertIsNone(item["raw_value"])
            self.assertTrue(item["missing"])
        self.assertEqual(len(unknown_payload["missing_dimensions"]), 6)

    def test_f3_keeps_adverse_conditions_missing_dimensions_and_strategy_divergence(self) -> None:
        snapshot, results, diagnostics = _kernel("normal")
        payload = build_f3(
            diagnostics,
            results,
            snapshot,
            fixture=fixture_metadata("normal"),
            security_id="SYN:000003",
            strategy_id="S01",
        )
        self.assertEqual(len(payload["strategy_rows"]), 8)
        self.assertIn("S01", payload["divergence"]["hit_strategies"])
        self.assertIn("S07", payload["divergence"]["non_hit_strategies"])
        self.assertIn("roe_threshold", payload["adverse_conditions_by_strategy"]["S07"])
        self.assertIn("concentration_slot", payload["adverse_conditions_by_strategy"]["S06"])
        self.assertIn("CONCENTRATION_EXCLUDED", payload["reasons_by_strategy"]["S06"])
        self.assertEqual(payload["divergence"]["candidate_rank_by_strategy"]["S01"], 3)
        self.assertEqual(payload["divergence"]["candidate_rank_by_strategy"]["S07"], None)
        self.assertEqual(
            payload["strategy_rows"][0]["strategy_id"],
            "S01",
        )
        self.assertEqual(
            [item["strategy_id"] for item in payload["strategy_rows"]],
            [f"S{index:02d}" for index in range(1, 9)],
        )

    def test_empty_unknown_and_failed_are_distinct(self) -> None:
        normal = build_result_bundle("normal")
        empty = build_result_bundle("empty")
        unknown = build_result_bundle("unknown")
        unavailable = build_result_bundle("unavailable")
        failed = build_result_bundle("failed")

        self.assertEqual(normal["f1"]["outcome"]["kind"], "CANDIDATES")
        self.assertEqual(empty["f1"]["outcome"]["kind"], "EMPTY")
        self.assertTrue(empty["f1"]["outcome"]["empty_is_success"])
        self.assertTrue(empty["f1"]["outcome"]["computation_ok"])
        self.assertEqual(empty["f1"]["candidates"], [])
        self.assertTrue(empty["f1"]["batch"]["pool_complete"])
        self.assertEqual(empty["f1"]["unknown_rows"], [])

        self.assertEqual(unknown["f1"]["outcome"]["kind"], "PREVIEW")
        self.assertTrue(unknown["f1"]["outcome"]["sample_only"])
        self.assertFalse(unknown["f1"]["outcome"]["formal_identity_available"])
        self.assertGreater(unknown["f1"]["counts"]["preview_candidates"], 0)
        self.assertGreater(unknown["f1"]["quality"]["unknown_rows"], 0)
        self.assertEqual(unknown["f1"]["quality"]["failed_rows"], 0)

        self.assertEqual(unavailable["f1"]["outcome"]["kind"], "UNKNOWN")
        self.assertGreater(unavailable["f1"]["quality"]["unknown_rows"], 0)
        self.assertEqual(unavailable["f1"]["quality"]["failed_rows"], 0)
        self.assertTrue(
            all(item["row_identity"] == "UNKNOWN" for item in unavailable["f1"]["unknown_rows"])
        )

        self.assertEqual(failed["f1"]["outcome"]["kind"], "FAILED")
        self.assertFalse(failed["f1"]["outcome"]["computation_ok"])
        self.assertIsNotNone(failed["f1"]["outcome"]["failure"])
        self.assertEqual(failed["f1"]["quality"]["failed_rows"], 6)
        self.assertEqual(failed["f1"]["quality"]["unknown_rows"], 0)
        self.assertEqual(failed["f1"]["unknown_rows"], [])
        self.assertTrue(all(item["row_identity"] == "FAILED" for item in failed["f1"]["failed_rows"]))

        self.assertEqual(
            {
                normal["f1"]["outcome"]["kind"],
                empty["f1"]["outcome"]["kind"],
                unknown["f1"]["outcome"]["kind"],
                unavailable["f1"]["outcome"]["kind"],
                failed["f1"]["outcome"]["kind"],
            },
            {"CANDIDATES", "EMPTY", "PREVIEW", "UNKNOWN", "FAILED"},
        )
        for bundle in (normal, empty, unknown, unavailable, failed):
            unknown_ids = {item["security_id"] for item in bundle["f1"]["unknown_rows"]}
            failed_ids = {item["security_id"] for item in bundle["f1"]["failed_rows"]}
            self.assertFalse(unknown_ids & failed_ids)

    def test_f7_marks_synthetic_unknown_source_time_and_no_actual_publication(self) -> None:
        for scenario in ("normal", "unknown", "failed", "unavailable"):
            snapshot, results, _diagnostics = _kernel(scenario)
            payload = build_f7(results, snapshot, fixture=fixture_metadata(scenario))
            self.assertEqual(payload["schema"]["contract"], F7_CONTRACT)
            self.assertEqual(payload["marker"], "SYNTHETIC / FIXTURE")
            self.assertEqual(payload["fixture"]["marker"], "SYNTHETIC / FIXTURE")
            self.assertEqual(payload["fixture"]["source"], "FIXTURE")
            self.assertFalse(payload["fixture"]["real_market_data"])
            self.assertFalse(payload["fixture"]["network_used"])
            self.assertEqual(payload["availability"]["source_time"], "UNKNOWN")
            self.assertEqual(payload["availability"]["source_time_status"], "UNKNOWN")
            self.assertEqual(payload["availability"]["source_times"]["price"], "UNKNOWN")
            self.assertEqual(payload["availability"]["source_times"]["financial"], "UNKNOWN")
            self.assertEqual(payload["availability"]["source_times"]["fund_flow"], "UNKNOWN")
            self.assertEqual(payload["availability"]["source_times"]["industry"], "UNKNOWN")
            self.assertFalse(payload["publication_identity"]["actual_published"])
            self.assertFalse(payload["publication_identity"]["history_ranking_writable"])
            self.assertFalse(payload["gates"]["formal_history_ranking"])
            self.assertNotIn("ACTUAL_PUBLISHED", dumps(payload))
            self.assertEqual(
                set(payload["coverage"]["strategies"]),
                {f"S{index:02d}" for index in range(1, 9)},
            )

        normal_snapshot, normal_results, _ = _kernel("normal")
        normal = build_f7(normal_results, normal_snapshot, fixture=fixture_metadata("normal"))
        self.assertEqual(normal["availability"]["available_at_kind"], "SYNTHETIC_DATE_COMPAT")
        self.assertEqual(normal["quality"]["unknown_rows"], 0)
        self.assertTrue(normal["coverage"]["all_strategies_pool_complete"])

        unknown_snapshot, unknown_results, _ = _kernel("unknown")
        unknown = build_f7(unknown_results, unknown_snapshot, fixture=fixture_metadata("unknown"))
        self.assertFalse(unknown["coverage"]["universe_complete"])
        self.assertGreater(unknown["quality"]["unknown_rows"], 0)
        self.assertIn("S01", unknown["quality"]["partial_strategies"])

        failed_snapshot, failed_results, _ = _kernel("failed")
        failed = build_f7(failed_results, failed_snapshot, fixture=fixture_metadata("failed"))
        self.assertGreater(failed["quality"]["failed_rows"], 0)
        self.assertEqual(failed["quality"]["unknown_rows"], 0)
        self.assertIn("S01", failed["quality"]["failed_strategies"])

        unavailable_snapshot, unavailable_results, _ = _kernel("unavailable")
        unavailable = build_f7(
            unavailable_results,
            unavailable_snapshot,
            fixture=fixture_metadata("unavailable"),
        )
        self.assertEqual(unavailable["availability"]["available_at"], "UNKNOWN")
        self.assertEqual(unavailable["availability"]["available_at_kind"], "UNKNOWN")
        self.assertEqual(unavailable["availability"]["availability_status"], "UNKNOWN")

    def test_repeated_build_and_json_serialization_are_deterministic(self) -> None:
        first = build_result_bundle("normal", strategy_id="S01", top_n=10, security_id="SYN:000001")
        second = build_result_bundle("normal", strategy_id="S01", top_n=10, security_id="SYN:000001")
        self.assertEqual(dumps(first), dumps(second))
        self.assertEqual(json.loads(dumps(first)), first)
        self.assertEqual(first["schema"]["contract"], "MISHI-FX01A-RESULT-BUNDLE")
        self.assertEqual(first["schema"]["contract_version"], RESULT_CONTRACT_VERSION)
        self.assertEqual(first["marker"], "SYNTHETIC / FIXTURE")
        self.assertEqual(first["f1"]["schema"]["contract"], F1_CONTRACT)
        self.assertEqual(first["f3"]["schema"]["contract"], F3_CONTRACT)
        self.assertEqual(first["f7"]["schema"]["contract"], F7_CONTRACT)

    def test_f1_rows_never_claim_actual_publication_or_history_rank(self) -> None:
        payload = build_result_bundle("normal", top_n=2)
        text = dumps(payload)
        self.assertNotIn("ACTUAL_PUBLISHED", text)
        self.assertNotIn('"actual_published": true', text)
        self.assertEqual(payload["publication_identity"]["identity"], "SYNTHETIC_FIXTURE")
        self.assertFalse(payload["publication_identity"]["actual_published"])
        self.assertFalse(payload["publication_identity"]["history_ranking_writable"])
        self.assertEqual(payload["f1"]["batch"]["batch_identity"], "SYNTHETIC_FIXTURE_BATCH")
        self.assertFalse(payload["f1"]["batch"]["actual_published"])
        self.assertFalse(payload["f1"]["batch"]["history_ranking_writable"])
        for row in (
            payload["f1"]["candidates"]
            + payload["f1"]["beyond_top_n"]
            + payload["f1"]["preview_candidates"]
            + payload["f1"]["unknown_rows"]
        ):
            self.assertFalse(row["actual_published"])
            self.assertIsNone(row["history_rank"])
            self.assertFalse(row["history_ranking_writable"])

    def test_f3_does_not_generate_cross_strategy_score(self) -> None:
        payload = build_result_bundle("normal", security_id="SYN:000001")
        f3 = payload["f3"]
        self.assertIsNone(f3["score_policy"]["cross_strategy_total"])
        self.assertIsNone(f3["score_policy"]["cross_strategy_prediction"])
        for item in f3["dimensions"]:
            self.assertIn(item["status"], {"VALUE", "CONFIRMED_ZERO", "NOT_APPLICABLE", "MISSING", "UNKNOWN"})
        text = dumps(f3)
        self.assertNotIn("prediction_score", text)
        self.assertNotIn("cross_strategy_score", text)


if __name__ == "__main__":
    unittest.main()

