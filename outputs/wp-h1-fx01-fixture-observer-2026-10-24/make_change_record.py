"""Generate the WP-H1-FX01 change record and code diff from the working tree."""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
BASELINE = "e7a081c3c4ccfd948c80a4956fe5aa7a0a0cd1ba"

CODE_PATHS = [
    "mishi_radar/demo/__init__.py",
    "mishi_radar/demo/app.py",
    "mishi_radar/demo/h1.py",
    "mishi_radar/demo/h1_service.py",
    "mishi_radar/demo/service.py",
    "mishi_radar/demo/static/app.css",
    "mishi_radar/demo/templates/base.html",
    "mishi_radar/demo/templates/h1.html",
    "mishi_radar/demo/templates/h1_end.html",
    "tests/test_h1_fixture.py",
    "docs/WP_H1_FX01_IMPLEMENTATION_2026-10-24.md",
]


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def file_entry(relative: str) -> dict[str, object]:
    path = ROOT / relative
    return {
        "path": relative,
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def run_git(*args: str) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    ).stdout


def main() -> None:
    diff = subprocess.run(
        ["git", "diff", "--", *CODE_PATHS],
        cwd=ROOT,
        check=True,
        capture_output=True,
    )
    (OUT / "diff.patch").write_bytes(diff.stdout)
    diff_stat = run_git("diff", "--stat", "--", *CODE_PATHS).strip()

    test_log = (OUT / "unittest.log").read_text(encoding="utf-8", errors="replace")
    total_match = re.search(r"Ran (\d+) tests", test_log)
    total = int(total_match.group(1)) if total_match else 0
    h1_tests = test_log.count("tests.test_h1_fixture.")
    product_tests = test_log.count("tests.test_demo_product.")

    browser_log = (OUT / "browser_check.log").read_text(encoding="utf-8", errors="replace")
    browser_lines = [line for line in browser_log.splitlines() if line.strip()]
    screenshots = sorted(
        {
            path.name
            for path in OUT.glob("*.png")
        }
    )

    evidence_paths = sorted(
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in OUT.iterdir()
        if path.is_file() and path.name not in {"change-record.json"}
    )

    record = {
        "record": "WP-H1-FX01_FIXTURE_OBSERVER_CHANGE_RECORD",
        "generated_at": datetime.now(ZoneInfo("Asia/Shanghai")).replace(tzinfo=None, microsecond=0).isoformat(),
        "baseline_git_head": BASELINE,
        "branch": run_git("branch", "--show-current").strip(),
        "review_status": "OWNER_REVIEW_PENDING",
        "acceptance_claimed": False,
        "scope": {
            "path": "CREATE -> STATIC VALUATION -> CORRECT -> END -> READ-ONLY HISTORY -> RE-OBSERVE",
            "user": "fixture-user",
            "data": "FX01A fixed synthetic fixture",
            "real_market_data": False,
            "network_used": False,
            "full_h1_acceptance": False,
        },
        "changed_files": [file_entry(path) for path in CODE_PATHS],
        "diff_stat": diff_stat,
        "diff_patch": "diff.patch",
        "contract_reuse": {
            "result_contract_modified": False,
            "strategy_core_modified": False,
            "cash_backtest_modified": False,
            "f5_watch_store_modified": False,
            "h1_store_independent": True,
            "fixture_id": "FX01A-SYNTHETIC-MARKET",
            "fixture_version": "FX01A-2026-10-23-v1",
            "result_contract_version": "FX01A-RESULT-CONTRACT-v1",
            "price_basis": "SYNTHETIC_RAW_CNY",
            "rule": "S01_DEFAULT/R3.2-2026-10-19-OD1-v1",
        },
        "storage": {
            "h1_default": "var/fixture-demo/h1-observations.json",
            "h1_env_override": "MISHI_H1_STORE",
            "f5_default": "var/fixture-demo/watchlist.json",
            "f5_env_override": "MISHI_FIXTURE_STORE",
            "separate_files": True,
        },
        "tests": {
            "command": "python -m unittest tests.test_h1_fixture tests.test_demo_product -v",
            "total": total,
            "result": "OK" if "OK" in test_log else "UNKNOWN",
            "h1_fixture": h1_tests,
            "fx01b_product": product_tests,
            "log": "unittest.log",
            "accepted_184_tests_rerun": False,
        },
        "browser_evidence": {
            "class": "BROWSER_SIMULATION",
            "browser": "Chromium 148.0.7778.96 headless",
            "desktop_viewport": "1440x1000",
            "mobile_viewport": "390x844",
            "script": "browser_check.py",
            "log": "browser_check.log",
            "store": "browser-h1-observer.json",
            "screenshots": screenshots,
            "real_device_tested": False,
            "limitation": "No physical Android/iPhone device evidence in this run.",
            "log_lines": browser_lines,
        },
        "review_fixes": [
            {
                "id": "H1_ENDED_QUERY_COLLISION",
                "fix": "The ?ended=1 query flag no longer overwrites the ENDED list in the template context.",
                "code": "mishi_radar/demo/app.py:h1_index; mishi_radar/demo/templates/h1.html",
                "test": "tests/test_h1_fixture.py:test_end_saves_snapshot_and_is_read_only",
            },
            {
                "id": "H1_EXTREME_DECIMAL_500",
                "fix": "Extreme finite quantity/cost values are rejected before display calculations instead of raising InvalidOperation.",
                "code": "mishi_radar/demo/h1_service.py:_positive_decimal",
                "test": "tests/test_h1_fixture.py:test_input_validation",
            },
        ],
        "behavior_evidence": {
            "valuation_formula": "q*P, q*c, q*(P-c), P/c-1",
            "example": "q=100, c=10, P=12 -> 1200.00, 200.00, 20.00%",
            "odd_lot_allowed": True,
            "stale_price_marked": True,
            "missing_price_unknown": True,
            "s01_true_false_unknown": True,
            "correction_versions": True,
            "end_snapshot_read_only": True,
            "re_observe_new_record": True,
            "restart_persistence": True,
            "f5_isolation": True,
            "auto_end": False,
        },
        "known_limitations": [
            "Full H1 acceptance, real positions, live prices, account equity and trade ledger are not implemented.",
            "Only the default S01 rule is linked; other strategies, F4, F8 and OD-3 numeric terms are not advanced.",
            "Trading fees, dividends, splits and other corporate actions are not adjusted.",
            "Static P&L does not replace the OD-2 unclosed economic P&L stop; the common OD-2 stop is not evaluated.",
            "Browser evidence is simulated viewport evidence, not real Android/iPhone device acceptance.",
        ],
        "evidence_files": [file_entry(path) for path in evidence_paths],
        "push_or_merge": False,
        "formal_release": False,
        "next_phase_authorized": False,
    }
    (OUT / "change-record.json").write_text(
        json.dumps(record, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps({"total_tests": total, "h1": h1_tests, "fx01b": product_tests}, ensure_ascii=False))


if __name__ == "__main__":
    main()
