"""Read-only F1/F3/F7 result contracts over the accepted OD-1 kernel.

This module does not calculate strategy conditions, ranks or diagnostics.  It
calls ``compute_all``, ``compute_diagnostics`` and ``signal_records`` and only
reshapes their existing output into stable, JSON-serializable consumption
contracts.  No cross-strategy score is produced.
"""

from __future__ import annotations

import json
from decimal import Decimal
from enum import Enum
from typing import Any, Mapping, Sequence

from ..strategy_core import compute_all, compute_diagnostics, signal_records
from ..strategy_core.model import (
    ConditionStatus,
    DiagnosticResult,
    DimensionResult,
    MarketSnapshot,
    StrategyResult,
    ValueStatus,
)
from .fixtures import (
    FIXTURE_MARKER,
    FIXTURE_VERSION,
    build_fixture_snapshot,
    fixture_metadata,
)

RESULT_CONTRACT_VERSION = "FX01A-RESULT-CONTRACT-v1"
F1_CONTRACT = "MISHI-F1-OPPORTUNITY"
F3_CONTRACT = "MISHI-F3-DIAGNOSTIC"
F7_CONTRACT = "MISHI-F7-DATA-STATUS"

_SIX_DIMENSIONS: tuple[str, ...] = (
    "momentum",
    "reversal",
    "value",
    "quality",
    "low_volatility",
    "liquidity",
)

_UNKNOWN_STATES = frozenset(
    {
        "INPUT_UNKNOWN",
        "MISSING",
        "FAILED",
        "STALE",
        "INVALID",
        "CONFLICT",
    }
)
_MISSING_STATUSES = frozenset(
    {
        ValueStatus.MISSING,
        ValueStatus.UNKNOWN,
        ValueStatus.INVALID,
        ValueStatus.CONFLICT,
        ValueStatus.REQUEST_FAILED,
        ValueStatus.STALE,
    }
)
_UNKNOWN_STATUSES = frozenset(
    {
        ValueStatus.UNKNOWN,
        ValueStatus.INVALID,
        ValueStatus.CONFLICT,
        ValueStatus.REQUEST_FAILED,
        ValueStatus.STALE,
    }
)


def _json_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _available_at_kind(available_at: str | None, input_version: str) -> str:
    if available_at is None:
        return "UNKNOWN"
    if len(available_at) > 10:
        return "LOCAL_DATETIME"
    if input_version.startswith("SYNTHETIC"):
        return "SYNTHETIC_DATE_COMPAT"
    return "NORMALIZED_AVAILABLE_DATE"


def _schema(contract: str) -> dict[str, str]:
    return {
        "contract": contract,
        "contract_version": RESULT_CONTRACT_VERSION,
        "fixture_version": FIXTURE_VERSION,
    }


def _fixture_view(metadata: Mapping[str, object]) -> dict[str, Any]:
    return {
        "fixture_id": metadata["fixture_id"],
        "fixture_version": metadata["fixture_version"],
        "scenario": metadata["scenario"],
        "scenario_label": metadata["scenario_label"],
        "scenario_description": metadata["scenario_description"],
        "marker": FIXTURE_MARKER,
        "source": "FIXTURE",
        "synthetic": True,
        "real_market_data": False,
        "network_used": False,
        "business_date": metadata["business_date"],
        "calendar": metadata["calendar"],
        "input_version": metadata["input_version"],
        "price_basis": metadata["price_basis"],
        "currency": metadata["currency"],
        "computed_at": metadata["computed_at"],
    }


def _publication_view(metadata: Mapping[str, object]) -> dict[str, Any]:
    return {
        "identity": "SYNTHETIC_FIXTURE",
        "actual_published": False,
        "actual_published_at": None,
        "fixture_declared_published_at": metadata["fixture_declared_published_at"],
        "history_ranking_writable": False,
        "formal_history_ranking_allowed": False,
        "reason": "SYNTHETIC_FIXTURE_IS_NOT_ACTUAL_PUBLICATION",
    }


def _records_by_strategy(results: Mapping[str, StrategyResult]) -> dict[str, list[dict[str, Any]]]:
    return {
        strategy_id: signal_records({strategy_id: results[strategy_id]})
        for strategy_id in sorted(results)
    }


def _state_counts(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        key = str(record["signal_state"])
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _eligibility_counts(records: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for record in records:
        key = str(record["qualification_status"])
        counts[key] = counts.get(key, 0) + 1
    return dict(sorted(counts.items()))


def _is_failed(record: Mapping[str, Any]) -> bool:
    return bool(
        record["qualification_status"] == "FAILED"
        or record["signal_state"] == "FAILED"
    )


def _is_unknown(record: Mapping[str, Any]) -> bool:
    return bool(
        not _is_failed(record)
        and (
            record["qualification_status"] in _UNKNOWN_STATES
            or record["signal_state"] in _UNKNOWN_STATES
        )
    )


def _counts(records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    failed = sum(1 for item in records if _is_failed(item))
    missing = sum(
        1 for item in records if item["signal_state"] == "MISSING" or item["qualification_status"] == "MISSING"
    )
    stale = sum(1 for item in records if item["signal_state"] == "STALE" or item["qualification_status"] == "STALE")
    invalid = sum(1 for item in records if item["signal_state"] == "INVALID" or item["qualification_status"] == "INVALID")
    conflict = sum(
        1 for item in records if item["signal_state"] == "CONFLICT" or item["qualification_status"] == "CONFLICT"
    )
    input_unknown = sum(
        1
        for item in records
        if item["signal_state"] == "INPUT_UNKNOWN" or item["qualification_status"] == "INPUT_UNKNOWN"
    )
    base_excluded = sum(
        1
        for item in records
        if item["signal_state"] == "BASE_EXCLUDED" or item["qualification_status"] == "BASE_EXCLUDED"
    )
    return {
        "rows": len(records),
        "unknown_rows": sum(1 for item in records if _is_unknown(item)),
        "failed_rows": failed,
        "missing_rows": missing,
        "stale_rows": stale,
        "invalid_rows": invalid,
        "conflict_rows": conflict,
        "input_unknown_rows": input_unknown,
        "base_excluded_rows": base_excluded,
        "state_counts": _state_counts(records),
        "eligibility_counts": _eligibility_counts(records),
    }


def _row_identity(record: Mapping[str, Any]) -> str:
    if record["signal_state"] == "FAILED" or record["qualification_status"] == "FAILED":
        return "FAILED"
    if (
        record["pool_complete"]
        and record["formal_candidate"]
        and record["candidate_rank"] is not None
    ):
        return "FORMAL_CANDIDATE"
    if not record["pool_complete"] and record["signal_state"] == "CANDIDATE":
        return "PREVIEW_CANDIDATE"
    if _is_unknown(record):
        return "UNKNOWN"
    return "NOT_CANDIDATE"


def _rank_scope(record: Mapping[str, Any]) -> str:
    if record["pool_complete"] and record["candidate_rank"] is not None:
        return "FIXTURE_BATCH_EXACT"
    if record["sample_candidate_rank"] is not None:
        return "SAMPLE_ONLY"
    return "NONE"


def _row_view(record: Mapping[str, Any]) -> dict[str, Any]:
    view = dict(record)
    view["kernel_formal_candidate"] = bool(record["formal_candidate"])
    view["formal_candidate"] = bool(
        record["pool_complete"]
        and record["formal_candidate"]
        and record["candidate_rank"] is not None
    )
    view["preview_candidate"] = bool(
        not record["pool_complete"] and record["signal_state"] == "CANDIDATE"
    )
    view["rank_scope"] = _rank_scope(record)
    view["row_identity"] = _row_identity(record)
    view["history_rank"] = None
    view["history_ranking_writable"] = False
    view["actual_published"] = False
    return view


def _find_record(
    records_by_strategy: Mapping[str, Sequence[Mapping[str, Any]]],
    security_id: str,
    strategy_id: str,
) -> Mapping[str, Any] | None:
    for record in records_by_strategy.get(strategy_id, ()):
        if record["security_id"] == security_id:
            return record
    return None


def _hit_tags(
    records_by_strategy: Mapping[str, Sequence[Mapping[str, Any]]],
    security_id: str,
    selected_strategy: str,
) -> list[dict[str, Any]]:
    tags: list[dict[str, Any]] = []
    for strategy_id in sorted(records_by_strategy):
        record = _find_record(records_by_strategy, security_id, strategy_id)
        if record is None or record["signal_state"] != "CANDIDATE":
            continue
        tags.append(
            {
                "strategy_id": strategy_id,
                "selected": strategy_id == selected_strategy,
                "signal_date": record["signal_date"],
                "input_version": record["input_version"],
                "config_id": record["config_id"],
                "config_version": record["config_version"],
                "bound_s01_config_version": record["bound_s01_config_version"],
                "qualification_status": record["qualification_status"],
                "signal_state": record["signal_state"],
                "formal_candidate": bool(
                    record["pool_complete"]
                    and record["formal_candidate"]
                    and record["candidate_rank"] is not None
                ),
                "preview_candidate": bool(
                    not record["pool_complete"] and record["signal_state"] == "CANDIDATE"
                ),
                "rank_scope": _rank_scope(record),
                "pool_rank": record["pool_rank"] if record["pool_complete"] else None,
                "candidate_rank": record["candidate_rank"] if record["pool_complete"] else None,
                "sample_pool_rank": record["sample_pool_rank"],
                "sample_candidate_rank": record["sample_candidate_rank"],
                "pool_size": record["pool_size"],
                "candidate_size": record["candidate_size"],
                "pool_complete": record["pool_complete"],
                "signal_status": record["signal_status"],
                "conditions": record["conditions"],
                "reasons": record["reasons"],
            }
        )
    return tags


def _f1_outcome(result: StrategyResult, records: Sequence[Mapping[str, Any]]) -> str:
    counts = _counts(records)
    if result.pool_size == 0 and counts["failed_rows"] == len(records) and records:
        return "FAILED"
    if result.pool_size == 0:
        if counts["unknown_rows"] > 0:
            return "UNKNOWN"
        return "EMPTY"
    if result.pool_complete:
        return "CANDIDATES" if result.candidate_size > 0 else "EMPTY"
    return "PREVIEW"


def _outcome_payload(kind: str, result: StrategyResult, records: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    counts = _counts(records)
    failure = None
    if kind == "FAILED":
        failure = {
            "code": "STRATEGY_INPUT_FAILED",
            "message": "all rows failed; no scorable pool",
            "failed_rows": counts["failed_rows"],
        }
    return {
        "kind": kind,
        "computation_ok": kind != "FAILED",
        "empty_is_success": kind == "EMPTY",
        "formal_identity_available": bool(result.pool_complete),
        "sample_only": kind == "PREVIEW",
        "failure": failure,
    }


def _strategy_catalog(
    results: Mapping[str, StrategyResult],
    records_by_strategy: Mapping[str, Sequence[Mapping[str, Any]]],
) -> dict[str, dict[str, Any]]:
    catalog: dict[str, dict[str, Any]] = {}
    for strategy_id in sorted(results):
        result = results[strategy_id]
        records = records_by_strategy[strategy_id]
        catalog[strategy_id] = {
            "strategy_id": strategy_id,
            "signal_date": result.signal_date,
            "config_id": result.config_id,
            "config_version": result.config_version,
            "input_version": result.input_version,
            "bound_s01_config_version": result.bound_s01_config_version,
            "pool_size": result.pool_size,
            "candidate_size": result.candidate_size,
            "pool_complete": result.pool_complete,
            "outcome": _f1_outcome(result, records),
            "counts": _counts(records),
        }
    return catalog


def build_f1(
    results: Mapping[str, StrategyResult],
    snapshot: MarketSnapshot,
    *,
    fixture: Mapping[str, object],
    strategy_id: str = "S01",
    top_n: int = 10,
) -> dict[str, Any]:
    if strategy_id not in results:
        raise KeyError(f"unknown strategy_id {strategy_id!r}")
    if not isinstance(top_n, int) or isinstance(top_n, bool) or not 1 <= top_n <= 30:
        raise ValueError("top_n must be an integer between 1 and 30")

    records_by_strategy = _records_by_strategy(results)
    result = results[strategy_id]
    records = records_by_strategy[strategy_id]

    formal = [
        item
        for item in records
        if item["pool_complete"]
        and item["formal_candidate"]
        and item["candidate_rank"] is not None
    ]
    formal.sort(key=lambda item: (item["candidate_rank"], item["security_id"]))

    preview = [
        item
        for item in records
        if not item["pool_complete"] and item["signal_state"] == "CANDIDATE"
    ]
    preview.sort(key=lambda item: (item["sample_candidate_rank"] or 10**9, item["security_id"]))

    unknown = [item for item in records if _is_unknown(item)]
    unknown.sort(key=lambda item: item["security_id"])
    failed = [item for item in records if _is_failed(item)]
    failed.sort(key=lambda item: item["security_id"])

    candidates = [_row_view(item) for item in formal[:top_n]]
    beyond = [_row_view(item) for item in formal[top_n:]]
    preview_rows = [_row_view(item) for item in preview]
    unknown_rows = [_row_view(item) for item in unknown]
    failed_rows = [_row_view(item) for item in failed]

    for index, row in enumerate(candidates, 1):
        row["display_rank"] = index
        row["within_top_n"] = True
    for row in beyond:
        row["display_rank"] = None
        row["within_top_n"] = False
    for row in preview_rows + unknown_rows + failed_rows:
        row["display_rank"] = None
        row["within_top_n"] = False

    for row in candidates + beyond + preview_rows + unknown_rows + failed_rows:
        row["hit_tags"] = _hit_tags(records_by_strategy, row["security_id"], strategy_id)

    kind = _f1_outcome(result, records)
    counts = _counts(records)
    batch_id = (
        f"{fixture['fixture_id']}:{fixture['scenario']}:{strategy_id}:"
        f"{result.signal_date}:{result.config_version}:{fixture['fixture_version']}"
    )
    return {
        "schema": _schema(F1_CONTRACT),
        "marker": FIXTURE_MARKER,
        "fixture": _fixture_view(fixture),
        "publication_identity": _publication_view(fixture),
        "batch": {
            "batch_id": batch_id,
            "batch_identity": "SYNTHETIC_FIXTURE_BATCH",
            "strategy_id": strategy_id,
            "signal_date": result.signal_date,
            "config_id": result.config_id,
            "config_version": result.config_version,
            "input_version": result.input_version,
            "bound_s01_config_version": result.bound_s01_config_version,
            "pool_size": result.pool_size,
            "candidate_size": result.candidate_size,
            "pool_complete": result.pool_complete,
            "available_at": records[0]["available_at"] if records else "UNKNOWN",
            "available_at_kind": records[0]["available_at_kind"] if records else "UNKNOWN",
            "actual_published": False,
            "actual_published_at": None,
            "fixture_declared_published_at": fixture["fixture_declared_published_at"],
            "history_ranking_writable": False,
        },
        "strategy": {
            "strategy_id": strategy_id,
            "config_id": result.config_id,
            "config_version": result.config_version,
            "input_version": result.input_version,
            "signal_date": result.signal_date,
            "pool_size": result.pool_size,
            "candidate_size": result.candidate_size,
            "pool_complete": result.pool_complete,
            "bound_s01_config_version": result.bound_s01_config_version,
        },
        "strategy_catalog": _strategy_catalog(results, records_by_strategy),
        "outcome": _outcome_payload(kind, result, records),
        "counts": {
            "formal_candidates": len(formal),
            "top_n_returned": len(candidates),
            "beyond_top_n": len(beyond),
            "preview_candidates": len(preview),
            "unknown_rows": len(unknown),
            "failed_rows": len(failed),
            "pool_size": result.pool_size,
            "kernel_candidate_size": result.candidate_size,
        },
        "quality": {
            "pool_complete": result.pool_complete,
            "universe_complete": snapshot.universe_complete,
            **counts,
        },
        "top_n": top_n,
        "candidates": candidates,
        "beyond_top_n": beyond,
        "preview_candidates": preview_rows,
        "unknown_rows": unknown_rows,
        "failed_rows": failed_rows,
        "notes": list(result.notes),
    }


def _dimension_view(dimension: DimensionResult) -> dict[str, Any]:
    return {
        "name": dimension.name,
        "raw_value": _json_value(dimension.raw_value),
        "raw_value_present": dimension.raw_value is not None,
        "unit": dimension.unit,
        "score": _json_value(dimension.score),
        "status": dimension.status.value,
        "pool_id": dimension.pool_id,
        "pool_size": dimension.pool_size,
        "pool_complete": dimension.pool_complete,
        "business_date": dimension.business_date,
        "window": dimension.window,
        "direction": dimension.direction,
        "explanation": dimension.explanation,
        "reason": dimension.reason,
        "extras": _json_value(dict(dimension.extras)),
        "missing": dimension.status in _MISSING_STATUSES,
        "unknown": dimension.status in _UNKNOWN_STATUSES,
        "not_applicable": dimension.status is ValueStatus.NOT_APPLICABLE,
    }


def _condition_details(record: Mapping[str, Any]) -> list[dict[str, str]]:
    return [
        {"name": str(name), "status": str(status)}
        for name, status in sorted(record["conditions"].items())
    ]


def build_f3(
    diagnostics: DiagnosticResult,
    results: Mapping[str, StrategyResult],
    snapshot: MarketSnapshot,
    *,
    fixture: Mapping[str, object],
    security_id: str,
    strategy_id: str = "S01",
) -> dict[str, Any]:
    if security_id not in snapshot.securities:
        raise KeyError(f"unknown security_id {security_id!r}")
    if strategy_id not in results:
        raise KeyError(f"unknown strategy_id {strategy_id!r}")

    records_by_strategy = _records_by_strategy(results)
    selected = _find_record(records_by_strategy, security_id, strategy_id)
    if selected is None:
        raise KeyError(f"security {security_id!r} is missing from strategy {strategy_id!r}")

    dimension_map = diagnostics.rows.get(security_id, {})
    ordered_names = [name for name in _SIX_DIMENSIONS if name in dimension_map]
    ordered_names.extend(name for name in dimension_map if name not in ordered_names)
    dimensions = [_dimension_view(dimension_map[name]) for name in ordered_names]

    missing_dimensions = [item["name"] for item in dimensions if item["missing"]]
    not_applicable_dimensions = [item["name"] for item in dimensions if item["not_applicable"]]
    dimension_counts = {
        "total": len(dimensions),
        "value": sum(1 for item in dimensions if item["status"] == ValueStatus.VALUE.value),
        "missing": len(missing_dimensions),
        "not_applicable": len(not_applicable_dimensions),
    }

    all_security_rows = [
        record
        for strategy in sorted(records_by_strategy)
        for record in records_by_strategy[strategy]
        if record["security_id"] == security_id
    ]
    all_security_rows.sort(key=lambda item: item["strategy_id"])
    strategy_rows = [_row_view(item) for item in all_security_rows]

    hit_strategies = [item["strategy_id"] for item in all_security_rows if item["signal_state"] == "CANDIDATE"]
    unknown_strategies = [item["strategy_id"] for item in all_security_rows if _is_unknown(item)]
    failed_strategies = [item["strategy_id"] for item in all_security_rows if _is_failed(item)]
    non_hit_strategies = [
        item["strategy_id"]
        for item in all_security_rows
        if item["signal_state"] != "CANDIDATE" and item["signal_state"] not in _UNKNOWN_STATES
    ]
    adverse_by_strategy = {
        item["strategy_id"]: [
            name
            for name, status in sorted(item["conditions"].items())
            if status == ConditionStatus.FALSE.value
        ]
        for item in all_security_rows
    }
    unknown_by_strategy = {
        item["strategy_id"]: [
            name
            for name, status in sorted(item["conditions"].items())
            if status == ConditionStatus.UNKNOWN.value
        ]
        for item in all_security_rows
    }
    reasons_by_strategy = {
        item["strategy_id"]: item["reasons"] for item in all_security_rows
    }

    security = snapshot.securities[security_id]
    conditions = _condition_details(selected)
    return {
        "schema": _schema(F3_CONTRACT),
        "marker": FIXTURE_MARKER,
        "fixture": _fixture_view(fixture),
        "publication_identity": _publication_view(fixture),
        "business_date": diagnostics.business_date,
        "security_id": security_id,
        "strategy_id": strategy_id,
        "security": {
            "security_id": security.security_id,
            "exchange": security.exchange,
            "board": security.board,
            "instrument_type": security.instrument_type,
            "industry_id": selected["industry_id"] or security.industry_id,
            "is_st": security.is_st,
            "is_delisting": security.is_delisting,
            "suspended": security.suspended,
        },
        "strategy_context": {
            "strategy_id": strategy_id,
            "config_id": selected["config_id"],
            "config_version": selected["config_version"],
            "signal_date": selected["signal_date"],
            "input_version": selected["input_version"],
            "available_at": selected["available_at"],
            "available_at_kind": selected["available_at_kind"],
        },
        "dimensions": dimensions,
        "missing_dimensions": missing_dimensions,
        "not_applicable_dimensions": not_applicable_dimensions,
        "dimension_counts": dimension_counts,
        "conditions": conditions,
        "positive_conditions": [item["name"] for item in conditions if item["status"] == ConditionStatus.TRUE.value],
        "adverse_conditions": [item["name"] for item in conditions if item["status"] == ConditionStatus.FALSE.value],
        "unknown_conditions": [item["name"] for item in conditions if item["status"] == ConditionStatus.UNKNOWN.value],
        "reasons": selected["reasons"],
        "adverse_conditions_by_strategy": adverse_by_strategy,
        "unknown_conditions_by_strategy": unknown_by_strategy,
        "reasons_by_strategy": reasons_by_strategy,
        "strategy_rows": strategy_rows,
        "divergence": {
            "hit_strategies": hit_strategies,
            "non_hit_strategies": non_hit_strategies,
            "unknown_strategies": unknown_strategies,
            "failed_strategies": failed_strategies,
            "signal_status_by_strategy": {
                item["strategy_id"]: item["signal_status"] for item in all_security_rows
            },
            "candidate_rank_by_strategy": {
                item["strategy_id"]: item["candidate_rank"] for item in all_security_rows
            },
            "sample_candidate_rank_by_strategy": {
                item["strategy_id"]: item["sample_candidate_rank"] for item in all_security_rows
            },
        },
        "score_policy": {
            "cross_strategy_total": None,
            "cross_strategy_prediction": None,
            "rule": "NO_CROSS_STRATEGY_TOTAL_SCORE",
        },
        "diagnostic_notes": list(diagnostics.notes),
        "time": {
            "business_date": diagnostics.business_date,
            "source_time": "UNKNOWN",
            "source_time_status": "UNKNOWN",
            "computed_at": fixture["computed_at"],
            "fixture_declared_published_at": fixture["fixture_declared_published_at"],
            "actual_published_at": None,
            "available_at": selected["available_at"] or "UNKNOWN",
            "available_at_kind": selected["available_at_kind"],
        },
    }


def _aggregate_counts(
    records_by_strategy: Mapping[str, Sequence[Mapping[str, Any]]]
) -> dict[str, Any]:
    total: dict[str, Any] = {}
    for records in records_by_strategy.values():
        for key, value in _counts(records).items():
            if isinstance(value, int):
                total[key] = total.get(key, 0) + value
            elif isinstance(value, dict):
                bucket = total.setdefault(key, {})
                for subkey, subvalue in value.items():
                    bucket[subkey] = bucket.get(subkey, 0) + subvalue
    return dict(sorted(total.items()))


def build_f7(
    results: Mapping[str, StrategyResult],
    snapshot: MarketSnapshot,
    *,
    fixture: Mapping[str, object],
) -> dict[str, Any]:
    records_by_strategy = _records_by_strategy(results)
    strategy_status: dict[str, dict[str, Any]] = {}
    for strategy_id in sorted(results):
        result = results[strategy_id]
        records = records_by_strategy[strategy_id]
        strategy_status[strategy_id] = {
            "strategy_id": strategy_id,
            "signal_date": result.signal_date,
            "config_id": result.config_id,
            "config_version": result.config_version,
            "input_version": result.input_version,
            "bound_s01_config_version": result.bound_s01_config_version,
            "pool_size": result.pool_size,
            "candidate_size": result.candidate_size,
            "pool_complete": result.pool_complete,
            "outcome": _f1_outcome(result, records),
            "counts": _counts(records),
            "notes": list(result.notes),
        }

    aggregate = _aggregate_counts(records_by_strategy)
    partial_strategies = [
        strategy_id for strategy_id, item in strategy_status.items() if not item["pool_complete"]
    ]
    failed_strategies = [
        strategy_id for strategy_id, item in strategy_status.items() if item["outcome"] == "FAILED"
    ]
    unknown_strategies = [
        strategy_id for strategy_id, item in strategy_status.items() if item["outcome"] == "UNKNOWN"
    ]
    empty_strategies = [
        strategy_id for strategy_id, item in strategy_status.items() if item["outcome"] == "EMPTY"
    ]
    complete_strategies = [
        strategy_id for strategy_id, item in strategy_status.items() if item["outcome"] == "CANDIDATES"
    ]

    available_at = snapshot.available_at
    return {
        "schema": _schema(F7_CONTRACT),
        "marker": FIXTURE_MARKER,
        "fixture": _fixture_view(fixture),
        "publication_identity": _publication_view(fixture),
        "business_date": snapshot.business_date,
        "coverage": {
            "universe_size": len(snapshot.securities),
            "universe_complete": snapshot.universe_complete,
            "industry_mapping_complete": snapshot.industry_mapping_complete,
            "industry_count": len(snapshot.industry_members),
            "calendar": {
                "start": snapshot.calendar[0],
                "end": snapshot.calendar[-1],
                "days": len(snapshot.calendar),
            },
            "business_date": snapshot.business_date,
            "input_version": snapshot.input_version,
            "taxonomy_id": snapshot.taxonomy_id,
            "taxonomy_version": snapshot.taxonomy_version,
            "strategies": strategy_status,
            "all_strategies_pool_complete": all(
                item["pool_complete"] for item in strategy_status.values()
            ),
        },
        "quality": {
            **aggregate,
            "partial_strategies": partial_strategies,
            "failed_strategies": failed_strategies,
            "unknown_strategies": unknown_strategies,
            "empty_strategies": empty_strategies,
            "candidate_strategies": complete_strategies,
        },
        "availability": {
            "source_time": "UNKNOWN",
            "source_time_status": "UNKNOWN",
            "source_times": {
                "price": "UNKNOWN",
                "financial": "UNKNOWN",
                "fund_flow": "UNKNOWN",
                "industry": "UNKNOWN",
            },
            "source_time_basis": "FIXTURE_HAS_NO_REAL_SOURCE_TIMESTAMP",
            "fetched_at": "UNKNOWN",
            "fetched_at_status": "UNKNOWN",
            "computed_at": fixture["computed_at"],
            "computed_at_status": "FIXTURE_DECLARED",
            "fixture_declared_published_at": fixture["fixture_declared_published_at"],
            "actual_published_at": None,
            "available_at": available_at or "UNKNOWN",
            "available_at_kind": _available_at_kind(available_at, snapshot.input_version),
            "availability_status": "SYNTHETIC_ONLY" if available_at is not None else "UNKNOWN",
        },
        "gates": {
            "real_market_data": False,
            "real_source_used": False,
            "actual_published": False,
            "formal_history_ranking": False,
            "current_scan_qualified": False,
            "historical_replay_qualified": False,
        },
        "notes": sorted({note for result in results.values() for note in result.notes}),
    }


def build_result_bundle(
    scenario: str,
    *,
    strategy_id: str = "S01",
    top_n: int = 10,
    security_id: str | None = None,
) -> dict[str, Any]:
    snapshot = build_fixture_snapshot(scenario)
    fixture = fixture_metadata(scenario)
    results = compute_all(snapshot)
    diagnostics = compute_diagnostics(snapshot)

    f1 = build_f1(results, snapshot, fixture=fixture, strategy_id=strategy_id, top_n=top_n)

    if security_id is None:
        if f1["candidates"]:
            security_id = f1["candidates"][0]["security_id"]
        elif f1["preview_candidates"]:
            security_id = f1["preview_candidates"][0]["security_id"]
        else:
            security_id = sorted(snapshot.securities)[0]

    f3 = build_f3(
        diagnostics,
        results,
        snapshot,
        fixture=fixture,
        security_id=security_id,
        strategy_id=strategy_id,
    )
    f7 = build_f7(results, snapshot, fixture=fixture)
    return {
        "schema": _schema("MISHI-FX01A-RESULT-BUNDLE"),
        "marker": FIXTURE_MARKER,
        "fixture": _fixture_view(fixture),
        "publication_identity": _publication_view(fixture),
        "f1": f1,
        "f3": f3,
        "f7": f7,
    }


def dumps(payload: Mapping[str, Any]) -> str:
    """Serialize a contract payload deterministically."""

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)

