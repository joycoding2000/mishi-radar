"""H1 static observation presentation over the accepted fixed fixture.

The service reads raw synthetic closes from the same FX01A fixture used by
F1/F3/F7, keeps H1 records in an independent local store, and reuses the
accepted OD-1 S01 exit decision only when the holding context and current
end-of-day inputs are complete.  It never treats a static observation as a
trade, never auto-ends a record and never calls a network source.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from zoneinfo import ZoneInfo

from ..result_contract import (
    BUSINESS_DATE,
    RESULT_CONTRACT_VERSION,
    SCENARIOS,
    fixture_metadata,
)
from ..result_contract import (
    FIXTURE_MARKER as CONTRACT_FIXTURE_MARKER,
)
from ..strategy_core import S01_DEFAULT_CONFIG_VERSION, evaluate_exit
from ..strategy_core.model import ExitContext
from ..time_contract import TimeContractError, validate_local_date
from . import FIXTURE_MARKER
from . import RESULT_CONTRACT_VERSION as DEMO_CONTRACT_VERSION
from .h1 import DEMO_USER, H1Observation, H1StateError, H1Store, H1Version
from .service import (
    SECURITY_NAMES,
    STRATEGY_LABELS,
    DemoInputError,
    _decimal_text,
    _display_number,
    _display_ratio,
    _kernel,
)

LOCAL_ZONE = ZoneInfo("Asia/Shanghai")
SECURITY_ORDER: tuple[str, ...] = tuple(SECURITY_NAMES)

PRICE_STATUS_LABELS: Mapping[str, str] = {
    "CURRENT": "当前业务日原始价",
    "STALE": "旧价（非当前业务日）",
    "MISSING": "无可用价格",
}

PRICE_NOTES: Mapping[str, str] = {
    "CURRENT": "当前固定 Fixture 业务日的合成原始价。",
    "STALE": "最后可用原始价不是当前业务日收盘；已标记旧价日期，浮盈基于旧价。",
    "MISSING": "固定 Fixture 中没有可用原始价；市值、浮盈及浮盈率均为 UNKNOWN。",
}

VALUATION_STATUS_LABELS: Mapping[str, str] = {
    "VALUED": "已按原始参考价计算",
    "OLD_PRICE": "按旧价计算（非当前）",
    "UNKNOWN": "UNKNOWN · 无法计算",
}

EXIT_STATUS_LABELS: Mapping[str, str] = {
    "TRUE": "TRUE · 规则提示退出",
    "FALSE": "FALSE · 未触发退出",
    "UNKNOWN": "UNKNOWN · 暂不可判断",
    "NOT_LINKED": "未关联 S01 规则",
}

EXIT_TONES: Mapping[str, str] = {
    "TRUE": "warn",
    "FALSE": "good",
    "UNKNOWN": "warn",
    "NOT_LINKED": "neutral",
}

EXIT_REASON_LABELS: Mapping[str, str] = {
    "STRATEGY_EXIT:S01_BELOW_MA20": "收盘价低于 MA20（S01 默认退出规则）",
    "MAX_HOLDING": "达到 S01 默认最长持有 20 个交易日",
    "PRICE_UNKNOWN": "必要价格输入 UNKNOWN",
    "S01_MA20_UNKNOWN": "MA20 输入 UNKNOWN",
    "COMMON_STOP_UNKNOWN": "通用止损输入 UNKNOWN",
    "BASIS_DATE_AFTER_BUSINESS_DATE": "成本基准日期晚于固定业务日",
    "FIXTURE_CALENDAR_INCOMPLETE": "固定 Fixture 日历不足以计算持有交易日",
    "NO_TRADING_DAY": "基准日至业务日之间没有合格交易日",
    "SECURITY_UNKNOWN": "证券不在固定 Fixture 中",
    "STRATEGY_NOT_SUPPORTED": "关联规则不是默认 S01",
}

LONG_LIMITATIONS: tuple[str, ...] = (
    "仅固定演示用户 fixture-user 与合成 Fixture 数据；不是券商持仓、成交账本、账户权益或实时价格。",
    "静态市值、浮盈和浮盈率未计交易费用、分红、送转及其他公司行为调整；如有重大公司行为或用户更正，数据/成本需本人核对。",
    "静态浮盈不能替代 OD-2 的未平仓经济损益止损口径；本页只复用 S01 策略退出条件与最长持有，不含 OD-2 通用止损。",
    "未入机会榜、行情缺失或规则 UNKNOWN 都不等于退出，也不会自动结束观察记录。",
)


def _local_today() -> date:
    return datetime.now(LOCAL_ZONE).date()


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _rate(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)


def _decimal_or_none(value: str | None) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _quantity_text(value: Decimal) -> str:
    text = format(value.normalize(), "f")
    return "0" if text in {"", "-0"} else text


def _money_text(value: Decimal | None) -> str:
    return "UNKNOWN" if value is None else _display_number(value, 2)


def compute_valuation(
    quantity: Decimal,
    average_cost: Decimal,
    reference_price: Decimal | None,
    *,
    price_status: str = "CURRENT",
) -> dict[str, Any]:
    """Compute q×P, q×c, q×(P-c) and P/c-1 without fees or corporate actions."""

    cost_value = _money(quantity * average_cost)
    if reference_price is None:
        return {
            "status": "UNKNOWN",
            "market_value": None,
            "cost_value": cost_value,
            "unrealized_pnl": None,
            "unrealized_pnl_rate": None,
        }
    market_value = _money(quantity * reference_price)
    unrealized_pnl = _money(quantity * (reference_price - average_cost))
    unrealized_pnl_rate = _rate(reference_price / average_cost - 1)
    return {
        "status": "OLD_PRICE" if price_status == "STALE" else "VALUED",
        "market_value": market_value,
        "cost_value": cost_value,
        "unrealized_pnl": unrealized_pnl,
        "unrealized_pnl_rate": unrealized_pnl_rate,
    }


def _fixture_quote(snapshot: Any, security_id: str) -> dict[str, Any]:
    bars = snapshot.bars.get(security_id, {})
    for day in reversed(snapshot.calendar):
        if day > snapshot.business_date:
            continue
        bar = bars.get(day)
        if bar is None:
            continue
        close = bar.close
        if close.usable and close.value is not None:
            return {
                "price": close.value,
                "date": day,
                "status": "CURRENT" if day == snapshot.business_date else "STALE",
            }
    return {"price": None, "date": None, "status": "MISSING"}


def _holding_days(
    calendar: tuple[str, ...],
    cost_basis_date: str,
    business_date: str,
) -> tuple[int | None, str | None]:
    if cost_basis_date > business_date:
        return None, "BASIS_DATE_AFTER_BUSINESS_DATE"
    if not calendar or cost_basis_date < calendar[0]:
        return None, "FIXTURE_CALENDAR_INCOMPLETE"
    days = [day for day in calendar if cost_basis_date <= day <= business_date]
    if not days:
        return None, "NO_TRADING_DAY"
    return len(days), None


def _exit_state(
    version: H1Version,
    snapshot: Any,
    holding_days: int | None,
    holding_reason: str | None,
) -> dict[str, Any]:
    if version.strategy_id is None:
        return {"status": "NOT_LINKED", "reasons": [], "primary_reason": None, "rule_id": None}
    if version.strategy_id != "S01":
        return {
            "status": "UNKNOWN",
            "reasons": ["STRATEGY_NOT_SUPPORTED"],
            "primary_reason": "STRATEGY_NOT_SUPPORTED",
            "rule_id": S01_DEFAULT_CONFIG_VERSION,
        }
    if version.security_id not in snapshot.securities:
        return {
            "status": "UNKNOWN",
            "reasons": ["SECURITY_UNKNOWN"],
            "primary_reason": "SECURITY_UNKNOWN",
            "rule_id": S01_DEFAULT_CONFIG_VERSION,
        }
    if holding_days is None:
        reason = holding_reason or "FIXTURE_CALENDAR_INCOMPLETE"
        return {
            "status": "UNKNOWN",
            "reasons": [reason],
            "primary_reason": reason,
            "rule_id": S01_DEFAULT_CONFIG_VERSION,
        }
    decision = evaluate_exit(
        snapshot,
        "S01",
        version.security_id,
        ExitContext(holding_days=holding_days),
    )
    return {
        "status": decision.status.value,
        "reasons": list(decision.reasons),
        "primary_reason": decision.primary_reason,
        "rule_id": S01_DEFAULT_CONFIG_VERSION,
    }


def _raw_version(observation: H1Observation, version: H1Version) -> dict[str, Any]:
    snapshot, _results, _diagnostics = _kernel(observation.scenario)
    meta = fixture_metadata(observation.scenario)
    quote = _fixture_quote(snapshot, version.security_id)
    quantity = Decimal(version.quantity)
    average_cost = Decimal(version.average_cost)
    valuation = compute_valuation(
        quantity,
        average_cost,
        quote["price"],
        price_status=quote["status"],
    )
    holding_days, holding_reason = _holding_days(
        snapshot.calendar,
        version.cost_basis_date,
        snapshot.business_date,
    )
    exit_state = _exit_state(version, snapshot, holding_days, holding_reason)
    return {
        "version": version.version,
        "security_id": version.security_id,
        "security_name": SECURITY_NAMES.get(version.security_id, version.security_id),
        "scenario": observation.scenario,
        "scenario_label": SCENARIOS.get(observation.scenario, {}).get("label", observation.scenario),
        "strategy_id": version.strategy_id,
        "strategy_label": (
            STRATEGY_LABELS.get(version.strategy_id, version.strategy_id)
            if version.strategy_id
            else "未关联规则"
        ),
        "quantity": _decimal_text(quantity),
        "average_cost": _decimal_text(average_cost),
        "cost_basis_date": version.cost_basis_date,
        "note": version.note,
        "created_at": version.created_at,
        "reference_price": _decimal_text(quote["price"]),
        "reference_price_date": quote["date"],
        "price_status": quote["status"],
        "valuation_status": valuation["status"],
        "market_value": _decimal_text(valuation["market_value"]),
        "cost_value": _decimal_text(valuation["cost_value"]),
        "unrealized_pnl": _decimal_text(valuation["unrealized_pnl"]),
        "unrealized_pnl_rate": _decimal_text(valuation["unrealized_pnl_rate"]),
        "holding_days": holding_days,
        "holding_days_status": "KNOWN" if holding_days is not None else "UNKNOWN",
        "holding_days_reason": holding_reason,
        "rule_status": exit_state["status"],
        "rule_reasons": list(exit_state["reasons"]),
        "rule_primary_reason": exit_state["primary_reason"],
        "rule_id": exit_state["rule_id"],
        "fixture_id": meta["fixture_id"],
        "fixture_version": meta["fixture_version"],
        "business_date": meta["business_date"],
        "price_basis": meta["price_basis"],
        "contract_version": RESULT_CONTRACT_VERSION,
        "marker": CONTRACT_FIXTURE_MARKER,
    }


def _display_view(raw: Mapping[str, Any]) -> dict[str, Any]:
    quantity = Decimal(str(raw["quantity"]))
    average_cost = Decimal(str(raw["average_cost"]))
    reference_price = _decimal_or_none(raw.get("reference_price"))
    market_value = _decimal_or_none(raw.get("market_value"))
    cost_value = _decimal_or_none(raw.get("cost_value"))
    unrealized_pnl = _decimal_or_none(raw.get("unrealized_pnl"))
    unrealized_pnl_rate = _decimal_or_none(raw.get("unrealized_pnl_rate"))
    price_status = str(raw.get("price_status", "MISSING"))
    valuation_status = str(raw.get("valuation_status", "UNKNOWN"))
    holding_days = raw.get("holding_days")
    holding_reason = raw.get("holding_days_reason")
    exit_status = str(raw.get("rule_status", "UNKNOWN"))
    reasons = list(raw.get("rule_reasons", ()))
    reason_labels = [
        {"code": str(reason), "label": EXIT_REASON_LABELS.get(str(reason), str(reason))}
        for reason in reasons
    ]
    if raw.get("rule_primary_reason"):
        primary_label = EXIT_REASON_LABELS.get(
            str(raw["rule_primary_reason"]), str(raw["rule_primary_reason"])
        )
    else:
        primary_label = "—"
    if holding_days is None:
        holding_text = "UNKNOWN（{}）".format(
            EXIT_REASON_LABELS.get(str(holding_reason), str(holding_reason or "未知原因"))
        )
    else:
        holding_text = f"{holding_days} 个交易日"
    return {
        **raw,
        "quantity_text": _quantity_text(quantity),
        "average_cost_text": _display_number(average_cost, 2),
        "reference_price_text": "UNKNOWN" if reference_price is None else _display_number(reference_price, 2),
        "price_status_label": PRICE_STATUS_LABELS.get(price_status, price_status),
        "price_is_stale": price_status == "STALE",
        "price_is_missing": price_status == "MISSING",
        "price_note": PRICE_NOTES.get(price_status, ""),
        "valuation_status_label": VALUATION_STATUS_LABELS.get(valuation_status, valuation_status),
        "market_value_text": _money_text(market_value),
        "cost_value_text": _money_text(cost_value),
        "unrealized_pnl_text": _money_text(unrealized_pnl),
        "unrealized_pnl_rate_text": (
            "UNKNOWN" if unrealized_pnl_rate is None else _display_ratio(unrealized_pnl_rate)
        ),
        "holding_days_text": holding_text,
        "exit_status_label": EXIT_STATUS_LABELS.get(exit_status, exit_status),
        "exit_tone": EXIT_TONES.get(exit_status, "neutral"),
        "exit_reason_labels": reason_labels,
        "exit_reason_text": "；".join(item["label"] for item in reason_labels) or "—",
        "primary_reason_label": primary_label,
        "rule_label": raw.get("rule_id") or "未关联 S01 规则",
        "needs_review": int(raw.get("version", 1)) > 1,
        "review_note": "已更正：数据/成本需本人核对；旧版本保留。",
        "auto_end": False,
        "exit_note": "仅复用 S01 策略退出条件与最长持有，不含 OD-2 通用止损；UNKNOWN、未入榜或行情缺失不等于退出，也不会自动结束记录。",
        "valuation_note": {
            "VALUED": "按当前固定业务日合成原始价计算；未计费用、分红、送转及其他公司行为调整；如有重大公司行为，数据/成本需本人核对。",
            "OLD_PRICE": "按最后可用原始价（旧价）计算；已标记日期，浮盈基于旧价；未计费用、分红、送转及其他公司行为调整。",
            "UNKNOWN": "无可用原始参考价，市值、浮盈及浮盈率均为 UNKNOWN；参考成本仍为数量×平均成本。",
        }.get(valuation_status, ""),
    }


def _version_view(version: H1Version) -> dict[str, Any]:
    return {
        "version": version.version,
        "security_id": version.security_id,
        "security_name": SECURITY_NAMES.get(version.security_id, version.security_id),
        "strategy_id": version.strategy_id,
        "strategy_label": (
            STRATEGY_LABELS.get(version.strategy_id, version.strategy_id)
            if version.strategy_id
            else "未关联规则"
        ),
        "quantity": version.quantity,
        "quantity_text": _quantity_text(Decimal(version.quantity)),
        "average_cost": version.average_cost,
        "average_cost_text": _display_number(Decimal(version.average_cost), 2),
        "cost_basis_date": version.cost_basis_date,
        "note": version.note or "—",
        "created_at": version.created_at,
    }


def _security_options(selected: str | None) -> list[dict[str, Any]]:
    return [
        {
            "security_id": security_id,
            "name": SECURITY_NAMES.get(security_id, security_id),
            "selected": security_id == selected,
        }
        for security_id in SECURITY_ORDER
    ]


def _strategy_options(selected: str | None) -> list[dict[str, Any]]:
    return [
        {"value": "", "label": "不关联规则", "selected": selected is None},
        {
            "value": "S01",
            "label": "S01 默认规则（可选）",
            "selected": selected == "S01",
        },
    ]


def _scenario_options(selected: str) -> list[dict[str, Any]]:
    return [
        {
            "value": key,
            "label": meta["label"],
            "description": meta["description"],
            "selected": key == selected,
        }
        for key, meta in SCENARIOS.items()
    ]


def observation_view(observation: H1Observation) -> dict[str, Any]:
    current = observation.current_version
    if observation.status == "ACTIVE":
        display = _display_view(_raw_version(observation, current))
    else:
        snapshot = observation.end_snapshot or _raw_version(observation, current)
        display = _display_view(snapshot)
    if observation.status == "ACTIVE":
        status_label = "ACTIVE · 已更正" if observation.version_count > 1 else "ACTIVE · 观察中"
    else:
        status_label = "ENDED · 已结束（只读）"
    return {
        "observation_id": observation.observation_id,
        "user": observation.user,
        "scenario": observation.scenario,
        "scenario_label": SCENARIOS.get(observation.scenario, {}).get("label", observation.scenario),
        "created_at": observation.created_at,
        "status": observation.status,
        "status_label": status_label,
        "version_count": observation.version_count,
        "display": display,
        "versions": [_version_view(version) for version in observation.versions],
        "security_options": _security_options(current.security_id),
        "strategy_options": _strategy_options(current.strategy_id),
        "ended_at": observation.ended_at,
        "end_reason": observation.end_reason,
        "can_correct": observation.status == "ACTIVE",
        "can_end": observation.status == "ACTIVE",
    }


def h1_data(store: H1Store) -> dict[str, Any]:
    observations = [observation_view(item) for item in reversed(store.observations())]
    active = [item for item in observations if item["status"] == "ACTIVE"]
    ended = [item for item in observations if item["status"] == "ENDED"]
    meta = fixture_metadata("normal")
    return {
        "contract_version": DEMO_CONTRACT_VERSION,
        "marker": CONTRACT_FIXTURE_MARKER,
        "display_marker": FIXTURE_MARKER,
        "user": DEMO_USER,
        "active": active,
        "ended": ended,
        "active_count": len(active),
        "ended_count": len(ended),
        "security_options": _security_options(None),
        "scenario_options": _scenario_options("normal"),
        "strategy_options": _strategy_options("S01"),
        "default_basis_date": BUSINESS_DATE,
        "today": _local_today().isoformat(),
        "fixture": {
            "fixture_id": meta["fixture_id"],
            "fixture_version": meta["fixture_version"],
            "business_date": meta["business_date"],
            "price_basis": meta["price_basis"],
            "marker": CONTRACT_FIXTURE_MARKER,
            "contract_version": RESULT_CONTRACT_VERSION,
            "source": "FIXTURE",
            "real_market_data": False,
        },
        "limitations": list(LONG_LIMITATIONS),
    }


def h1_end_data(store: H1Store, observation_id: str) -> dict[str, Any]:
    observation = store.get(observation_id)
    if observation is None:
        raise DemoInputError(f"观察记录不存在: {observation_id}")
    if observation.status != "ACTIVE":
        raise DemoInputError("已结束记录只读，不能再次结束")
    display = _display_view(_raw_version(observation, observation.current_version))
    return {
        "observation_id": observation.observation_id,
        "display": display,
        "user": DEMO_USER,
        "marker": CONTRACT_FIXTURE_MARKER,
        "display_marker": FIXTURE_MARKER,
        "contract_version": DEMO_CONTRACT_VERSION,
    }


def _validate_scenario(scenario: str) -> str:
    text = (scenario or "").strip()
    if text not in SCENARIOS:
        raise DemoInputError(f"未知固定场景: {scenario}")
    return text


def _validate_security(snapshot: Any, security_id: str) -> str:
    text = (security_id or "").strip()
    if text not in snapshot.securities:
        raise DemoInputError(f"证券不在固定 Fixture 中: {security_id}")
    return text


def _positive_decimal(raw: str, label: str) -> Decimal:
    text = str(raw).strip()
    if not text:
        raise DemoInputError(f"{label}不能为空")
    try:
        value = Decimal(text)
    except (InvalidOperation, ValueError):
        raise DemoInputError(f"{label}必须是有限正数") from None
    if not value.is_finite() or value <= 0:
        raise DemoInputError(f"{label}必须是有限正数")
    if value.adjusted() > 12 or value.adjusted() < -9:
        raise DemoInputError(f"{label}超出可支持范围")
    try:
        _money(value)
        (Decimal(1) / value).quantize(Decimal("0.000001"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ZeroDivisionError):
        raise DemoInputError(f"{label}超出可支持范围") from None
    return value


def _basis_date(raw: str, today: date) -> str:
    text = str(raw).strip()
    if not text:
        raise DemoInputError("成本基准日期不能为空")
    try:
        value = validate_local_date(text, field="cost_basis_date")
    except TimeContractError:
        raise DemoInputError("成本基准日期必须是有效的 YYYY-MM-DD 日期") from None
    if date.fromisoformat(value) > today:
        raise DemoInputError("成本基准日期不能在未来")
    return value


def _strategy_link(raw: str | None) -> str | None:
    text = (raw or "").strip().upper()
    if not text:
        return None
    if text != "S01":
        raise DemoInputError("关联规则仅支持默认 S01")
    return "S01"


def _note(raw: str | None) -> str | None:
    text = (raw or "").strip()
    if len(text) > 200:
        raise DemoInputError("备注最多 200 个字符")
    return text or None


def _end_reason(raw: str) -> str:
    text = (raw or "").strip()
    if not text:
        raise DemoInputError("结束原因不能为空")
    if len(text) > 200:
        raise DemoInputError("结束原因最多 200 个字符")
    return text


def create_observation(
    store: H1Store,
    *,
    security_id: str,
    scenario: str,
    strategy_id: str | None,
    quantity: str,
    average_cost: str,
    cost_basis_date: str,
    note: str | None,
    today: date | None = None,
) -> H1Observation:
    scenario = _validate_scenario(scenario)
    snapshot, _results, _diagnostics = _kernel(scenario)
    security_id = _validate_security(snapshot, security_id)
    quantity_value = _positive_decimal(quantity, "数量")
    cost_value = _positive_decimal(average_cost, "平均成本")
    basis_date = _basis_date(cost_basis_date, today or _local_today())
    strategy = _strategy_link(strategy_id)
    note_text = _note(note)
    return store.create(
        scenario=scenario,
        security_id=security_id,
        strategy_id=strategy,
        quantity=_decimal_text(quantity_value),
        average_cost=_decimal_text(cost_value),
        cost_basis_date=basis_date,
        note=note_text,
    )


def correct_observation(
    store: H1Store,
    observation_id: str,
    *,
    security_id: str,
    strategy_id: str | None,
    quantity: str,
    average_cost: str,
    cost_basis_date: str,
    note: str | None,
    today: date | None = None,
) -> H1Observation:
    observation = store.get(observation_id)
    if observation is None:
        raise DemoInputError(f"观察记录不存在: {observation_id}")
    if observation.status != "ACTIVE":
        raise DemoInputError("已结束记录只读，不能更正")
    snapshot, _results, _diagnostics = _kernel(observation.scenario)
    security_id = _validate_security(snapshot, security_id)
    quantity_value = _positive_decimal(quantity, "数量")
    cost_value = _positive_decimal(average_cost, "平均成本")
    basis_date = _basis_date(cost_basis_date, today or _local_today())
    strategy = _strategy_link(strategy_id)
    note_text = _note(note)
    try:
        return store.correct(
            observation_id,
            security_id=security_id,
            strategy_id=strategy,
            quantity=_decimal_text(quantity_value),
            average_cost=_decimal_text(cost_value),
            cost_basis_date=basis_date,
            note=note_text,
        )
    except H1StateError:
        raise DemoInputError("已结束记录只读，不能更正") from None


def end_observation(
    store: H1Store,
    observation_id: str,
    *,
    reason: str,
) -> H1Observation:
    observation = store.get(observation_id)
    if observation is None:
        raise DemoInputError(f"观察记录不存在: {observation_id}")
    if observation.status != "ACTIVE":
        raise DemoInputError("已结束记录只读，不能再次结束")
    reason_text = _end_reason(reason)
    snapshot = _raw_version(observation, observation.current_version)
    try:
        return store.end(observation_id, reason=reason_text, snapshot=snapshot)
    except H1StateError:
        raise DemoInputError("已结束记录只读，不能再次结束") from None


def api_h1_data(store: H1Store) -> dict[str, Any]:
    data = h1_data(store)
    return {
        "contract_version": data["contract_version"],
        "marker": data["marker"],
        "display_marker": data["display_marker"],
        "user": data["user"],
        "fixture": data["fixture"],
        "active_count": data["active_count"],
        "ended_count": data["ended_count"],
        "observations": data["active"] + data["ended"],
        "limitations": data["limitations"],
    }
