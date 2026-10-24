"""WP-FX01B Web presentation service.

F1/F3/F7 are thin presentation adapters over the Owner-accepted
``mishi_radar.result_contract`` payloads.  Rank, condition, diagnosis and
quality semantics are never recalculated here.  F6 stays on the accepted OD-2
cash kernel and uses fixed synthetic inputs only.
"""

from __future__ import annotations

import csv
import io
import json
from decimal import Decimal
from functools import lru_cache
from typing import Any, Iterable, Mapping
from urllib.parse import urlencode

from ..result_contract import (
    F1_CONTRACT,
    F3_CONTRACT,
    F7_CONTRACT,
    RESULT_CONTRACT_VERSION,
    SCENARIOS as CONTRACT_SCENARIOS,
    build_f1,
    build_f3,
    build_f7,
    build_fixture_snapshot,
    fixture_metadata as contract_fixture_metadata,
)
from ..strategy_core import compute_all, compute_diagnostics, style_view
from . import (
    CONTRACT_FIXTURE_VERSION,
    CONTRACT_MARKER,
    FIXTURE_MARKER,
    FIXTURE_VERSION,
)
from .backtest import run_fixture_backtest
from .fixtures import BACKTEST_SCENARIOS
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

# Small N values expose the contract's beyond_top_n exact ranks on the
# six-security fixture without changing any ranking calculation.
N_CHOICES: tuple[int, ...] = (1, 2, 3, 5, 10, 20, 30)

SECURITY_NAMES: Mapping[str, str] = {
    "SYN:000001": "合成样本一 · 非真实证券",
    "SYN:000002": "合成样本二 · 非真实证券",
    "SYN:000003": "合成样本三 · 非真实证券",
    "SYN:000004": "合成样本四 · 非真实证券",
    "SYN:000005": "合成样本五 · 非真实证券",
    "SYN:000006": "合成样本六 · 非真实证券",
}

INDUSTRY_NAMES: Mapping[str, str] = {
    "IND_ALPHA": "合成行业·阿尔法",
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
    "AVG_AMOUNT_REQUEST_FAILED": "20 日平均成交额请求失败",
    "FIXTURE_REQUEST_FAILED": "固定输入请求失败",
    "FIXTURE_INPUT_MISSING": "固定输入缺失",
    "PRICE_UNKNOWN": "价格输入未知",
    "FUND_FLOW_MISSING": "资金流输入缺失",
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
    "TRUE": "TRUE · 成立",
    "FALSE": "FALSE · 不成立",
    "UNKNOWN": "UNKNOWN · 未知",
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

ROW_IDENTITY_LABELS: Mapping[str, str] = {
    "FORMAL_CANDIDATE": "正式候选",
    "PREVIEW_CANDIDATE": "样本候选（非正式）",
    "UNKNOWN": "UNKNOWN",
    "FAILED": "FAILED",
    "NOT_CANDIDATE": "非候选 / 未触发",
}

RANK_SCOPE_LABELS: Mapping[str, str] = {
    "FIXTURE_BATCH_EXACT": "固定批次精确名次",
    "SAMPLE_ONLY": "局部样本序号（非正式）",
    "NONE": "无名次",
}

OUTCOME_LABELS: Mapping[str, tuple[str, str]] = {
    "CANDIDATES": ("CANDIDATES · 正常候选", "good"),
    "EMPTY": ("EMPTY · 完整空结果（成功）", "good"),
    "PREVIEW": ("PREVIEW · 池不完整（非正式）", "warn"),
    "UNKNOWN": ("UNKNOWN · 无法判定", "warn"),
    "FAILED": ("FAILED · 计算失败", "bad"),
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
def _kernel(scenario: str):
    snapshot = build_fixture_snapshot(scenario)
    return snapshot, compute_all(snapshot), compute_diagnostics(snapshot)


@lru_cache(maxsize=16)
def _f1_contract(scenario: str, strategy_id: str, top_n: int) -> dict[str, Any]:
    snapshot, results, _diagnostics = _kernel(scenario)
    return build_f1(
        results,
        snapshot,
        fixture=contract_fixture_metadata(scenario),
        strategy_id=strategy_id,
        top_n=top_n,
    )


@lru_cache(maxsize=32)
def _f3_contract(scenario: str, security_id: str, strategy_id: str) -> dict[str, Any]:
    snapshot, results, diagnostics = _kernel(scenario)
    return build_f3(
        diagnostics,
        results,
        snapshot,
        fixture=contract_fixture_metadata(scenario),
        security_id=security_id,
        strategy_id=strategy_id,
    )


@lru_cache(maxsize=8)
def _f7_contract(scenario: str) -> dict[str, Any]:
    snapshot, results, _diagnostics = _kernel(scenario)
    return build_f7(results, snapshot, fixture=contract_fixture_metadata(scenario))


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _display_number(value: Decimal | str | float | int | None, places: int = 2) -> str:
    if value is None:
        return "—"
    decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    quantum = Decimal(1).scaleb(-places)
    return format(decimal.quantize(quantum), "f")


def _display_ratio(value: Decimal | str | None) -> str:
    if value is None:
        return "—"
    decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    return f"{_display_number(decimal * Decimal(100), 2)}%"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return _decimal_text(value)
    if isinstance(value, tuple):
        return [_json_safe(item) for item in value]
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return value


def _condition_label(name: str) -> str:
    return CONDITION_LABELS.get(name, name.replace("_", " "))


def _reason_label(reason: str) -> str:
    if reason in REASON_LABELS:
        return REASON_LABELS[reason]
    if ":" in reason:
        head, _, tail = reason.partition(":")
        return f"{REASON_LABELS.get(head, head.replace('_', ' '))}（{tail.replace('_', ' ')}）"
    return reason.replace("_", " ")


def _condition_view(conditions: Mapping[str, str] | Iterable[Mapping[str, str]]) -> list[dict[str, str]]:
    if isinstance(conditions, Mapping):
        items = conditions.items()
    else:
        items = ((item["name"], item["status"]) for item in conditions)
    rows: list[dict[str, str]] = []
    for name, status in items:
        tone = "positive" if status == "TRUE" else "adverse" if status == "FALSE" else "unknown"
        rows.append(
            {
                "name": str(name),
                "label": _condition_label(str(name)),
                "status": str(status),
                "status_label": STATUS_LABELS.get(str(status), str(status)),
                "tone": tone,
            }
        )
    return rows


def _reason_view(reasons: Iterable[str]) -> list[dict[str, str]]:
    return [{"name": str(reason), "label": _reason_label(str(reason)), "tone": "adverse"} for reason in reasons]


def _outcome_view(outcome: Mapping[str, Any]) -> dict[str, Any]:
    kind = str(outcome["kind"])
    label, tone = OUTCOME_LABELS.get(kind, (kind, "neutral"))
    return {**outcome, "label": label, "tone": tone}


def _security_name(security_id: str) -> str:
    return SECURITY_NAMES.get(security_id, security_id)


def _industry_name(industry_id: str | None) -> str | None:
    if industry_id is None:
        return None
    return INDUSTRY_NAMES.get(industry_id, industry_id)


def _security_view(scenario: str, security_id: str) -> dict[str, Any]:
    snapshot, _results, _diagnostics = _kernel(scenario)
    security = snapshot.securities[security_id]
    return {
        "security_id": security_id,
        "security_name": _security_name(security_id),
        "industry_id": security.industry_id,
        "industry_name": _industry_name(security.industry_id),
        "exchange": security.exchange,
        "board": security.board,
        "is_st": security.is_st,
        "is_delisting": security.is_delisting,
        "suspended": security.suspended,
    }


def _price_view(scenario: str, security_id: str) -> dict[str, str | None]:
    snapshot, _results, _diagnostics = _kernel(scenario)
    bar = snapshot.bars.get(security_id, {}).get(snapshot.business_date)
    if bar is None:
        return {"price_date": snapshot.business_date, "price_close": None, "price_status": "MISSING"}
    return {
        "price_date": bar.date,
        "price_close": _display_number(bar.close.value, 2) if bar.close.usable else None,
        "price_status": bar.close.status.value,
    }


def _main_adverse(row: Mapping[str, Any]) -> str | None:
    for name, status in row.get("conditions", {}).items():
        if status == "FALSE":
            return _condition_label(name)
    reasons = list(row.get("reasons", ()))
    if reasons:
        return _reason_label(str(reasons[0]))
    return None


def _decorate_row(
    scenario: str,
    strategy_id: str,
    style_id: str,
    row: Mapping[str, Any],
    *,
    batch_id: str,
) -> dict[str, Any]:
    view = dict(row)
    security = _security_view(scenario, str(row["security_id"]))
    price = _price_view(scenario, str(row["security_id"]))
    conditions = _condition_view(row.get("conditions", {}))
    reasons = _reason_view(row.get("reasons", ()))
    positive = [item["label"] for item in conditions if item["tone"] == "positive"]
    adverse = [item["label"] for item in conditions if item["tone"] == "adverse"]
    unknown = [item["label"] for item in conditions if item["tone"] == "unknown"]
    formal = bool(row.get("formal_candidate"))
    preview = bool(row.get("preview_candidate"))
    main_adverse = _main_adverse(row)
    if formal and main_adverse is None:
        main_adverse = "没有已知 FALSE 条件；仍仅为固定规则展示"
    elif preview and main_adverse is None:
        main_adverse = "池不完整：样本序号不能视为正式名次"
    elif row.get("row_identity") == "UNKNOWN" and main_adverse is None:
        main_adverse = "输入 UNKNOWN；没有精确名次"
    elif row.get("row_identity") == "FAILED" and main_adverse is None:
        main_adverse = "计算失败；没有候选结果"
    query = urlencode(
        {
            "scenario": scenario,
            "strategy_id": strategy_id,
            "style": style_id,
            "security_id": row["security_id"],
            "batch_id": batch_id,
        }
    )
    view.update(
        {
            "security_name": security["security_name"],
            "industry_id": security["industry_id"],
            "industry_name": security["industry_name"],
            "strategy_label": STRATEGY_LABELS.get(strategy_id, strategy_id),
            "signal_state_label": STATE_LABELS.get(str(row.get("signal_state")), str(row.get("signal_state"))),
            "signal_status_label": STATUS_LABELS.get(str(row.get("signal_status")), str(row.get("signal_status"))),
            "qualification_label": ELIGIBILITY_LABELS.get(
                str(row.get("qualification_status")), str(row.get("qualification_status"))
            ),
            "row_identity_label": ROW_IDENTITY_LABELS.get(
                str(row.get("row_identity")), str(row.get("row_identity"))
            ),
            "rank_scope_label": RANK_SCOPE_LABELS.get(
                str(row.get("rank_scope")), str(row.get("rank_scope"))
            ),
            "formal_candidate": formal,
            "preview_candidate": preview,
            "conditions_view": conditions,
            "reasons_view": reasons,
            "positive_conditions": positive,
            "adverse_conditions": adverse,
            "unknown_conditions": unknown,
            "main_adverse": main_adverse,
            "price_date": price["price_date"],
            "price_close": price["price_close"],
            "price_status": price["price_status"],
            "batch_id": batch_id,
            "stock_url": f"/stock?{query}",
            "hit_tags": [
                {
                    **tag,
                    "strategy_label": STRATEGY_LABELS.get(str(tag["strategy_id"]), str(tag["strategy_id"])),
                    "rank_scope_label": RANK_SCOPE_LABELS.get(
                        str(tag.get("rank_scope")), str(tag.get("rank_scope"))
                    ),
                }
                for tag in row.get("hit_tags", ())
            ],
        }
    )
    return view


def _find_f1_row(payload: Mapping[str, Any], security_id: str) -> Mapping[str, Any]:
    for group in ("candidates", "beyond_top_n", "preview_candidates", "unknown_rows", "failed_rows"):
        for row in payload.get(group, ()):
            if row["security_id"] == security_id:
                return row
    raise DemoInputError(f"固定批次中没有证券 {security_id}")


def _row_from_f3(payload: Mapping[str, Any], strategy_id: str) -> Mapping[str, Any]:
    for row in payload.get("strategy_rows", ()):
        if row["strategy_id"] == strategy_id:
            return row
    raise DemoInputError(f"固定批次中没有策略 {strategy_id}")


def _strategy_catalog_view(scenario: str, contract: Mapping[str, Any], style_id: str) -> list[dict[str, Any]]:
    order = style_view(style_id).strategy_order
    catalog = contract["strategy_catalog"]
    rows: list[dict[str, Any]] = []
    for strategy_id in order:
        item = catalog[strategy_id]
        label, tone = OUTCOME_LABELS.get(item["outcome"], (item["outcome"], "neutral"))
        rows.append(
            {
                **item,
                "strategy_label": STRATEGY_LABELS.get(strategy_id, strategy_id),
                "outcome_label": label,
                "outcome_tone": tone,
                "active": strategy_id == contract["strategy"]["strategy_id"],
            }
        )
    return rows


def f1_data(
    *,
    scenario: str = "normal",
    strategy_id: str = "S01",
    style_id: str = "BALANCED/1",
    n: int = 10,
    query: str = "",
    refresh: bool = False,
) -> dict[str, Any]:
    if scenario not in CONTRACT_SCENARIOS:
        raise DemoInputError(f"未知 scenario: {scenario}")
    if strategy_id not in STRATEGY_LABELS:
        raise DemoInputError(f"未知 strategy: {strategy_id}")
    if style_id not in STYLE_LABELS:
        raise DemoInputError(f"未知 style: {style_id}")
    if n not in N_CHOICES:
        raise DemoInputError("显示 N 只能是 " + " / ".join(str(value) for value in N_CHOICES))
    contract = _f1_contract(scenario, strategy_id, n)
    batch_id = contract["batch"]["batch_id"]
    candidates = [
        _decorate_row(scenario, strategy_id, style_id, row, batch_id=batch_id)
        for row in contract["candidates"]
    ]
    beyond = [
        _decorate_row(scenario, strategy_id, style_id, row, batch_id=batch_id)
        for row in contract["beyond_top_n"]
    ]
    preview = [
        _decorate_row(scenario, strategy_id, style_id, row, batch_id=batch_id)
        for row in contract["preview_candidates"]
    ]
    unknown = [
        _decorate_row(scenario, strategy_id, style_id, row, batch_id=batch_id)
        for row in contract["unknown_rows"]
    ]
    failed = [
        _decorate_row(scenario, strategy_id, style_id, row, batch_id=batch_id)
        for row in contract["failed_rows"]
    ]
    query_text = query.strip().lower()
    if query_text:
        def matches(item: Mapping[str, Any]) -> bool:
            haystack = f"{item['security_id']} {item['security_name']} {item.get('industry_name') or ''}".lower()
            return query_text in haystack

        candidates = [item for item in candidates if matches(item)]
        beyond = [item for item in beyond if matches(item)]
        preview = [item for item in preview if matches(item)]
        unknown = [item for item in unknown if matches(item)]
        failed = [item for item in failed if matches(item)]
    outcome = _outcome_view(contract["outcome"])
    style = style_view(style_id)
    strategy_catalog = _strategy_catalog_view(scenario, contract, style_id)
    return {
        "contract": contract["schema"],
        "marker": contract["marker"],
        "display_marker": FIXTURE_MARKER,
        "fixture": contract["fixture"],
        "publication_identity": contract["publication_identity"],
        "batch": contract["batch"],
        "strategy": contract["strategy"],
        "strategy_label": STRATEGY_LABELS.get(strategy_id, strategy_id),
        "outcome": outcome,
        "counts": contract["counts"],
        "quality": contract["quality"],
        "strategy_catalog": strategy_catalog,
        "strategy_tabs": [
            {
                "strategy_id": item["strategy_id"],
                "label": item["strategy_label"],
                "active": item["active"],
                "outcome": item["outcome"],
                "outcome_label": item["outcome_label"],
                "outcome_tone": item["outcome_tone"],
                "url": "/?" + urlencode(
                    {"scenario": scenario, "strategy": item["strategy_id"], "style": style_id, "n": n, "q": query}
                ),
            }
            for item in strategy_catalog
        ],
        "style": {
            "style_id": style.style_id,
            "label": STYLE_LABELS[style.style_id],
            "order": list(style.strategy_order),
            "diagnostic_priority": list(style.diagnostic_priority),
            "note": style.note,
        },
        "style_tabs": [
            {
                "style_id": key,
                "label": label,
                "active": key == style_id,
                "url": "/?" + urlencode(
                    {"scenario": scenario, "strategy": strategy_id, "style": key, "n": n, "q": query}
                ),
            }
            for key, label in STYLE_LABELS.items()
        ],
        "scenario_tabs": [
            {
                "scenario": key,
                "label": meta["label"],
                "description": meta["description"],
                "active": key == scenario,
                "url": "/?" + urlencode(
                    {"scenario": key, "strategy": strategy_id, "style": style_id, "n": n, "q": query}
                ),
            }
            for key, meta in CONTRACT_SCENARIOS.items()
        ],
        "n_tabs": [
            {
                "n": value,
                "active": value == n,
                "url": "/?" + urlencode(
                    {"scenario": scenario, "strategy": strategy_id, "style": style_id, "n": value, "q": query}
                ),
            }
            for value in N_CHOICES
        ],
        "n": n,
        "query": query,
        "refresh": refresh,
        "refresh_note": "固定 FX01A FIXTURE 批次：刷新只重读同一输入，不抓取真实行情。",
        "refresh_url": "/?" + urlencode(
            {
                "scenario": scenario,
                "strategy": strategy_id,
                "style": style_id,
                "n": n,
                "q": query,
                "refresh": "1",
            }
        ),
        "candidates": candidates,
        "beyond_top_n": beyond,
        "preview_candidates": preview,
        "unknown_rows": unknown,
        "failed_rows": failed,
        "notes": list(contract.get("notes", ())),
        "empty_message": {
            "EMPTY": "完整空结果（成功）：可评分池完整，但该策略没有候选。",
            "UNKNOWN": "UNKNOWN：没有可评分池或全部输入不可判定，不产生名次。",
            "FAILED": "FAILED：输入请求失败，与空结果和 UNKNOWN 分开。",
            "PREVIEW": "PREVIEW：池不完整，下列样本序号不是正式名次。",
        }.get(outcome["kind"], ""),
    }


def _dimension_view(name: str, dimension: Mapping[str, Any]) -> dict[str, Any]:
    raw = dimension.get("raw_value")
    score = dimension.get("score")
    unit = dimension.get("unit")
    value_text = _display_number(raw, 4)
    if raw is not None and unit == "ratio":
        value_text = _display_ratio(raw)
    elif raw is not None and unit == "x":
        value_text = f"{_display_number(raw, 2)}x"
    elif raw is not None and unit == "1/CNY":
        value_text = f"{_display_number(Decimal(str(raw)) * Decimal(100000000), 4)} ×10⁻⁸ /元"
    score_width = None
    if score is not None:
        score_width = min(100.0, max(0.0, float(Decimal(str(score)))))
    extras: list[dict[str, str]] = []
    for key, value in dimension.get("extras", {}).items():
        extras.append(
            {
                "name": str(key),
                "label": METRIC_LABELS.get(str(key), str(key)),
                "value": _display_number(value, 4) if value is not None else "UNKNOWN",
            }
        )
    return {
        **dimension,
        "label": DIMENSION_LABELS.get(name, name),
        "value_text": value_text,
        "score_text": _display_number(score, 1) if score is not None else "UNKNOWN",
        "score_width": score_width,
        "status_label": VALUE_STATUS_LABELS.get(str(dimension.get("status")), str(dimension.get("status"))),
        "extras_view": extras,
    }


def stock_data(
    *,
    scenario: str,
    security_id: str,
    strategy_id: str,
    style_id: str,
    expected_batch_id: str,
) -> dict[str, Any]:
    if scenario not in CONTRACT_SCENARIOS:
        raise DemoInputError(f"未知 scenario: {scenario}")
    if strategy_id not in STRATEGY_LABELS:
        raise DemoInputError(f"未知 strategy: {strategy_id}")
    if style_id not in STYLE_LABELS:
        raise DemoInputError(f"未知 style: {style_id}")
    snapshot, _results, _diagnostics = _kernel(scenario)
    if security_id not in snapshot.securities:
        raise DemoInputError(f"未知证券: {security_id}")
    f1 = _f1_contract(scenario, strategy_id, 10)
    actual_batch = f1["batch"]["batch_id"]
    if expected_batch_id != actual_batch:
        raise BatchMismatch(
            f"批次不一致：链接批次 {expected_batch_id} / 当前固定批次 {actual_batch}"
        )
    f3 = _f3_contract(scenario, security_id, strategy_id)
    row = _row_from_f3(f3, strategy_id)
    batch_id = actual_batch
    summary = _decorate_row(scenario, strategy_id, style_id, row, batch_id=batch_id)
    dimension_map = {item["name"]: item for item in f3["dimensions"]}
    order = STYLE_DIMENSION_ORDER[style_id]
    ordered_names = [name for name in order if name in dimension_map]
    ordered_names.extend(name for name in dimension_map if name not in ordered_names)
    dimensions = [_dimension_view(name, dimension_map[name]) for name in ordered_names]
    conditions = _condition_view(f3["conditions"])
    reasons = _reason_view(f3["reasons"])
    strategy_rows = [
        _decorate_row(scenario, str(item["strategy_id"]), style_id, item, batch_id=batch_id)
        for item in f3["strategy_rows"]
    ]
    divergence = {
        **f3["divergence"],
        "hit_strategy_labels": [
            STRATEGY_LABELS.get(strategy_id, strategy_id)
            for strategy_id in f3["divergence"]["hit_strategies"]
        ],
        "non_hit_strategy_labels": [
            STRATEGY_LABELS.get(strategy_id, strategy_id)
            for strategy_id in f3["divergence"]["non_hit_strategies"]
        ],
        "unknown_strategy_labels": [
            STRATEGY_LABELS.get(strategy_id, strategy_id)
            for strategy_id in f3["divergence"]["unknown_strategies"]
        ],
        "failed_strategy_labels": [
            STRATEGY_LABELS.get(strategy_id, strategy_id)
            for strategy_id in f3["divergence"]["failed_strategies"]
        ],
    }
    security = _security_view(scenario, security_id)
    query = urlencode(
        {"scenario": scenario, "strategy_id": strategy_id, "style": style_id, "security_id": security_id}
    )
    return {
        "contract": f3["schema"],
        "marker": f3["marker"],
        "display_marker": FIXTURE_MARKER,
        "fixture": f3["fixture"],
        "publication_identity": f3["publication_identity"],
        "batch": f1["batch"],
        "f1_outcome": _outcome_view(f1["outcome"]),
        "security": security,
        "security_id": security_id,
        "security_name": security["security_name"],
        "industry_name": security["industry_name"],
        "strategy_context": f3["strategy_context"],
        "summary": summary,
        "conditions": conditions,
        "reasons": reasons,
        "positive_conditions": [item["label"] for item in conditions if item["tone"] == "positive"],
        "adverse_conditions": [item["label"] for item in conditions if item["tone"] == "adverse"],
        "unknown_conditions": [item["label"] for item in conditions if item["tone"] == "unknown"],
        "dimensions": dimensions,
        "available_dimensions": f3["dimension_counts"]["value"],
        "dimension_counts": f3["dimension_counts"],
        "missing_dimensions": [
            DIMENSION_LABELS.get(name, name) for name in f3["missing_dimensions"]
        ],
        "not_applicable_dimensions": [
            DIMENSION_LABELS.get(name, name) for name in f3["not_applicable_dimensions"]
        ],
        "diagnostic_notes": list(f3.get("diagnostic_notes", ())),
        "strategy_rows": strategy_rows,
        "divergence": divergence,
        "score_policy": f3["score_policy"],
        "time": f3["time"],
        "style": {
            "style_id": style_id,
            "label": STYLE_LABELS[style_id],
            "note": style_view(style_id).note,
        },
        "backtest_url": "/backtest",
        "board_url": "/?" + urlencode({"scenario": scenario, "strategy": strategy_id, "style": style_id}),
        "watch_url": f"/watch?{query}",
    }


def _snapshot_payload(scenario: str, security_id: str, strategy_id: str, style_id: str) -> dict[str, Any]:
    detail = stock_data(
        scenario=scenario,
        security_id=security_id,
        strategy_id=strategy_id,
        style_id=style_id,
        expected_batch_id=_f1_contract(scenario, strategy_id, 10)["batch"]["batch_id"],
    )
    summary = detail["summary"]
    dimensions = {
        item["name"]: {
            "label": item["label"],
            "value_text": item["value_text"],
            "score_text": item["score_text"],
            "status": item["status"],
            "status_label": item["status_label"],
            "pool_size": item["pool_size"],
            "pool_complete": item["pool_complete"],
            "missing": item["missing"],
        }
        for item in detail["dimensions"]
    }
    return {
        "contract_version": RESULT_CONTRACT_VERSION,
        "f1_contract": F1_CONTRACT,
        "f3_contract": F3_CONTRACT,
        "fixture_marker": CONTRACT_MARKER,
        "fixture_version": CONTRACT_FIXTURE_VERSION,
        "scenario": scenario,
        "batch_id": detail["batch"]["batch_id"],
        "security_id": security_id,
        "security_name": detail["security_name"],
        "industry_id": detail["security"]["industry_id"],
        "industry_name": detail["industry_name"],
        "strategy_id": strategy_id,
        "strategy_label": STRATEGY_LABELS[strategy_id],
        "signal_date": detail["strategy_context"]["signal_date"],
        "config_id": detail["strategy_context"]["config_id"],
        "config_version": detail["strategy_context"]["config_version"],
        "input_version": detail["strategy_context"]["input_version"],
        "available_at": detail["strategy_context"]["available_at"],
        "available_at_kind": detail["strategy_context"]["available_at_kind"],
        "row_identity": summary["row_identity"],
        "row_identity_label": summary["row_identity_label"],
        "rank_scope": summary["rank_scope"],
        "rank_scope_label": summary["rank_scope_label"],
        "formal_candidate": summary["formal_candidate"],
        "preview_candidate": summary["preview_candidate"],
        "candidate_rank": summary["candidate_rank"],
        "sample_candidate_rank": summary["sample_candidate_rank"],
        "pool_rank": summary["pool_rank"],
        "sample_pool_rank": summary["sample_pool_rank"],
        "pool_size": summary["pool_size"],
        "pool_complete": summary["pool_complete"],
        "signal_state": summary["signal_state"],
        "signal_state_label": summary["signal_state_label"],
        "signal_status": summary["signal_status"],
        "signal_status_label": summary["signal_status_label"],
        "qualification_status": summary["qualification_status"],
        "qualification_label": summary["qualification_label"],
        "main_adverse": summary["main_adverse"],
        "positive_conditions": summary["positive_conditions"],
        "adverse_conditions": summary["adverse_conditions"],
        "dimensions": dimensions,
        "dimension_counts": detail["dimension_counts"],
        "available_dimensions": detail["available_dimensions"],
        "price_date": summary["price_date"],
        "price_close": summary["price_close"],
        "price_status": summary["price_status"],
        "publication_identity": detail["publication_identity"],
        "outcome": detail["f1_outcome"],
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
    if scenario not in CONTRACT_SCENARIOS or strategy_id not in STRATEGY_LABELS:
        raise DemoInputError("未知固定场景或策略")
    actual = _f1_contract(scenario, strategy_id, 10)["batch"]["batch_id"]
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
    if scenario not in CONTRACT_SCENARIOS:
        return {"scenario": scenario, "status": "UNKNOWN", "status_label": "未知场景"}
    snapshot, _results, _diagnostics = _kernel(scenario)
    if entry.security_id not in snapshot.securities:
        return {
            "scenario": scenario,
            "status": "NOT_IN_BATCH",
            "status_label": "当前批次无该证券",
        }
    try:
        f1 = _f1_contract(scenario, entry.strategy_id, 10)
        f3 = _f3_contract(scenario, entry.security_id, entry.strategy_id)
        row = _row_from_f3(f3, entry.strategy_id)
    except (DemoInputError, KeyError):
        return {"scenario": scenario, "status": "UNKNOWN", "status_label": "当前批次无法计算"}
    summary = _decorate_row(scenario, entry.strategy_id, entry.style, row, batch_id=f1["batch"]["batch_id"])
    identity = summary["row_identity"]
    if identity == "FORMAL_CANDIDATE":
        status = "FORMAL_CANDIDATE"
        label = f"FIXTURE 正式候选 #{summary['candidate_rank']} · {summary['rank_scope_label']}"
    elif identity == "PREVIEW_CANDIDATE":
        status = "PREVIEW"
        label = f"PREVIEW 样本 #{summary['sample_candidate_rank']} · {summary['rank_scope_label']}"
    elif identity == "UNKNOWN":
        status = "UNKNOWN"
        label = f"UNKNOWN · {summary['main_adverse'] or '输入不可判定'}"
    elif identity == "FAILED":
        status = "FAILED"
        label = f"FAILED · {summary['main_adverse'] or '计算失败'}"
    else:
        status = "NOT_TRIGGERED"
        label = "未触发 / 非当前候选"
    return {
        "scenario": scenario,
        "status": status,
        "status_label": label,
        "batch_id": f1["batch"]["batch_id"],
        "outcome": _outcome_view(f1["outcome"]),
        "pool_complete": summary["pool_complete"],
        "row_identity": summary["row_identity"],
        "row_identity_label": summary["row_identity_label"],
        "rank_scope": summary["rank_scope"],
        "rank_scope_label": summary["rank_scope_label"],
        "candidate_rank": summary["candidate_rank"],
        "sample_candidate_rank": summary["sample_candidate_rank"],
        "price_date": summary["price_date"],
        "price_close": summary["price_close"],
        "main_adverse": summary["main_adverse"],
        "signal_state": summary["signal_state"],
    }


def watch_data(store: WatchStore, *, scenario: str = "normal") -> dict[str, Any]:
    if scenario not in CONTRACT_SCENARIOS:
        raise DemoInputError(f"未知 scenario: {scenario}")
    entries = store.entries()
    active = [entry for entry in entries if entry.status == "ACTIVE"]
    removed = [entry for entry in entries if entry.status == "REMOVED"]

    def present(entry: WatchEntry) -> dict[str, Any]:
        payload = entry.to_dict()
        payload["current"] = _current_watch_state(entry, scenario)
        payload["snapshot_changed"] = False
        payload["snapshot_note"] = "首次关注快照保持不变；当前对照仅用于另一次固定批次的状态变化。"
        return payload

    return {
        "contract_version": RESULT_CONTRACT_VERSION,
        "marker": CONTRACT_MARKER,
        "display_marker": FIXTURE_MARKER,
        "user": DEMO_USER,
        "scenario": scenario,
        "scenario_tabs": [
            {
                "scenario": key,
                "label": meta["label"],
                "active": key == scenario,
                "url": "/watch?" + urlencode({"scenario": key}),
            }
            for key, meta in CONTRACT_SCENARIOS.items()
        ],
        "active": [present(entry) for entry in reversed(active)],
        "removed": [present(entry) for entry in reversed(removed)],
        "active_count": len(active),
        "removed_count": len(removed),
    }


def _backtest_metric_rows(metrics: Mapping[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for key, value in metrics.items():
        label = BACKTEST_METRIC_LABELS.get(key, key)
        if value is None:
            display = "N/A"
        elif key in BACKTEST_PERCENT_METRICS:
            display = _display_ratio(value)
        elif key in BACKTEST_COUNT_METRICS:
            display = str(int(Decimal(str(value))))
        elif key in {"sharpe", "profit_loss_ratio"}:
            display = _display_number(value, 3)
        else:
            display = _display_number(value, 4)
        rows.append({"key": key, "label": label, "value": display})
    return rows


def backtest_data(scenario: str) -> dict[str, Any]:
    if scenario not in BACKTEST_SCENARIOS:
        raise DemoInputError(f"未知回测场景: {scenario}")
    result, meta = run_fixture_backtest(scenario)
    failed_orders = [order for order in result.orders if order.status in {"UNFILLED", "BLOCKED_UNKNOWN", "EXPIRED"}]
    recon_ok = all(item.get("cash_ok") and item.get("equity_ok") for item in result.reconciliation)
    metric_rows = _backtest_metric_rows(result.metrics)
    return {
        "fixture": {
            "marker": FIXTURE_MARKER,
            "fixture_version": FIXTURE_VERSION,
            "scenario": scenario,
            "scenario_label": BACKTEST_SCENARIOS[scenario]["label"],
            "scenario_description": BACKTEST_SCENARIOS[scenario]["description"],
            "backtest_scenario": scenario,
            "backtest_label": BACKTEST_SCENARIOS[scenario]["label"],
            "backtest_description": BACKTEST_SCENARIOS[scenario]["description"],
            "source": "FIXTURE",
            "synthetic": True,
            "real_market_data": False,
            "network_used": False,
            "business_date": "2026-10-16",
            "input_version": FIXTURE_VERSION,
            "contract_version": RESULT_CONTRACT_VERSION,
            "contract_relation": "F6_IS_INDEPENDENT_OD2_SYNTHETIC_SCENARIO",
        },
        "meta": meta,
        "status": result.status,
        "succeeded": result.succeeded,
        "blockers": list(result.blockers),
        "warnings": list(result.warnings),
        "synthetic": result.synthetic,
        "initial_cash": _decimal_text(result.initial_cash),
        "contract_independent": True,
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
                "position_ratio_text": "—" if point.position_ratio is None else _display_ratio(point.position_ratio),
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
        "fees": _json_safe(result.fee_entries),
        "dividend_taxes": _json_safe(result.dividend_tax_entries),
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
                "r_open_text": "—" if position.r_open is None else _display_ratio(position.r_open),
                "holding_days": position.holding_days,
                "industry_id": position.industry_id,
                "mark_status": position.mark_status,
            }
            for position in result.final_positions
        ],
        "reconciliation": _json_safe(result.reconciliation),
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
        "metrics": _json_safe(result.metrics),
        "metric_rows": metric_rows,
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
    for key, meta in CONTRACT_SCENARIOS.items():
        f7 = _f7_contract(key)
        f1 = _f1_contract(key, "S01", 10)
        rows: list[dict[str, Any]] = []
        for strategy_id, item in f7["coverage"]["strategies"].items():
            label, tone = OUTCOME_LABELS.get(item["outcome"], (item["outcome"], "neutral"))
            rows.append(
                {
                    **item,
                    "strategy_label": STRATEGY_LABELS.get(strategy_id, strategy_id),
                    "outcome_label": label,
                    "outcome_tone": tone,
                }
            )
        scenarios.append(
            {
                "scenario": key,
                "label": meta["label"],
                "description": meta["description"],
                "outcome": _outcome_view(f1["outcome"]),
                "counts": f1["counts"],
                "f7_contract": f7["schema"],
                "fixture": f7["fixture"],
                "publication_identity": f7["publication_identity"],
                "coverage": f7["coverage"],
                "quality": f7["quality"],
                "availability": f7["availability"],
                "gates": f7["gates"],
                "strategy_rows": rows,
            }
        )
    return {
        "accepted_contract": {
            "contract_version": RESULT_CONTRACT_VERSION,
            "contracts": [F1_CONTRACT, F3_CONTRACT, F7_CONTRACT],
            "owner_acceptance": "PASS_WITH_LIMITATION",
            "fx01a_fixture_version": CONTRACT_FIXTURE_VERSION,
        },
        "marker": CONTRACT_MARKER,
        "display_marker": FIXTURE_MARKER,
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
            {"name": "F1/F3/F7 结果合同", "status": "FX01A ACCEPTED / REUSED", "detail": RESULT_CONTRACT_VERSION},
            {"name": "真实行情 / 真实扫描", "status": "NOT_USED / GATED", "detail": "固定 Fixture，无网络调用。"},
            {"name": "OD-1 规则内核", "status": "REUSED", "detail": "mishi_radar.strategy_core"},
            {"name": "OD-2 现金内核", "status": "REUSED", "detail": "mishi_radar.cash_backtest.run_backtest"},
            {"name": "F4 市场/行业/资金", "status": "GATED / NOT_IMPLEMENTED", "detail": "本轮不提供空壳页面。"},
            {"name": "H1 观察仓", "status": "FIXTURE SLICE / OWNER REVIEW PENDING", "detail": "固定 Fixture 静态观察仓；完整 H1、真实持仓与实时价格未验收。"},
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
            "contract_version",
            "fixture_version",
            "scenario",
            "batch_id",
            "strategy_id",
            "outcome",
            "row_identity",
            "rank_scope",
            "formal_candidate",
            "candidate_rank",
            "sample_candidate_rank",
            "pool_rank",
            "sample_pool_rank",
            "pool_size",
            "pool_complete",
            "security_id",
            "security_name",
            "signal_state",
            "signal_status",
            "reasons",
            "main_adverse",
            "actual_published",
            "history_rank",
            "row_type",
        ]
    )
    rows: Iterable[Mapping[str, Any]] = (
        list(data["candidates"])
        + list(data["beyond_top_n"])
        + list(data["preview_candidates"])
        + list(data["unknown_rows"])
        + list(data["failed_rows"])
    )
    for item in rows:
        writer.writerow(
            [
                _csv_safe(FIXTURE_MARKER),
                _csv_safe(data["contract"]["contract_version"]),
                _csv_safe(data["fixture"]["fixture_version"]),
                _csv_safe(data["fixture"]["scenario"]),
                _csv_safe(data["batch"]["batch_id"]),
                _csv_safe(item["strategy_id"]),
                _csv_safe(data["outcome"]["kind"]),
                _csv_safe(item["row_identity"]),
                _csv_safe(item["rank_scope"]),
                _csv_safe(item["formal_candidate"]),
                _csv_safe(item["candidate_rank"]),
                _csv_safe(item["sample_candidate_rank"]),
                _csv_safe(item["pool_rank"]),
                _csv_safe(item["sample_pool_rank"]),
                _csv_safe(item["pool_size"]),
                _csv_safe(item["pool_complete"]),
                _csv_safe(item["security_id"]),
                _csv_safe(item["security_name"]),
                _csv_safe(item["signal_state"]),
                _csv_safe(item["signal_status"]),
                _csv_safe("; ".join(reason["label"] for reason in item["reasons_view"])),
                _csv_safe(item["main_adverse"]),
                _csv_safe(item["actual_published"]),
                _csv_safe(item["history_rank"]),
                "RESULT",
            ]
        )
    if not rows:
        empty = data["outcome"]["kind"] == "EMPTY"
        writer.writerow(
            [
                _csv_safe(FIXTURE_MARKER),
                _csv_safe(data["contract"]["contract_version"]),
                _csv_safe(data["fixture"]["fixture_version"]),
                _csv_safe(data["fixture"]["scenario"]),
                _csv_safe(data["batch"]["batch_id"]),
                _csv_safe(data["strategy"]["strategy_id"]),
                _csv_safe(data["outcome"]["kind"]),
                "EMPTY" if empty else "NO_EXPORTED_ROWS",
                "NONE",
                _csv_safe(False),
                "",
                "",
                "",
                "",
                _csv_safe(data["counts"]["pool_size"]),
                _csv_safe(data["batch"]["pool_complete"]),
                "",
                "",
                "",
                "",
                "EMPTY_IS_SUCCESS" if empty else "NO_RESULT_ROWS_AFTER_FILTER",
                "NO_CANDIDATE_ROWS",
                _csv_safe(False),
                "",
                "STATUS",
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
