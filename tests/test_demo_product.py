from __future__ import annotations

import csv
import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

import mishi_radar.demo.service as demo_service
from mishi_radar.cash_backtest import run_backtest
from mishi_radar.demo import (
    CONTRACT_FIXTURE_VERSION,
    CONTRACT_MARKER,
    FIXTURE_MARKER,
    FIXTURE_VERSION,
)
from mishi_radar.demo.app import create_app
from mishi_radar.result_contract import (
    F1_CONTRACT,
    F3_CONTRACT,
    F7_CONTRACT,
    RESULT_CONTRACT_VERSION,
    build_f1,
    build_f3,
    build_f7,
    build_result_bundle,
)


def text(response) -> str:
    return response.content.decode("utf-8")


class FixtureProductTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.store_path = Path(self.tmp.name) / "watchlist.json"
        self.client = TestClient(create_app(self.store_path))

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _f1(self, **params):
        query = {"scenario": "normal", "strategy": "S01", "style": "BALANCED/1", "n": 10}
        query.update(params)
        response = self.client.get("/api/f1", params=query)
        self.assertEqual(response.status_code, 200, text(response))
        return response.json()

    def _add_watch(self, *, scenario="normal", strategy="S01", security_id="SYN:000001"):
        board = self._f1(scenario=scenario, strategy=strategy)
        row = next(
            item
            for item in board["candidates"]
            + board["preview_candidates"]
            + board["unknown_rows"]
            + board["failed_rows"]
            if item["security_id"] == security_id
        )
        response = self.client.post(
            "/api/watch",
            json={
                "scenario": scenario,
                "security_id": security_id,
                "strategy_id": strategy,
                "style": "BALANCED/1",
                "batch_id": row["batch_id"],
            },
        )
        self.assertEqual(response.status_code, 200, text(response))
        return response.json()

    def test_f1_reuses_accepted_contract_and_switches_eight_strategies(self) -> None:
        expected = build_result_bundle("normal", strategy_id="S01", top_n=10, security_id="SYN:000001")
        board = self._f1()
        self.assertEqual(board["contract"]["contract"], F1_CONTRACT)
        self.assertEqual(board["contract"]["contract_version"], RESULT_CONTRACT_VERSION)
        self.assertEqual(board["fixture"]["fixture_version"], CONTRACT_FIXTURE_VERSION)
        self.assertEqual(board["outcome"]["kind"], expected["f1"]["outcome"]["kind"])
        self.assertEqual(board["outcome"]["sample_only"], expected["f1"]["outcome"]["sample_only"])
        self.assertEqual(board["counts"]["formal_candidates"], expected["f1"]["candidates"].__len__())
        self.assertEqual(
            [item["security_id"] for item in board["candidates"]],
            [item["security_id"] for item in expected["f1"]["candidates"]],
        )
        self.assertEqual(
            [item["candidate_rank"] for item in board["candidates"]],
            [item["candidate_rank"] for item in expected["f1"]["candidates"]],
        )
        self.assertEqual(
            [item["pool_rank"] for item in board["candidates"]],
            [item["pool_rank"] for item in expected["f1"]["candidates"]],
        )
        for actual, source in zip(board["candidates"], expected["f1"]["candidates"]):
            self.assertEqual(actual["conditions"], source["conditions"])
            self.assertEqual(actual["reasons"], source["reasons"])
            self.assertEqual(actual["rank_scope"], source["rank_scope"])
            self.assertEqual(actual["row_identity"], source["row_identity"])
            self.assertFalse(actual["actual_published"])
            self.assertIsNone(actual["history_rank"])
            self.assertEqual(
                [tag["strategy_id"] for tag in actual["hit_tags"]],
                [tag["strategy_id"] for tag in source["hit_tags"]],
            )
        self.assertIn("S06", [tag["strategy_id"] for tag in board["candidates"][0]["hit_tags"]])

        strategy_ids = []
        for index in range(1, 9):
            strategy = f"S{index:02d}"
            payload = self._f1(strategy=strategy)
            self.assertEqual(payload["strategy"]["strategy_id"], strategy)
            self.assertEqual(payload["contract"]["contract"], F1_CONTRACT)
            self.assertEqual(len(payload["strategy_catalog"]), 8)
            self.assertEqual(
                [item["strategy_id"] for item in payload["strategy_catalog"]],
                list(payload["style"]["order"]),
            )
            strategy_ids.append(strategy)
        self.assertEqual(strategy_ids, [f"S{index:02d}" for index in range(1, 9)])

        attack = self._f1(strategy="S01", style="ATTACK/1")
        self.assertEqual(
            [(item["security_id"], item["candidate_rank"], item["pool_rank"]) for item in board["candidates"]],
            [(item["security_id"], item["candidate_rank"], item["pool_rank"]) for item in attack["candidates"]],
        )
        self.assertEqual(attack["style"]["order"][0], "S02")
        self.assertEqual(board["style"]["order"][0], "S01")

        demo_service._f1_contract.cache_clear()
        with mock.patch.object(demo_service, "build_f1", wraps=build_f1) as wrapped:
            self.client.get("/api/f1", params={"scenario": "normal", "strategy": "S01"})
            self.assertEqual(wrapped.call_count, 1)

    def test_small_n_reaches_beyond_top_n_exact_ranks(self) -> None:
        for n in (1, 2, 3, 5):
            board = self._f1(strategy="S01", n=n)
            expected = build_result_bundle("normal", strategy_id="S01", top_n=n, security_id="SYN:000001")
            self.assertEqual(
                [item["security_id"] for item in board["candidates"]],
                [item["security_id"] for item in expected["f1"]["candidates"]],
            )
            self.assertEqual(
                [item["security_id"] for item in board["beyond_top_n"]],
                [item["security_id"] for item in expected["f1"]["beyond_top_n"]],
            )
            self.assertEqual(len(board["candidates"]), min(n, 4))
            self.assertEqual(len(board["beyond_top_n"]), max(0, 4 - n))
            for item in board["beyond_top_n"]:
                self.assertTrue(item["formal_candidate"])
                self.assertFalse(item["within_top_n"])
                self.assertEqual(item["rank_scope"], "FIXTURE_BATCH_EXACT")
                self.assertIsNotNone(item["candidate_rank"])
                self.assertIsNotNone(item["pool_rank"])
        n1 = self._f1(strategy="S01", n=1)
        self.assertEqual([item["candidate_rank"] for item in n1["beyond_top_n"]], [2, 3, 4])
        n1_html = text(self.client.get("/?scenario=normal&strategy=S01&style=BALANCED/1&n=1"))
        self.assertIn("榜外但仍具精确名次", n1_html)
        self.assertIn("榜外候选 #2", n1_html)
        csv_text = text(self.client.get("/export/f1.csv?scenario=normal&strategy=S01&n=1"))
        rows = list(csv.reader(io.StringIO(csv_text)))
        header = {name: position for position, name in enumerate(rows[0])}
        ranks = {
            row[header["candidate_rank"]]
            for row in rows[1:]
            if row[header["row_type"]] == "RESULT"
        }
        self.assertEqual(ranks, {"1", "2", "3", "4"})

    def test_f1_to_f3_carries_contract_identity_and_missing_dimensions(self) -> None:
        board = self._f1(strategy="S01")
        candidate = board["candidates"][0]
        response = self.client.get(
            "/api/stock",
            params={
                "scenario": "normal",
                "strategy_id": "S01",
                "style": "BALANCED/1",
                "security_id": candidate["security_id"],
                "batch_id": candidate["batch_id"],
            },
        )
        self.assertEqual(response.status_code, 200, text(response))
        detail = response.json()
        self.assertEqual(detail["contract"]["contract"], F3_CONTRACT)
        self.assertEqual(detail["security_id"], candidate["security_id"])
        self.assertEqual(detail["summary"]["candidate_rank"], candidate["candidate_rank"])
        self.assertEqual(detail["strategy_context"]["config_version"], "S01_DEFAULT/R3.2-2026-10-19-OD1-v1")
        self.assertEqual(detail["strategy_context"]["signal_date"], "2026-10-16")
        self.assertEqual(detail["batch"]["batch_id"], candidate["batch_id"])
        self.assertEqual(len(detail["dimensions"]), 6)
        self.assertTrue(all(item["score"] is not None for item in detail["dimensions"]))
        self.assertIn("S01", detail["divergence"]["hit_strategies"])
        self.assertGreaterEqual(len(detail["divergence"]["hit_strategies"]), 2)
        self.assertEqual(len(detail["strategy_rows"]), 8)
        self.assertIsNone(detail["score_policy"]["cross_strategy_total"])

        expected = build_result_bundle("normal", strategy_id="S01", top_n=10, security_id="SYN:000001")
        source_dimensions = {item["name"]: item for item in expected["f3"]["dimensions"]}
        for item in detail["dimensions"]:
            source = source_dimensions[item["name"]]
            self.assertEqual(item["raw_value"], source["raw_value"])
            self.assertEqual(item["score"], source["score"])
            self.assertEqual(item["status"], source["status"])
            self.assertEqual(item["business_date"], source["business_date"])

        mismatch = self.client.get(
            "/api/stock",
            params={
                "scenario": "normal",
                "strategy_id": "S01",
                "style": "BALANCED/1",
                "security_id": candidate["security_id"],
                "batch_id": "stale-batch",
            },
        )
        self.assertEqual(mismatch.status_code, 409)
        self.assertEqual(mismatch.json()["fixture"]["marker"], FIXTURE_MARKER)
        self.assertEqual(mismatch.json()["fixture"]["contract_version"], RESULT_CONTRACT_VERSION)

        unknown = self._f1(scenario="unknown", strategy="S01")
        response = self.client.get(
            "/api/stock",
            params={
                "scenario": "unknown",
                "strategy_id": "S01",
                "style": "BALANCED/1",
                "security_id": "SYN:000006",
                "batch_id": unknown["batch"]["batch_id"],
            },
        )
        self.assertEqual(response.status_code, 200, text(response))
        payload = response.json()
        self.assertEqual(payload["summary"]["row_identity"], "UNKNOWN")
        self.assertEqual(payload["summary"]["candidate_rank"], None)
        self.assertEqual(len(payload["missing_dimensions"]), 6)
        self.assertTrue(all(item["missing"] for item in payload["dimensions"]))
        self.assertTrue(all(item["score"] is None for item in payload["dimensions"]))

        demo_service._f3_contract.cache_clear()
        with mock.patch.object(demo_service, "build_f3", wraps=build_f3) as wrapped:
            self.client.get(
                "/api/stock",
                params={
                    "scenario": "normal",
                    "strategy_id": "S01",
                    "style": "BALANCED/1",
                    "security_id": "SYN:000001",
                    "batch_id": board["batch"]["batch_id"],
                },
            )
            self.assertEqual(wrapped.call_count, 1)

    def test_empty_preview_unknown_and_failed_are_distinct(self) -> None:
        empty = self._f1(scenario="empty", strategy="S01")
        self.assertEqual(empty["outcome"]["kind"], "EMPTY")
        self.assertTrue(empty["outcome"]["empty_is_success"])
        self.assertEqual(empty["candidates"], [])
        self.assertEqual(empty["unknown_rows"], [])
        self.assertTrue(empty["quality"]["pool_complete"])
        self.assertIn("完整空结果（成功）", text(self.client.get("/?scenario=empty&strategy=S01&style=BALANCED/1")))

        preview = self._f1(scenario="unknown", strategy="S01")
        self.assertEqual(preview["outcome"]["kind"], "PREVIEW")
        self.assertTrue(preview["outcome"]["sample_only"])
        self.assertFalse(preview["outcome"]["formal_identity_available"])
        self.assertEqual(preview["candidates"], [])
        self.assertGreater(len(preview["preview_candidates"]), 0)
        for item in preview["preview_candidates"]:
            self.assertFalse(item["formal_candidate"])
            self.assertTrue(item["preview_candidate"])
            self.assertIsNone(item["candidate_rank"])
            self.assertIsNone(item["pool_rank"])
            self.assertEqual(item["rank_scope"], "SAMPLE_ONLY")
            self.assertIsNotNone(item["sample_candidate_rank"])
        self.assertEqual(preview["unknown_rows"][0]["row_identity"], "UNKNOWN")
        self.assertIn("PREVIEW / 池不完整", text(self.client.get("/?scenario=unknown&strategy=S01&style=BALANCED/1")))

        unavailable = self._f1(scenario="unavailable", strategy="S01")
        self.assertEqual(unavailable["outcome"]["kind"], "UNKNOWN")
        self.assertEqual(unavailable["counts"]["pool_size"], 0)
        self.assertEqual(unavailable["preview_candidates"], [])
        self.assertEqual(len(unavailable["unknown_rows"]), 6)
        self.assertTrue(all(item["row_identity"] == "UNKNOWN" for item in unavailable["unknown_rows"]))
        self.assertTrue(all(item["sample_candidate_rank"] is None for item in unavailable["unknown_rows"]))
        self.assertIn("UNKNOWN / 不产生名次", text(self.client.get("/?scenario=unavailable&strategy=S01&style=BALANCED/1")))

        failed = self._f1(scenario="failed", strategy="S01")
        self.assertEqual(failed["outcome"]["kind"], "FAILED")
        self.assertFalse(failed["outcome"]["computation_ok"])
        self.assertEqual(failed["outcome"]["failure"]["code"], "STRATEGY_INPUT_FAILED")
        self.assertEqual(failed["candidates"], [])
        self.assertEqual(failed["unknown_rows"], [])
        self.assertEqual(len(failed["failed_rows"]), 6)
        self.assertTrue(all(item["row_identity"] == "FAILED" for item in failed["failed_rows"]))
        self.assertIn("FAILED / 输入请求失败", text(self.client.get("/?scenario=failed&strategy=S01&style=BALANCED/1")))

        status = self.client.get("/api/status").json()
        self.assertEqual(
            [item["outcome"]["kind"] for item in status["scenarios"]],
            ["CANDIDATES", "EMPTY", "PREVIEW", "UNKNOWN", "FAILED"],
        )
        self.assertEqual(status["accepted_contract"]["contract_version"], RESULT_CONTRACT_VERSION)

        for scenario, identity in (("unavailable", "UNKNOWN"), ("failed", "FAILED")):
            board = self._f1(scenario=scenario, strategy="S01")
            detail = self.client.get(
                "/api/stock",
                params={
                    "scenario": scenario,
                    "strategy_id": "S01",
                    "style": "BALANCED/1",
                    "security_id": "SYN:000001",
                    "batch_id": board["batch"]["batch_id"],
                },
            )
            self.assertEqual(detail.status_code, 200, text(detail))
            payload = detail.json()
            self.assertEqual(payload["summary"]["row_identity"], identity)
            self.assertEqual(len(payload["dimensions"]), 6)
            self.assertTrue(all(item["missing"] for item in payload["dimensions"]))
            self.assertTrue(all(item["score"] is None for item in payload["dimensions"]))

        demo_service._f7_contract.cache_clear()
        with mock.patch.object(demo_service, "build_f7", wraps=build_f7) as wrapped:
            self.client.get("/api/status")
            self.assertGreaterEqual(wrapped.call_count, 1)

    def test_watch_snapshot_immutable_and_removal_history(self) -> None:
        added = self._add_watch(security_id="SYN:000001")
        entry = added["entry"]
        self.assertEqual(entry["status"], "ACTIVE")
        snapshot = entry["snapshot"]
        self.assertTrue(snapshot["formal_candidate"])
        self.assertEqual(snapshot["candidate_rank"], 1)
        self.assertEqual(snapshot["contract_version"], RESULT_CONTRACT_VERSION)
        self.assertEqual(snapshot["fixture_version"], CONTRACT_FIXTURE_VERSION)
        self.assertEqual(snapshot["row_identity"], "FORMAL_CANDIDATE")

        unknown = self.client.get("/api/watch", params={"scenario": "unknown"}).json()
        self.assertEqual(unknown["active"][0]["snapshot"], snapshot)
        self.assertEqual(unknown["active"][0]["current"]["status"], "PREVIEW")
        self.assertEqual(unknown["active"][0]["current"]["row_identity"], "PREVIEW_CANDIDATE")
        self.assertFalse(unknown["active"][0]["snapshot_changed"])

        unavailable = self.client.get("/api/watch", params={"scenario": "unavailable"}).json()
        self.assertEqual(unavailable["active"][0]["snapshot"], snapshot)
        self.assertEqual(unavailable["active"][0]["current"]["status"], "UNKNOWN")

        html = text(self.client.get("/watch?scenario=unknown"))
        self.assertIn(FIXTURE_MARKER, html)
        self.assertIn("首次快照已冻结", html)
        self.assertIn(RESULT_CONTRACT_VERSION, html)

        removed = self.client.delete(f"/api/watch/{entry['watch_id']}")
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.json()["entry"]["status"], "REMOVED")
        after = self.client.get("/api/watch", params={"scenario": "unavailable"}).json()
        self.assertEqual(after["active"], [])
        self.assertEqual(after["removed"][0]["snapshot"], snapshot)

        again = self._add_watch(security_id="SYN:000001")
        self.assertNotEqual(again["entry"]["watch_id"], entry["watch_id"])
        self.assertEqual(len(self.client.get("/api/watch").json()["removed"]), 1)

    def test_f6_uses_od2_kernel_and_reconciles(self) -> None:
        with mock.patch("mishi_radar.demo.backtest.run_backtest", wraps=run_backtest) as wrapped:
            response = self.client.get("/api/backtest/u3")
            self.assertEqual(response.status_code, 200, text(response))
            self.assertEqual(wrapped.call_count, 1)
            data = response.json()

        self.assertEqual(data["status"], "SUCCEEDED")
        self.assertEqual(data["meta"]["engine"], "mishi_radar.cash_backtest.run_backtest")
        self.assertTrue(data["synthetic"])
        self.assertTrue(data["reconciliation_ok"])
        self.assertEqual(data["nav"][-1]["cash"], "3564.40")
        self.assertEqual(data["nav"][-1]["equity"], "3564.40")
        self.assertEqual(data["nav"][-1]["nav"], "0.8911")
        self.assertEqual(data["nav"][-1]["position_ratio_text"], "0.00%")
        self.assertEqual(len(data["fills"]), 3)
        self.assertEqual([item["version"] for item in data["fees"]], ["F1", "F2", "F2"])
        self.assertEqual(sorted(item["tax"] for item in data["dividend_taxes"]), ["0.00", "20.00"])
        self.assertEqual(data["closed_cycles"][0]["total_pnl"], "-435.60")
        self.assertTrue(all(item["cash_ok"] and item["equity_ok"] for item in data["reconciliation"]))
        self.assertIn("累计收益", [item["label"] for item in data["metric_rows"]])

        again = self.client.get("/api/backtest/u3").json()
        self.assertEqual(data["nav"], again["nav"])
        self.assertEqual(data["orders"], again["orders"])
        self.assertEqual(data["fees"], again["fees"])

        failures = self.client.get("/api/backtest/failures").json()
        reasons = {(item["security_id"], item["status"], item["reason"]) for item in failures["failed_orders"]}
        self.assertIn(("SH:600001", "UNFILLED", "SUSPENDED"), reasons)
        self.assertIn(("SH:600003", "UNFILLED", "LIMIT_DOWN"), reasons)
        blocked = self.client.get("/api/backtest/blocked").json()
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertEqual(blocked["nav"], [])
        empty = self.client.get("/api/backtest/empty").json()
        self.assertEqual(empty["status"], "SUCCEEDED")
        self.assertEqual(empty["nav"][-1]["nav"], "1")
        self.assertEqual(empty["fills"], [])

        html = text(self.client.get("/backtest?scenario=u3"))
        self.assertIn("3564.40", html)
        self.assertIn("mishi_radar.cash_backtest.run_backtest", html)
        self.assertIn(FIXTURE_MARKER, html)

    def test_fixture_identity_in_pages_apis_and_exports(self) -> None:
        stock = self._f1()["candidates"][0]
        stock_url = (
            "/stock?scenario=normal&strategy_id=S01&style=BALANCED%2F1"
            f"&security_id={stock['security_id'].replace(':', '%3A')}"
            f"&batch_id={stock['batch_id'].replace(':', '%3A').replace('/', '%2F')}"
        )
        for path in ("/", "/?scenario=failed", stock_url, "/watch", "/backtest", "/status"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            body = text(response)
            self.assertIn(FIXTURE_MARKER, body, path)
            self.assertIn("SYNTHETIC / FIXTURE", body, path)
            self.assertIn(RESULT_CONTRACT_VERSION, body, path)
            self.assertIn("SYNTHETIC; FIXTURE; NON-REAL-MARKET", response.headers["X-Mishi-Fixture"])
            self.assertEqual(response.headers["X-Mishi-Fixture-Version"], FIXTURE_VERSION)
            self.assertEqual(response.headers["X-Mishi-Contract-Fixture-Version"], CONTRACT_FIXTURE_VERSION)
            self.assertEqual(response.headers["X-Mishi-Contract-Version"], RESULT_CONTRACT_VERSION)

        for path in ("/api/f1", "/api/status", "/api/backtest/u3", "/api/health"):
            payload = self.client.get(path).json()
            body = text(self.client.get(path))
            self.assertIn("SYNTHETIC / FIXTURE", body, path)
            self.assertIn(RESULT_CONTRACT_VERSION, body, path)
            self.assertFalse(payload.get("fixture", {}).get("real_market_data", False) if isinstance(payload.get("fixture"), dict) else False)

        f1_csv = text(self.client.get("/export/f1.csv?scenario=normal&strategy=S01"))
        rows = list(csv.reader(io.StringIO(f1_csv)))
        header = rows[0]
        index = {name: position for position, name in enumerate(header)}
        self.assertEqual(header[0], "fixture_marker")
        self.assertIn("contract_version", header)
        self.assertIn("row_identity", header)
        self.assertIn("row_type", header)
        self.assertGreater(len(rows), 1)
        widths = {len(row) for row in rows}
        self.assertEqual(len(widths), 1)
        for row in rows[1:]:
            self.assertEqual(row[index["fixture_marker"]], FIXTURE_MARKER)
            self.assertEqual(row[index["contract_version"]], RESULT_CONTRACT_VERSION)
            self.assertEqual(row[index["fixture_version"]], CONTRACT_FIXTURE_VERSION)
            self.assertEqual(row[index["history_rank"]], "")
            self.assertEqual(row[index["actual_published"]], "False")
            self.assertEqual(row[index["row_type"]], "RESULT")

        empty_csv = text(self.client.get("/export/f1.csv?scenario=empty&strategy=S01"))
        empty_rows = list(csv.reader(io.StringIO(empty_csv)))
        empty_header = empty_rows[0]
        empty_index = {name: position for position, name in enumerate(empty_header)}
        self.assertEqual(len(empty_rows), 2)
        status_row = empty_rows[1]
        self.assertEqual(status_row[empty_index["fixture_marker"]], FIXTURE_MARKER)
        self.assertEqual(status_row[empty_index["contract_version"]], RESULT_CONTRACT_VERSION)
        self.assertEqual(status_row[empty_index["fixture_version"]], CONTRACT_FIXTURE_VERSION)
        self.assertEqual(status_row[empty_index["outcome"]], "EMPTY")
        self.assertEqual(status_row[empty_index["row_identity"]], "EMPTY")
        self.assertEqual(status_row[empty_index["row_type"]], "STATUS")
        self.assertEqual(status_row[empty_index["reasons"]], "EMPTY_IS_SUCCESS")
        self.assertTrue(status_row[empty_index["batch_id"]])
        self.assertEqual(status_row[empty_index["security_id"]], "")
        self.assertEqual(status_row[empty_index["candidate_rank"]], "")
        self.assertEqual(status_row[empty_index["pool_size"]], "6")
        self.assertEqual(status_row[empty_index["pool_complete"]], "True")
        self.assertEqual(status_row[empty_index["actual_published"]], "False")
        self.assertEqual(status_row[empty_index["history_rank"]], "")

        f6_csv = text(self.client.get("/export/f6.csv?scenario=u3"))
        rows = list(csv.reader(io.StringIO(f6_csv)))
        self.assertEqual({len(row) for row in rows}, {19})
        for row in rows[1:]:
            self.assertEqual(row[0], FIXTURE_MARKER)
            self.assertEqual(row[1], FIXTURE_VERSION)
        self.assertTrue(any(row[3] == "ORDER" and row[7] == "FILLED" for row in rows[1:]))

        self.assertEqual(CONTRACT_MARKER, "SYNTHETIC / FIXTURE")

    def test_responsive_viewport_and_mobile_css(self) -> None:
        home = text(self.client.get("/"))
        self.assertIn('name="viewport"', home)
        self.assertIn("width=device-width", home)
        self.assertIn("F1 今日机会", home)
        self.assertIn("查看个股诊断 F3", home)
        stock_link = next(
            part.split('"')[0]
            for part in home.split('href="')
            if part.startswith("/stock?")
        ).replace("&amp;", "&")
        self.assertIn("batch_id=", stock_link)
        self.assertIn("strategy_id=S01", stock_link)
        detail = text(self.client.get(stock_link))
        self.assertIn("F3 个股诊断", detail)
        self.assertIn("六维描述性画像", detail)
        css = text(self.client.get("/static/app.css"))
        self.assertIn("@media (max-width: 760px)", css)
        self.assertIn("overflow-x: auto", css)
        self.assertIn(".candidate-card", css)


if __name__ == "__main__":
    unittest.main()
