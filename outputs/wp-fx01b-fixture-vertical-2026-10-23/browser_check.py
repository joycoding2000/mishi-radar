"""Reproducible WP-FX01B browser evidence.

Evidence class: Chromium headless simulation at desktop and mobile viewports.
Not a real Android/iPhone device test.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8766"
OUT = Path(__file__).resolve().parent
MARKER = "SYNTHETIC / FIXTURE / 非真实行情"
CONTRACT = "FX01A-RESULT-CONTRACT-v1"
FIXTURE = "FX01A-2026-10-23-v1"


def assert_marker(page, label: str) -> None:
    body = page.content()
    assert MARKER in body, f"{label}: full fixture marker missing"
    assert "SYNTHETIC / FIXTURE" in body, f"{label}: contract marker missing"
    assert CONTRACT in body, f"{label}: contract version missing"


def check_no_page_overflow(page, label: str) -> None:
    overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 1, f"{label}: page horizontally overflows by {overflow}px"
    print(f"{label}: no page-level horizontal overflow")


def run_desktop(browser) -> None:
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(f"{BASE}/?scenario=normal&strategy=S01&style=BALANCED/1&n=10")
    assert_marker(page, "desktop F1")
    assert "CANDIDATES" in page.content()
    assert page.locator(".candidate-card").count() == 4
    print("desktop F1: four contract candidates")
    page.screenshot(path=str(OUT / "desktop-01-f1-normal.png"), full_page=True)

    page.goto(f"{BASE}/?scenario=normal&strategy=S01&style=BALANCED/1&n=1")
    assert_marker(page, "desktop F1 n=1")
    assert "榜外但仍具精确名次" in page.content()
    assert "榜外候选 #2" in page.content()
    assert page.locator(".candidate-card").count() == 4
    print("desktop F1 n=1: three beyond_top_n exact ranks visible")
    page.screenshot(path=str(OUT / "desktop-01b-f1-n1.png"), full_page=True)

    empty_csv_path = OUT / "empty-f1-export.csv"
    page.goto(f"{BASE}/?scenario=empty&strategy=S01&style=BALANCED/1&n=10")
    with page.expect_download() as download_info:
        page.evaluate(
            """(url) => {
                const anchor = document.createElement("a");
                anchor.href = url;
                anchor.download = "empty-f1-export.csv";
                document.body.appendChild(anchor);
                anchor.click();
            }""",
            f"{BASE}/export/f1.csv?scenario=empty&strategy=S01",
        )
    download_info.value.save_as(str(empty_csv_path))
    empty_csv = empty_csv_path.read_text(encoding="utf-8")
    assert MARKER in empty_csv
    assert "SYNTHETIC / FIXTURE" in empty_csv
    assert "EMPTY" in empty_csv
    assert "STATUS" in empty_csv
    assert "FX01A-SYNTHETIC-MARKET:empty:S01" in empty_csv
    print("desktop F1 empty CSV: identity, batch and EMPTY status preserved")

    page.goto(f"{BASE}/?scenario=normal&strategy=S01&style=BALANCED/1&n=10")

    page.locator(".candidate-card a[href^='/stock?']").first.click()
    page.wait_for_url("**/stock?**")
    assert_marker(page, "desktop F3")
    assert page.locator(".dimension-card").count() == 6
    assert "FX01A-SYNTHETIC-MARKET" in page.url
    assert "S01_DEFAULT" in page.url
    print("desktop F3: six dimensions, contract batch carried in URL")
    page.screenshot(path=str(OUT / "desktop-02-f3.png"), full_page=True)

    page.locator("form[action='/watch/add'] button").first.click()
    page.wait_for_url("**/watch**")
    assert_marker(page, "desktop F5")
    assert "首次快照已冻结" in page.content()
    assert FIXTURE in page.content()
    print("desktop F5: first snapshot frozen")
    page.screenshot(path=str(OUT / "desktop-03-f5.png"), full_page=True)

    page.locator("form[action='/watch/remove'] button").first.click()
    page.wait_for_load_state("networkidle")
    assert "历史关注记录" in page.content()
    assert "取消时间" in page.content()
    assert "FX01A-SYNTHETIC-MARKET:normal:S01" in page.content()
    print("desktop F5: cancel keeps historical snapshot")
    page.screenshot(path=str(OUT / "desktop-03b-f5-cancelled.png"), full_page=True)

    for scenario, label, filename in (
        ("empty", "EMPTY", "desktop-04-f1-empty.png"),
        ("unknown", "PREVIEW", "desktop-05-f1-preview.png"),
        ("unavailable", "UNKNOWN", "desktop-06-f1-unknown.png"),
        ("failed", "FAILED", "desktop-07-f1-failed.png"),
    ):
        page.goto(f"{BASE}/?scenario={scenario}&strategy=S01&style=BALANCED/1&n=10")
        assert_marker(page, f"desktop F1 {scenario}")
        assert label in page.content()
        page.screenshot(path=str(OUT / filename), full_page=True)
        print(f"desktop F1 {scenario}: {label} visible")

    page.goto(f"{BASE}/backtest?scenario=u3")
    assert_marker(page, "desktop F6")
    assert "3564.40" in page.content()
    assert "SUCCEEDED" in page.content()
    assert "累计收益" in page.content()
    print("desktop F6 U3: NAV final cash 3564.40 and formatted metrics visible")
    page.screenshot(path=str(OUT / "desktop-08-f6-u3.png"), full_page=True)

    page.goto(f"{BASE}/backtest?scenario=failures")
    assert "SUSPENDED" in page.content()
    assert "LIMIT_DOWN" in page.content()
    print("desktop F6 failures: failure reasons visible")
    page.screenshot(path=str(OUT / "desktop-09-f6-failures.png"), full_page=True)

    page.goto(f"{BASE}/status")
    assert_marker(page, "desktop F7")
    assert "CANDIDATES" in page.content()
    assert "EMPTY" in page.content()
    assert "PREVIEW" in page.content()
    assert "UNKNOWN" in page.content()
    assert "FAILED" in page.content()
    print("desktop F7: all five contract outcomes visible")
    page.screenshot(path=str(OUT / "desktop-10-f7.png"), full_page=True)
    page.close()


def run_mobile(browser) -> None:
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
    )
    page = context.new_page()
    page.goto(f"{BASE}/?scenario=normal&strategy=S01&style=BALANCED/1&n=10")
    assert_marker(page, "mobile F1")
    check_no_page_overflow(page, "mobile F1")
    assert page.locator(".candidate-card").count() == 4
    page.screenshot(path=str(OUT / "mobile-01-f1.png"), full_page=True)
    page.screenshot(path=str(OUT / "mobile-01b-f1-viewport.png"))

    page.locator(".candidate-card a[href^='/stock?']").first.click()
    page.wait_for_url("**/stock?**")
    assert page.locator(".dimension-card").count() == 6
    check_no_page_overflow(page, "mobile F3")
    page.screenshot(path=str(OUT / "mobile-02-f3.png"), full_page=True)
    page.screenshot(path=str(OUT / "mobile-02b-f3-viewport.png"))

    page.locator("form[action='/watch/add'] button").first.click()
    page.wait_for_url("**/watch**")
    assert "首次快照已冻结" in page.content()
    check_no_page_overflow(page, "mobile F5")
    page.screenshot(path=str(OUT / "mobile-03-f5.png"), full_page=True)
    page.screenshot(path=str(OUT / "mobile-03b-f5-viewport.png"))

    page.goto(f"{BASE}/backtest?scenario=u3")
    assert "3564.40" in page.content()
    check_no_page_overflow(page, "mobile F6")
    page.screenshot(path=str(OUT / "mobile-04-f6.png"), full_page=True)
    page.screenshot(path=str(OUT / "mobile-04b-f6-viewport.png"))

    page.goto(f"{BASE}/?scenario=failed&strategy=S01&style=BALANCED/1&n=10")
    assert "FAILED" in page.content()
    check_no_page_overflow(page, "mobile F1 failed")
    page.screenshot(path=str(OUT / "mobile-05-f1-failed.png"), full_page=True)
    context.close()


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        print(f"browser={browser.version}")
        run_desktop(browser)
        run_mobile(browser)
        browser.close()


if __name__ == "__main__":
    main()
