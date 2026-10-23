"""Read-only product service over fixed synthetic fixtures.

All rankings, conditions, dimensions and backtest results come from the
accepted OD-1/OD-2 kernels.  This module only validates demo inputs, shapes
kernel output for HTML/JSON and stores the demo watchlist.
"""

from __future__ import annotations

import csv
import io
import json
from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from typing import Any, Iterable, Mapping
from urllib.parse import urlencode

from ..cash_backtest.model import BacktestResult
from ..strategy_core import compute_all, compute_diagnostics, style_view
from ..strategy_core.config import default_configs
from ..strategy_core.model import (
    ConditionStatus,
    DiagnosticResult,
    DimensionResult,
    RowResult,
    StrategyResult,
    ValueStatus,
)
from . import FIXTURE_MARKER, FIXTURE_VERSION
from .backtest import run_fixture_backtest
from .fixtures import (
    BACKTEST_SCENARIOS,
    BUSINESS_DATE,
    FIXTURE_COMPUTED_AT,
    FIXTURE_PUBLISHED_AT,
    INDUSTRY_NAMES,
    SCENARIOS,
    SECURITY_NAMES,
    build_snapshot,
    fixture_metadata,
)
from .watch import DEMO_USER, WatchEntry, WatchStore

STRATEGY_LABELS: Mapping[str, str] = {
    "S01": "S01 趋势强势",
    "S02": "S02 平台放量突破",
    "S03": "S03 强势回调再启动",
    "S04": "S04 超跌修复",
    "S05": "S05 低波稳健",
    "S06": "S06 板块强股",
    "S07": "S07 价值质量",
    "S08": "S08 日度资金持续流入",
}

STYLE_LABELS: Mapping[str, str] = {
    "BALANCED/1": "均衡 · BALANCED/1",
    "ATTACK/1": "进攻 · ATTACK/1",
    "DEFENSIVE/1": "防守 · DEFENSIVE/1",
}

STYLE_DIMENSION_ORDER: Mapping[str, tuple[str, ...]] = {
    "BALANCED/1": ("momentum", "value", "quality", "reversal", "low_volatility", "liquidity"),
    "ATTACK/1": ("momentum", "reversal", "liquidity", "low_volatility", "value", "quality"),
    "DEFENSIVE/1": ("low_volatility", "liquidity", "quality", "value", "momentum", "reversal"),
}

DIMENSION_LABELS: Mapping[str, str] = {
    "momentum": "动量",
    "reversal": "反转",
    "value": "价值",
    "quality": "质量",
    "low_volatility": "低波",
    "liquidity": "流动性",
}

CONDITION_LABELS: Mapping[str, str] = {
    "trend": "趋势条件（P>MA20>MA60）",
    "er20_positive": "ER20>0",
    "platform_quiet": "平台收敛且缩量",
    "breakout": "突破平台上沿且放量",
    "pullback_observation": "MA20 上方回调 3%–10%",
    "reclaim_yesterday_high": "收盘高于昨日最高",
    "prior_drop5": "截至昨日的 5 日跌幅 ≤ -8%",
    "repair_confirmation": "站上 MA5 且高于昨日最高",
    "entry_conflict_exit": "确认日已满足 MA20 退出（买入前冲突）",
    "low_vol_percentile": "波动位于低波分位 ≤40%",
    "bound_s01_trigger": "绑定 S01 默认版本触发",
    "strong_industry": "行业广度≥60% 且超额>0",
    "concentration_slot": "行业触发名次在正式前 2",
    "positive_np": "TTM 归母净利润>0",
    "positive_ocf": "TTM 经营现金流>0",
    "roe_threshold": "ROE_TTM≥10%",
    "positive_days": "近 5 日净流入至少 3 日",
    "net_sum_positive": "近 5 日净额合计>0",
    "price_above_ma20": "P>MA20",
}

REASON_LABELS: Mapping[str, str] = {
    "CONCENTRATION_EXCLUDED": "S06 行业前 2 限额已满，正式榜单身份仍为集中度剔除",
    "INDUSTRY_NOT_STRONG": "所属行业未达到强行业条件",
    "INDUSTRY_CROSS_SECTION_INCOMPLETE": "行业横截面不完整",
    "INDUSTRY_MEMBER_STATUS_UNKNOWN": "行业成员状态未知",
    "INDUSTRY_STATS_UNKNOWN": "行业统计未知",
    "AVG_AMOUNT_MISSING": "20 日平均成交额缺失",
    "PRICE_UNKNOWN": "价格输入未知",
    "FIXTURE_INPUT_MISSING": "固定输入缺失",
}

STATE_LABELS: Mapping[str, str] = {
    "CANDIDATE": "候选",
    "ELIGIBLE_NOT_TRIGGERED": "资格通过但未触发",
    "CONCENTRATION_EXCLUDED": "行业集中度剔除",
    "BASE_EXCLUDED": "基础资格剔除",
    "STRATEGY_NOT_APPLICABLE": "该策略不适用",
    "INPUT_UNKNOWN": "输入 UNKNOWN",
    "MISSING": "输入缺失",
    "FAILED": "计算失败",
    "STALE": "数据过期",
    "INVALID": "输入无效",
    "CONFLICT": "输入冲突",
}

ELIGIBILITY_LABELS: Mapping[str, str] = {
    "SCORABLE": "可评分",
    "BASE_EXCLUDED": "基础资格剔除",
    "STRATEGY_NOT_APPLICABLE": "策略不适用",
    "INPUT_UNKNOWN": "输入 UNKNOWN",
    "MISSING": "输入缺失",
    "FAILED": "失败",
    "STALE": "过期",
    "INVALID": "无效",
    "CONFLICT": "冲突",
}

STATUS_LABELS: Mapping[str, str] = {
    ConditionStatus.TRUE.value: "TRUE · 成立",
    ConditionStatus.FALSE.value: "FALSE · 不成立",
    ConditionStatus.UNKNOWN.value: "UNKNOWN · 未知",
}

VALUE_STATUS_LABELS: Mapping[str, str] = {
    "VALUE": "有效值",
    "CONFIRMED_ZERO": "确认零",
    "RAW_ZERO_SEMANTICS_UNKNOWN": "原始零但语义未知",
    "NOT_APPLICABLE": "不适用",
    "MISSING": "缺失",
    "INVALID": "无效",
    "CONFLICT": "冲突",
    "REQUEST_FAILED": "请求失败",
    "STALE": "过期",
    "UNKNOWN": "UNKNOWN",
}

UNKNOWN_STATES = {
    "INPUT_UNKNOWN",
    "MISSING",
    "FAILED",
    "STALE",
    "INVALID",
    "CONFLICT",
    "BASE_EXCLUDED",
    "STRATEGY_NOT_APPLICABLE",
}

METRIC_LABELS: Mapping[str, str] = {
    "er20": "ER20",
    "er60": "ER60",
    "score01": "S01 评分键",
    "u20": "平台 20 日上沿",
    "l20": "平台 20 日下沿",
    "width": "平台幅度",
    "v20": "20 日均量",
    "v5": "5 日均量",
    "volume_ratio": "放量倍数",
    "breakout": "突破幅度",
    "distance": "距 MA20",
    "drawdown": "距 20 日高回撤",
    "prior_drop5": "前 5 日跌幅",
    "repair": "当日修复幅度",
    "sigma60": "60 日波动",
    "illiq60": "Amihud 60 日",
    "avg_amount20": "20 日平均成交额",
    "pe_ttm": "PE_TTM",
    "np_ttm": "NP_TTM",
    "ocf_ttm": "OCF_TTM",
    "roe_ttm": "ROE_TTM",
    "net_sum": "近 5 日净额合计",
    "flow_ratio": "资金净额/成交额",
    "positive_days": "近 5 日净流入天数",
    "excess": "行业超额",
    "breadth": "行业广度",
    "industry_score": "行业评分键",
}

BACKTEST_METRIC_LABELS: Mapping[str, str] = {
    "cumulative_return": "累计收益",
    "annualized_return": "年化收益",
    "cumulative_excess": "累计超额",
    "max_drawdown": "最大回撤",
    "sharpe": "夏普",
    "win_rate": "胜率",
    "profit_loss_ratio": "盈亏比",
    "buy_count": "买入成交数",
    "sell_count": "卖出成交数",
    "closed_cycle_count": "结束周期数",
    "avg_daily_turnover": "日均单边换手",
    "position_ratio": "期末仓位",
    "benchmark_return": "基准收益",
}

BACKTEST_PERCENT_METRICS = {
    "cumulative_return",
    "annualized_return",
    "cumulative_excess",
    "max_drawdown",
    "win_rate",
    "avg_daily_turnover",
    "position_ratio",
    "benchmark_return",
}

BACKTEST_COUNT_METRICS = {"buy_count", "sell_count", "closed_cycle_count"}


class DemoInputError(ValueError):
    pass


class BatchMismatch(DemoInputError):
    pass


@lru_cache(maxsize=8)
def _snapshot(scenario: str):
    return build_snapshot(scenario)


@lru_cache(maxsize=8)
def _results(scenario: str) -> Mapping[str, StrategyResult]:
    return compute_all(_snapshot(scenario), default_configs())


@lru_cache(maxsize=8)
def _diagnostics(scenario: str) -> DiagnosticResult:
    return compute_diagnostics(_snapshot(scenario), default_configs())


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _display_number(value: Decimal | None, places: int = 2) -> str:
    if value is None:
        return "—"
    quantum = Decimal(1).scaleb(-places)
    return format(value.quantize(quantum), "f")


def _display_ratio(value: Decimal | None) -> str:
    if value is None:
        return "—"
    return f"{_display_number(value * Decimal(100), 2)}%"


def _clean_label(text: str) -> str:
    return text.replace("_", " ")


def _condition_label(key: str) -> str:
    return CONDITION_LABELS.get(key, _clean_label(key))


def _reason_label(key: str) -> str:
    if key in REASON_LABELS:
        return REASON_LABELS[key]
    if ":" in key:
        head, _, tail = key.partition(":")
        return f"{REASON_LABELS.get(head, _clean_label(head))}（{_clean_label(tail)}）"
    return _clean_label(key)


def _status_tone(status: ConditionStatus) -> str:
    if status is ConditionStatus.TRUE:
        return "positive"
    if status is ConditionStatus.FALSE:
        return "adverse"
    return "unknown"


def _condition_rows(row: RowResult) -> list[dict[str, str]]:
    result: list[dict[str, str]] = []
    for key, status in row.conditions.items():
        result.append(
            {
                "key": key,
                "label": _condition_label(key),
                "status": status.value,
                "status_label": STATUS_LABELS[status.value],
                "tone": _status_tone(status),
            }
        )
    return result


def _reason_rows(row: RowResult) -> list[dict[str, str]]:
    return [
        {"key": reason, "label": _reason_label(reason), "tone": "adverse" if row.eligibility.value != "SCORABLE" else "neutral"}
        for reason in row.reasons
    ]


def _adverse_label(row: RowResult) -> str | None:
    for key, status in row.conditions.items():
        if status is ConditionStatus.FALSE:
            return _condition_label(key)
    for reason in row.reasons:
        return _reason_label(reason)
    return None


def _strategy_label(strategy_id: str) -> str:
    return STRATEGY_LABELS.get(strategy_id, strategy_id)


def _industry_name(industry_id: str | None) -> str | None:
    if industry_id is None:
        return None
    return INDUSTRY_NAMES.get(industry_id, industry_id)


def _security_name(security_id: str) -> str:
    return SECURITY_NAMES.get(security_id, security_id)


def _price_for(scenario: str, security_id: str) -> dict[str, str | None]:
    snapshot = _snapshot(scenario)
    bar = snapshot.bars.get(security_id, {}).get(snapshot.business_date)
    if bar is None:
        return {"date": snapshot.business_date, "close": None, "status": "MISSING"}
    return {
        "date": bar.date,
        "close": _display_number(bar.close.value, 2) if bar.close.usable else None,
        "status": bar.close.status.value,
    }


def _available_at_kind(value: str | None, input_version: str) -> str:
    if value is None:
        return "UNKNOWN"
    if len(value) > 10:
        return "LOCAL_DATETIME"
    if input_version.startswith("SYNTHETIC"):
        return "SYNTHETIC_DATE_COMPAT"
    return "NORMALIZED_AVAILABLE_DATE"


def batch_id(scenario: str, strategy_id: str) -> str:
    result = _results(scenario)[strategy_id]
    config_version = result.config_version.replace("/", "_")
    return f"FX01:{scenario}:{strategy_id}:{result.signal_date}:{config_version}:{FIXTURE_VERSION}"


def _batch_payload(scenario: str, strategy_id: str) -> dict[str, Any]:
    result = _results(scenario)[strategy_id]
    style_note = "风格仅调整策略入口和解释顺序，不改变 OD-1 计算结果。"
    return {
        "batch_id": batch_id(scenario, strategy_id),
        "strategy_id": strategy_id,
        "strategy_label": _strategy_label(strategy_id),
        "signal_date": result.signal_date,
        "config_id": result.config_id,
        "config_version": result.config_version,
        "input_version": result.input_version,
        "pool_size": result.pool_size,
        "candidate_size": result.candidate_size,
        "pool_complete": result.pool_complete,
        "bound_s01_config_version": result.bound_s01_config_version,
        "computed_at": FIXTURE_COMPUTED_AT,
        "published_at": FIXTURE_PUBLISHED_AT,
        "available_at": _snapshot(scenario).available_at,
        "style_note": style_note,
    }


def _formal_candidate(result: StrategyResult, row: RowResult) -> bool:
    return bool(
        result.pool_complete
        and row.signal_state.value == "CANDIDATE"
        and row.candidate_rank is not None
        and row.pool_rank is not None
    )


def _preview_candidate(result: StrategyResult, row: RowResult) -> bool:
    return bool(not result.pool_complete and row.signal_state.value == "CANDIDATE")


def _row_summary(
    scenario: str,
    strategy_id: str,
    security_id: str,
    *,
    style_id: str,
) -> dict[str, Any]:
    result = _results(scenario)[strategy_id]
    row = result.rows[security_id]
    security = _snapshot(scenario).securities[security_id]
    industry_id = row.industry_id or security.industry_id
    price = _price_for(scenario, security_id)
    formal = _formal_candidate(result, row)
    preview = _preview_candidate(result, row)
    conditions = _condition_rows(row)
    adverse = _adverse_label(row)
    if preview:
        adverse = "池不完整：只能作为 PREVIEW，不能视为正式候选"
    elif formal and adverse is None:
        adverse = "没有已知 FALSE 条件；仍仅为固定规则展示"
    query = urlencode(
        {
            "scenario": scenario,
            "strategy_id": strategy_id,
            "style": style_id,
            "security_id": security_id,
            "batch_id": batch_id(scenario, strategy_id),
        }
    )
    positive = [item["label"] for item in conditions if item["tone"] == "positive"]
    negative = [item["label"] for item in conditions if item["tone"] == "adverse"]
    unknown = [item["label"] for item in conditions if item["tone"] == "unknown"]
    return {
        "scenario": scenario,
        "style_id": style_id,
        "security_id": security_id,
        "security_name": _security_name(security_id),
        "industry_id": industry_id,
        "industry_name": _industry_name(industry_id),
        "strategy_id": strategy_id,
        "strategy_label": _strategy_label(strategy_id),
        "eligibility": row.eligibility.value,
        "eligibility_label": ELIGIBILITY_LABELS.get(row.eligibility.value, row.eligibility.value),
        "signal_state": row.signal_state.value,
        "signal_state_label": STATE_LABELS.get(row.signal_state.value, row.signal_state.value),
        "signal_status": row.signal_status.value,
        "signal_status_label": STATUS_LABELS.get(row.signal_status.value, row.signal_status.value),
        "formal_candidate": formal,
        "preview_candidate": preview,
        "candidate_rank": row.candidate_rank if formal else None,
        "pool_rank": row.pool_rank if formal else None,
        "sample_candidate_rank": row.sample_candidate_rank,
        "sample_pool_rank": row.sample_pool_rank,
        "pool_size": result.pool_size,
        "pool_complete": result.pool_complete,
        "signal_date": row.signal_date,
        "config_id": row.config_id,
        "config_version": row.config_version,
        "input_version": row.input_version,
        "available_at": row.available_at,
        "available_at_kind": _available_at_kind(row.available_at, row.input_version),
        "industry_pool_rank": row.industry_pool_rank,
        "industry_trigger_rank": row.industry_trigger_rank,
        "industry_total_rank": row.industry_total_rank,
        "price_date": price["date"],
        "price_close": price["close"],
        "price_status": price["status"],
        "conditions": conditions,
        "reasons": _reason_rows(row),
        "positive_conditions": positive,
        "adverse_conditions": negative,
        "unknown_conditions": unknown,
        "main_adverse": adverse,
        "stock_url": f"/stock?{query}",
        "batch_id": batch_id(scenario, strategy_id),
    }


def _hit_tags(scenario: str, security_id: str, selected_strategy: str) -> list[dict[str, Any]]:
    tags: list[dict[str, Any]] = []
    for strategy_id in sorted(_results(scenario)):
        result = _results(scenario)[strategy_id]
        row = result.rows.get(security_id)
        if row is None:
            continue
        if strategy_id == selected_strategy:
            continue
        if row.signal_state.value != "CANDIDATE":
            continue
        formal = _formal_candidate(result, row)
        tags.append(
            {
                "strategy_id": strategy_id,
                "strategy_label": _strategy_label(strategy_id),
                "formal": formal,
                "preview": not formal,
                "candidate_rank": row.candidate_rank if formal else None,
                "sample_candidate_rank": row.sample_candidate_rank,
            }
        )
    return tags


def f1_data(
    *,
    scenario: str = "normal",
    strategy_id: str = "S01",
    style_id: str = "BALANCED/1",
    n: int = 10,
    query: str = "",
    refresh: bool = False,
) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise DemoInputError(f"未知 scenario: {scenario}")
    if style_id not in STYLE_LABELS:
        raise DemoInputError(f"未知 style: {style_id}")
    if strategy_id not in STRATEGY_LABELS:
        raise DemoInputError(f"未知 strategy: {strategy_id}")
    if n not in (10, 20, 30):
        raise DemoInputError("显示 N 只能是 10 / 20 / 30")
    style = style_view(style_id)
    result = _results(scenario)[strategy_id]
    formal_rows = [
        result.rows[sid]
        for sid in sorted(result.rows)
        if _formal_candidate(result, result.rows[sid])
    ]
    formal_rows.sort(key=lambda row: (row.candidate_rank or 9999, row.security_id))
    preview_rows = [
        result.rows[sid]
        for sid in sorted(result.rows)
        if _preview_candidate(result, result.rows[sid])
    ]
    preview_rows.sort(key=lambda row: (row.sample_candidate_rank or 9999, row.security_id))
    unknown_rows = [
        result.rows[sid]
        for sid in sorted(result.rows)
        if result.rows[sid].eligibility.value != "SCORABLE"
        or result.rows[sid].signal_state.value in UNKNOWN_STATES
    ]
    unknown_rows.sort(key=lambda row: (row.industry_id or "", row.security_id))
    candidates = [_row_summary(scenario, strategy_id, row.security_id, style_id=style_id) for row in formal_rows[:n]]
    preview = [_row_summary(scenario, strategy_id, row.security_id, style_id=style_id) for row in preview_rows[:n]]
    unknown = [
        _row_summary(scenario, strategy_id, row.security_id, style_id=style_id)
        for row in unknown_rows[:20]
    ]
    for item in candidates + preview + unknown:
        item["hit_tags"] = _hit_tags(scenario, item["security_id"], strategy_id)
    query_text = query.strip().lower()
    if query_text:
        def matches(item: Mapping[str, Any]) -> bool:
            haystack = f"{item['security_id']} {item['security_name']} {item.get('industry_name') or ''}".lower()
            return query_text in haystack

        candidates = [item for item in candidates if matches(item)]
        preview = [item for item in preview if matches(item)]
        unknown = [item for item in unknown if matches(item)]
    if result.pool_complete:
        status = "PUBLISHED_FIXTURE" if formal_rows else "EMPTY"
        status_label = "FIXTURE 固定批次（非真实发布）" if formal_rows else "完整空结果（成功）"
    else:
        status = "PREVIEW"
        status_label = "PREVIEW / 池不完整（不是正式发布）"
    batch = _batch_payload(scenario, strategy_id)
    batch["status"] = status
    batch["status_label"] = status_label
    return {
        "fixture": fixture_metadata(scenario),
        "batch": batch,
        "strategy_id": strategy_id,
        "strategy_label": _strategy_label(strategy_id),
        "style": {
            "style_id": style.style_id,
            "label": STYLE_LABELS[style.style_id],
            "order": list(style.strategy_order),
            "diagnostic_priority": list(style.diagnostic_priority),
            "note": style.note,
        },
        "strategy_tabs": [
            {
                "strategy_id": sid,
                "label": _strategy_label(sid),
                "active": sid == strategy_id,
                "url": "/?" + urlencode(
                    {"scenario": scenario, "strategy": sid, "style": style_id, "n": n, "q": query}
                ),
            }
            for sid in style.strategy_order
        ],
        "style_tabs": [
            {
                "style_id": sid,
                "label": label,
                "active": sid == style_id,
                "url": "/?" + urlencode(
                    {"scenario": scenario, "strategy": strategy_id, "style": sid, "n": n, "q": query}
                ),
            }
            for sid, label in STYLE_LABELS.items()
        ],
        "scenario_tabs": [
            {
                "scenario": key,
                "label": meta["label"],
                "active": key == scenario,
                "url": "/?" + urlencode(
                    {"scenario": key, "strategy": strategy_id, "style": style_id, "n": n, "q": query}
                ),
            }
            for key, meta in SCENARIOS.items()
        ],
        "n_tabs": [
            {
                "n": value,
                "active": value == n,
                "url": "/?" + urlencode(
                    {"scenario": scenario, "strategy": strategy_id, "style": style_id, "n": value, "q": query}
                ),
            }
            for value in (10, 20, 30)
        ],
        "n": n,
        "query": query,
        "refresh": refresh,
        "refresh_note": "固定 FIXTURE 批次：刷新只重读同一输入，不抓取真实行情。",
        "candidates": candidates,
        "preview_candidates": preview,
        "unknown_rows": unknown,
        "counts": {
            "formal_candidates": len(formal_rows),
            "preview_candidates": len(preview_rows),
            "unknown_rows": len(unknown_rows),
            "pool_size": result.pool_size,
            "kernel_candidate_size": result.candidate_size,
        },
    }


def _dimension_view(name: str, dimension: DimensionResult) -> dict[str, Any]:
    raw = dimension.raw_value
    unit = dimension.unit
    value_text = _display_number(raw, 4)
    if unit == "ratio" and raw is not None:
        value_text = _display_ratio(raw)
    elif unit == "x" and raw is not None:
        value_text = f"{_display_number(raw, 2)}x"
    elif unit == "1/CNY" and raw is not None:
        value_text = f"{_display_number(raw * Decimal(100000000), 4)} ×10⁻⁸ /元"
    score_text = _display_number(dimension.score, 1) if dimension.score is not None else "UNKNOWN"
    score_width = None
    if dimension.score is not None:
        score_width = min(100.0, max(0.0, float(dimension.score)))
    extras = []
    for key, value in dimension.extras.items():
        extras.append(
            {
                "key": key,
                "label": METRIC_LABELS.get(key, key),
                "value": _display_number(value, 4) if value is not None else "UNKNOWN",
            }
        )
    return {
        "name": name,
        "label": DIMENSION_LABELS.get(name, name),
        "raw_value": _decimal_text(raw),
        "value_text": value_text,
        "unit": unit,
        "score": _decimal_text(dimension.score),
        "score_text": score_text,
        "score_width": score_width,
        "status": dimension.status.value,
        "status_label": VALUE_STATUS_LABELS.get(dimension.status.value, dimension.status.value),
        "pool_id": dimension.pool_id,
        "pool_size": dimension.pool_size,
        "pool_complete": dimension.pool_complete,
        "business_date": dimension.business_date,
        "window": dimension.window,
        "direction": dimension.direction,
        "explanation": dimension.explanation,
        "reason": dimension.reason,
        "extras": extras,
    }


def _strategy_cross_view(scenario: str, security_id: str, selected_strategy: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for strategy_id in sorted(_results(scenario)):
        result = _results(scenario)[strategy_id]
        row = result.rows[security_id]
        formal = _formal_candidate(result, row)
        preview = _preview_candidate(result, row)
        rows.append(
            {
                "strategy_id": strategy_id,
                "strategy_label": _strategy_label(strategy_id),
                "selected": strategy_id == selected_strategy,
                "eligibility": row.eligibility.value,
                "eligibility_label": ELIGIBILITY_LABELS.get(row.eligibility.value, row.eligibility.value),
                "signal_state": row.signal_state.value,
                "signal_state_label": STATE_LABELS.get(row.signal_state.value, row.signal_state.value),
                "signal_status": row.signal_status.value,
                "formal_candidate": formal,
                "preview_candidate": preview,
                "candidate_rank": row.candidate_rank if formal else None,
                "sample_candidate_rank": row.sample_candidate_rank,
                "pool_rank": row.pool_rank if formal else None,
                "pool_size": result.pool_size,
                "pool_complete": result.pool_complete,
                "reasons": _reason_rows(row),
            }
        )
    return rows


def stock_data(
    *,
    scenario: str,
    security_id: str,
    strategy_id: str,
    style_id: str,
    expected_batch_id: str,
) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise DemoInputError(f"未知 scenario: {scenario}")
    if strategy_id not in STRATEGY_LABELS:
        raise DemoInputError(f"未知 strategy: {strategy_id}")
    if style_id not in STYLE_LABELS:
        raise DemoInputError(f"未知 style: {style_id}")
    if security_id not in SECURITY_NAMES:
        raise DemoInputError(f"未知证券: {security_id}")
    actual_batch = batch_id(scenario, strategy_id)
    if expected_batch_id != actual_batch:
        raise BatchMismatch(
            f"批次不一致：链接批次 {expected_batch_id} / 当前固定批次 {actual_batch}"
        )
    summary = _row_summary(scenario, strategy_id, security_id, style_id=style_id)
    result = _results(scenario)[strategy_id]
    row = result.rows[security_id]
    diagnostics = _diagnostics(scenario)
    dimension_map = diagnostics.rows.get(security_id, {})
    order = STYLE_DIMENSION_ORDER[style_id]
    dimensions = [
        _dimension_view(name, dimension_map[name])
        for name in order
        if name in dimension_map
    ]
    remaining = [name for name in dimension_map if name not in order]
    dimensions.extend(_dimension_view(name, dimension_map[name]) for name in remaining)
    available_dimensions = sum(1 for item in dimensions if item["status"] == ValueStatus.VALUE.value)
    batch = _batch_payload(scenario, strategy_id)
    batch["status"] = "PREVIEW" if not result.pool_complete else "PUBLISHED_FIXTURE"
    batch["status_label"] = (
        "PREVIEW / 池不完整，不是正式发布" if not result.pool_complete else "FIXTURE 固定批次（非真实发布）"
    )
    condition_rows = _condition_rows(row)
    query = urlencode(
        {"scenario": scenario, "strategy_id": strategy_id, "style": style_id, "security_id": security_id}
    )
    return {
        "fixture": fixture_metadata(scenario),
        "batch": batch,
        "security_id": security_id,
        "security_name": _security_name(security_id),
        "industry_id": summary["industry_id"],
        "industry_name": summary["industry_name"],
        "summary": summary,
        "conditions": condition_rows,
        "positive_conditions": [item for item in condition_rows if item["tone"] == "positive"],
        "adverse_conditions": [item for item in condition_rows if item["tone"] == "adverse"],
        "unknown_conditions": [item for item in condition_rows if item["tone"] == "unknown"],
        "dimensions": dimensions,
        "available_dimensions": available_dimensions,
        "diagnostic_notes": list(diagnostics.notes),
        "strategy_rows": _strategy_cross_view(scenario, security_id, strategy_id),
        "time": {
            "business_date": BUSINESS_DATE,
            "signal_date": row.signal_date,
            "computed_at": FIXTURE_COMPUTED_AT,
            "published_at": FIXTURE_PUBLISHED_AT,
            "available_at": row.available_at or "UNKNOWN",
            "available_at_kind": _available_at_kind(row.available_at, row.input_version),
            "input_version": row.input_version,
            "config_id": row.config_id,
            "config_version": row.config_version,
            "batch_id": actual_batch,
            "price_date": summary["price_date"],
            "price_status": summary["price_status"],
            "price_source": "SYNTHETIC_RAW_CLOSE",
            "source_time": "UNKNOWN（固定 Fixture 无真实源时间）",
        },
        "backtest_url": "/backtest",
        "watch_url": f"/watch?{query}",
        "board_url": "/?" + urlencode({"scenario": scenario, "strategy": strategy_id, "style": style_id}),
    }


def _snapshot_payload(scenario: str, security_id: str, strategy_id: str, style_id: str) -> dict[str, Any]:
    detail = stock_data(
        scenario=scenario,
        security_id=security_id,
        strategy_id=strategy_id,
        style_id=style_id,
        expected_batch_id=batch_id(scenario, strategy_id),
    )
    dims = {
        item["name"]: {
            "label": item["label"],
            "value_text": item["value_text"],
            "score_text": item["score_text"],
            "status": item["status"],
            "pool_size": item["pool_size"],
            "pool_complete": item["pool_complete"],
        }
        for item in detail["dimensions"]
    }
    summary = detail["summary"]
    return {
        "fixture_version": FIXTURE_VERSION,
        "fixture_marker": FIXTURE_MARKER,
        "scenario": scenario,
        "security_id": security_id,
        "security_name": detail["security_name"],
        "industry_id": detail["industry_id"],
        "industry_name": detail["industry_name"],
        "strategy_id": strategy_id,
        "strategy_label": detail["batch"]["strategy_label"],
        "batch_id": detail["time"]["batch_id"],
        "signal_date": detail["time"]["signal_date"],
        "config_id": detail["time"]["config_id"],
        "config_version": detail["time"]["config_version"],
        "input_version": detail["time"]["input_version"],
        "available_at": detail["time"]["available_at"],
        "available_at_kind": detail["time"]["available_at_kind"],
        "price_date": detail["time"]["price_date"],
        "price_close": summary["price_close"],
        "price_status": summary["price_status"],
        "eligibility": summary["eligibility"],
        "signal_state": summary["signal_state"],
        "signal_state_label": summary["signal_state_label"],
        "signal_status": summary["signal_status"],
        "formal_candidate": summary["formal_candidate"],
        "preview_candidate": summary["preview_candidate"],
        "candidate_rank": summary["candidate_rank"],
        "sample_candidate_rank": summary["sample_candidate_rank"],
        "pool_rank": summary["pool_rank"],
        "sample_pool_rank": summary["sample_pool_rank"],
        "pool_size": summary["pool_size"],
        "pool_complete": summary["pool_complete"],
        "main_adverse": summary["main_adverse"],
        "positive_conditions": summary["positive_conditions"],
        "adverse_conditions": summary["adverse_conditions"],
        "dimensions": dims,
        "available_dimensions": detail["available_dimensions"],
    }


def add_watch(
    store: WatchStore,
    *,
    scenario: str,
    security_id: str,
    strategy_id: str,
    style_id: str,
    expected_batch_id: str,
) -> WatchEntry:
    actual = batch_id(scenario, strategy_id) if scenario in SCENARIOS and strategy_id in STRATEGY_LABELS else None
    if actual != expected_batch_id:
        raise BatchMismatch(f"关注批次不一致：{expected_batch_id!r} / 当前 {actual!r}")
    snapshot = _snapshot_payload(scenario, security_id, strategy_id, style_id)
    return store.add(
        security_id=security_id,
        strategy_id=strategy_id,
        scenario=scenario,
        style=style_id,
        batch_id=expected_batch_id,
        snapshot=snapshot,
    )


def _current_watch_state(entry: WatchEntry, scenario: str) -> dict[str, Any]:
    if scenario not in SCENARIOS:
        return {"scenario": scenario, "status": "UNKNOWN", "status_label": "未知场景", "details": []}
    if entry.security_id not in _snapshot(scenario).securities:
        return {
            "scenario": scenario,
            "status": "NOT_IN_BATCH",
            "status_label": "当前批次无该证券",
            "details": [],
        }
    try:
        summary = _row_summary(scenario, entry.strategy_id, entry.security_id, style_id=entry.style)
    except KeyError:
        return {"scenario": scenario, "status": "UNKNOWN", "status_label": "当前批次无法计算", "details": []}
    if summary["formal_candidate"]:
        status = "FORMAL_CANDIDATE"
        label = f"FIXTURE 正式候选 #{summary['candidate_rank']}"
    elif summary["preview_candidate"]:
        status = "PREVIEW"
        label = f"PREVIEW 样本 #{summary['sample_candidate_rank']}（池不完整）"
    elif summary["signal_state"] in UNKNOWN_STATES:
        status = "UNKNOWN"
        label = f"UNKNOWN · {summary['signal_state_label']}"
    elif summary["signal_state"] == "CONCENTRATION_EXCLUDED":
        status = "CONCENTRATION_EXCLUDED"
        label = "行业集中度剔除（正式榜外）"
    else:
        status = "NOT_TRIGGERED"
        label = "已不满足当前固定规则"
    return {
        "scenario": scenario,
        "status": status,
        "status_label": label,
        "batch_id": batch_id(scenario, entry.strategy_id),
        "pool_complete": summary["pool_complete"],
        "main_adverse": summary["main_adverse"],
        "signal_state": summary["signal_state"],
        "candidate_rank": summary["candidate_rank"],
        "sample_candidate_rank": summary["sample_candidate_rank"],
        "price_date": summary["price_date"],
        "price_close": summary["price_close"],
    }


def watch_data(store: WatchStore, *, scenario: str = "normal") -> dict[str, Any]:
    if scenario not in SCENARIOS:
        raise DemoInputError(f"未知 scenario: {scenario}")
    entries = store.entries()
    active = [entry for entry in entries if entry.status == "ACTIVE"]
    removed = [entry for entry in entries if entry.status == "REMOVED"]
    def present(entry: WatchEntry) -> dict[str, Any]:
        payload = entry.to_dict()
        payload["current"] = _current_watch_state(entry, scenario)
        payload["snapshot_changed"] = False
        payload["snapshot_note"] = "首次关注快照保持不变；上方仅为另一次固定批次的当前对照。"
        return payload

    return {
        "fixture": fixture_metadata(scenario),
        "user": DEMO_USER,
        "scenario": scenario,
        "scenario_tabs": [
            {
                "scenario": key,
                "label": meta["label"],
                "active": key == scenario,
                "url": "/watch?" + urlencode({"scenario": key}),
            }
            for key, meta in SCENARIOS.items()
        ],
        "active": [present(entry) for entry in reversed(active)],
        "removed": [present(entry) for entry in reversed(removed)],
        "active_count": len(active),
        "removed_count": len(removed),
    }


def _backtest_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, tuple):
        return [_backtest_value(item) for item in value]
    if isinstance(value, list):
        return [_backtest_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _backtest_value(item) for key, item in value.items()}
    return value


def backtest_data(scenario: str) -> dict[str, Any]:
    if scenario not in BACKTEST_SCENARIOS:
        raise DemoInputError(f"未知回测场景: {scenario}")
    result, meta = run_fixture_backtest(scenario)
    failed_orders = [order for order in result.orders if order.status in {"UNFILLED", "BLOCKED_UNKNOWN", "EXPIRED"}]
    recon_ok = all(item.get("cash_ok") and item.get("equity_ok") for item in result.reconciliation)
    return {
        "fixture": {
            **fixture_metadata("normal"),
            "backtest_scenario": scenario,
            "backtest_label": BACKTEST_SCENARIOS[scenario]["label"],
            "backtest_description": BACKTEST_SCENARIOS[scenario]["description"],
        },
        "meta": meta,
        "status": result.status,
        "succeeded": result.succeeded,
        "blockers": list(result.blockers),
        "warnings": list(result.warnings),
        "synthetic": result.synthetic,
        "initial_cash": _decimal_text(result.initial_cash),
        "nav": [
            {
                "date": point.date,
                "cash": _decimal_text(point.cash),
                "receivables": _decimal_text(point.receivables),
                "payables": _decimal_text(point.payables),
                "market_value": _decimal_text(point.market_value),
                "equity": _decimal_text(point.equity),
                "nav": _decimal_text(point.nav),
                "benchmark": _decimal_text(point.benchmark),
                "daily_return": _decimal_text(point.daily_return),
                "drawdown": _decimal_text(point.drawdown),
                "position_count": point.position_count,
                "position_ratio": _decimal_text(point.position_ratio),
            }
            for point in result.nav_points
        ],
        "orders": [
            {
                "order_id": order.order_id,
                "security_id": order.security_id,
                "side": order.side,
                "attempt_date": order.attempt_date,
                "signal_date": order.signal_date,
                "status": order.status,
                "reason": order.reason,
                "requested_quantity": order.requested_quantity,
                "filled_quantity": order.filled_quantity,
                "price": _decimal_text(order.price),
                "gross": _decimal_text(order.gross),
                "commission": _decimal_text(order.commission),
                "other_fees": _decimal_text(order.other_fees),
            }
            for order in result.orders
        ],
        "fills": [
            {
                "order_id": fill.order_id,
                "security_id": fill.security_id,
                "side": fill.side,
                "date": fill.date,
                "quantity": fill.quantity,
                "price": _decimal_text(fill.price),
                "gross": _decimal_text(fill.gross),
                "commission": _decimal_text(fill.commission),
                "other_fees": _decimal_text(fill.other_fees),
            }
            for fill in result.fills
        ],
        "fees": _backtest_value(result.fee_entries),
        "dividend_taxes": _backtest_value(result.dividend_tax_entries),
        "closed_cycles": [
            {
                "security_id": cycle.security_id,
                "strategy_id": cycle.strategy_id,
                "opened_on": cycle.opened_on,
                "closed_on": cycle.closed_on,
                "realized_trading_pnl": _decimal_text(cycle.realized_trading_pnl),
                "realized_dividend": _decimal_text(cycle.realized_dividend),
                "total_pnl": _decimal_text(cycle.total_pnl),
            }
            for cycle in result.closed_cycles
        ],
        "final_positions": [
            {
                "date": position.date,
                "security_id": position.security_id,
                "quantity": position.quantity,
                "sellable_quantity": position.sellable_quantity,
                "cost_open": _decimal_text(position.cost_open),
                "dividend_open": _decimal_text(position.dividend_open),
                "market_value": _decimal_text(position.market_value),
                "unrealized_pnl": _decimal_text(position.unrealized_pnl),
                "r_open": _decimal_text(position.r_open),
                "holding_days": position.holding_days,
                "industry_id": position.industry_id,
                "mark_status": position.mark_status,
            }
            for position in result.final_positions
        ],
        "reconciliation": _backtest_value(result.reconciliation),
        "reconciliation_ok": recon_ok,
        "failed_orders": [
            {
                "security_id": order.security_id,
                "side": order.side,
                "attempt_date": order.attempt_date,
                "status": order.status,
                "reason": order.reason,
            }
            for order in failed_orders
        ],
        "metrics": _backtest_value(result.metrics),
        "scenario_tabs": [
            {
                "scenario": key,
                "label": meta_item["label"],
                "active": key == scenario,
                "url": "/backtest?" + urlencode({"scenario": key}),
            }
            for key, meta_item in BACKTEST_SCENARIOS.items()
        ],
    }


def status_data() -> dict[str, Any]:
    scenarios: list[dict[str, Any]] = []
    for key, meta in SCENARIOS.items():
        snapshot = _snapshot(key)
        results = _results(key)
        strategies = []
        for strategy_id in sorted(results):
            result = results[strategy_id]
            states: dict[str, int] = {}
            for row in result.rows.values():
                states[row.signal_state.value] = states.get(row.signal_state.value, 0) + 1
            strategies.append(
                {
                    "strategy_id": strategy_id,
                    "strategy_label": _strategy_label(strategy_id),
                    "config_id": result.config_id,
                    "config_version": result.config_version,
                    "pool_size": result.pool_size,
                    "candidate_size": result.candidate_size,
                    "pool_complete": result.pool_complete,
                    "states": states,
                }
            )
        scenarios.append(
            {
                "scenario": key,
                "label": meta["label"],
                "description": meta["description"],
                "business_date": snapshot.business_date,
                "calendar_days": len(snapshot.calendar),
                "calendar_start": snapshot.calendar[0],
                "calendar_end": snapshot.calendar[-1],
                "universe_size": len(snapshot.securities),
                "universe_complete": snapshot.universe_complete,
                "industry_mapping_complete": snapshot.industry_mapping_complete,
                "input_version": snapshot.input_version,
                "available_at": snapshot.available_at,
                "taxonomy_id": snapshot.taxonomy_id,
                "taxonomy_version": snapshot.taxonomy_version,
                "strategies": strategies,
            }
        )
    return {
        "fixture": {
            "marker": FIXTURE_MARKER,
            "fixture_version": FIXTURE_VERSION,
            "source": "FIXTURE",
            "real_market_data": False,
            "network_used": False,
            "computed_at": FIXTURE_COMPUTED_AT,
            "published_at": FIXTURE_PUBLISHED_AT,
            "business_date": BUSINESS_DATE,
        },
        "scenarios": scenarios,
        "backtest_scenarios": [
            {
                "scenario": key,
                "label": meta["label"],
                "description": meta["description"],
                "url": "/backtest?" + urlencode({"scenario": key}),
            }
            for key, meta in BACKTEST_SCENARIOS.items()
        ],
        "gates": [
            {"name": "真实行情/真实扫描", "status": "NOT_USED / GATED", "detail": "固定 Fixture，无网络调用。"},
            {"name": "OD-1 规则内核", "status": "REUSED", "detail": "mishi_radar.strategy_core"},
            {"name": "OD-2 现金内核", "status": "REUSED", "detail": "mishi_radar.cash_backtest.run_backtest"},
            {"name": "F4 市场/行业/资金", "status": "GATED / NOT_IMPLEMENTED", "detail": "本轮不提供空壳页面。"},
            {"name": "H1 观察仓", "status": "GATED / NOT_IMPLEMENTED", "detail": "本轮仅完成 F5 关注快照。"},
            {"name": "F8 正式认证/付费权益", "status": "NOT_IMPLEMENTED", "detail": "仅固定演示用户入口，不声称权益系统。"},
            {"name": "OD-3 价格/配额/SLA/权限", "status": "UNKNOWN", "detail": "未自行确定，保持 Owner 决策边界。"},
        ],
    }


def _csv_safe(value: Any) -> str:
    text = "" if value is None else str(value)
    if text[:1] in {"=", "+", "-", "@"}:
        return "'" + text
    return text


def f1_csv(data: Mapping[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(
        [
            "fixture_marker",
            "fixture_version",
            "scenario",
            "batch_id",
            "strategy_id",
            "status",
            "candidate_rank",
            "sample_candidate_rank",
            "pool_rank",
            "pool_size",
            "pool_complete",
            "security_id",
            "security_name",
            "signal_state",
            "signal_status",
            "price_date",
            "price_close",
            "main_adverse",
        ]
    )
    rows: Iterable[Mapping[str, Any]] = (
        list(data["candidates"]) + list(data["preview_candidates"]) + list(data["unknown_rows"])
    )
    for item in rows:
        writer.writerow(
            [
                _csv_safe(FIXTURE_MARKER),
                _csv_safe(FIXTURE_VERSION),
                _csv_safe(data["fixture"]["scenario"]),
                _csv_safe(data["batch"]["batch_id"]),
                _csv_safe(item["strategy_id"]),
                _csv_safe(data["batch"]["status"]),
                _csv_safe(item["candidate_rank"]),
                _csv_safe(item["sample_candidate_rank"]),
                _csv_safe(item["pool_rank"]),
                _csv_safe(item["pool_size"]),
                _csv_safe(item["pool_complete"]),
                _csv_safe(item["security_id"]),
                _csv_safe(item["security_name"]),
                _csv_safe(item["signal_state"]),
                _csv_safe(item["signal_status"]),
                _csv_safe(item["price_date"]),
                _csv_safe(item["price_close"]),
                _csv_safe(item["main_adverse"]),
            ]
        )
    return buffer.getvalue()


def backtest_csv(data: Mapping[str, Any]) -> str:
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    columns = [
        "fixture_marker",
        "fixture_version",
        "scenario",
        "row_type",
        "date",
        "security_id",
        "side",
        "status",
        "reason",
        "quantity",
        "price",
        "gross",
        "commission",
        "other_fees",
        "cash",
        "market_value",
        "equity",
        "nav",
        "detail_json",
    ]
    writer.writerow(columns)
    common = [_csv_safe(FIXTURE_MARKER), _csv_safe(FIXTURE_VERSION), _csv_safe(data["meta"]["scenario"])]

    def emit(row_type: str, **values: Any) -> None:
        row_values = {key: "" for key in columns[3:]}
        row_values.update(values)
        row_values["row_type"] = row_type
        writer.writerow(common + [_csv_safe(row_values[key]) for key in columns[3:]])

    for point in data["nav"]:
        emit(
            "NAV",
            date=point["date"],
            cash=point["cash"],
            market_value=point["market_value"],
            equity=point["equity"],
            nav=point["nav"],
            detail_json=json.dumps({"benchmark": point["benchmark"]}, ensure_ascii=False),
        )
    for order in data["orders"]:
        emit(
            "ORDER",
            date=order["attempt_date"],
            security_id=order["security_id"],
            side=order["side"],
            status=order["status"],
            reason=order["reason"],
            quantity=order["filled_quantity"],
            price=order["price"],
            gross=order["gross"],
            commission=order["commission"],
            other_fees=order["other_fees"],
            detail_json=json.dumps(
                {"order_id": order["order_id"], "requested": order["requested_quantity"]},
                ensure_ascii=False,
            ),
        )
    for fill in data["fills"]:
        emit(
            "FILL",
            date=fill["date"],
            security_id=fill["security_id"],
            side=fill["side"],
            status="FILLED",
            quantity=fill["quantity"],
            price=fill["price"],
            gross=fill["gross"],
            commission=fill["commission"],
            other_fees=fill["other_fees"],
            detail_json=json.dumps({"order_id": fill["order_id"]}, ensure_ascii=False),
        )
    for fee in data["fees"]:
        emit(
            "FEE",
            date=fee.get("date"),
            security_id=fee.get("security_id"),
            side=fee.get("side"),
            status="CHARGED",
            gross=fee.get("gross"),
            commission=fee.get("commission"),
            other_fees=fee.get("other_fees"),
            detail_json=json.dumps({"version": fee.get("version")}, ensure_ascii=False),
        )
    for tax in data["dividend_taxes"]:
        emit(
            "DIVIDEND_TAX",
            date=tax.get("effective_date"),
            security_id=tax.get("security_id"),
            status="RECORDED",
            quantity=tax.get("quantity"),
            price=tax.get("rate"),
            gross=tax.get("gross"),
            other_fees=tax.get("tax"),
            detail_json=json.dumps(
                {key: tax.get(key) for key in ("rule_version", "lot_id", "pay_date")},
                ensure_ascii=False,
            ),
        )
    for position in data["final_positions"]:
        emit(
            "POSITION",
            date=position["date"],
            security_id=position["security_id"],
            status="OPEN",
            quantity=position["quantity"],
            price=position["cost_open"],
            market_value=position["market_value"],
            detail_json=json.dumps(
                {"unrealized_pnl": position["unrealized_pnl"], "r_open": position["r_open"]},
                ensure_ascii=False,
            ),
        )
    emit(
        "STATUS",
        status=data["status"],
        reason="; ".join(data["blockers"]),
        detail_json=json.dumps({"reconciliation_ok": data["reconciliation_ok"]}, ensure_ascii=False),
    )
    return buffer.getvalue()
