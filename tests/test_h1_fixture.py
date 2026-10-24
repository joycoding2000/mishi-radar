from __future__ import annotations

import json
import tempfile
import unittest
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from fastapi.testclient import TestClient

from mishi_radar.demo.app import create_app
from mishi_radar.demo.h1_service import _display_view, compute_valuation
from mishi_radar.result_contract import (
    FIXTURE_ID,
    FIXTURE_VERSION,
    RESULT_CONTRACT_VERSION,
)


def text(response) -> str:
    return response.content.decode("utf-8")


class H1FixtureTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.watch_path = Path(self.tmp.name) / "watchlist.json"
        self.h1_path = Path(self.tmp.name) / "h1-observations.json"
        self.client = TestClient(create_app(self.watch_path, self.h1_path))
        self.base = {
            "security_id": "SYN:000001",
            "scenario": "normal",
            "strategy_id": "S01",
            "quantity": "100",
            "average_cost": "10",
            "cost_basis_date": "2026-10-15",
            "note": "手工观察",
        }

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _create(self, **overrides):
        payload = dict(self.base)
        payload.update(overrides)
        return self.client.post("/h1/create", data=payload, follow_redirects=False)

    def _api(self):
        response = self.client.get("/api/h1")
        self.assertEqual(response.status_code, 200, text(response))
        return response.json()

    def _observations(self):
        return self._api()["observations"]

    def _record(self, observation_id: str):
        for item in self._observations():
            if item["observation_id"] == observation_id:
                return item
        self.fail(f"observation not found: {observation_id}")

    def test_valuation_formula_and_odd_lot(self) -> None:
        sample = compute_valuation(Decimal(100), Decimal(10), Decimal(12))
        self.assertEqual(sample["status"], "VALUED")
        self.assertEqual(sample["market_value"], Decimal("1200.00"))
        self.assertEqual(sample["cost_value"], Decimal("1000.00"))
        self.assertEqual(sample["unrealized_pnl"], Decimal("200.00"))
        self.assertEqual(sample["unrealized_pnl_rate"], Decimal("0.200000"))

        response = self._create(quantity="3", average_cost="10", strategy_id="")
        self.assertEqual(response.status_code, 303, text(response))
        record = self._observations()[0]
        display = record["display"]
        self.assertEqual(display["quantity_text"], "3")
        reference = Decimal(display["reference_price"])
        quantum = Decimal("0.01")
        self.assertEqual(
            Decimal(display["market_value"]),
            (reference * 3).quantize(quantum, rounding=ROUND_HALF_UP),
        )
        self.assertEqual(
            Decimal(display["unrealized_pnl"]),
            (reference * 3 - 30).quantize(quantum, rounding=ROUND_HALF_UP),
        )
        self.assertEqual(display["reference_price_date"], "2026-10-16")
        self.assertEqual(display["price_status"], "CURRENT")
        self.assertEqual(display["holding_days"], 2)
        self.assertFalse(display["needs_review"])
        page = text(self.client.get("/h1"))
        self.assertIn("3 股", page)
        self.assertIn("静态市值", page)

    def test_input_validation(self) -> None:
        invalid = [
            {"quantity": "0"},
            {"quantity": "-1"},
            {"quantity": "NaN"},
            {"quantity": "Infinity"},
            {"quantity": "1e100"},
            {"quantity": "1e-100"},
            {"quantity": "abc"},
            {"quantity": ""},
            {"average_cost": "0"},
            {"average_cost": "-1"},
            {"average_cost": "NaN"},
            {"average_cost": "1e100"},
            {"average_cost": "1e-100"},
            {"cost_basis_date": "2099-01-01"},
            {"cost_basis_date": "2026-13-01"},
            {"cost_basis_date": ""},
            {"security_id": "SYN:999999"},
            {"scenario": "bogus"},
            {"strategy_id": "S02"},
            {"note": "x" * 201},
        ]
        for override in invalid:
            with self.subTest(override=override):
                response = self._create(**override)
                self.assertEqual(response.status_code, 400, override)
                self.assertIn("观察仓输入无效", text(response))
        self.assertEqual(self._api()["active_count"], 0)

    def test_stale_and_missing_price_states(self) -> None:
        response = self._create(security_id="SYN:000001", scenario="unavailable")
        self.assertEqual(response.status_code, 303, text(response))
        response = self._create(security_id="SYN:000006", scenario="unknown")
        self.assertEqual(response.status_code, 303, text(response))
        records = self._observations()
        self.assertEqual(len(records), 2)
        for record in records:
            display = record["display"]
            self.assertEqual(display["price_status"], "STALE")
            self.assertEqual(display["reference_price_date"], "2026-10-13")
            self.assertEqual(display["valuation_status"], "OLD_PRICE")
            self.assertIn("旧价", display["price_note"])
            self.assertNotEqual(display["market_value"], "UNKNOWN")
            self.assertEqual(display["rule_status"], "UNKNOWN")
            self.assertEqual(record["status"], "ACTIVE")
            self.assertFalse(display["auto_end"])

        missing = compute_valuation(Decimal(100), Decimal(10), None)
        self.assertEqual(missing["status"], "UNKNOWN")
        self.assertIsNone(missing["market_value"])
        self.assertIsNone(missing["unrealized_pnl"])
        self.assertIsNone(missing["unrealized_pnl_rate"])
        self.assertEqual(missing["cost_value"], Decimal("1000.00"))

        missing_display = _display_view(
            {
                "version": 1,
                "quantity": "100",
                "average_cost": "10",
                "reference_price": None,
                "market_value": None,
                "cost_value": "1000.00",
                "unrealized_pnl": None,
                "unrealized_pnl_rate": None,
                "price_status": "MISSING",
                "valuation_status": "UNKNOWN",
                "holding_days": 1,
                "holding_days_reason": None,
                "rule_status": "UNKNOWN",
                "rule_reasons": ["PRICE_UNKNOWN"],
                "rule_primary_reason": "PRICE_UNKNOWN",
                "rule_id": "S01_DEFAULT/R3.2-2026-10-19-OD1-v1",
            }
        )
        self.assertTrue(missing_display["price_is_missing"])
        self.assertEqual(missing_display["reference_price_text"], "UNKNOWN")
        self.assertEqual(missing_display["market_value_text"], "UNKNOWN")
        self.assertEqual(missing_display["unrealized_pnl_text"], "UNKNOWN")
        self.assertEqual(missing_display["unrealized_pnl_rate_text"], "UNKNOWN")

    def test_s01_exit_true_false_max_holding_and_unknown(self) -> None:
        cases = [
            ("below_ma20", {"security_id": "SYN:000005", "cost_basis_date": "2026-10-15"}, "TRUE"),
            ("not_triggered", {"security_id": "SYN:000001", "cost_basis_date": "2026-10-15"}, "FALSE"),
            ("max_holding", {"security_id": "SYN:000001", "cost_basis_date": "2026-09-01"}, "TRUE"),
            ("basis_after_business", {"security_id": "SYN:000001", "cost_basis_date": "2026-10-17"}, "UNKNOWN"),
            ("calendar_incomplete", {"security_id": "SYN:000001", "cost_basis_date": "2026-01-01"}, "UNKNOWN"),
        ]
        for label, override, expected in cases:
            with self.subTest(label=label):
                response = self._create(**override)
                self.assertEqual(response.status_code, 303, label)

        by_security = {
            (item["display"]["security_id"], item["display"]["cost_basis_date"]): item
            for item in self._observations()
        }
        below = by_security[("SYN:000005", "2026-10-15")]
        self.assertEqual(below["display"]["rule_status"], "TRUE")
        self.assertIn("STRATEGY_EXIT:S01_BELOW_MA20", below["display"]["rule_reasons"])
        self.assertEqual(below["status"], "ACTIVE")

        not_triggered = by_security[("SYN:000001", "2026-10-15")]
        self.assertEqual(not_triggered["display"]["rule_status"], "FALSE")

        max_holding = by_security[("SYN:000001", "2026-09-01")]
        self.assertEqual(max_holding["display"]["rule_status"], "TRUE")
        self.assertIn("MAX_HOLDING", max_holding["display"]["rule_reasons"])
        self.assertGreaterEqual(max_holding["display"]["holding_days"], 20)

        after_business = by_security[("SYN:000001", "2026-10-17")]
        self.assertEqual(after_business["display"]["rule_status"], "UNKNOWN")
        self.assertEqual(after_business["display"]["holding_days_status"], "UNKNOWN")
        self.assertIn("BASIS_DATE_AFTER_BUSINESS_DATE", after_business["display"]["rule_reasons"])

        incomplete = by_security[("SYN:000001", "2026-01-01")]
        self.assertEqual(incomplete["display"]["rule_status"], "UNKNOWN")
        self.assertIn("FIXTURE_CALENDAR_INCOMPLETE", incomplete["display"]["rule_reasons"])

        for record in self._observations():
            self.assertEqual(record["status"], "ACTIVE")
            self.assertFalse(record["display"]["auto_end"])
        page = text(self.client.get("/h1"))
        self.assertIn("不会自动结束", page)

    def test_correction_keeps_old_versions_and_review_flag(self) -> None:
        response = self._create(quantity="100", average_cost="10", note="V1 备注")
        self.assertEqual(response.status_code, 303, text(response))
        observation_id = self._observations()[0]["observation_id"]

        response = self.client.post(
            f"/h1/{observation_id}/correct",
            data={
                "security_id": "SYN:000001",
                "strategy_id": "S01",
                "quantity": "120",
                "average_cost": "9.5",
                "cost_basis_date": "2026-10-15",
                "note": "V2 更正",
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303, text(response))
        record = self._record(observation_id)
        self.assertEqual(record["status"], "ACTIVE")
        self.assertEqual(record["status_label"], "ACTIVE · 已更正")
        self.assertEqual(record["version_count"], 2)
        self.assertEqual(record["display"]["version"], 2)
        self.assertEqual(record["display"]["quantity_text"], "120")
        self.assertEqual(record["display"]["average_cost_text"], "9.50")
        self.assertTrue(record["display"]["needs_review"])
        self.assertIn("数据/成本需本人核对", record["display"]["review_note"])
        self.assertEqual(record["versions"][0]["quantity"], "100")
        self.assertEqual(record["versions"][0]["note"], "V1 备注")
        self.assertEqual(record["versions"][1]["quantity"], "120")
        self.assertEqual(record["versions"][1]["note"], "V2 更正")

        reference = Decimal(record["display"]["reference_price"])
        self.assertEqual(
            Decimal(record["display"]["market_value"]),
            (reference * 120).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        )
        page = text(self.client.get("/h1"))
        self.assertIn("版本历史（2）", page)
        self.assertIn("数据/成本需本人核对", page)
        self.assertIn("V2 更正", page)

    def test_end_saves_snapshot_and_is_read_only(self) -> None:
        response = self._create(quantity="100", average_cost="10", note="结束前")
        self.assertEqual(response.status_code, 303, text(response))
        observation_id = self._observations()[0]["observation_id"]
        self.client.post(
            f"/h1/{observation_id}/correct",
            data={
                "security_id": "SYN:000005",
                "strategy_id": "S01",
                "quantity": "120",
                "average_cost": "9.5",
                "cost_basis_date": "2026-10-15",
                "note": "结束版本",
            },
            follow_redirects=False,
        )
        live = self._record(observation_id)["display"]

        page = self.client.get(f"/h1/{observation_id}/end")
        self.assertEqual(page.status_code, 200, text(page))
        self.assertIn("确认结束观察", text(page))

        missing_reason = self.client.post(
            f"/h1/{observation_id}/end", data={"reason": ""}, follow_redirects=False
        )
        self.assertEqual(missing_reason.status_code, 400)
        self.assertEqual(self._record(observation_id)["status"], "ACTIVE")

        response = self.client.post(
            f"/h1/{observation_id}/end",
            data={"reason": "手动归档"},
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 303, text(response))
        record = self._record(observation_id)
        self.assertEqual(record["status"], "ENDED")
        self.assertEqual(record["end_reason"], "手动归档")
        self.assertIsNotNone(record["ended_at"])
        self.assertFalse(record["can_correct"])
        self.assertFalse(record["can_end"])
        self.assertEqual(record["display"]["version"], 2)
        self.assertEqual(record["display"]["quantity_text"], "120")
        self.assertEqual(record["display"]["average_cost_text"], "9.50")
        self.assertEqual(record["display"]["cost_basis_date"], "2026-10-15")
        self.assertEqual(record["display"]["reference_price"], live["reference_price"])
        self.assertEqual(record["display"]["reference_price_date"], live["reference_price_date"])
        self.assertEqual(record["display"]["rule_status"], live["rule_status"])
        self.assertEqual(record["display"]["reason"], "手动归档")
        self.assertEqual(record["display"]["ended_at"], record["ended_at"])
        self.assertTrue(record["display"]["needs_review"])

        stored = json.loads(self.h1_path.read_text(encoding="utf-8"))
        snapshot = stored["observations"][0]["end_snapshot"]
        for key in (
            "quantity",
            "average_cost",
            "cost_basis_date",
            "reference_price",
            "reference_price_date",
            "rule_status",
            "reason",
            "ended_at",
        ):
            self.assertIn(key, snapshot)
        self.assertEqual(snapshot["quantity"], "120")
        self.assertEqual(snapshot["average_cost"], "9.5")
        self.assertEqual(snapshot["reason"], "手动归档")
        self.assertEqual(snapshot["ended_at"], record["ended_at"])

        for action in ("correct", "end"):
            if action == "correct":
                response = self.client.post(
                    f"/h1/{observation_id}/correct",
                    data={
                        "security_id": "SYN:000005",
                        "strategy_id": "S01",
                        "quantity": "1",
                        "average_cost": "1",
                        "cost_basis_date": "2026-10-15",
                        "note": "",
                    },
                    follow_redirects=False,
                )
            else:
                response = self.client.post(
                    f"/h1/{observation_id}/end",
                    data={"reason": "再次结束"},
                    follow_redirects=False,
                )
            self.assertEqual(response.status_code, 400, action)
            self.assertIn("只读", text(response))
        self.assertEqual(self._record(observation_id)["version_count"], 2)

        page = text(self.client.get("/h1"))
        self.assertIn("已结束记录", page)
        self.assertIn("只读", page)
        self.assertIn("手动归档", page)
        self.assertIn("数据/成本需本人核对", page)

        response = self._create(security_id="SYN:000005", note="再次观察")
        self.assertEqual(response.status_code, 303, text(response))
        records = self._observations()
        self.assertEqual(len(records), 2)
        self.assertEqual(sum(1 for item in records if item["status"] == "ACTIVE"), 1)
        self.assertEqual(sum(1 for item in records if item["status"] == "ENDED"), 1)
        self.assertNotEqual(records[0]["observation_id"], records[1]["observation_id"])

    def test_persistence_reload_and_f5_storage_isolation(self) -> None:
        response = self._create(security_id="SYN:000001", note="H1 记录")
        self.assertEqual(response.status_code, 303, text(response))
        self.assertEqual(len(self._observations()), 1)
        self.assertTrue(self.h1_path.exists())
        self.assertFalse(self.watch_path.exists())

        board = self.client.get(
            "/api/f1",
            params={"scenario": "normal", "strategy": "S01", "style": "BALANCED/1", "n": 10},
        ).json()
        candidate = board["candidates"][0]
        watch = self.client.post(
            "/api/watch",
            json={
                "scenario": "normal",
                "security_id": candidate["security_id"],
                "strategy_id": "S01",
                "style": "BALANCED/1",
                "batch_id": candidate["batch_id"],
            },
        )
        self.assertEqual(watch.status_code, 200, text(watch))
        self.assertTrue(self.watch_path.exists())
        watch_bytes = self.watch_path.read_bytes()
        h1_bytes = self.h1_path.read_bytes()
        self.assertNotEqual(watch_bytes, h1_bytes)
        self.assertIn(b"watch_id", watch_bytes)
        self.assertNotIn(b"observation_id", watch_bytes)
        self.assertIn(b"observation_id", h1_bytes)
        self.assertNotIn(b"watch_id", h1_bytes)

        response = self._create(security_id="SYN:000002", note="第二条 H1")
        self.assertEqual(response.status_code, 303, text(response))
        self.assertEqual(self.watch_path.read_bytes(), watch_bytes)
        h1_bytes = self.h1_path.read_bytes()

        watch_id = watch.json()["entry"]["watch_id"]
        self.client.delete(f"/api/watch/{watch_id}")
        self.assertEqual(self.h1_path.read_bytes(), h1_bytes)

        reloaded = TestClient(create_app(self.watch_path, self.h1_path))
        h1_after = reloaded.get("/api/h1").json()
        self.assertEqual(h1_after["active_count"], 2)
        self.assertEqual(
            [item["observation_id"] for item in h1_after["observations"]],
            [item["observation_id"] for item in self._observations()],
        )
        watch_after = reloaded.get("/api/watch", params={"scenario": "normal"}).json()
        self.assertEqual(watch_after["active"], [])
        self.assertEqual(watch_after["removed_count"], 1)

    def test_fixture_identity_and_page_limits(self) -> None:
        response = self._create(security_id="SYN:000001")
        self.assertEqual(response.status_code, 303, text(response))
        page_response = self.client.get("/h1")
        self.assertEqual(page_response.status_code, 200, text(page_response))
        page = text(page_response)
        for value in (
            FIXTURE_ID,
            FIXTURE_VERSION,
            RESULT_CONTRACT_VERSION,
            "SYNTHETIC / FIXTURE",
            "SYNTHETIC_RAW_CNY",
            "观察仓 H1",
            "未计交易费用",
            "分红",
            "送转",
            "OD-2",
            "不会自动结束",
            "H1 与 F5",
        ):
            self.assertIn(value, page)
        self.assertIn("X-Mishi-Fixture", page_response.headers)
        self.assertEqual(page_response.headers["X-Mishi-Fixture-Version"], "FX01B-OD2-2026-10-23-v1")
        self.assertEqual(page_response.headers["X-Mishi-Contract-Version"], RESULT_CONTRACT_VERSION)

        api = self._api()
        self.assertEqual(api["fixture"]["fixture_id"], FIXTURE_ID)
        self.assertEqual(api["fixture"]["fixture_version"], FIXTURE_VERSION)
        self.assertEqual(api["fixture"]["price_basis"], "SYNTHETIC_RAW_CNY")
        self.assertFalse(api["fixture"]["real_market_data"])
        self.assertEqual(api["user"], "fixture-user")
        self.assertTrue(any("静态浮盈不能替代 OD-2" in item for item in api["limitations"]))

    def test_mobile_css_and_viewport_contract(self) -> None:
        home = text(self.client.get("/h1"))
        self.assertIn('name="viewport"', home)
        self.assertIn("width=device-width", home)
        css = text(self.client.get("/static/app.css"))
        self.assertIn("@media (max-width: 760px)", css)
        self.assertIn(".h1-form-grid", css)
        self.assertIn(".h1-grid", css)
        self.assertIn(".form-field", css)


if __name__ == "__main__":
    unittest.main()
