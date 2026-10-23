from __future__ import annotations

import csv
import io
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from mishi_radar.cash_backtest import run_backtest
from mishi_radar.demo import FIXTURE_MARKER, FIXTURE_VERSION
from mishi_radar.demo.app import create_app


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

    def _watch(self, *, scenario="normal", strategy="S01", security_id="SH:600001"):
        data = self._f1(scenario=scenario, strategy=strategy)
        candidate = next(
            item
            for item in data["candidates"] + data["preview_candidates"]
            if item["security_id"] == security_id
        )
        response = self.client.post(
            "/api/watch",
            json={
                "scenario": scenario,
                "security_id": security_id,
                "strategy_id": strategy,
                "style": "BALANCED/1",
                "batch_id": candidate["batch_id"],
            },
        )
        self.assertEqual(response.status_code, 200, text(response))
        return response.json()

    def test_f1_strategy_switch_and_stable_rank_identity(self) -> None:
        s01_balanced = self._f1(strategy="S01", style="BALANCED/1")
        s01_balanced_again = self._f1(strategy="S01", style="BALANCED/1")
        s01_attack = self._f1(strategy="S01", style="ATTACK/1")
        s02 = self._f1(strategy="S02", style="BALANCED/1")

        self.assertEqual(s01_balanced["batch"]["status"], "PUBLISHED_FIXTURE")
        self.assertEqual(s01_balanced["counts"]["formal_candidates"], 8)
        self.assertEqual(s01_balanced, s01_balanced_again)
        self.assertEqual(
            [(item["security_id"], item["candidate_rank"], item["pool_rank"]) for item in s01_balanced["candidates"]],
            [(item["security_id"], item["candidate_rank"], item["pool_rank"]) for item in s01_attack["candidates"]],
        )
        self.assertEqual(s01_balanced["candidates"][0]["security_id"], "SH:600012")
        self.assertEqual(s01_balanced["candidates"][0]["candidate_rank"], 1)
        self.assertEqual(s02["candidates"][0]["security_id"], "SH:600004")
        self.assertEqual(s02["candidates"][0]["candidate_rank"], 1)
        self.assertNotEqual(
            [item["security_id"] for item in s01_balanced["candidates"]],
            [item["security_id"] for item in s02["candidates"]],
        )
        self.assertIn("SH:600001", [item["security_id"] for item in s01_balanced["candidates"]])
        multi_hit = next(item for item in s01_balanced["candidates"] if item["security_id"] == "SH:600001")
        self.assertIn("S06", [tag["strategy_id"] for tag in multi_hit["hit_tags"]])
        self.assertIn("S07", [tag["strategy_id"] for tag in multi_hit["hit_tags"]])

    def test_f1_to_f3_carries_security_rule_and_batch(self) -> None:
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
        self.assertEqual(detail["security_id"], candidate["security_id"])
        self.assertEqual(detail["summary"]["strategy_id"], "S01")
        self.assertEqual(detail["time"]["batch_id"], candidate["batch_id"])
        self.assertEqual(detail["time"]["config_version"], "S01_DEFAULT/R3.2-2026-10-19-OD1-v1")
        self.assertEqual(detail["time"]["signal_date"], "2026-10-16")
        self.assertEqual(len(detail["dimensions"]), 6)

        mismatch = self.client.get(
            "/api/stock",
            params={
                "scenario": "normal",
                "strategy_id": "S01",
                "style": "BALANCED/1",
                "security_id": candidate["security_id"],
                "batch_id": "FX01:stale:batch",
            },
        )
        self.assertEqual(mismatch.status_code, 409)
        payload = mismatch.json()
        self.assertIn("error", payload)
        self.assertEqual(payload["fixture"]["marker"], FIXTURE_MARKER)
        self.assertFalse(payload["fixture"]["real_market_data"])

        html = text(
            self.client.get(
                "/stock",
                params={
                    "scenario": "normal",
                    "strategy_id": "S01",
                    "style": "BALANCED/1",
                    "security_id": candidate["security_id"],
                    "batch_id": candidate["batch_id"],
                },
            )
        )
        self.assertIn(FIXTURE_MARKER, html)
        self.assertIn("六维描述性画像", html)

    def test_unknown_and_empty_are_never_formal_candidates(self) -> None:
        preview = self._f1(scenario="unknown", strategy="S01")
        self.assertEqual(preview["batch"]["status"], "PREVIEW")
        self.assertEqual(preview["batch"]["status_label"], "PREVIEW / 池不完整（不是正式发布）")
        self.assertEqual(preview["candidates"], [])
        self.assertGreater(len(preview["preview_candidates"]), 0)
        for item in preview["preview_candidates"]:
            self.assertFalse(item["formal_candidate"])
            self.assertTrue(item["preview_candidate"])
            self.assertIsNone(item["candidate_rank"])
            self.assertIsNone(item["pool_rank"])
            self.assertIsNotNone(item["sample_candidate_rank"])
        unknown_stock = self.client.get(
            "/api/stock",
            params={
                "scenario": "unknown",
                "strategy_id": "S01",
                "style": "BALANCED/1",
                "security_id": "SH:600012",
                "batch_id": preview["batch"]["batch_id"],
            },
        ).json()
        self.assertEqual(unknown_stock["summary"]["signal_state"], "MISSING")
        self.assertEqual(unknown_stock["summary"]["candidate_rank"], None)
        self.assertTrue(all(item["score"] is None for item in unknown_stock["dimensions"]))

        empty = self._f1(scenario="empty", strategy="S01")
        self.assertEqual(empty["batch"]["status"], "EMPTY")
        self.assertEqual(empty["candidates"], [])
        self.assertEqual(empty["preview_candidates"], [])
        self.assertEqual(empty["counts"]["formal_candidates"], 0)
        self.assertTrue(empty["batch"]["pool_complete"])
        empty_html = text(self.client.get("/?scenario=empty&strategy=S01&style=BALANCED/1"))
        self.assertIn("完整空结果（成功）", empty_html)

        blocked = self.client.get("/api/backtest/blocked").json()
        self.assertEqual(blocked["status"], "BLOCKED")
        self.assertFalse(blocked["succeeded"])
        self.assertEqual(blocked["nav"], [])
        self.assertTrue(blocked["blockers"])
        self.assertIn("SIGNAL_AVAILABILITY_UNKNOWN", blocked["blockers"][0])

        failures = self.client.get("/api/backtest/failures").json()
        self.assertEqual(failures["status"], "SUCCEEDED")
        reasons = {(item["security_id"], item["status"], item["reason"]) for item in failures["failed_orders"]}
        self.assertIn(("SH:600001", "UNFILLED", "SUSPENDED"), reasons)
        self.assertIn(("SH:600003", "UNFILLED", "LIMIT_DOWN"), reasons)

    def test_watch_snapshot_is_immutable_and_removal_keeps_history(self) -> None:
        added = self._watch(scenario="normal", security_id="SH:600001")
        entry = added["entry"]
        self.assertEqual(entry["status"], "ACTIVE")
        snapshot = entry["snapshot"]
        self.assertTrue(snapshot["formal_candidate"])
        self.assertEqual(snapshot["candidate_rank"], 2)
        self.assertEqual(snapshot["strategy_id"], "S01")
        self.assertEqual(snapshot["batch_id"], self._f1(strategy="S01")["batch"]["batch_id"])

        normal = self.client.get("/api/watch", params={"scenario": "normal"}).json()
        self.assertEqual(normal["active"][0]["snapshot"], snapshot)
        unknown = self.client.get("/api/watch", params={"scenario": "unknown"}).json()
        self.assertEqual(unknown["active"][0]["snapshot"], snapshot)
        self.assertEqual(unknown["active"][0]["current"]["status"], "PREVIEW")
        self.assertNotEqual(unknown["active"][0]["snapshot"]["batch_id"], unknown["active"][0]["current"]["batch_id"])
        self.assertFalse(unknown["active"][0]["snapshot_changed"])

        removed = self.client.delete(f"/api/watch/{entry['watch_id']}")
        self.assertEqual(removed.status_code, 200)
        self.assertEqual(removed.json()["entry"]["status"], "REMOVED")
        after = self.client.get("/api/watch", params={"scenario": "unknown"}).json()
        self.assertEqual(after["active"], [])
        self.assertEqual(after["removed"][0]["snapshot"], snapshot)

        again = self._watch(scenario="normal", security_id="SH:600001")
        self.assertNotEqual(again["entry"]["watch_id"], entry["watch_id"])
        self.assertEqual(len(self.client.get("/api/watch").json()["removed"]), 1)

    def test_html_main_journey_and_watch_form(self) -> None:
        home = text(self.client.get("/?scenario=normal&strategy=S01&style=BALANCED/1&n=10"))
        self.assertIn(FIXTURE_MARKER, home)
        stock_link = next(
            part.split('"')[0]
            for part in home.split('href="')
            if part.startswith("/stock?")
        ).replace("&amp;", "&")
        detail = text(self.client.get(stock_link))
        self.assertIn("F3 个股诊断", detail)
        self.assertIn("关注并保存首次快照", detail)
        batch = detail.split('name="batch_id" value="', 1)[1].split('"', 1)[0]
        response = self.client.post(
            "/watch/add",
            data={
                "scenario": "normal",
                "security_id": "SH:600012",
                "strategy_id": "S01",
                "style": "BALANCED/1",
                "batch_id": batch,
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303)
        watch = text(self.client.get("/watch?scenario=normal"))
        self.assertIn(FIXTURE_MARKER, watch)
        self.assertIn("首次快照已冻结", watch)

    def test_f6_uses_od2_kernel_and_reconciles(self) -> None:
        with mock.patch("mishi_radar.demo.backtest.run_backtest", wraps=run_backtest) as wrapped:
            response = self.client.get("/api/backtest/u3")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(wrapped.call_count, 1)
            data = response.json()

        self.assertEqual(data["status"], "SUCCEEDED")
        self.assertEqual(data["meta"]["engine"], "mishi_radar.cash_backtest.run_backtest")
        self.assertTrue(data["synthetic"])
        self.assertTrue(data["reconciliation_ok"])
        self.assertEqual(data["nav"][-1]["cash"], "3564.40")
        self.assertEqual(data["nav"][-1]["equity"], "3564.40")
        self.assertEqual(data["nav"][-1]["nav"], "0.8911")
        self.assertEqual(len(data["fills"]), 3)
        self.assertEqual([item["version"] for item in data["fees"]], ["F1", "F2", "F2"])
        self.assertEqual(sorted(item["tax"] for item in data["dividend_taxes"]), ["0.00", "20.00"])
        self.assertEqual(data["closed_cycles"][0]["total_pnl"], "-435.60")
        self.assertTrue(all(item["cash_ok"] and item["equity_ok"] for item in data["reconciliation"]))

        again = self.client.get("/api/backtest/u3").json()
        self.assertEqual(data["nav"], again["nav"])
        self.assertEqual(data["orders"], again["orders"])
        self.assertEqual(data["fees"], again["fees"])

    def test_fixture_marker_in_pages_apis_and_exports(self) -> None:
        for path in ("/", "/watch", "/backtest", "/status"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn(FIXTURE_MARKER, text(response), path)
            self.assertIn("SYNTHETIC; FIXTURE; NON-REAL-MARKET", response.headers["X-Mishi-Fixture"])
            self.assertEqual(response.headers["X-Mishi-Fixture-Version"], FIXTURE_VERSION)

        for path in ("/api/f1", "/api/status", "/api/backtest/u3"):
            payload = self.client.get(path).json()
            self.assertIn("fixture", payload, path)
            self.assertEqual(payload["fixture"]["marker"], FIXTURE_MARKER)

        f1_csv = text(self.client.get("/export/f1.csv?scenario=normal&strategy=S01"))
        rows = list(csv.reader(io.StringIO(f1_csv)))
        self.assertEqual(rows[0][0], "fixture_marker")
        self.assertGreater(len(rows), 1)
        for row in rows[1:]:
            self.assertEqual(row[0], FIXTURE_MARKER)
            self.assertEqual(row[1], FIXTURE_VERSION)

        f6_csv = text(self.client.get("/export/f6.csv?scenario=u3"))
        rows = list(csv.reader(io.StringIO(f6_csv)))
        self.assertEqual(rows[0][0], "fixture_marker")
        widths = {len(row) for row in rows}
        self.assertEqual(widths, {19})
        for row in rows[1:]:
            self.assertEqual(row[0], FIXTURE_MARKER)
            self.assertEqual(row[1], FIXTURE_VERSION)
        self.assertTrue(any(row[3] == "ORDER" and row[7] == "FILLED" for row in rows[1:]))

    def test_f6_export_contains_failure_reasons(self) -> None:
        payload = self.client.get("/api/backtest/failures").json()
        csv_text = text(self.client.get("/export/f6.csv?scenario=failures"))
        self.assertIn("SUSPENDED", csv_text)
        self.assertIn("LIMIT_DOWN", csv_text)
        self.assertEqual(payload["failed_orders"][0]["status"], "UNFILLED")


if __name__ == "__main__":
    unittest.main()
