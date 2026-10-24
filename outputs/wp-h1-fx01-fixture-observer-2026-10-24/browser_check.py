"""Reproducible WP-H1-FX01 browser evidence.

Evidence class: Chromium headless simulation at desktop and mobile viewports.
Not a real Android/iPhone device test.  The script starts the FastAPI app with
isolation stores inside this evidence directory, drives the complete H1 path
(create -> value -> correct -> end -> read-only history -> re-observe) and
writes screenshots plus a PASS log.
"""

from __future__ import annotations

import sys
import threading
import time
import urllib.request
from pathlib import Path

import uvicorn
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from mishi_radar.demo.app import create_app

BASE = "http://127.0.0.1:8767"
OUT = Path(__file__).resolve().parent
WATCH_STORE = OUT / "browser-watchlist.json"
H1_STORE = OUT / "browser-h1-observer.json"
MARKER = "SYNTHETIC / FIXTURE / 非真实行情"
CONTRACT = "FX01A-RESULT-CONTRACT-v1"
FIXTURE = "FX01A-2026-10-23-v1"


def start_server() -> tuple[uvicorn.Server, threading.Thread]:
    for path in (WATCH_STORE, H1_STORE):
        if path.exists():
            path.unlink()
    app = create_app(WATCH_STORE, H1_STORE)
    config = uvicorn.Config(app, host="127.0.0.1", port=8767, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(100):
        try:
            with urllib.request.urlopen(f"{BASE}/api/health", timeout=0.5) as response:
                if response.status == 200:
                    return server, thread
        except Exception:
            time.sleep(0.1)
    raise RuntimeError("demo server did not start")


def assert_marker(page, label: str) -> None:
    body = page.content()
    assert MARKER in body, f"{label}: full fixture marker missing"
    assert "SYNTHETIC / FIXTURE" in body, f"{label}: contract marker missing"
    assert CONTRACT in body, f"{label}: contract version missing"
    assert FIXTURE in body, f"{label}: fixture version missing"
    assert "不会自动结束" in body, f"{label}: no-auto-end note missing"


def check_no_page_overflow(page, label: str) -> None:
    overflow = page.evaluate("() => document.documentElement.scrollWidth - window.innerWidth")
    assert overflow <= 1, f"{label}: page horizontally overflows by {overflow}px"
    print(f"{label}: no page-level horizontal overflow")


def fill_create(
    page,
    *,
    security: str,
    scenario: str,
    strategy: str,
    quantity: str,
    cost: str,
    basis: str,
    note: str,
) -> None:
    form = page.locator("form[action='/h1/create']")
    form.locator("select[name=security_id]").select_option(security)
    form.locator("select[name=scenario]").select_option(scenario)
    form.locator("select[name=strategy_id]").select_option(strategy)
    form.locator("input[name=quantity]").fill(quantity)
    form.locator("input[name=average_cost]").fill(cost)
    form.locator("input[name=cost_basis_date]").fill(basis)
    form.locator("input[name=note]").fill(note)


def submit_and_wait(page, selector: str, expected_url: str) -> None:
    with page.expect_navigation():
        page.locator(selector).click()
    page.wait_for_url(expected_url)
    page.wait_for_load_state("networkidle")


def run_desktop(browser) -> None:
    page = browser.new_page(viewport={"width": 1440, "height": 1000})
    page.goto(f"{BASE}/h1")
    assert_marker(page, "desktop H1 empty")
    assert "创建观察" in page.content()
    assert "H1 与 F5" in page.content()
    page.screenshot(path=str(OUT / "desktop-01-h1-empty.png"), full_page=True)
    print("desktop H1: empty state, create form and storage-isolation note visible")

    fill_create(
        page,
        security="SYN:000005",
        scenario="normal",
        strategy="S01",
        quantity="100",
        cost="10",
        basis="2026-10-15",
        note="浏览器桌面观察",
    )
    submit_and_wait(page, "form[action='/h1/create'] button[type=submit]", "**/h1?created=1")
    assert_marker(page, "desktop H1 active")
    body = page.content()
    assert "ACTIVE · 观察中" in body
    assert "规则提示退出" in body
    assert "静态市值" in body
    assert "未计费用、分红、送转" in body
    print("desktop H1 active: S01 TRUE hint shown without auto-end")
    page.screenshot(path=str(OUT / "desktop-02-h1-active.png"), full_page=True)

    page.locator("details.h1-correct summary").first.click()
    form = page.locator("details.h1-correct form[action$='/correct']").first
    form.locator("input[name=quantity]").fill("120")
    form.locator("input[name=average_cost]").fill("9.5")
    form.locator("input[name=note]").fill("浏览器桌面更正")
    submit_and_wait(
        page,
        "details.h1-correct form[action$='/correct'] button[type=submit]",
        "**/h1?corrected=1",
    )
    body = page.content()
    assert "版本历史（2）" in body
    assert "数据/成本需本人核对" in body
    assert "浏览器桌面更正" in body
    print("desktop H1 corrected: version 2 active, version history preserved")
    page.screenshot(path=str(OUT / "desktop-03-h1-corrected.png"), full_page=True)

    with page.expect_navigation():
        page.locator("a[href$='/end']").first.click()
    page.wait_for_url("**/end")
    assert "确认结束观察" in page.content()
    page.locator("textarea[name=reason]").fill("浏览器桌面主动结束")
    page.screenshot(path=str(OUT / "desktop-04-h1-end-confirm.png"), full_page=True)
    print("desktop H1 end confirmation: explicit read-only warning and reason field visible")

    submit_and_wait(page, "form[action$='/end'] button[type=submit]", "**/h1?ended=1")
    body = page.content()
    assert "ENDED · 已结束（只读）" in body
    assert "已结束记录" in body
    assert "浏览器桌面主动结束" in body
    assert "只读" in body
    print("desktop H1 ended: end snapshot and read-only history visible")
    page.screenshot(path=str(OUT / "desktop-05-h1-ended.png"), full_page=True)

    fill_create(
        page,
        security="SYN:000001",
        scenario="normal",
        strategy="S01",
        quantity="3",
        cost="10",
        basis="2026-10-15",
        note="浏览器再次观察",
    )
    submit_and_wait(page, "form[action='/h1/create'] button[type=submit]", "**/h1?created=1")
    body = page.content()
    assert "当前观察（1）" in body
    assert "已结束记录（1）" in body
    assert "3 股" in body
    print("desktop H1 re-observe: new record created while old ended record stays read-only")
    page.screenshot(path=str(OUT / "desktop-06-h1-reobserve.png"), full_page=True)

    fill_create(
        page,
        security="SYN:000001",
        scenario="unavailable",
        strategy="S01",
        quantity="100",
        cost="10",
        basis="2026-10-13",
        note="浏览器旧价观察",
    )
    submit_and_wait(page, "form[action='/h1/create'] button[type=submit]", "**/h1?created=1")
    body = page.content()
    assert "旧价（非当前业务日）" in body
    assert "2026-10-13" in body
    assert "UNKNOWN · 暂不可判断" in body
    assert "浏览器旧价观察" in body
    print("desktop H1 stale price: old-price date and UNKNOWN exit visible")
    page.screenshot(path=str(OUT / "desktop-07-h1-stale.png"), full_page=True)
    page.close()


def run_mobile(browser) -> None:
    context = browser.new_context(
        viewport={"width": 390, "height": 844},
        device_scale_factor=2,
        is_mobile=True,
        has_touch=True,
    )
    page = context.new_page()
    page.goto(f"{BASE}/h1")
    assert_marker(page, "mobile H1 empty")
    check_no_page_overflow(page, "mobile H1 empty")
    page.screenshot(path=str(OUT / "mobile-01-h1-empty.png"), full_page=True)

    fill_create(
        page,
        security="SYN:000002",
        scenario="normal",
        strategy="S01",
        quantity="5",
        cost="10",
        basis="2026-10-15",
        note="浏览器手机观察",
    )
    submit_and_wait(page, "form[action='/h1/create'] button[type=submit]", "**/h1?created=1")
    body = page.content()
    assert "ACTIVE · 观察中" in body
    assert "5 股" in body
    assert "浏览器手机观察" in body
    check_no_page_overflow(page, "mobile H1 active")
    page.screenshot(path=str(OUT / "mobile-02-h1-active.png"), full_page=True)
    page.screenshot(path=str(OUT / "mobile-02b-h1-active-viewport.png"))

    page.locator("details.h1-correct summary").first.click()
    form = page.locator("details.h1-correct form[action$='/correct']").first
    form.locator("input[name=quantity]").fill("6")
    form.locator("input[name=note]").fill("浏览器手机更正")
    with page.expect_navigation():
        form.locator("button[type=submit]").click()
    page.wait_for_url("**/h1?corrected=1")
    page.wait_for_load_state("networkidle")
    body = page.content()
    assert "版本历史（2）" in body
    assert "浏览器手机更正" in body
    check_no_page_overflow(page, "mobile H1 corrected")
    page.screenshot(path=str(OUT / "mobile-03-h1-corrected.png"), full_page=True)

    with page.expect_navigation():
        page.locator("a[href$='/end']").first.click()
    page.wait_for_url("**/end")
    assert "确认结束观察" in page.content()
    page.locator("textarea[name=reason]").fill("浏览器手机主动结束")
    check_no_page_overflow(page, "mobile H1 end confirm")
    page.screenshot(path=str(OUT / "mobile-04-h1-end-confirm.png"), full_page=True)
    page.screenshot(path=str(OUT / "mobile-04b-h1-end-confirm-viewport.png"))

    submit_and_wait(page, "form[action$='/end'] button[type=submit]", "**/h1?ended=1")
    body = page.content()
    assert "ENDED · 已结束（只读）" in body
    assert "浏览器手机主动结束" in body
    assert "已结束记录" in body
    check_no_page_overflow(page, "mobile H1 ended")
    page.screenshot(path=str(OUT / "mobile-05-h1-ended.png"), full_page=True)
    page.screenshot(path=str(OUT / "mobile-05b-h1-ended-viewport.png"))
    context.close()


def main() -> None:
    server, thread = start_server()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch()
            print(f"browser={browser.version}")
            run_desktop(browser)
            run_mobile(browser)
            browser.close()
    finally:
        server.should_exit = True
        thread.join(timeout=5)


if __name__ == "__main__":
    main()
