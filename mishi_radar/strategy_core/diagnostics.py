"""Six descriptive dimensions and the three transparent display styles."""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from .config import (
    S01_DEFAULT_CONFIG,
    S05_DEFAULT_CONFIG,
    S07_DEFAULT_CONFIG,
    ConfigBundle,
)
from .mathx import ZERO, mean, percentile_high
from .model import (
    ConditionStatus,
    DiagnosticResult,
    DimensionResult,
    Eligibility,
    MarketSnapshot,
    Numeric,
    StyleView,
    ValueStatus,
)
from .strategies import (
    _avg_amount,
    _base_eligibility,
    _s01_metrics,
    _s05_metrics,
    _s07_metrics,
    _value_at,
    _index,
)

_STYLES: dict[str, StyleView] = {
    "BALANCED/1": StyleView(
        style_id="BALANCED/1",
        strategy_order=("S01", "S02", "S03", "S04", "S05", "S06", "S07", "S08"),
        diagnostic_priority=("momentum", "value", "quality"),
        note="均衡：仅调整策略入口顺序和诊断展开重点。",
    ),
    "ATTACK/1": StyleView(
        style_id="ATTACK/1",
        strategy_order=("S02", "S03", "S01", "S06", "S08", "S04", "S07", "S05"),
        diagnostic_priority=("volume_price", "momentum", "fund_flow"),
        note="进攻：仅调整策略入口顺序和诊断展开重点，同时固定显示风险。",
    ),
    "DEFENSIVE/1": StyleView(
        style_id="DEFENSIVE/1",
        strategy_order=("S05", "S07", "S01", "S06", "S08", "S03", "S02", "S04"),
        diagnostic_priority=("low_volatility", "liquidity", "quality"),
        note="防守：仅调整策略入口顺序和诊断展开重点，同时显示估值和缺失。",
    ),
}


def style_view(style_id: str) -> StyleView:
    try:
        return _STYLES[style_id]
    except KeyError as exc:
        raise ValueError(f"unknown style_id {style_id!r}; expected BALANCED/1, ATTACK/1 or DEFENSIVE/1") from exc


def _dimension(
    *,
    name: str,
    raw_value: Decimal | None,
    unit: str | None,
    score: Decimal | None,
    status: ValueStatus,
    pool_id: str,
    pool_size: int,
    pool_complete: bool,
    snapshot: MarketSnapshot,
    window: str,
    direction: str,
    explanation: str,
    reason: str | None = None,
    extras: Mapping[str, Decimal | None] | None = None,
) -> DimensionResult:
    return DimensionResult(
        name=name,
        raw_value=raw_value,
        unit=unit,
        score=score,
        status=status,
        pool_id=pool_id,
        pool_size=pool_size,
        pool_complete=pool_complete,
        business_date=snapshot.business_date,
        window=window,
        direction=direction,
        explanation=explanation,
        reason=reason,
        extras=dict(extras or {}),
    )


def _reversal_metrics(snapshot: MarketSnapshot, security_id: str) -> tuple[dict[str, Decimal], Numeric | None]:
    end_index = _index(snapshot, snapshot.business_date)
    if end_index is None or end_index < 6:
        return {}, Numeric(None, ValueStatus.MISSING, "INSUFFICIENT_HISTORY")
    d_minus_1 = snapshot.calendar[end_index - 1]
    d_minus_6 = snapshot.calendar[end_index - 6]
    p_prev = _value_at(snapshot, security_id, d_minus_1, "adjusted_close")
    p_6 = _value_at(snapshot, security_id, d_minus_6, "adjusted_close")
    price = _value_at(snapshot, security_id, snapshot.business_date, "adjusted_close")
    for item in (p_prev, p_6, price):
        if item.status is ValueStatus.NOT_APPLICABLE:
            return {}, item
        if not item.usable:
            return {}, item
    assert p_prev.value is not None and p_6.value is not None and price.value is not None
    if p_6.value <= 0 or p_prev.value <= 0:
        return {}, Numeric(None, ValueStatus.INVALID, "NON_POSITIVE_PRICE")
    return {
        "prior_drop5": p_prev.value / p_6.value - 1,
        "repair": price.value / p_prev.value - 1,
    }, None


def _base_status(snapshot: MarketSnapshot, security_id: str, bundle: ConfigBundle) -> tuple[Eligibility, list[str]]:
    security = snapshot.securities[security_id]
    return _base_eligibility(snapshot, security, bundle)


def _unknown_dimension(
    snapshot: MarketSnapshot,
    name: str,
    status: ValueStatus,
    reason: str,
    pool_id: str,
    window: str,
    direction: str,
    explanation: str,
    *,
    raw_value: Decimal | None = None,
    unit: str | None = None,
    pool_size: int = 0,
) -> DimensionResult:
    return _dimension(
        name=name,
        raw_value=raw_value,
        unit=unit,
        score=None,
        status=status,
        pool_id=pool_id,
        pool_size=pool_size,
        pool_complete=False,
        snapshot=snapshot,
        window=window,
        direction=direction,
        explanation=explanation,
        reason=reason,
    )


def _status_from_eligibility(eligibility: Eligibility) -> ValueStatus:
    mapping = {
        Eligibility.BASE_EXCLUDED: ValueStatus.NOT_APPLICABLE,
        Eligibility.STRATEGY_NOT_APPLICABLE: ValueStatus.NOT_APPLICABLE,
        Eligibility.INPUT_UNKNOWN: ValueStatus.UNKNOWN,
        Eligibility.MISSING: ValueStatus.MISSING,
        Eligibility.FAILED: ValueStatus.REQUEST_FAILED,
        Eligibility.STALE: ValueStatus.STALE,
        Eligibility.INVALID: ValueStatus.INVALID,
        Eligibility.CONFLICT: ValueStatus.CONFLICT,
    }
    return mapping.get(eligibility, ValueStatus.UNKNOWN)


def _base_pool_incomplete(base: Mapping[str, tuple[Eligibility, list[str]]]) -> bool:
    determinate = {
        Eligibility.SCORABLE,
        Eligibility.BASE_EXCLUDED,
        Eligibility.STRATEGY_NOT_APPLICABLE,
    }
    return any(eligibility not in determinate for eligibility, _ in base.values())


def compute_diagnostics(snapshot: MarketSnapshot, bundle: ConfigBundle | None = None) -> DiagnosticResult:
    bundle = bundle or ConfigBundle()
    rows: dict[str, dict[str, DimensionResult]] = {}
    notes: list[str] = []

    base: dict[str, tuple[Eligibility, list[str]]] = {}
    for sid in sorted(snapshot.securities):
        base[sid] = _base_status(snapshot, sid, bundle)
        rows[sid] = {}

    # Momentum: same E01 and score01 as S01.
    momentum_metrics: dict[str, dict[str, Decimal]] = {}
    momentum_errors: dict[str, Numeric] = {}
    for sid, (eligibility, _) in base.items():
        if eligibility is not Eligibility.SCORABLE:
            continue
        metrics, blocker = _s01_metrics(snapshot, sid, S01_DEFAULT_CONFIG)
        if blocker is not None:
            momentum_errors[sid] = blocker
        else:
            momentum_metrics[sid] = metrics
    momentum_pool_complete = snapshot.universe_complete and not _base_pool_incomplete(base)
    for sid, (eligibility, _) in base.items():
        if eligibility is Eligibility.SCORABLE and sid not in momentum_metrics:
            momentum_pool_complete = False
            break
    if any(item.status is not ValueStatus.NOT_APPLICABLE for item in momentum_errors.values()):
        momentum_pool_complete = False
    momentum_ids = sorted(momentum_metrics)
    if momentum_ids:
        er20_population = [momentum_metrics[sid]["er20"] for sid in momentum_ids]
        er60_population = [momentum_metrics[sid]["er60"] for sid in momentum_ids]
        momentum_scores: dict[str, Decimal] = {}
        for sid in momentum_ids:
            q20 = percentile_high(momentum_metrics[sid]["er20"], er20_population)
            q60 = percentile_high(momentum_metrics[sid]["er60"], er60_population)
            assert q20 is not None and q60 is not None
            momentum_scores[sid] = (q20 + q60) / 2
    else:
        momentum_scores = {}
    for sid, (eligibility, reasons) in base.items():
        if eligibility is not Eligibility.SCORABLE:
            rows[sid]["momentum"] = _unknown_dimension(
                snapshot,
                "momentum",
                _status_from_eligibility(eligibility),
                "BASE_ELIGIBILITY:" + ",".join(reasons),
                "E01",
                "ER20/ER60",
                "high",
                "动量描述分：高超额高分，不代表收益概率。",
            )
            continue
        metrics = momentum_metrics.get(sid)
        blocker = momentum_errors.get(sid)
        if metrics is None:
            status = blocker.status if blocker is not None else ValueStatus.UNKNOWN
            rows[sid]["momentum"] = _unknown_dimension(
                snapshot,
                "momentum",
                status,
                blocker.reason if blocker is not None and blocker.reason else "MOMENTUM_INPUT_UNKNOWN",
                "E01",
                "ER20/ER60",
                "high",
                "动量描述分：高超额高分，不代表收益概率。",
                pool_size=len(momentum_metrics),
            )
            continue
        score = (
            momentum_scores.get(sid)
            if momentum_pool_complete and len(momentum_metrics) >= 2
            else None
        )
        rows[sid]["momentum"] = _dimension(
            name="momentum",
            raw_value=metrics["er20"],
            unit="ratio",
            score=Decimal(100) * score if score is not None else None,
            status=ValueStatus.VALUE,
            pool_id="E01",
            pool_size=len(momentum_metrics),
            pool_complete=momentum_pool_complete,
            snapshot=snapshot,
            window="20/60 market days",
            direction="high",
            explanation="动量描述分；原值先显示 ER20，附 ER60；高动量不代表便宜或可成交。",
            extras={"er60": metrics["er60"]},
        )

    # Reversal: E0 with a complete D-6 and D-1 close.
    reversal_metrics: dict[str, dict[str, Decimal]] = {}
    reversal_errors: dict[str, Numeric] = {}
    for sid, (eligibility, _) in base.items():
        if eligibility is not Eligibility.SCORABLE:
            continue
        metrics, blocker = _reversal_metrics(snapshot, sid)
        if blocker is not None:
            reversal_errors[sid] = blocker
        else:
            reversal_metrics[sid] = metrics
    reversal_pool_complete = (
        snapshot.universe_complete
        and not _base_pool_incomplete(base)
        and len(reversal_metrics) == sum(
            1 for eligibility, _ in base.values() if eligibility is Eligibility.SCORABLE
        )
    )
    reversal_population = [reversal_metrics[sid]["prior_drop5"] for sid in sorted(reversal_metrics)]
    for sid, (eligibility, reasons) in base.items():
        if eligibility is not Eligibility.SCORABLE:
            rows[sid]["reversal"] = _unknown_dimension(
                snapshot,
                "reversal",
                _status_from_eligibility(eligibility),
                "BASE_ELIGIBILITY:" + ",".join(reasons),
                "E_REVERSAL",
                "D-6..D-1",
                "high",
                "短期超跌程度；不叫修复成功率，高分可能仍在下跌。",
            )
            continue
        metrics = reversal_metrics.get(sid)
        if metrics is None:
            blocker = reversal_errors[sid]
            rows[sid]["reversal"] = _unknown_dimension(
                snapshot,
                "reversal",
                blocker.status,
                blocker.reason or "REVERSAL_INPUT_UNKNOWN",
                "E_REVERSAL",
                "D-6..D-1",
                "high",
                "短期超跌程度；不叫修复成功率，高分可能仍在下跌。",
                pool_size=len(reversal_metrics),
            )
            continue
        q = percentile_high(metrics["prior_drop5"], reversal_population)
        score = (
            Decimal(100) * (1 - q)
            if q is not None and reversal_pool_complete and len(reversal_metrics) >= 2
            else None
        )
        rows[sid]["reversal"] = _dimension(
            name="reversal",
            raw_value=metrics["prior_drop5"],
            unit="ratio",
            score=score,
            status=ValueStatus.VALUE,
            pool_id="E_REVERSAL",
            pool_size=len(reversal_metrics),
            pool_complete=reversal_pool_complete,
            snapshot=snapshot,
            window="5 completed returns through D-1",
            direction="high",
            explanation="短期超跌程度；修复确认是 S04 的两个条件，不并入该分。",
            extras={"repair": metrics["repair"]},
        )

    # Financial dimensions: E07 per industry.
    financial_metrics: dict[str, dict[str, Decimal]] = {}
    financial_errors: dict[str, Numeric] = {}
    financial_industry: dict[str, str] = {}
    industry_incomplete: set[str] = set()
    global_financial_incomplete = (
        not snapshot.universe_complete or _base_pool_incomplete(base)
    )
    for sid, (eligibility, _) in base.items():
        if eligibility is not Eligibility.SCORABLE:
            continue
        fin = snapshot.financials.get(sid)
        industry = fin.industry_id if fin is not None and fin.industry_id else snapshot.securities[sid].industry_id
        metrics, blocker = _s07_metrics(snapshot, sid)
        if blocker is None:
            financial_metrics[sid] = metrics
            if industry is None:
                global_financial_incomplete = True
            else:
                financial_industry[sid] = industry
        else:
            financial_errors[sid] = blocker
            if blocker.status is not ValueStatus.NOT_APPLICABLE:
                if industry is None:
                    global_financial_incomplete = True
                else:
                    industry_incomplete.add(industry)
    industry_pools: dict[str, list[str]] = {}
    for sid, industry in financial_industry.items():
        industry_pools.setdefault(industry, []).append(sid)
    industry_scores: dict[str, Decimal] = {}
    industry_pool_complete: dict[str, bool] = {}
    for industry, members in industry_pools.items():
        complete = not global_financial_incomplete and industry not in industry_incomplete
        industry_pool_complete[industry] = complete
        pe_population = [financial_metrics[sid]["pe_ttm"] for sid in members]
        roe_population = [financial_metrics[sid]["roe_ttm"] for sid in members]
        for sid in members:
            q_pe = percentile_high(financial_metrics[sid]["pe_ttm"], pe_population)
            q_roe = percentile_high(financial_metrics[sid]["roe_ttm"], roe_population)
            assert q_pe is not None and q_roe is not None
            industry_scores[sid] = ((1 - q_pe) + q_roe) / 2
    for sid, (eligibility, reasons) in base.items():
        if eligibility is not Eligibility.SCORABLE:
            rows[sid]["value"] = _unknown_dimension(
                snapshot,
                "value",
                _status_from_eligibility(eligibility),
                "BASE_ELIGIBILITY:" + ",".join(reasons),
                "E07",
                "PE_TTM",
                "high",
                "相对估值位置；非正 PE 或金融模板明确不适用。",
            )
            rows[sid]["quality"] = _unknown_dimension(
                snapshot,
                "quality",
                _status_from_eligibility(eligibility),
                "BASE_ELIGIBILITY:" + ",".join(reasons),
                "E07",
                "ROE_TTM",
                "high",
                "ROE_TTM 相对位置；同时显示利润和经营现金流。",
            )
            continue
        fin = snapshot.financials.get(sid)
        raw_pe = fin.pe_ttm.value if fin is not None and fin.pe_ttm.usable else None
        raw_roe = financial_metrics[sid]["roe_ttm"] if sid in financial_metrics else None
        raw_np = financial_metrics[sid]["np_ttm"] if sid in financial_metrics else None
        raw_ocf = financial_metrics[sid]["ocf_ttm"] if sid in financial_metrics else None
        industry = financial_industry.get(sid) or (fin.industry_id if fin is not None else None)
        if sid in financial_metrics:
            complete = industry_pool_complete.get(industry or "", False)
            q_pe = percentile_high(financial_metrics[sid]["pe_ttm"], [financial_metrics[x]["pe_ttm"] for x in industry_pools.get(industry or "", [])])
            q_roe = percentile_high(financial_metrics[sid]["roe_ttm"], [financial_metrics[x]["roe_ttm"] for x in industry_pools.get(industry or "", [])])
            assert q_pe is not None and q_roe is not None
            score_available = complete and len(industry_pools.get(industry or "", [])) >= 2
            value_score = Decimal(100) * (1 - q_pe) if score_available else None
            quality_score = Decimal(100) * q_roe if score_available else None
            rows[sid]["value"] = _dimension(
                name="value",
                raw_value=financial_metrics[sid]["pe_ttm"],
                unit="x",
                score=value_score,
                status=ValueStatus.VALUE,
                pool_id=f"E07:{industry}",
                pool_size=len(industry_pools.get(industry or "", [])),
                pool_complete=complete,
                snapshot=snapshot,
                window="designated-day PE_TTM",
                direction="high",
                explanation="同行业相对估值位置；低 PE 不自动证明质量。",
            )
            ocf_np = raw_ocf / raw_np if raw_np is not None and raw_np > 0 and raw_ocf is not None else None
            rows[sid]["quality"] = _dimension(
                name="quality",
                raw_value=raw_roe,
                unit="ratio",
                score=quality_score,
                status=ValueStatus.VALUE,
                pool_id=f"E07:{industry}",
                pool_size=len(industry_pools.get(industry or "", [])),
                pool_complete=complete,
                snapshot=snapshot,
                window="TTM",
                direction="high",
                explanation="同行业 ROE_TTM 相对位置；同时显示净利润、经营现金流和 OCF/NP。",
                extras={"np_ttm": raw_np, "ocf_ttm": raw_ocf, "ocf_np": ocf_np},
            )
            continue
        blocker = financial_errors.get(sid)
        if blocker is None:
            blocker = Numeric(None, ValueStatus.UNKNOWN, "FINANCIAL_UNKNOWN")
        rows[sid]["value"] = _unknown_dimension(
            snapshot,
            "value",
            blocker.status,
            blocker.reason or "FINANCIAL_UNKNOWN",
            f"E07:{industry or 'UNKNOWN'}",
            "PE_TTM",
            "high",
            "相对估值位置；非正 PE 或金融模板明确不适用。",
            raw_value=raw_pe,
            unit="x",
            pool_size=len(industry_pools.get(industry or "", [])),
        )
        rows[sid]["quality"] = _unknown_dimension(
            snapshot,
            "quality",
            blocker.status,
            blocker.reason or "FINANCIAL_UNKNOWN",
            f"E07:{industry or 'UNKNOWN'}",
            "TTM",
            "high",
            "ROE_TTM 相对位置；同时显示利润和经营现金流。",
            raw_value=raw_roe,
            unit="ratio",
            pool_size=len(industry_pools.get(industry or "", [])),
        )

    # Low volatility and liquidity: E05.
    e05_metrics: dict[str, dict[str, Decimal]] = {}
    e05_errors: dict[str, Numeric] = {}
    for sid, (eligibility, _) in base.items():
        if eligibility is not Eligibility.SCORABLE:
            continue
        metrics, blocker = _s05_metrics(snapshot, sid)
        if blocker is not None:
            e05_errors[sid] = blocker
        else:
            e05_metrics[sid] = metrics
    e05_pool_complete = snapshot.universe_complete and not _base_pool_incomplete(base)
    for sid, (eligibility, _) in base.items():
        if eligibility is Eligibility.SCORABLE and sid not in e05_metrics:
            blocker = e05_errors.get(sid)
            if blocker is None or blocker.status is not ValueStatus.NOT_APPLICABLE:
                e05_pool_complete = False
                break
    e05_ids = sorted(e05_metrics)
    sigma_population = [e05_metrics[sid]["sigma60"] for sid in e05_ids]
    illiq_population = [e05_metrics[sid]["illiq60"] for sid in e05_ids]
    for sid, (eligibility, reasons) in base.items():
        if eligibility is not Eligibility.SCORABLE:
            rows[sid]["low_volatility"] = _unknown_dimension(
                snapshot,
                "low_volatility",
                _status_from_eligibility(eligibility),
                "BASE_ELIGIBILITY:" + ",".join(reasons),
                "E05",
                "60 market days",
                "high",
                "历史波动越低分越高；不是保本或低风险认证。",
            )
            rows[sid]["liquidity"] = _unknown_dimension(
                snapshot,
                "liquidity",
                _status_from_eligibility(eligibility),
                "BASE_ELIGIBILITY:" + ",".join(reasons),
                "E05",
                "60 market days",
                "high",
                "Amihud 低冲击代理越高分；不代表开盘订单保证成交。",
            )
            continue
        metrics = e05_metrics.get(sid)
        scorer = e05_errors.get(sid)
        if metrics is None:
            status = scorer.status if scorer is not None else ValueStatus.UNKNOWN
            raw_sigma = None
            raw_illiq = None
            rows[sid]["low_volatility"] = _unknown_dimension(
                snapshot,
                "low_volatility",
                status,
                scorer.reason if scorer is not None and scorer.reason else "LOW_VOL_INPUT_UNKNOWN",
                "E05",
                "60 market days",
                "high",
                "历史波动越低分越高；不是保本或低风险认证。",
                raw_value=raw_sigma,
                pool_size=len(e05_metrics),
            )
            rows[sid]["liquidity"] = _unknown_dimension(
                snapshot,
                "liquidity",
                status,
                scorer.reason if scorer is not None and scorer.reason else "LIQUIDITY_INPUT_UNKNOWN",
                "E05",
                "60 market days",
                "high",
                "Amihud 低冲击代理越高分；不代表开盘订单保证成交。",
                raw_value=raw_illiq,
                pool_size=len(e05_metrics),
            )
            continue
        q_sigma = percentile_high(metrics["sigma60"], sigma_population)
        q_illiq = percentile_high(metrics["illiq60"], illiq_population)
        assert q_sigma is not None and q_illiq is not None
        rows[sid]["low_volatility"] = _dimension(
            name="low_volatility",
            raw_value=metrics["sigma60"],
            unit="ratio",
            score=(
                Decimal(100) * (1 - q_sigma)
                if e05_pool_complete and len(e05_metrics) >= 2
                else None
            ),
            status=ValueStatus.VALUE,
            pool_id="E05",
            pool_size=len(e05_metrics),
            pool_complete=e05_pool_complete,
            snapshot=snapshot,
            window="60 daily returns",
            direction="high",
            explanation="历史波动越低分越高；不是保本或低风险认证。",
        )
        avg_amount = _avg_amount(snapshot, sid, 20)
        rows[sid]["liquidity"] = _dimension(
            name="liquidity",
            raw_value=metrics["illiq60"],
            unit="1/CNY",
            score=(
                Decimal(100) * (1 - q_illiq)
                if e05_pool_complete and len(e05_metrics) >= 2
                else None
            ),
            status=ValueStatus.VALUE,
            pool_id="E05",
            pool_size=len(e05_metrics),
            pool_complete=e05_pool_complete,
            snapshot=snapshot,
            window="60 market days",
            direction="high",
            explanation="Amihud 低冲击代理越高分；不代表开盘订单保证成交。",
            extras={"avg_amount_20": avg_amount.value if avg_amount.usable else None},
        )

    if not all(item.pool_complete for row in rows.values() for item in row.values()):
        notes.append("部分维度比较池不完整，相对分为 UNKNOWN；原值仍保留。")
    return DiagnosticResult(
        business_date=snapshot.business_date,
        input_version=snapshot.input_version,
        rows={sid: rows[sid] for sid in sorted(rows)},
        notes=tuple(notes),
    )
