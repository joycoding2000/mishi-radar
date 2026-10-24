"""FastAPI entry point for the WP-FX01 fixed-fixture vertical slice."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Form, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from . import (
    CONTRACT_FIXTURE_VERSION,
    CONTRACT_MARKER,
    FIXTURE_MARKER,
    FIXTURE_VERSION,
    RESULT_CONTRACT_VERSION,
)
from .h1 import H1Store
from .h1_service import (
    api_h1_data,
    correct_observation,
    create_observation,
    end_observation,
    h1_data,
    h1_end_data,
)
from .service import (
    BatchMismatch,
    DemoInputError,
    add_watch,
    backtest_csv,
    backtest_data,
    f1_csv,
    f1_data,
    status_data,
    stock_data,
    watch_data,
)
from .watch import DEMO_USER, WatchStore

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_STORE = Path(
    os.environ.get(
        "MISHI_FIXTURE_STORE",
        BASE_DIR.parents[1] / "var" / "fixture-demo" / "watchlist.json",
    )
)
DEFAULT_H1_STORE = Path(
    os.environ.get(
        "MISHI_H1_STORE",
        BASE_DIR.parents[1] / "var" / "fixture-demo" / "h1-observations.json",
    )
)


class WatchRequest(BaseModel):
    scenario: str = Field(default="normal")
    security_id: str
    strategy_id: str
    style: str = Field(default="BALANCED/1")
    batch_id: str


def _fixture_error_payload(message: str) -> dict[str, Any]:
    return {
        "error": message,
        "fixture": {
            "marker": FIXTURE_MARKER,
            "fixture_version": FIXTURE_VERSION,
            "contract_marker": CONTRACT_MARKER,
            "contract_fixture_version": CONTRACT_FIXTURE_VERSION,
            "contract_version": RESULT_CONTRACT_VERSION,
            "source": "FIXTURE",
            "real_market_data": False,
        },
    }


def create_app(
    store_path: Path | str | None = None,
    h1_store_path: Path | str | None = None,
) -> FastAPI:
    app = FastAPI(
        title="Mishi Radar — WP-FX01/WP-H1-FX01 FIXTURE vertical slice",
        description="Fixed synthetic product path: F1 -> F3 -> F5 -> H1 -> F6 with FIXTURE markers.",
        version="FX01B-H1-2026-10-24-v1",
    )
    templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
    app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
    store = WatchStore(store_path or DEFAULT_STORE)
    h1_store = H1Store(h1_store_path or DEFAULT_H1_STORE)

    @app.middleware("http")
    async def fixture_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Mishi-Fixture"] = "SYNTHETIC; FIXTURE; NON-REAL-MARKET"
        response.headers["X-Mishi-Fixture-Version"] = FIXTURE_VERSION
        response.headers["X-Mishi-Contract-Fixture-Version"] = CONTRACT_FIXTURE_VERSION
        response.headers["X-Mishi-Contract-Version"] = RESULT_CONTRACT_VERSION
        response.headers["Cache-Control"] = "no-store"
        return response

    def render_error(request: Request, title: str, message: str, status_code: int) -> HTMLResponse:
        return templates.TemplateResponse(
            request,
            "error.html",
            {"title": title, "message": message},
            status_code=status_code,
        )

    @app.get("/", response_class=HTMLResponse)
    def index(
        request: Request,
        scenario: str = Query("normal"),
        strategy: str = Query("S01"),
        style: str = Query("BALANCED/1"),
        n: int = Query(10),
        q: str = Query(""),
        refresh: bool = Query(False),
    ):
        try:
            data = f1_data(scenario=scenario, strategy_id=strategy, style_id=style, n=n, query=q, refresh=refresh)
        except DemoInputError as exc:
            return render_error(request, "机会榜输入无效", str(exc), 400)
        return templates.TemplateResponse(request, "index.html", data)

    @app.get("/stock", response_class=HTMLResponse)
    def stock(
        request: Request,
        scenario: str = Query(...),
        strategy_id: str = Query(...),
        style: str = Query(...),
        security_id: str = Query(...),
        batch_id: str = Query(...),
    ):
        try:
            data = stock_data(
                scenario=scenario,
                security_id=security_id,
                strategy_id=strategy_id,
                style_id=style,
                expected_batch_id=batch_id,
            )
        except BatchMismatch as exc:
            return render_error(request, "批次不一致", str(exc), 409)
        except DemoInputError as exc:
            return render_error(request, "个股输入无效", str(exc), 400)
        return templates.TemplateResponse(request, "stock.html", data)

    @app.get("/watch", response_class=HTMLResponse)
    def watch(request: Request, scenario: str = Query("normal"), error: str = Query(""), added: bool = Query(False)):
        try:
            data = watch_data(store, scenario=scenario)
        except DemoInputError as exc:
            return render_error(request, "关注页输入无效", str(exc), 400)
        data["error"] = error
        data["added"] = added
        return templates.TemplateResponse(request, "watch.html", data)

    @app.post("/watch/add")
    def watch_add(
        scenario: str = Form(...),
        security_id: str = Form(...),
        strategy_id: str = Form(...),
        style: str = Form(...),
        batch_id: str = Form(...),
    ):
        try:
            add_watch(
                store,
                scenario=scenario,
                security_id=security_id,
                strategy_id=strategy_id,
                style_id=style,
                expected_batch_id=batch_id,
            )
        except BatchMismatch as exc:
            return RedirectResponse(f"/watch?scenario={scenario}&error=batch", status_code=303)
        except DemoInputError:
            return RedirectResponse(f"/watch?scenario={scenario}&error=input", status_code=303)
        return RedirectResponse(f"/watch?scenario={scenario}&added=1", status_code=303)

    @app.post("/watch/remove")
    def watch_remove(watch_id: str = Form(...)):
        store.remove(watch_id)
        return RedirectResponse("/watch", status_code=303)

    @app.get("/h1", response_class=HTMLResponse)
    def h1_index(
        request: Request,
        created: bool = Query(False),
        corrected: bool = Query(False),
        ended: bool = Query(False),
    ):
        data = h1_data(h1_store)
        data.update(
            {
                "notice_created": created,
                "notice_corrected": corrected,
                "notice_ended": ended,
            }
        )
        return templates.TemplateResponse(request, "h1.html", data)

    @app.post("/h1/create")
    def h1_create(
        request: Request,
        security_id: str = Form(""),
        scenario: str = Form("normal"),
        strategy_id: str = Form(""),
        quantity: str = Form(""),
        average_cost: str = Form(""),
        cost_basis_date: str = Form(""),
        note: str = Form(""),
    ):
        try:
            create_observation(
                h1_store,
                security_id=security_id,
                scenario=scenario,
                strategy_id=strategy_id,
                quantity=quantity,
                average_cost=average_cost,
                cost_basis_date=cost_basis_date,
                note=note,
            )
        except DemoInputError as exc:
            return render_error(request, "观察仓输入无效", str(exc), 400)
        return RedirectResponse("/h1?created=1", status_code=303)

    @app.post("/h1/{observation_id}/correct")
    def h1_correct(
        request: Request,
        observation_id: str,
        security_id: str = Form(""),
        strategy_id: str = Form(""),
        quantity: str = Form(""),
        average_cost: str = Form(""),
        cost_basis_date: str = Form(""),
        note: str = Form(""),
    ):
        try:
            correct_observation(
                h1_store,
                observation_id,
                security_id=security_id,
                strategy_id=strategy_id,
                quantity=quantity,
                average_cost=average_cost,
                cost_basis_date=cost_basis_date,
                note=note,
            )
        except DemoInputError as exc:
            return render_error(request, "观察仓更正无效", str(exc), 400)
        return RedirectResponse("/h1?corrected=1", status_code=303)

    @app.get("/h1/{observation_id}/end", response_class=HTMLResponse)
    def h1_end_confirm(request: Request, observation_id: str):
        try:
            data = h1_end_data(h1_store, observation_id)
        except DemoInputError as exc:
            return render_error(request, "无法结束观察", str(exc), 400)
        return templates.TemplateResponse(request, "h1_end.html", data)

    @app.post("/h1/{observation_id}/end")
    def h1_end(request: Request, observation_id: str, reason: str = Form("")):
        try:
            end_observation(h1_store, observation_id, reason=reason)
        except DemoInputError as exc:
            return render_error(request, "无法结束观察", str(exc), 400)
        return RedirectResponse("/h1?ended=1", status_code=303)

    @app.get("/backtest", response_class=HTMLResponse)
    def backtest(request: Request, scenario: str = Query("u3")):
        try:
            data = backtest_data(scenario)
        except DemoInputError as exc:
            return render_error(request, "回测场景无效", str(exc), 400)
        return templates.TemplateResponse(request, "backtest.html", data)

    @app.get("/status", response_class=HTMLResponse)
    def status(request: Request):
        return templates.TemplateResponse(request, "status.html", status_data())

    @app.get("/export/f1.csv")
    def export_f1(
        scenario: str = Query("normal"),
        strategy: str = Query("S01"),
        style: str = Query("BALANCED/1"),
        n: int = Query(10),
        q: str = Query(""),
    ):
        try:
            data = f1_data(scenario=scenario, strategy_id=strategy, style_id=style, n=n, query=q)
        except DemoInputError as exc:
            return PlainTextResponse(str(exc), status_code=400)
        response = Response(content=f1_csv(data), media_type="text/csv; charset=utf-8")
        response.headers["Content-Disposition"] = 'attachment; filename="mishi-f1-fixture.csv"'
        return response

    @app.get("/export/f6.csv")
    def export_f6(scenario: str = Query("u3")):
        try:
            data = backtest_data(scenario)
        except DemoInputError as exc:
            return PlainTextResponse(str(exc), status_code=400)
        response = Response(content=backtest_csv(data), media_type="text/csv; charset=utf-8")
        response.headers["Content-Disposition"] = 'attachment; filename="mishi-f6-fixture.csv"'
        return response

    @app.get("/api/f1")
    def api_f1(
        scenario: str = Query("normal"),
        strategy: str = Query("S01"),
        style: str = Query("BALANCED/1"),
        n: int = Query(10),
        q: str = Query(""),
    ):
        try:
            return f1_data(scenario=scenario, strategy_id=strategy, style_id=style, n=n, query=q)
        except DemoInputError as exc:
            return JSONResponse(_fixture_error_payload(str(exc)), status_code=400)

    @app.get("/api/stock")
    def api_stock(
        scenario: str = Query(...),
        strategy_id: str = Query(...),
        style: str = Query(...),
        security_id: str = Query(...),
        batch_id: str = Query(...),
    ):
        try:
            return stock_data(
                scenario=scenario,
                security_id=security_id,
                strategy_id=strategy_id,
                style_id=style,
                expected_batch_id=batch_id,
            )
        except BatchMismatch as exc:
            return JSONResponse(_fixture_error_payload(str(exc)), status_code=409)
        except DemoInputError as exc:
            return JSONResponse(_fixture_error_payload(str(exc)), status_code=400)

    @app.get("/api/watch")
    def api_watch(scenario: str = Query("normal")):
        try:
            return watch_data(store, scenario=scenario)
        except DemoInputError as exc:
            return JSONResponse(_fixture_error_payload(str(exc)), status_code=400)

    @app.post("/api/watch")
    def api_watch_add(payload: WatchRequest):
        try:
            entry = add_watch(
                store,
                scenario=payload.scenario,
                security_id=payload.security_id,
                strategy_id=payload.strategy_id,
                style_id=payload.style,
                expected_batch_id=payload.batch_id,
            )
        except BatchMismatch as exc:
            return JSONResponse(_fixture_error_payload(str(exc)), status_code=409)
        except DemoInputError as exc:
            return JSONResponse(_fixture_error_payload(str(exc)), status_code=400)
        return {
            "fixture": {
                "marker": FIXTURE_MARKER,
                "fixture_version": FIXTURE_VERSION,
                "contract_marker": CONTRACT_MARKER,
                "contract_fixture_version": CONTRACT_FIXTURE_VERSION,
                "contract_version": RESULT_CONTRACT_VERSION,
                "source": "FIXTURE",
                "real_market_data": False,
            },
            "user": DEMO_USER,
            "entry": entry.to_dict(),
        }

    @app.delete("/api/watch/{watch_id}")
    def api_watch_remove(watch_id: str):
        entry = store.remove(watch_id)
        if entry is None:
            return JSONResponse(_fixture_error_payload(f"关注记录不存在: {watch_id}"), status_code=404)
        return {
            "fixture": {
                "marker": FIXTURE_MARKER,
                "fixture_version": FIXTURE_VERSION,
                "contract_marker": CONTRACT_MARKER,
                "contract_fixture_version": CONTRACT_FIXTURE_VERSION,
                "contract_version": RESULT_CONTRACT_VERSION,
                "source": "FIXTURE",
                "real_market_data": False,
            },
            "user": DEMO_USER,
            "entry": entry.to_dict(),
        }

    @app.get("/api/backtest/{scenario}")
    def api_backtest(scenario: str):
        try:
            return backtest_data(scenario)
        except DemoInputError as exc:
            return JSONResponse(_fixture_error_payload(str(exc)), status_code=400)

    @app.get("/api/h1")
    def api_h1():
        return api_h1_data(h1_store)

    @app.get("/api/status")
    def api_status():
        return status_data()

    @app.get("/api/health")
    def health():
        return {
            "status": "ok",
            "fixture": FIXTURE_MARKER,
            "fixture_version": FIXTURE_VERSION,
            "contract_marker": CONTRACT_MARKER,
            "contract_fixture_version": CONTRACT_FIXTURE_VERSION,
            "contract_version": RESULT_CONTRACT_VERSION,
            "real_market_data": False,
        }

    return app


app = create_app()
