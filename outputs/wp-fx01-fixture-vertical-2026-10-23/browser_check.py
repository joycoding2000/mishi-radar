"""Reproducible browser evidence for the WP-FX01 fixture vertical slice.

Evidence class: browser simulation (Chromium 148 headless), not a real device.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765"
OUT = Path(__file__).resolve().parent
MARKER = "SYNTHETIC / FIXTURE / 非真实行情"


def check_no_page_overflow(page, label: str) -> None:
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - window.innerWidth"
    )
    assert overflow <= 1, f"{label}: page horizontally overflows by {overflow}px"
    print(f"{label}: no page-level horizontal overflow")


def run_desktop(browser) -> None:
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(f"{BASE}/?scenario=normal&strategy=S01&style=BALANCED/1&n=10")
    assert MARKER in page.content()
    assert "固定 Fixture 候选榜" in page.content()
    pages = page.locator(".candidate-card").count()
    assert pages >= 1, "expected fixture candidate cards"
    print(f"desktop F1: {pages} candidate cards")
    page.screenshot(path=str(OUT / "desktop-01-f1.png"), full_page=True)

    page.locator(".candidate-card a[href^='/stock?']").first.click()
    page.wait_for_url("**/stock?**")
    assert MARKER in page.content()
    assert page.locator(".dimension-card").count() == 6
    print("desktop F3: six dimension cards visible")
    page.screenshot(path=str(OUT / "desktop-02-f3.png"), full_page=True)

    page.locator("form[action='/watch/add'] button").first.click()
    page.wait_for_url("**/watch**")
    assert MARKER in page.content()
    assert "首次快照已冻结" in page.content()
    print("desktop F5: watch snapshot frozen")
    page.screenshot(path=str(OUT / "desktop-03-f5.png"), full_page=True)

    page.goto(f"{BASE}/backtest?scenario=u3")
    assert MARKER in page.content()
    assert "3564.40" in page.content()
    assert "SUCCEEDED" in page.content()
    print("desktop F6 U3: NAV final cash 3564.40 visible")
    page.screenshot(path=str(OUT / "desktop-04-f6-u3.png"), full_page=True)

    page.goto(f"{BASE}/backtest?scenario=failures")
    assert "SUSPENDED" in page.content()
    assert "LIMIT_DOWN" in page.content()
    print("desktop F6 failures: failure reasons visible")
    page.screenshot(path=str(OUT / "desktop-05-f6-failures.png"), full_page=True)

    page.goto(f"{BASE}/?scenario=empty&strategy=S01&style=BALANCED/1&n=10")
    assert "完整空结果（成功）" in page.content()
    page.screenshot(path=str(OUT / "desktop-06-f1-empty.png"), full_page=True)

    page.goto(f"{BASE}/?scenario=unknown&strategy=S01&style=BALANCED/1&n=10")
    assert "PREVIEW / 池不完整" in page.content()
    assert "PREVIEW · 非正式" in page.content()
    page.screenshot(path=str(OUT / "desktop-07-f1-unknown.png"), full_page=True)

    page.goto(f"{BASE}/status")
    assert "固定 Fixture 数据与批次状态" in page.content()
    page.screenshot(path=str(OUT / "desktop-08-f7.png"), full_page=True)
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
    assert MARKER in page.content()
    check_no_page_overflow(page, "mobile F1")
    assert page.locator(".candidate-card").count() >= 1
    page.screenshot(path=str(OUT / "mobile-01-f1.png"), full_page=True)

    page.locator(".candidate-card a[href^='/stock?']").first.click()
    page.wait_for_url("**/stock?**")
    assert page.locator(".dimension-card").count() == 6
    check_no_page_overflow(page, "mobile F3")
    page.screenshot(path=str(OUT / "mobile-02-f3.png"), full_page=True)

    page.locator("form[action='/watch/add'] button").first.click()
    page.wait_for_url("**/watch**")
    assert "首次快照已冻结" in page.content()
    check_no_page_overflow(page, "mobile F5")
    page.screenshot(path=str(OUT / "mobile-03-f5.png"), full_page=True)

    page.goto(f"{BASE}/backtest?scenario=u3")
    assert "3564.40" in page.content()
    check_no_page_overflow(page, "mobile F6")
    page.screenshot(path=str(OUT / "mobile-04-f6.png"), full_page=True)

    page.goto(f"{BASE}/?scenario=unknown&strategy=S01&style=BALANCED/1&n=10")
    assert "PREVIEW · 非正式" in page.content()
    check_no_page_overflow(page, "mobile F1 unknown")
    page.screenshot(path=str(OUT / "mobile-05-f1-unknown.png"), full_page=True)
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
