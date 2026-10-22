"""OD-2 daily cash, order, position and NAV engine.

The engine intentionally knows nothing about S01-S08 conditions.  It consumes
structured signals and exit decisions, and owns only portfolio mechanics,
execution restrictions, fees, corporate actions and accounting.
"""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import Iterable, Mapping, Sequence

from .accounting import (
    allocate_sale_cost,
    cycle_total_pnl,
    remaining_open_stop_ratio,
    split_dividend_entitlement,
)
from ..time_contract import parse_local_datetime, validate_local_datetime
from .model import (
    BacktestConfig,
    BacktestInput,
    BacktestResult,
    ClosedCycle,
    CorporateAction,
    DailyBar,
    DividendTaxBinding,
    EligibilityRecord,
    EligibilitySnapshot,
    ExitRequest,
    FeeSchedule,
    Fill,
    Lot,
    MarketDay,
    NavPoint,
    Order,
    Position,
    PositionSnapshot,
    Signal,
    SignalBatch,
    TradingRule,
    dec,
)

CENT = Decimal("0.01")
ZERO = Decimal("0")


class _Blocked(Exception):
    pass


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _floor_tick(value: Decimal, tick: Decimal) -> Decimal:
    return (value / tick).to_integral_value(rounding=ROUND_FLOOR) * tick


def _ceil_tick(value: Decimal, tick: Decimal) -> Decimal:
    return (value / tick).to_integral_value(rounding=ROUND_CEILING) * tick


def _round_tick(value: Decimal, tick: Decimal) -> Decimal:
    return (value / tick).to_integral_value(rounding=ROUND_HALF_UP) * tick


def _action_key(action: CorporateAction) -> str:
    return "|".join(
        [
            action.security_id,
            action.action_type,
            action.effective_date,
            action.record_date or "",
            action.pay_date or "",
            str(action.cash_per_share or ""),
            str(action.share_multiplier or ""),
        ]
    )


class _Engine:
    def __init__(self, data: BacktestInput, config: BacktestConfig):
        self.data = data
        self.config = config
        self.full_calendar = list(data.calendar)
        self.start_date = config.start_date or self.full_calendar[0]
        self.end_date = config.end_date or self.full_calendar[-1]
        if self.start_date not in self.full_calendar:
            raise ValueError("start_date is not in the market calendar")
        if self.end_date not in self.full_calendar:
            raise ValueError("end_date is not in the market calendar")
        start_index = self.full_calendar.index(self.start_date)
        end_index = self.full_calendar.index(self.end_date)
        if start_index > end_index:
            raise ValueError("start_date must not be after end_date")
        self.start_index = start_index
        self.dates = self.full_calendar[start_index : end_index + 1]

        self.cash = config.initial_cash
        self.positions: dict[str, Position] = {}
        self.legacy_positions: list[Position] = []
        self.receivables = ZERO
        self.payables = ZERO
        self.total_fees = ZERO
        self.total_commission = ZERO
        self.total_tax = ZERO
        self.orders: list[Order] = []
        self.fills: list[Fill] = []
        self.nav_points: list[NavPoint] = []
        self.position_history: list[PositionSnapshot] = []
        self.closed_cycles: list[ClosedCycle] = []
        self.reconciliation: list[dict] = []
        self.warnings: list[str] = []
        self.blockers: list[str] = []
        self.locked_exits: dict[str, list[ExitRequest]] = {}
        self.pending_batches: list[dict] = []
        self.proposal_entries: list[dict] = []
        self.eligibility_entries: list[dict] = []
        self.fee_entries: list[dict] = []
        self.dividend_tax_entries: list[dict] = []
        self.dividend_entitlements: dict[str, tuple[str, int]] = {}
        self.pending_actions: dict[str, CorporateAction] = {}
        self.external_dividend_claims: list[dict] = []
        self.dividend_payments: list[dict] = []
        self.cash_adjustments: list[dict] = []
        self.order_counter = 0
        self.lot_counter = 0
        self.exited_today: set[str] = set()
        self.today_buy_gross = ZERO
        self.today_sell_gross = ZERO
        self.today_sell_gross_by_security: dict[str, Decimal] = {}
        self.today_sell_fees_by_security: dict[str, tuple[Decimal, Decimal]] = {}
        self.prev_equity = config.initial_cash
        self.prev_nav = Decimal(1)
        self.nav_peak = Decimal(1)
        self.benchmark_base: Decimal | None = None
        self.actions_by_record: dict[str, list[CorporateAction]] = {}
        self.actions_by_effective: dict[str, list[CorporateAction]] = {}
        self.actions_by_pay: dict[str, list[CorporateAction]] = {}
        self.corporate_action_coverage: dict[str, bool] = {}

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def _prepare(self) -> None:
        for schedule in self._fee_candidates():
            if schedule.known_at is not None:
                validate_local_datetime(schedule.known_at, field="known_at")
            elif not schedule.synthetic:
                raise _Blocked(f"FEE_SCHEDULE_KNOWN_AT_MISSING:{schedule.version}")
        if self.data.fee_schedule is not None and not self.data.fee_schedules:
            if not self.data.fee_schedule.applies(self.start_date):
                raise _Blocked("FEE_SCHEDULE_NOT_APPLICABLE_AT_START")
        boundaries = tuple(self.config.segment_boundaries)
        if boundaries:
            if len(set(boundaries)) != len(boundaries) or tuple(sorted(boundaries)) != boundaries:
                raise _Blocked("SEGMENT_BOUNDARIES_INVALID")
            if any(boundary not in self.dates or boundary <= self.start_date for boundary in boundaries):
                raise _Blocked("SEGMENT_BOUNDARY_NOT_IN_RANGE")
        for date in self.dates:
            if date not in self.data.market_days:
                raise _Blocked(f"MARKET_DAY_MISSING:{date}")
            day = self.data.market_days[date]
            if not day.corporate_actions_complete:
                self.corporate_action_coverage[date] = False
            for action in day.corporate_actions:
                if action.record_date:
                    self.actions_by_record.setdefault(action.record_date, []).append(action)
                self.actions_by_effective.setdefault(action.effective_date, []).append(action)
                if action.pay_date:
                    self.actions_by_pay.setdefault(action.pay_date, []).append(action)
        first_day = self.data.market_days[self.start_date]
        if first_day.benchmark_open is None:
            raise _Blocked("BENCHMARK_OPEN_UNKNOWN_AT_START")
        self.benchmark_base = first_day.benchmark_open
        for date in self.dates:
            if self.data.market_days[date].benchmark_close is None:
                raise _Blocked(f"BENCHMARK_CLOSE_UNKNOWN:{date}")

    # ------------------------------------------------------------------
    # Main day loop
    # ------------------------------------------------------------------

    def _holdings(self) -> dict[str, Position]:
        holdings = dict(self.positions)
        for index, position in enumerate(self.legacy_positions):
            holdings[f"{position.security_id}#LEGACY{index}"] = position
        return holdings

    def _remove_position(self, position: Position) -> None:
        sid = position.security_id
        if self.positions.get(sid) is position:
            del self.positions[sid]
        elif position in self.legacy_positions:
            self.legacy_positions.remove(position)

    def _has_holding(self, security_id: str) -> bool:
        if security_id in self.positions:
            return True
        return any(
            position.security_id == security_id and position.quantity > 0
            for position in self.legacy_positions
        )

    def _run_day(self, date: str, day_index: int) -> None:
        day = self.data.market_days[date]
        self.current_date = date
        self.exited_today = set()
        self.today_buy_gross = ZERO
        self.today_sell_gross = ZERO
        self.today_sell_gross_by_security = {}
        self.today_sell_fees_by_security = {}
        full_index = self.full_calendar.index(date)
        previous_date = self.full_calendar[full_index - 1] if full_index > 0 else None
        raw_signals = self.data.signals_by_signal_date.get(previous_date, ()) if previous_date else ()
        relevant_ids = (
            set(self.positions)
            | {position.security_id for position in self.legacy_positions}
            | {signal.security_id for signal in raw_signals}
        )
        self._apply_corporate_actions(date, day, relevant_ids)
        self._process_external_dividend_claims(date)
        self._process_dividend_payments(date)

        if previous_date is not None:
            for request in self.data.exit_requests_by_signal_date.get(previous_date, ()):
                self._add_locked_exit(request)

        holdings = self._holdings()
        for position in holdings.values():
            if position.holding_start < date:
                position.holding_days += 1

        mark_open: dict[str, Decimal] = {}
        open_values: dict[str, Decimal] = {}
        for key, position in holdings.items():
            price = self._mark_open(date, position.security_id, position)
            mark_open[key] = price
            open_values[key] = Decimal(position.quantity) * price
        e_open = self.cash + self.receivables - self.payables + sum(open_values.values(), ZERO)
        target_weight = e_open / Decimal(self.config.top_n) if e_open > 0 else ZERO

        is_rebalance = (self.full_calendar.index(date) - self.start_index) % self.config.rebalance_days == 0
        if self.data.signal_batches:
            signals, deferred_batches, normal_decision = self._update_batches(date, is_rebalance)
        else:
            signals = self._signals_for_trade_date(previous_date, date)
            deferred_batches = []
            normal_decision = True
        effective_rebalance = is_rebalance and normal_decision
        candidate_pool, targets = self._build_targets(signals)
        target_ids = {signal.security_id for signal in targets}

        self._apply_eligibility_locks(date)
        locked_ids = {sid for sid, requests in self.locked_exits.items() if requests}
        sell_plan = self._build_sell_plan(
            date,
            mark_open,
            open_values,
            target_weight,
            target_ids,
            effective_rebalance,
            locked_ids,
            previous_date,
        )
        for key in sorted(sell_plan, key=lambda item: self._sell_sort_key(item, sell_plan[item])):
            plan = sell_plan[key]
            self._execute_sell(
                date,
                plan["position"],
                plan["quantity"],
                plan["reasons"],
                plan["locked"],
                plan["exit_intent"],
                plan["signal_date"],
            )

        if effective_rebalance:
            self._execute_buys(date, targets, mark_open, target_weight, candidate_pool)

        for pending in deferred_batches:
            deferred_signals = list(pending["batch"].signals)
            deferred_candidates, deferred_targets = self._build_targets(deferred_signals)
            before_fills = len(self.fills)
            self._execute_buys(
                date,
                deferred_targets,
                mark_open,
                target_weight,
                deferred_candidates,
            )
            self._record_proposal(
                pending["batch"],
                "FILLED" if len(self.fills) > before_fills else "ATTEMPT_FAILED",
                "DEFERRED_ATTEMPT",
                date,
            )

        self._close_day(date, day, mark_open, e_open, target_weight)

    # ------------------------------------------------------------------
    # Signals and target construction
    # ------------------------------------------------------------------

    def _build_targets(self, signals: Sequence[Signal]) -> tuple[list[Signal], list[Signal]]:
        eligible_signals = [
            signal
            for signal in signals
            if signal.strategy_id == self.config.strategy_id
            and signal.qualification_status == "SCORABLE"
            and signal.entry_conflict_exit != "TRUE"
        ]
        if self.config.strategy_id == "S06":
            candidate_pool = [
                signal
                for signal in eligible_signals
                if signal.signal_status == "TRUE"
                or signal.signal_state == "CONCENTRATION_EXCLUDED"
            ]
            formal_targets = [signal for signal in candidate_pool if signal.formal_candidate]
        else:
            candidate_pool = [signal for signal in eligible_signals if signal.signal_status == "TRUE"]
            formal_targets = list(candidate_pool)
        candidate_pool.sort(key=self._candidate_sort_key)
        formal_targets.sort(key=self._candidate_sort_key)
        return candidate_pool, formal_targets[: self.config.top_n]

    def _batch_anchor(self, batch: SignalBatch) -> str | None:
        try:
            index = self.full_calendar.index(batch.signal_date)
        except ValueError:
            raise _Blocked(f"SIGNAL_BATCH_DATE_NOT_IN_CALENDAR:{batch.batch_id}")
        if index + 1 >= len(self.full_calendar):
            return None
        return self.full_calendar[index + 1]

    @staticmethod
    def _signal_available_instant(signal: Signal) -> datetime | None:
        if signal.available_at is None:
            return None
        value = signal.available_at
        if len(value) == 10:
            close = "T15:00:00" if signal.available_at_kind == "NORMALIZED_AVAILABLE_DATE" else "T00:00:00"
            return datetime.fromisoformat(f"{value}{close}")
        return parse_local_datetime(value, field="available_at")

    def _batch_decision_instant(self, batch: SignalBatch) -> datetime:
        effective = parse_local_datetime(
            batch.decision_available_at, field="decision_available_at"
        )
        for signal in batch.signals:
            if not signal.pool_complete:
                raise _Blocked(f"SIGNAL_POOL_INCOMPLETE:{batch.batch_id}:{signal.security_id}")
            instant = self._signal_available_instant(signal)
            if instant is None:
                raise _Blocked(
                    f"SIGNAL_AVAILABILITY_UNKNOWN:{batch.batch_id}:{signal.security_id}"
                )
            if instant > effective:
                effective = instant
        return effective

    @staticmethod
    def _open_instant(trade_date: str) -> datetime:
        return datetime.fromisoformat(f"{trade_date}T09:30:00")

    def _batch_available_before_open(self, batch: SignalBatch, trade_date: str) -> bool:
        try:
            return self._batch_decision_instant(batch) < self._open_instant(trade_date)
        except ValueError as exc:
            raise _Blocked(f"SIGNAL_BATCH_AVAILABILITY_INVALID:{batch.batch_id}:{exc}") from exc

    def _batch_first_eligible_open(self, batch: SignalBatch) -> str | None:
        anchor = self._batch_anchor(batch)
        if anchor is None:
            return None
        start = self.full_calendar.index(anchor)
        for day in self.full_calendar[start:]:
            if self._batch_available_before_open(batch, day):
                return day
        return None

    def _require_batch_coverage(self, batch: SignalBatch, date: str) -> None:
        if batch.coverage_until is None:
            self._record_proposal(batch, "BLOCKED", "COVERAGE_UNKNOWN", date)
            raise _Blocked(f"SIGNAL_BATCH_COVERAGE_UNKNOWN:{batch.batch_id}")
        try:
            covered = parse_local_datetime(
                batch.coverage_until, field="coverage_until"
            ) >= self._open_instant(date)
        except ValueError as exc:
            raise _Blocked(f"SIGNAL_BATCH_COVERAGE_INVALID:{batch.batch_id}:{exc}") from exc
        if not covered:
            self._record_proposal(batch, "BLOCKED", "COVERAGE_INCOMPLETE", date)
            raise _Blocked(f"SIGNAL_BATCH_COVERAGE_INCOMPLETE:{batch.batch_id}")

    def _record_proposal(
        self,
        batch: SignalBatch,
        status: str,
        reason: str,
        date: str | None,
    ) -> None:
        self.proposal_entries.append(
            {
                "batch_id": batch.batch_id,
                "scope_key": batch.scope_key,
                "strategy_id": batch.strategy_id,
                "config_id": batch.config_id,
                "config_version": batch.config_version,
                "signal_date": batch.signal_date,
                "available_at": batch.available_at,
                "published_at": batch.published_at,
                "decision_available_at": batch.decision_available_at,
                "anchor_date": self._batch_anchor(batch),
                "coverage_until": batch.coverage_until,
                "status": status,
                "reason": reason,
                "date": date,
                "signal_count": len(batch.signals),
            }
        )

    def _replacement_for(self, pending: dict, open_at: str) -> SignalBatch | None:
        old: SignalBatch = pending["batch"]
        old_available = self._batch_decision_instant(old)
        open_time = parse_local_datetime(open_at, field="trade_open")
        candidates: list[tuple[datetime, SignalBatch]] = []
        for batch in self.data.signal_batches:
            if (
                batch.strategy_id != self.config.strategy_id
                or batch.scope_key != old.scope_key
                or batch.batch_id == old.batch_id
                or batch.signal_date < old.signal_date
            ):
                continue
            available = self._batch_decision_instant(batch)
            if old_available < available <= open_time:
                candidates.append((available, batch))
        candidates.sort(key=lambda item: (item[0], item[1].signal_date, item[1].batch_id))
        for _available, batch in candidates:
            if batch.status in {"UNKNOWN", "INCOMPLETE"}:
                self._record_proposal(batch, "BLOCKED", "SIGNAL_BATCH_UNKNOWN", open_at[:10])
                raise _Blocked(f"SIGNAL_BATCH_UNKNOWN:{batch.batch_id}")
            if batch.complete:
                return batch
        return None

    def _update_batches(
        self, date: str, is_rebalance: bool
    ) -> tuple[list[Signal], list[dict], bool]:
        open_at = f"{date}T09:30:00"
        batches = [
            batch
            for batch in self.data.signal_batches
            if batch.strategy_id == self.config.strategy_id
        ]

        for pending in list(self.pending_batches):
            replacement = self._replacement_for(pending, open_at)
            if replacement is not None:
                self._record_proposal(
                    pending["batch"],
                    "REPLACED",
                    f"REPLACED_BY:{replacement.batch_id}",
                    date,
                )
                self.pending_batches.remove(pending)

        for batch in batches:
            anchor = self._batch_anchor(batch)
            if anchor is None or anchor > date:
                continue
            if parse_local_datetime(
                batch.decision_available_at, field="decision_available_at"
            ) > parse_local_datetime(open_at, field="trade_open"):
                continue
            if batch.status in {"UNKNOWN", "INCOMPLETE"}:
                self._record_proposal(batch, "BLOCKED", "SIGNAL_BATCH_UNKNOWN", date)
                raise _Blocked(f"SIGNAL_BATCH_UNKNOWN:{batch.batch_id}")

        normal_signals: list[Signal] = []
        normal_decision = False
        for batch in batches:
            anchor = self._batch_anchor(batch)
            if anchor != date:
                continue
            if batch.status in {"UNKNOWN", "INCOMPLETE"}:
                if parse_local_datetime(
                    batch.decision_available_at, field="decision_available_at"
                ) <= parse_local_datetime(open_at, field="trade_open"):
                    self._record_proposal(batch, "BLOCKED", "SIGNAL_BATCH_UNKNOWN", date)
                    raise _Blocked(f"SIGNAL_BATCH_UNKNOWN:{batch.batch_id}")
                self._record_proposal(batch, "IGNORED", "UNKNOWN_NOT_YET_AVAILABLE", date)
                continue
            if batch.status == "NO_PUBLICATION":
                self._record_proposal(batch, "NO_PUBLICATION", "CONFIRMED_NO_RELEASE", date)
                continue
            if batch.status == "COMPLETE_EMPTY":
                if self._batch_available_before_open(batch, date):
                    self._require_batch_coverage(batch, date)
                    normal_decision = True
                    self._record_proposal(batch, "EMPTY", "COMPLETE_EMPTY_BATCH", date)
                    continue
                if not is_rebalance:
                    self._record_proposal(batch, "IGNORED", "NON_REBALANCE_NEW_BATCH", date)
                    continue
                first_eligible = self._batch_first_eligible_open(batch)
                if first_eligible is None:
                    if batch.coverage_until is None:
                        self._record_proposal(batch, "BLOCKED", "COVERAGE_UNKNOWN", date)
                        raise _Blocked(f"SIGNAL_BATCH_COVERAGE_UNKNOWN:{batch.batch_id}")
                    self.pending_batches.append(
                        {
                            "batch": batch,
                            "anchor_date": anchor,
                            "first_eligible_open": None,
                            "attempted": False,
                            "empty": True,
                        }
                    )
                    self._record_proposal(
                        batch, "PENDING", "AWAITING_FIRST_ELIGIBLE_OPEN", date
                    )
                    continue
                self.pending_batches.append(
                    {
                        "batch": batch,
                        "anchor_date": anchor,
                        "first_eligible_open": first_eligible,
                        "attempted": False,
                        "empty": True,
                    }
                )
                self._record_proposal(batch, "PENDING", "AVAILABLE_AFTER_ANCHOR_OPEN", date)
                continue
            if batch.status != "COMPLETE":
                continue
            if self._batch_available_before_open(batch, date):
                normal_decision = True
                if is_rebalance:
                    self._require_batch_coverage(batch, date)
                    self._record_proposal(batch, "NORMAL", "AVAILABLE_BEFORE_ANCHOR_OPEN", date)
                    normal_signals.extend(batch.signals)
                else:
                    self._record_proposal(batch, "IGNORED", "NON_REBALANCE_NEW_BATCH", date)
                continue
            if not is_rebalance:
                self._record_proposal(batch, "IGNORED", "NON_REBALANCE_NEW_BATCH", date)
                continue
            first_eligible = self._batch_first_eligible_open(batch)
            if first_eligible is None:
                if batch.coverage_until is None:
                    self._record_proposal(batch, "BLOCKED", "COVERAGE_UNKNOWN", date)
                    raise _Blocked(f"SIGNAL_BATCH_COVERAGE_UNKNOWN:{batch.batch_id}")
                self.pending_batches.append(
                    {
                        "batch": batch,
                        "anchor_date": anchor,
                        "first_eligible_open": None,
                        "attempted": False,
                        "empty": False,
                    }
                )
                self._record_proposal(
                    batch, "PENDING", "AWAITING_FIRST_ELIGIBLE_OPEN", date
                )
                continue
            pending = {
                "batch": batch,
                "anchor_date": anchor,
                "first_eligible_open": first_eligible,
                "attempted": False,
                "empty": False,
            }
            self.pending_batches.append(pending)
            self._record_proposal(batch, "PENDING", "AVAILABLE_AFTER_ANCHOR_OPEN", date)

        ready: list[dict] = []
        for pending in list(self.pending_batches):
            first_eligible = pending["first_eligible_open"]
            if first_eligible is None or date < first_eligible:
                continue
            batch = pending["batch"]
            self._require_batch_coverage(batch, date)
            pending["attempted"] = True
            self.pending_batches.remove(pending)
            if pending.get("empty"):
                self._record_proposal(batch, "EMPTY", "COMPLETE_EMPTY_BATCH", date)
                continue
            self._record_proposal(batch, "ATTEMPTING", "DEFERRED_ATTEMPT", date)
            ready.append(pending)
        return normal_signals, ready, normal_decision

    def _eligibility_status(self, date: str, security_id: str) -> tuple[str, str | None]:
        if not self.data.eligibility_by_date:
            if not self.config.synthetic:
                raise _Blocked(f"ELIGIBILITY_COVERAGE_MISSING:{date}")
            return "ELIGIBLE", None
        snapshot = self.data.eligibility_by_date.get(date)
        if snapshot is None:
            raise _Blocked(f"ELIGIBILITY_COVERAGE_MISSING:{date}")
        if not snapshot.complete:
            raise _Blocked(f"ELIGIBILITY_COVERAGE_INCOMPLETE:{date}")
        open_at = parse_local_datetime(f"{date}T09:30:00", field="trade_open")
        records = [
            record
            for record in snapshot.records
            if record.security_id == security_id and record.applies(date)
        ]
        if not records:
            return "UNKNOWN", "ELIGIBILITY_RECORD_MISSING"
        usable = [
            record
            for record in records
            if parse_local_datetime(record.known_at, field="known_at") < open_at
        ]
        if not usable:
            if any(parse_local_datetime(record.known_at, field="known_at") >= open_at for record in records):
                raise _Blocked(f"ELIGIBILITY_NOT_KNOWN_AT_OPEN:{security_id}:{date}")
            return "UNKNOWN", "ELIGIBILITY_NOT_YET_KNOWN"
        statuses = {record.status for record in usable}
        if len(statuses) > 1:
            raise _Blocked(f"ELIGIBILITY_CONFLICT:{security_id}:{date}")
        chosen = max(usable, key=lambda record: (record.known_at, record.version))
        return chosen.status, chosen.reason or None

    def _apply_eligibility_locks(self, date: str) -> None:
        if not self.data.eligibility_by_date:
            return
        for position in self._holdings().values():
            status, reason = self._eligibility_status(date, position.security_id)
            self.eligibility_entries.append(
                {
                    "date": date,
                    "security_id": position.security_id,
                    "status": status,
                    "reason": reason,
                }
            )
            if status == "INELIGIBLE":
                self._add_locked_exit(
                    ExitRequest(
                        security_id=position.security_id,
                        reason="ELIGIBILITY_RISK",
                        trigger_date=date,
                        priority=2,
                        strategy_id=position.strategy_id,
                    )
                )

    def _signals_for_trade_date(self, previous_date: str | None, trade_date: str) -> list[Signal]:
        if previous_date is None:
            return []
        signals = list(self.data.signals_by_signal_date.get(previous_date, ()))
        strategy_signals = [signal for signal in signals if signal.strategy_id == self.config.strategy_id]
        if strategy_signals and not self.config.synthetic:
            raise _Blocked(
                f"LEGACY_SIGNAL_ROUTE_REQUIRES_SYNTHETIC_COMPAT:"
                f"{self.config.strategy_id}:{previous_date}"
            )
        if any(not signal.pool_complete for signal in strategy_signals):
            raise _Blocked(f"SIGNAL_POOL_INCOMPLETE:{self.config.strategy_id}:{previous_date}")
        result: list[Signal] = []
        for signal in signals:
            if signal.signal_date != previous_date:
                self.warnings.append(f"SIGNAL_DATE_MISMATCH:{signal.security_id}:{signal.signal_date}!={previous_date}")
                continue
            if signal.strategy_id == self.config.strategy_id and signal.qualification_status == "SCORABLE" and signal.signal_status == "TRUE":
                if signal.formal_candidate and signal.candidate_rank is None:
                    raise _Blocked(f"CANDIDATE_RANK_MISSING:{signal.security_id}")
            execution_date = self._execution_date(signal)
            if execution_date is None:
                self.warnings.append(
                    f"LEGACY_SIGNAL_PENDING_OUTSIDE_REPLAY:{signal.security_id}:{signal.signal_date}"
                )
                continue
            if execution_date > trade_date:
                next_signals = [
                    item
                    for item in self.data.signals_by_signal_date.get(trade_date, ())
                    if item.strategy_id == self.config.strategy_id
                ]
                if not next_signals:
                    raise _Blocked(
                        f"LEGACY_SIGNAL_REQUIRES_BATCH:{signal.security_id}:{signal.signal_date}"
                    )
                self._record_simple_order(
                    signal,
                    trade_date,
                    "EXPIRED",
                    "EXPIRED_INPUT_WINDOW",
                )
                continue
            result.append(signal)
        return result

    def _execution_date(self, signal: Signal) -> str | None:
        try:
            base_index = self.full_calendar.index(signal.signal_date)
        except ValueError:
            raise _Blocked(f"SIGNAL_DATE_NOT_IN_CALENDAR:{signal.security_id}:{signal.signal_date}")
        next_index = base_index + 1
        if next_index >= len(self.full_calendar):
            return None
        first_open = self.full_calendar[next_index]
        instant = self._signal_available_instant(signal)
        if instant is None:
            if self.config.require_known_signal_availability:
                raise _Blocked(f"SIGNAL_AVAILABILITY_UNKNOWN:{signal.security_id}")
            return first_open
        if instant < self._open_instant(first_open):
            return first_open
        for date in self.full_calendar[next_index + 1 :]:
            if instant < self._open_instant(date):
                return date
        return None

    @staticmethod
    def _candidate_sort_key(signal: Signal) -> tuple:
        return (
            signal.candidate_rank if signal.candidate_rank is not None else 10**9,
            signal.pool_rank if signal.pool_rank is not None else 10**9,
            signal.security_id,
        )

    def _build_sell_plan(
        self,
        date: str,
        mark_open: Mapping[str, Decimal],
        open_values: Mapping[str, Decimal],
        target_weight: Decimal,
        target_ids: set[str],
        is_rebalance: bool,
        locked_ids: set[str],
        previous_date: str | None,
    ) -> dict[str, dict]:
        plan: dict[str, dict] = {}
        for key, position in self._holdings().items():
            sid = position.security_id
            is_legacy = position in self.legacy_positions
            reasons: list[str] = []
            locked = sid in locked_ids
            exit_intent = locked
            quantity = 0
            signal_date = previous_date
            if locked:
                requests = self.locked_exits.get(sid, ())
                reasons = [request.reason for request in requests]
                signal_date = min(request.trigger_date for request in requests) if requests else previous_date
                quantity = position.quantity
            elif is_rebalance and not is_legacy:
                if sid not in target_ids:
                    if not any(
                        request.reason == "RANK_REMOVAL"
                        for request in self.locked_exits.get(sid, ())
                    ):
                        self._add_locked_exit(
                            ExitRequest(
                                security_id=sid,
                                reason="RANK_REMOVAL",
                                trigger_date=previous_date or date,
                                priority=4,
                                strategy_id=position.strategy_id,
                            )
                        )
                    locked = True
                    exit_intent = True
                    requests = self.locked_exits.get(sid, ())
                    reasons = [request.reason for request in requests]
                    signal_date = (
                        min(request.trigger_date for request in requests)
                        if requests
                        else previous_date
                    )
                    quantity = position.quantity
                else:
                    current_value = open_values.get(key, ZERO)
                    if current_value > target_weight:
                        sell_price = self._probe_sell_price(date, sid)
                        if sell_price is not None and sell_price > 0:
                            excess = current_value - target_weight
                            quantity = int((excess / sell_price).to_integral_value(rounding=ROUND_FLOOR))
                            if quantity > 0:
                                reasons = ["TARGET_WEIGHT_REDUCTION"]
            if quantity > 0:
                plan[key] = {
                    "quantity": min(quantity, position.quantity),
                    "reasons": reasons,
                    "locked": locked,
                    "exit_intent": exit_intent,
                    "signal_date": signal_date,
                    "position": position,
                }
        return plan

    @staticmethod
    def _sell_sort_key(sid: str, plan: Mapping) -> tuple:
        return (0 if plan["locked"] else 1, plan["signal_date"] or "", sid)

    def _execute_buys(
        self,
        date: str,
        targets: Sequence[Signal],
        mark_open: Mapping[str, Decimal],
        target_weight: Decimal,
        all_candidates: Sequence[Signal],
    ) -> None:
        used: set[str] = set()

        def attempt(signal: Signal, replacement_for: Signal | None = None, replacement_reason: str | None = None) -> bool:
            if len(self.positions) >= self.config.top_n and signal.security_id not in self.positions:
                return False
            if signal.security_id in self.exited_today:
                return False
            existing = self.positions.get(signal.security_id)
            if existing is not None and signal.strategy_id == "S04":
                return False
            used.add(signal.security_id)
            filled, _reason = self._try_buy(
                date,
                signal,
                mark_open.get(signal.security_id),
                target_weight,
                replacement_for=replacement_for,
                replacement_reason=replacement_reason,
            )
            return filled

        for index, target in enumerate(targets):
            if len(self.positions) >= self.config.top_n and target.security_id not in self.positions:
                continue
            if target.security_id in used:
                continue
            filled, reason = False, None
            if target.security_id not in self.exited_today:
                existing = self.positions.get(target.security_id)
                if not (existing is not None and target.strategy_id == "S04"):
                    used.add(target.security_id)
                    filled, reason = self._try_buy(
                        date, target, mark_open.get(target.security_id), target_weight
                    )
            if filled or reason is None:
                continue
            if self.config.strategy_id == "S06" and target.formal_candidate:
                replacements = self._s06_replacements(target, all_candidates, used, date)
            else:
                replacements = [
                    candidate
                    for candidate in all_candidates[index + 1 :]
                    if candidate.security_id not in used
                    and candidate.security_id not in self.positions
                    and candidate.security_id not in self.exited_today
                ]
            for replacement in replacements:
                if replacement.security_id in used or replacement.security_id in self.positions:
                    continue
                if replacement.security_id in self.exited_today:
                    continue
                if attempt(replacement, replacement_for=target, replacement_reason=reason):
                    break

        if self.config.strategy_id != "S06":
            for candidate in all_candidates[len(targets) :]:
                if len(self.positions) >= self.config.top_n:
                    break
                if candidate.security_id in used or candidate.security_id in self.positions:
                    continue
                if candidate.security_id in self.exited_today:
                    continue
                attempt(candidate)

    def _s06_replacements(
        self,
        target: Signal,
        candidates: Sequence[Signal],
        used: set[str],
        date: str,
    ) -> list[Signal]:
        if target.industry_id is None:
            return []
        replacements = [
            candidate
            for candidate in candidates
            if candidate.industry_id == target.industry_id
            and candidate.security_id not in used
            and candidate.security_id not in self.positions
            and candidate.security_id not in self.exited_today
            and not candidate.formal_candidate
            and candidate.signal_state == "CONCENTRATION_EXCLUDED"
            and candidate.qualification_status == "SCORABLE"
            and candidate.entry_conflict_exit != "TRUE"
        ]
        replacements.sort(
            key=lambda item: (
                item.industry_trigger_rank if item.industry_trigger_rank is not None else 10**9,
                item.execution_replacement_order if item.execution_replacement_order is not None else 10**9,
                item.security_id,
            )
        )
        return replacements

    # ------------------------------------------------------------------
    # Orders
    # ------------------------------------------------------------------

    def _execute_sell(
        self,
        date: str,
        position: Position,
        requested_quantity: int,
        reasons: Sequence[str],
        locked: bool,
        exit_intent: bool,
        signal_date: str | None,
    ) -> None:
        sid = position.security_id
        bar = self._bar(date, sid)
        rule = self._rule(date, sid)
        if bar is None:
            raise _Blocked(f"SELL_BAR_MISSING:{sid}:{date}")
        if rule is None:
            raise _Blocked(f"TRADING_RULE_UNKNOWN:{sid}:{date}")
        if bar.suspended is True:
            self._record_order(
                sid,
                "SELL",
                date,
                requested_quantity,
                "UNFILLED",
                reason="SUSPENDED",
                strategy_id=position.strategy_id,
                signal_date=signal_date,
            )
            return
        if bar.suspended is None:
            raise _Blocked(f"TRADING_STATUS_UNKNOWN:{sid}:{date}")
        if bar.data_status != "OK":
            raise _Blocked(f"SELL_BAR_STATUS_UNKNOWN:{sid}:{date}:{bar.data_status}")
        if bar.open is None or bar.open <= 0:
            raise _Blocked(f"SELL_OPEN_PRICE_UNKNOWN:{sid}:{date}")
        fee_schedule = self._fee_schedule(date, sid, "SELL")
        sell_price = _floor_tick(bar.open * (Decimal(1) - fee_schedule.slippage_rate), rule.tick_size)
        limit_down = self._limit_down(date, sid, bar, rule)
        if limit_down is None and not (bar.no_price_limit or rule.no_price_limit):
            raise _Blocked(f"SELL_PRICE_LIMIT_UNKNOWN:{sid}:{date}")
        if limit_down is not None and bar.open <= limit_down:
            self._record_order(
                sid,
                "SELL",
                date,
                requested_quantity,
                "UNFILLED",
                reason="LIMIT_DOWN",
                strategy_id=position.strategy_id,
                signal_date=signal_date,
            )
            return
        if limit_down is not None and sell_price < limit_down:
            self._record_order(
                sid,
                "SELL",
                date,
                requested_quantity,
                "UNFILLED",
                reason="PRICE_OUTSIDE_LIMIT",
                strategy_id=position.strategy_id,
                signal_date=signal_date,
            )
            return
        sellable = position.sellable_quantity(date)
        if sellable <= 0:
            self._record_order(
                sid,
                "SELL",
                date,
                requested_quantity,
                "UNFILLED",
                reason="T_SELL_RESTRICTED",
                strategy_id=position.strategy_id,
                signal_date=signal_date,
            )
            return
        if not exit_intent and rule.sell_lot_size > 0:
            requested_quantity = (requested_quantity // rule.sell_lot_size) * rule.sell_lot_size
            if requested_quantity <= 0:
                return
        quantity = min(requested_quantity, sellable)
        if quantity <= 0:
            return
        will_close = quantity == position.quantity
        gross = _money(sell_price * Decimal(quantity))
        commission, other_fees = self._incremental_sell_fees(date, sid, gross)
        fees = commission + other_fees
        cash_in = gross - fees
        self.cash += cash_in
        self.total_fees += fees
        self.total_commission += commission
        self.total_tax += _money(gross * fee_schedule.sell_tax_rate)
        cost_sold, cost_remaining = allocate_sale_cost(position.cost_open, quantity, position.quantity)
        taken_lots = self._reduce_lots(position, date, quantity)
        dividend_sold = self._sell_dividend_layers(position, taken_lots)
        new_claims = self._allocate_pending_entitlements(position, taken_lots, date, will_close)
        position.dividend_open = sum(
            (layer["remaining_amount"] for layer in position.dividend_layers), ZERO
        )
        position.dividend_units = int(
            sum((layer["remaining_quantity"] for layer in position.dividend_layers), Decimal(0))
        )
        realized_trade = _money(gross - fees - cost_sold)
        position.realized_trading_pnl += realized_trade
        position.realized_dividend += dividend_sold
        position.cost_open = cost_remaining
        position.quantity -= quantity
        order_status = "FILLED" if quantity == requested_quantity else "PARTIAL_QUANTITY"
        order = self._record_order(
            sid,
            "SELL",
            date,
            requested_quantity,
            order_status,
            filled_quantity=quantity,
            price=sell_price,
            gross=gross,
            commission=commission,
            other_fees=other_fees,
            reason=";".join(reasons),
            strategy_id=position.strategy_id,
            signal_date=signal_date,
        )
        self.fills.append(
            Fill(order.order_id, sid, "SELL", date, quantity, sell_price, gross, commission, other_fees)
        )
        self.today_sell_gross += gross
        if exit_intent:
            self.exited_today.add(sid)
        if position.quantity == 0:
            future_share_claims = [
                claim
                for claim in new_claims
                if claim["action"].action_type in ("BONUS_SHARES", "SPLIT", "MERGE")
            ]
            if future_share_claims:
                for claim in self.external_dividend_claims:
                    if (
                        claim["security_id"] == sid
                        and not claim["processed"]
                        and claim["closed_cycle_index"] is None
                    ):
                        claim["pending_cycle"] = position
                for claim in new_claims:
                    claim["pending_cycle"] = position
                self._remove_position(position)
                if not self._has_holding(sid):
                    self.locked_exits.pop(sid, None)
            else:
                position.realized_dividend += position.dividend_open
                position.dividend_open = ZERO
                cycle_total = cycle_total_pnl(position.realized_trading_pnl, position.realized_dividend)
                self.closed_cycles.append(
                    ClosedCycle(
                        security_id=sid,
                        strategy_id=position.strategy_id,
                        opened_on=position.holding_start,
                        closed_on=date,
                        realized_trading_pnl=position.realized_trading_pnl,
                        realized_dividend=position.realized_dividend,
                        total_pnl=cycle_total,
                    )
                )
                cycle_index = len(self.closed_cycles) - 1
                for claim in self.external_dividend_claims:
                    if (
                        claim["security_id"] == sid
                        and not claim["processed"]
                        and claim["closed_cycle_index"] is None
                    ):
                        claim["closed_cycle_index"] = cycle_index
                for claim in new_claims:
                    claim["closed_cycle_index"] = cycle_index
                self._remove_position(position)
                if not self._has_holding(sid):
                    self.locked_exits.pop(sid, None)
        self.external_dividend_claims.extend(new_claims)

    def _try_buy(
        self,
        date: str,
        signal: Signal,
        mark_open: Decimal | None,
        target_weight: Decimal,
        *,
        replacement_for: Signal | None = None,
        replacement_reason: str | None = None,
    ) -> tuple[bool, str | None]:
        sid = signal.security_id
        eligibility_status, eligibility_reason = self._eligibility_status(date, sid)
        if self.data.eligibility_by_date:
            self.eligibility_entries.append(
                {
                    "date": date,
                    "security_id": sid,
                    "status": eligibility_status,
                    "reason": eligibility_reason,
                    "source": "BUY_CANDIDATE",
                }
            )
        if eligibility_status == "INELIGIBLE":
            self._record_signal_order(
                signal,
                date,
                "UNFILLED",
                "ELIGIBILITY_INELIGIBLE",
                replacement_for,
                replacement_reason,
            )
            return False, "ELIGIBILITY_INELIGIBLE"
        if eligibility_status == "UNKNOWN":
            self._record_signal_order(
                signal,
                date,
                "UNFILLED",
                "ELIGIBILITY_UNKNOWN",
                replacement_for,
                replacement_reason,
            )
            raise _Blocked(f"ELIGIBILITY_UNKNOWN:{sid}:{date}")
        bar = self._bar(date, sid)
        rule = self._rule(date, sid)
        if bar is None:
            raise _Blocked(f"BUY_BAR_MISSING:{sid}:{date}")
        if rule is None:
            raise _Blocked(f"TRADING_RULE_UNKNOWN:{sid}:{date}")
        if bar.suspended is True:
            self._record_signal_order(signal, date, "UNFILLED", "SUSPENDED", replacement_for, replacement_reason)
            return False, "SUSPENDED"
        if bar.suspended is None:
            raise _Blocked(f"TRADING_STATUS_UNKNOWN:{sid}:{date}")
        if bar.data_status != "OK":
            raise _Blocked(f"BUY_BAR_STATUS_UNKNOWN:{sid}:{date}:{bar.data_status}")
        if bar.open is None or bar.open <= 0:
            raise _Blocked(f"BUY_OPEN_PRICE_UNKNOWN:{sid}:{date}")
        if signal.entry_conflict_exit == "UNKNOWN":
            raise _Blocked(f"ENTRY_CONFLICT_UNKNOWN:{sid}:{date}")
        current_position = self.positions.get(sid)
        if current_position is not None and signal.strategy_id == "S04":
            return False, None
        fee_schedule = self._fee_schedule(date, sid, "BUY")
        buy_price = _ceil_tick(bar.open * (Decimal(1) + fee_schedule.slippage_rate), rule.tick_size)
        current_value = Decimal(current_position.quantity) * mark_open if current_position is not None and mark_open is not None else ZERO
        budget = max(ZERO, target_weight - current_value)
        if budget <= 0:
            return False, None
        lot_size = rule.lot_size
        if lot_size <= 0:
            raise _Blocked(f"LOT_SIZE_INVALID:{sid}:{date}")
        planned_quantity = self._max_affordable_quantity(date, sid, buy_price, budget, lot_size)

        if self.config.strategy_id == "S06":
            if signal.industry_id is None:
                raise _Blocked(f"INDUSTRY_UNKNOWN:{sid}:{date}")
            if current_position is None:
                industry_count = sum(
                    1
                    for position in self.positions.values()
                    if position.strategy_id == "S06" and position.industry_id == signal.industry_id
                )
                if industry_count >= self.config.s06_industry_cap:
                    self._record_signal_order(
                        signal,
                        date,
                        "UNFILLED",
                        "INDUSTRY_CAP",
                        replacement_for,
                        replacement_reason,
                        requested_quantity=planned_quantity,
                    )
                    return False, "INDUSTRY_CAP"
        limit_up = self._limit_up(date, sid, bar, rule)
        if limit_up is None and not (bar.no_price_limit or rule.no_price_limit):
            raise _Blocked(f"BUY_PRICE_LIMIT_UNKNOWN:{sid}:{date}")
        if limit_up is not None and bar.open >= limit_up:
            self._record_signal_order(
                signal,
                date,
                "UNFILLED",
                "LIMIT_UP",
                replacement_for,
                replacement_reason,
                requested_quantity=planned_quantity,
            )
            return False, "LIMIT_UP"
        if limit_up is not None and buy_price > limit_up:
            self._record_signal_order(
                signal,
                date,
                "UNFILLED",
                "PRICE_OUTSIDE_LIMIT",
                replacement_for,
                replacement_reason,
                requested_quantity=planned_quantity,
            )
            return False, "PRICE_OUTSIDE_LIMIT"
        if planned_quantity < lot_size:
            self._record_signal_order(
                signal,
                date,
                "UNFILLED",
                "INSUFFICIENT_CASH",
                replacement_for,
                replacement_reason,
                requested_quantity=planned_quantity,
            )
            return False, "INSUFFICIENT_CASH"
        quantity = planned_quantity

        gross = _money(buy_price * Decimal(quantity))
        commission, other_fees = self._buy_fees(date, sid, gross)
        fees = commission + other_fees
        self.fee_entries.append(
            {
                "date": date,
                "security_id": sid,
                "side": "BUY",
                "version": fee_schedule.version,
                "gross": gross,
                "commission": commission,
                "other_fees": other_fees,
            }
        )
        total_cost = gross + fees
        self.cash -= total_cost
        self.total_fees += fees
        self.total_commission += commission
        self.total_tax += _money(gross * fee_schedule.buy_tax_rate)
        self.today_buy_gross += gross
        if current_position is None:
            sellable_date = self._sellable_date(date, rule.sell_delay_days)
            position = Position(
                security_id=sid,
                strategy_id=signal.strategy_id,
                quantity=quantity,
                cost_open=total_cost,
                dividend_open=ZERO,
                dividend_units=0,
                lots=[Lot(quantity, date, sellable_date, lot_id=self._allocate_lot_id(sid, date))],
                holding_start=date,
                holding_days=1,
                last_mark=buy_price,
                entry_platform_upper=signal.entry_platform_upper,
                industry_id=signal.industry_id,
            )
            self.positions[sid] = position
        else:
            current_position.quantity += quantity
            current_position.cost_open += total_cost
            current_position.lots.append(
                Lot(
                    quantity,
                    date,
                    self._sellable_date(date, rule.sell_delay_days),
                    lot_id=self._allocate_lot_id(sid, date),
                )
            )
            if current_position.entry_platform_upper is None:
                current_position.entry_platform_upper = signal.entry_platform_upper
            if current_position.industry_id is None:
                current_position.industry_id = signal.industry_id
        order = self._record_signal_order(
            signal,
            date,
            "FILLED",
            None,
            replacement_for,
            replacement_reason,
            filled_quantity=quantity,
            price=buy_price,
            gross=gross,
            commission=commission,
            other_fees=other_fees,
        )
        self.fills.append(Fill(order.order_id, sid, "BUY", date, quantity, buy_price, gross, commission, other_fees))
        return True, None

    # ------------------------------------------------------------------
    # Corporate actions
    # ------------------------------------------------------------------

    def _sell_dividend_layers(self, position: Position, taken_lots: Sequence[tuple[Lot, int]]) -> Decimal:
        sold = ZERO
        for lot, quantity_sold in taken_lots:
            if quantity_sold <= 0:
                continue
            for key in lot.dividend_actions:
                layer = next(
                    (
                        item
                        for item in position.dividend_layers
                        if item["key"] == key
                        and item["remaining_quantity"] > 0
                        and (
                            item.get("lot_id") is None
                            or lot.lot_id is None
                            or item.get("lot_id") == lot.lot_id
                        )
                    ),
                    None,
                )
                if layer is None:
                    continue
                if Decimal(quantity_sold) >= layer["remaining_quantity"]:
                    amount = layer["remaining_amount"]
                    layer["remaining_amount"] = ZERO
                    layer["remaining_quantity"] = Decimal(0)
                else:
                    amount = _money(layer["per_share"] * Decimal(quantity_sold))
                    layer["remaining_amount"] -= amount
                    layer["remaining_quantity"] -= Decimal(quantity_sold)
                sold += amount
        position.dividend_layers = [
            layer for layer in position.dividend_layers if layer["remaining_quantity"] > 0
        ]
        return sold

    def _allocate_pending_entitlements(
        self,
        position: Position,
        taken_lots: Sequence[tuple[Lot, int]],
        date: str,
        will_close: bool,
    ) -> list[dict]:
        claims: list[dict] = []
        for lot, quantity_sold in taken_lots:
            if quantity_sold <= 0:
                continue
            for key in lot.dividend_actions:
                action = self.pending_actions.get(key)
                if action is None or action.effective_date <= date:
                    continue
                if action.action_type not in ("CASH_DIVIDEND", "BONUS_SHARES", "SPLIT", "MERGE"):
                    raise _Blocked(
                        f"ENTITLEMENT_SALE_BEFORE_EFFECTIVE:{position.security_id}:{action.action_type}:{date}"
                    )
                entitlement = self.dividend_entitlements.get(key)
                if entitlement is not None:
                    security_id, entitled_quantity = entitlement
                    self.dividend_entitlements[key] = (
                        security_id,
                        max(0, entitled_quantity - quantity_sold),
                    )
                claims.append(
                    {
                        "security_id": position.security_id,
                        "quantity": quantity_sold,
                        "action": action,
                        "strategy_id": position.strategy_id,
                        "industry_id": position.industry_id,
                        "entry_platform_upper": position.entry_platform_upper,
                        "closed_cycle_index": None,
                        "opened_on": position.holding_start,
                        "closed_on": date if will_close else None,
                        "lot_id": lot.lot_id,
                        "acquired_date": lot.acquired_date,
                        "processed": False,
                    }
                )
        return claims

    def _process_external_dividend_claims(self, date: str) -> None:
        for claim in self.external_dividend_claims:
            if claim["processed"]:
                continue
            action: CorporateAction = claim["action"]
            if action.effective_date != date:
                continue
            if action.action_type in ("BONUS_SHARES", "SPLIT", "MERGE"):
                self._apply_external_share_claim(claim, action, date)
                claim["processed"] = True
                continue
            if action.action_type != "CASH_DIVIDEND":
                raise _Blocked(f"EXTERNAL_ACTION_UNSUPPORTED:{action.action_type}:{claim['security_id']}:{date}")
            if action.cash_per_share is None:
                raise _Blocked(f"EXTERNAL_DIVIDEND_TERMS_UNKNOWN:{claim['security_id']}:{date}")
            gross = _money(action.cash_per_share * Decimal(claim["quantity"]))
            tax, _basis, _version = self._select_dividend_tax(
                action,
                lot_id=claim.get("lot_id"),
                acquired_date=claim.get("acquired_date") or claim.get("opened_on") or date,
                quantity=int(claim["quantity"]),
                gross=gross,
                date=date,
            )
            net = gross - tax
            self.receivables += gross
            self.payables += tax
            self.total_tax += tax
            pending = claim.get("pending_cycle")
            if pending is not None:
                pending.realized_dividend += net
                self.dividend_payments.append(
                    {
                        "security_id": claim["security_id"],
                        "pay_date": action.pay_date,
                        "gross": gross,
                        "tax": tax,
                        "net": net,
                        "paid": False,
                    }
                )
                claim["processed"] = True
                continue
            cycle_index = claim["closed_cycle_index"]
            if cycle_index is not None:
                cycle = self.closed_cycles[cycle_index]
                self.closed_cycles[cycle_index] = ClosedCycle(
                    security_id=cycle.security_id,
                    strategy_id=cycle.strategy_id,
                    opened_on=cycle.opened_on,
                    closed_on=cycle.closed_on,
                    realized_trading_pnl=cycle.realized_trading_pnl,
                    realized_dividend=cycle.realized_dividend + net,
                    total_pnl=cycle.total_pnl + net,
                )
            else:
                position = self.positions.get(claim["security_id"])
                if position is not None:
                    position.realized_dividend += net
                else:
                    cycle_index = next(
                        (
                            index
                            for index in range(len(self.closed_cycles) - 1, -1, -1)
                            if self.closed_cycles[index].security_id == claim["security_id"]
                        ),
                        None,
                    )
                    if cycle_index is not None:
                        cycle = self.closed_cycles[cycle_index]
                        self.closed_cycles[cycle_index] = ClosedCycle(
                            security_id=cycle.security_id,
                            strategy_id=cycle.strategy_id,
                            opened_on=cycle.opened_on,
                            closed_on=cycle.closed_on,
                            realized_trading_pnl=cycle.realized_trading_pnl,
                            realized_dividend=cycle.realized_dividend + net,
                            total_pnl=cycle.total_pnl + net,
                        )
                    else:
                        self.closed_cycles.append(
                            ClosedCycle(
                                security_id=claim["security_id"],
                                strategy_id="UNKNOWN",
                                opened_on=claim["opened_on"],
                                closed_on=claim["closed_on"] or date,
                                realized_trading_pnl=ZERO,
                                realized_dividend=net,
                                total_pnl=net,
                            )
                        )
            self.dividend_payments.append(
                {
                    "security_id": claim["security_id"],
                    "pay_date": action.pay_date,
                    "gross": gross,
                    "tax": tax,
                    "net": net,
                    "paid": False,
                }
            )
            claim["processed"] = True

    def _apply_external_share_claim(self, claim: dict, action: CorporateAction, date: str) -> None:
        if action.share_multiplier is None or action.share_multiplier <= 0:
            raise _Blocked(f"SHARE_MULTIPLIER_MISSING:{claim['security_id']}:{date}")
        exact = Decimal(claim["quantity"]) * (action.share_multiplier - 1)
        new_quantity = int(exact.to_integral_value(rounding=ROUND_FLOOR))
        if new_quantity < 0:
            raise _Blocked(f"REVERSE_SHARE_CLAIM_UNSUPPORTED:{claim['security_id']}:{date}")
        pending = claim.get("pending_cycle")
        existing = self.positions.get(claim["security_id"])
        legacy_cycle = pending is not None and existing is not None and existing is not pending
        if legacy_cycle:
            position = pending
        elif pending is not None:
            position = pending
        else:
            position = existing
        cash_in_lieu_pnl = ZERO
        if new_quantity != exact:
            if action.cash_in_lieu is None:
                raise _Blocked(f"FRACTIONAL_SHARES_UNHANDLED:{claim['security_id']}:{date}")
            self.cash += action.cash_in_lieu
            self.cash_adjustments.append(
                {"reason": f"CASH_IN_LIEU:{claim['security_id']}:{date}", "amount": action.cash_in_lieu}
            )
            if position is not None:
                position.realized_trading_pnl += action.cash_in_lieu
            else:
                cash_in_lieu_pnl = action.cash_in_lieu
        if new_quantity <= 0:
            return
        sellable_date = action.new_share_sellable_date or date
        platform = claim.get("entry_platform_upper")
        if platform is not None:
            platform = platform / action.share_multiplier
        if position is None:
            position = Position(
                security_id=claim["security_id"],
                strategy_id=claim.get("strategy_id") or "UNKNOWN",
                quantity=0,
                cost_open=ZERO,
                dividend_open=ZERO,
                dividend_units=0,
                lots=[],
                holding_start=claim.get("opened_on") or date,
                holding_days=0,
                last_mark=None,
                entry_platform_upper=platform,
                industry_id=claim.get("industry_id"),
                realized_trading_pnl=cash_in_lieu_pnl,
            )
        else:
            position.realized_trading_pnl += cash_in_lieu_pnl
            if position.entry_platform_upper is None and platform is not None:
                position.entry_platform_upper = platform
        position.quantity += new_quantity
        position.lots.append(
            Lot(
                new_quantity,
                claim.get("acquired_date") or date,
                sellable_date,
                lot_id=claim.get("lot_id") or self._allocate_lot_id(claim["security_id"], date),
            )
        )
        if legacy_cycle:
            if position not in self.legacy_positions:
                self.legacy_positions.append(position)
        else:
            self.positions[claim["security_id"]] = position
        self.warnings.append(
            f"BONUS_DELIVERED_AFTER_SALE:{claim['security_id']}:{new_quantity}:{date}"
        )

    def _process_record_dates(self, date: str) -> None:
        for action in self.actions_by_record.get(date, ()):
            if action.status in ("ANNOUNCED", "CANCELLED"):
                continue
            if action.status in ("UNKNOWN", "CONFLICT"):
                if action.security_id in self.positions:
                    raise _Blocked(f"CORPORATE_ACTION_UNKNOWN:{action.security_id}:{action.action_type}")
                continue
            if action.status != "IMPLEMENTED":
                if action.security_id in self.positions:
                    raise _Blocked(f"CORPORATE_ACTION_NOT_IMPLEMENTED:{action.security_id}:{action.action_type}")
                continue
            position = self.positions.get(action.security_id)
            if position is not None:
                key = _action_key(action)
                self.dividend_entitlements[key] = (action.security_id, position.quantity)
                self.pending_actions[key] = action
                for lot in position.lots:
                    lot.dividend_actions.add(key)

    def _apply_corporate_actions(self, date: str, day: MarketDay, relevant_ids: set[str]) -> None:
        if not day.corporate_actions_complete and relevant_ids:
            raise _Blocked(f"CORPORATE_ACTION_COVERAGE_INCOMPLETE:{date}")
        for action in self.actions_by_effective.get(date, ()):
            position = self.positions.get(action.security_id)
            if action.status in ("ANNOUNCED", "CANCELLED"):
                continue
            if action.status in ("UNKNOWN", "CONFLICT"):
                if action.security_id in relevant_ids:
                    raise _Blocked(f"CORPORATE_ACTION_UNKNOWN:{action.security_id}:{action.action_type}:{date}")
                self.warnings.append(f"CORPORATE_ACTION_UNKNOWN_IGNORED:{action.security_id}:{date}")
                continue
            if action.status != "IMPLEMENTED":
                if action.security_id in relevant_ids:
                    raise _Blocked(f"CORPORATE_ACTION_STATUS_UNKNOWN:{action.security_id}:{date}")
                continue
            if position is None:
                continue
            if action.action_type == "CASH_DIVIDEND":
                self._apply_cash_dividend(action, position, date)
            elif action.action_type in ("BONUS_SHARES", "SPLIT", "MERGE"):
                self._apply_share_change(action, position, date)
            elif action.action_type == "RIGHTS_ISSUE":
                raise _Blocked(f"RIGHTS_ISSUE_UNHANDLED:{action.security_id}:{date}")
            elif action.action_type == "DELISTING":
                raise _Blocked(f"DELISTING_SETTLEMENT_UNKNOWN:{action.security_id}:{date}")
            else:
                raise _Blocked(f"CORPORATE_ACTION_UNHANDLED:{action.action_type}:{action.security_id}:{date}")

    def _select_dividend_tax(
        self,
        action: CorporateAction,
        *,
        lot_id: str | None,
        acquired_date: str,
        quantity: int,
        gross: Decimal,
        date: str,
    ) -> tuple[Decimal, str, str]:
        if action.dividend_tax_bindings and action.dividend_tax_rate is not None:
            raise _Blocked(f"DIVIDEND_TAX_DOUBLE_SOURCE:{action.security_id}:{date}")
        if not action.dividend_tax_bindings:
            if action.dividend_tax_rate is None:
                raise _Blocked(f"DIVIDEND_TAX_RATE_UNKNOWN:{action.security_id}:{date}")
            return _money(gross * action.dividend_tax_rate), "SCALAR", action.version
        open_at = parse_local_datetime(f"{date}T09:30:00", field="trade_open")
        matches = []
        probe = Lot(quantity, acquired_date, date, lot_id=lot_id)
        for binding in action.dividend_tax_bindings:
            if not binding.matches(probe):
                continue
            if binding.known_at is None:
                raise _Blocked(f"DIVIDEND_TAX_KNOWN_AT_MISSING:{action.security_id}:{date}")
            if parse_local_datetime(binding.known_at, field="known_at") >= open_at:
                continue
            matches.append(binding)
        if len(matches) != 1:
            raise _Blocked(
                f"DIVIDEND_TAX_BINDING_{'AMBIGUOUS' if matches else 'MISSING'}:{action.security_id}:{date}"
            )
        binding = matches[0]
        if binding.status != "CONFIRMED":
            raise _Blocked(f"DIVIDEND_TAX_BINDING_{binding.status}:{action.security_id}:{date}")
        if binding.tax_rate is not None:
            tax = _money(gross * binding.tax_rate)
            basis = "RATE"
        else:
            assert binding.tax_per_share is not None
            tax = _money(binding.tax_per_share * Decimal(quantity))
            basis = "PER_SHARE"
        self.dividend_tax_entries.append(
            {
                "security_id": action.security_id,
                "effective_date": action.effective_date,
                "record_date": action.record_date,
                "pay_date": action.pay_date,
                "known_at": binding.known_at,
                "lot_id": lot_id,
                "acquired_date": acquired_date,
                "quantity": quantity,
                "gross": gross,
                "tax": tax,
                "basis": basis,
                "rate": binding.tax_rate,
                "per_share": binding.tax_per_share,
                "rule_version": binding.rule_version,
                "source": binding.source,
            }
        )
        return tax, basis, binding.rule_version

    def _apply_cash_dividend(self, action: CorporateAction, position: Position, date: str) -> None:
        if action.cash_per_share is None:
            raise _Blocked(f"DIVIDEND_CASH_PER_SHARE_MISSING:{action.security_id}:{date}")
        if position.last_mark is not None:
            position.last_mark = max(ZERO, position.last_mark - action.cash_per_share)
        key = _action_key(action)
        if action.record_date is not None:
            lots = [lot for lot in position.lots if key in lot.dividend_actions]
        else:
            lots = list(position.lots)
        total_quantity = sum(lot.quantity for lot in lots)
        if total_quantity <= 0:
            return
        total_gross = ZERO
        total_tax = ZERO
        layers: list[dict] = []
        for lot in lots:
            if lot.quantity <= 0:
                continue
            gross = _money(action.cash_per_share * Decimal(lot.quantity))
            tax, _basis, tax_version = self._select_dividend_tax(
                action,
                lot_id=lot.lot_id,
                acquired_date=lot.acquired_date,
                quantity=lot.quantity,
                gross=gross,
                date=date,
            )
            net = gross - tax
            total_gross += gross
            total_tax += tax
            layers.append(
                {
                    "key": key,
                    "lot_id": lot.lot_id,
                    "per_share": net / Decimal(lot.quantity),
                    "remaining_quantity": Decimal(lot.quantity),
                    "remaining_amount": net,
                    "tax": tax,
                    "tax_version": tax_version,
                    "action": action,
                }
            )
        net_total = total_gross - total_tax
        self.receivables += total_gross
        self.payables += total_tax
        self.total_tax += total_tax
        position.dividend_layers.extend(layers)
        position.dividend_open += net_total
        position.dividend_units = int(
            sum(layer["remaining_quantity"] for layer in position.dividend_layers)
        )
        self.dividend_payments.append(
            {
                "security_id": action.security_id,
                "pay_date": action.pay_date,
                "gross": total_gross,
                "tax": total_tax,
                "net": net_total,
                "paid": False,
            }
        )

    def _apply_share_change(self, action: CorporateAction, position: Position, date: str) -> None:
        if action.share_multiplier is None or action.share_multiplier <= 0:
            raise _Blocked(f"SHARE_MULTIPLIER_MISSING:{action.security_id}:{date}")
        if action.record_date is not None:
            entitlement = self.dividend_entitlements.get(_action_key(action))
            entitled_quantity = entitlement[1] if entitlement is not None else 0
            if entitled_quantity <= 0:
                return
            if entitled_quantity != position.quantity:
                raise _Blocked(f"SHARE_CHANGE_ENTITLEMENT_MISMATCH:{action.security_id}:{date}")
        old_quantity = position.quantity
        exact = Decimal(old_quantity) * action.share_multiplier
        new_quantity = int(exact.to_integral_value(rounding=ROUND_FLOOR))
        if new_quantity <= 0:
            raise _Blocked(f"ZERO_SHARES_AFTER_CORPORATE_ACTION:{action.security_id}:{date}")
        if new_quantity != exact:
            if action.cash_in_lieu is None:
                raise _Blocked(f"FRACTIONAL_SHARES_UNHANDLED:{action.security_id}:{date}")
            self.cash += action.cash_in_lieu
            position.realized_trading_pnl += action.cash_in_lieu
            self.cash_adjustments.append(
                {"reason": f"CASH_IN_LIEU:{action.security_id}:{date}", "amount": action.cash_in_lieu}
            )
            self.warnings.append(f"CASH_IN_LIEU:{action.security_id}:{date}:{action.cash_in_lieu}")
        delta = new_quantity - old_quantity
        if delta > 0:
            source_lots = list(position.lots)
            remaining_delta = delta
            sellable_date = action.new_share_sellable_date or date
            allocations: list[tuple[Lot, int]] = []
            for source in source_lots:
                if remaining_delta <= 0:
                    break
                share = int(
                    (Decimal(source.quantity) * (action.share_multiplier - 1)).to_integral_value(
                        rounding=ROUND_FLOOR
                    )
                )
                share = min(share, remaining_delta)
                allocations.append((source, share))
                remaining_delta -= share
            if remaining_delta > 0 and source_lots:
                first_source, first_share = allocations[0] if allocations else (source_lots[0], 0)
                allocations = [(first_source, first_share + remaining_delta)] + [
                    item for item in allocations[1:]
                ]
                remaining_delta = 0
            for source, share in allocations:
                if share <= 0:
                    continue
                position.lots.append(
                    Lot(
                        share,
                        source.acquired_date,
                        sellable_date,
                        set(source.dividend_actions),
                        source.lot_id,
                    )
                )
            if remaining_delta > 0:
                actions: set[str] = set()
                for source in source_lots:
                    actions.update(source.dividend_actions)
                position.lots.append(
                    Lot(
                        remaining_delta,
                        date,
                        sellable_date,
                        actions,
                        self._allocate_lot_id(action.security_id, date),
                    )
                )
        elif delta < 0:
            self._reduce_lots(position, date, -delta, respect_sellable=False)
        position.quantity = new_quantity
        for layer in position.dividend_layers:
            layer["per_share"] = layer["per_share"] / action.share_multiplier
            layer["remaining_quantity"] = layer["remaining_quantity"] * action.share_multiplier
        position.dividend_units = int(
            sum((layer["remaining_quantity"] for layer in position.dividend_layers), Decimal(0))
        )
        if position.entry_platform_upper is not None:
            position.entry_platform_upper = position.entry_platform_upper / action.share_multiplier
        if position.last_mark is not None:
            position.last_mark = position.last_mark / action.share_multiplier

    def _process_dividend_payments(self, date: str) -> None:
        for payment in self.dividend_payments:
            if payment["paid"] or payment["pay_date"] != date:
                continue
            self.cash += payment["net"]
            self.receivables -= payment["gross"]
            self.payables -= payment["tax"]
            payment["paid"] = True

    # ------------------------------------------------------------------
    # Valuation, stop loss, metrics
    # ------------------------------------------------------------------

    def _close_day(
        self,
        date: str,
        day: MarketDay,
        mark_open: Mapping[str, Decimal],
        open_equity: Decimal,
        target_weight: Decimal,
    ) -> None:
        holdings = self._holdings()
        mark_close: dict[str, Decimal] = {}
        for key, position in holdings.items():
            price = self._mark_close(date, position.security_id, position)
            mark_close[key] = price
            position.last_mark = price
        market_value = sum(
            (Decimal(position.quantity) * mark_close[key] for key, position in holdings.items()),
            ZERO,
        )
        equity = self.cash + self.receivables - self.payables + market_value
        nav = equity / self.config.initial_cash
        benchmark_close = day.benchmark_close
        assert benchmark_close is not None and self.benchmark_base is not None
        benchmark = benchmark_close / self.benchmark_base
        daily_return = nav / self.prev_nav - 1
        self.nav_peak = max(self.nav_peak, nav)
        drawdown = nav / self.nav_peak - 1
        turnover = None
        if self.prev_equity > 0:
            turnover = (self.today_buy_gross + self.today_sell_gross) / (Decimal(2) * self.prev_equity)
        position_ratio = market_value / equity if equity > 0 else None
        nav_point = NavPoint(
            date=date,
            cash=self.cash,
            receivables=self.receivables,
            payables=self.payables,
            market_value=market_value,
            equity=equity,
            nav=nav,
            benchmark=benchmark,
            daily_return=daily_return,
            drawdown=drawdown,
            position_count=len({position.security_id for position in holdings.values()}),
            open_equity=open_equity,
            target_weight=target_weight,
            turnover=turnover,
            position_ratio=position_ratio,
        )
        self.nav_points.append(nav_point)
        for key in sorted(holdings):
            position = holdings[key]
            sid = position.security_id
            price = mark_close[key]
            bar = self._bar(date, sid)
            mark_status = (
                "STALE_MARK_CONFIRMED_SUSPENSION"
                if bar is not None and bar.suspended is True
                else "RAW_CLOSE"
            )
            self.position_history.append(
                PositionSnapshot(
                    date=date,
                    security_id=sid,
                    strategy_id=position.strategy_id,
                    quantity=position.quantity,
                    sellable_quantity=position.sellable_quantity(date),
                    cost_open=position.cost_open,
                    dividend_open=position.dividend_open,
                    market_value=Decimal(position.quantity) * price,
                    unrealized_pnl=position.unrealized_pnl(price),
                    r_open=position.r_open(price),
                    holding_days=position.holding_days,
                    industry_id=position.industry_id,
                    mark_status=mark_status,
                )
            )
        self._append_reconciliation(date, mark_open, mark_close, market_value, equity)
        self._process_record_dates(date)
        self._evaluate_stop_loss(date, mark_close)
        self.prev_equity = equity
        self.prev_nav = nav

    def _evaluate_stop_loss(self, date: str, mark_close: Mapping[str, Decimal]) -> None:
        if self.config.stop_loss is None:
            return
        for key, position in self._holdings().items():
            if position.cost_open <= 0:
                continue
            sid = position.security_id
            price = mark_close[key]
            r_open = remaining_open_stop_ratio(
                Decimal(position.quantity) * price, position.dividend_open, position.cost_open
            )
            if r_open is None:
                raise _Blocked(f"STOP_RISK_UNKNOWN:{sid}:{date}")
            if r_open <= -self.config.stop_loss:
                self._add_locked_exit(
                    ExitRequest(
                        security_id=sid,
                        reason="STOP_LOSS",
                        trigger_date=date,
                        priority=1,
                        strategy_id=position.strategy_id,
                    )
                )

    def _append_reconciliation(
        self,
        date: str,
        mark_open: Mapping[str, Decimal],
        mark_close: Mapping[str, Decimal],
        market_value: Decimal,
        equity: Decimal,
    ) -> None:
        expected_cash = self.config.initial_cash
        for order in self.orders:
            if order.status in ("FILLED", "PARTIAL_QUANTITY") and order.filled_quantity > 0:
                if order.side == "BUY":
                    expected_cash -= order.gross + order.commission + order.other_fees
                else:
                    expected_cash += order.gross - order.commission - order.other_fees
        for payment in self.dividend_payments:
            if payment["paid"]:
                expected_cash += payment["net"]
        for adjustment in self.cash_adjustments:
            expected_cash += adjustment["amount"]
        equity_equation = self.cash + self.receivables - self.payables + market_value
        holdings = self._holdings()
        open_market_value = sum(
            (
                Decimal(position.quantity) * mark_open.get(key, position.last_mark or ZERO)
                for key, position in holdings.items()
            ),
            ZERO,
        )
        close_market_value = sum(
            (
                Decimal(position.quantity) * mark_close.get(key, position.last_mark or ZERO)
                for key, position in holdings.items()
            ),
            ZERO,
        )
        self.reconciliation.append(
            {
                "date": date,
                "cash": self.cash,
                "receivables": self.receivables,
                "payables": self.payables,
                "market_value": market_value,
                "equity": equity,
                "equity_equation": equity_equation,
                "equity_ok": _money(equity_equation) == _money(equity),
                "expected_cash": expected_cash,
                "cash_ok": _money(expected_cash) == _money(self.cash),
                "open_market_diagnostic": open_market_value,
                "close_market_diagnostic": close_market_value,
            }
        )

    # ------------------------------------------------------------------
    # Prices and rules
    # ------------------------------------------------------------------

    def _bar(self, date: str, security_id: str) -> DailyBar | None:
        day = self.data.market_days.get(date)
        if day is None:
            return None
        bar = day.bars.get(security_id)
        if bar is None:
            return None
        if bar.date != date:
            raise _Blocked(f"BAR_BUSINESS_DATE_MISMATCH:{security_id}:{bar.date}!={date}")
        prices = (bar.open, bar.high, bar.low, bar.close)
        if any(value is not None and value <= 0 for value in prices):
            raise _Blocked(f"NON_POSITIVE_BAR_PRICE:{security_id}:{date}")
        if all(value is not None for value in prices):
            open_value = bar.open
            high_value = bar.high
            low_value = bar.low
            close_value = bar.close
            assert open_value is not None and high_value is not None
            assert low_value is not None and close_value is not None
            if high_value < max(open_value, close_value) or low_value > min(open_value, close_value):
                raise _Blocked(f"INVALID_BAR_OHLC:{security_id}:{date}")
            if high_value < low_value:
                raise _Blocked(f"INVALID_BAR_OHLC:{security_id}:{date}")
        if bar.volume is not None and bar.volume < 0:
            raise _Blocked(f"NEGATIVE_BAR_VOLUME:{security_id}:{date}")
        if bar.amount is not None and bar.amount < 0:
            raise _Blocked(f"NEGATIVE_BAR_AMOUNT:{security_id}:{date}")
        return bar

    def _previous_close(self, date: str, security_id: str) -> Decimal | None:
        index = self.full_calendar.index(date)
        for previous in reversed(self.full_calendar[:index]):
            bar = self._bar(previous, security_id)
            if bar is not None and bar.close is not None and bar.close > 0:
                return bar.close
        return None

    def _limit_up(self, date: str, security_id: str, bar: DailyBar, rule: TradingRule) -> Decimal | None:
        if bar.limit_up is not None:
            return bar.limit_up
        if bar.no_price_limit or rule.no_price_limit:
            return None
        if rule.price_limit_pct is None:
            return None
        previous = self._previous_close(date, security_id)
        if previous is None:
            return None
        return _round_tick(previous * (Decimal(1) + rule.price_limit_pct), rule.tick_size)

    def _limit_down(self, date: str, security_id: str, bar: DailyBar, rule: TradingRule) -> Decimal | None:
        if bar.limit_down is not None:
            return bar.limit_down
        if bar.no_price_limit or rule.no_price_limit:
            return None
        if rule.price_limit_pct is None:
            return None
        previous = self._previous_close(date, security_id)
        if previous is None:
            return None
        return _round_tick(previous * (Decimal(1) - rule.price_limit_pct), rule.tick_size)

    def _probe_sell_price(self, date: str, security_id: str) -> Decimal | None:
        bar = self._bar(date, security_id)
        rule = self._rule(date, security_id)
        if bar is None or rule is None or bar.open is None or bar.suspended is True:
            return None
        schedule = self._fee_schedule(date, security_id, "SELL")
        return _floor_tick(bar.open * (Decimal(1) - schedule.slippage_rate), rule.tick_size)

    def _rule(self, date: str, security_id: str) -> TradingRule | None:
        exchange = security_id.split(":", 1)[0]
        applicable = [
            rule
            for rule in self.data.trading_rules
            if rule.applies(date, exchange, self._board(security_id), "STOCK")
        ]
        if not applicable:
            return None
        applicable.sort(key=lambda rule: rule.effective_from)
        return applicable[-1]

    def _board(self, security_id: str) -> str:
        # The synthetic fixture uses MAIN unless the caller supplies a board
        # map; a real consumer must supply the DR06 board fact.
        return self.data.board_by_security.get(security_id, "MAIN")

    def _mark_open(self, date: str, security_id: str, position: Position) -> Decimal:
        bar = self._bar(date, security_id)
        if bar is None:
            raise _Blocked(f"OPEN_BAR_MISSING:{security_id}:{date}")
        if bar.data_status != "OK" and bar.suspended is not True:
            raise _Blocked(f"OPEN_DATA_UNKNOWN:{security_id}:{date}")
        if bar.suspended is True:
            if position.last_mark is None:
                raise _Blocked(f"STALE_MARK_UNKNOWN:{security_id}:{date}")
            return position.last_mark
        if bar.suspended is None:
            raise _Blocked(f"SUSPENSION_STATUS_UNKNOWN:{security_id}:{date}")
        if bar.open is None or bar.open <= 0:
            raise _Blocked(f"OPEN_PRICE_UNKNOWN:{security_id}:{date}")
        return bar.open

    def _mark_close(self, date: str, security_id: str, position: Position) -> Decimal:
        bar = self._bar(date, security_id)
        if bar is None:
            raise _Blocked(f"CLOSE_BAR_MISSING:{security_id}:{date}")
        if bar.data_status != "OK" and bar.suspended is not True:
            raise _Blocked(f"CLOSE_DATA_UNKNOWN:{security_id}:{date}")
        if bar.suspended is True:
            if position.last_mark is None:
                raise _Blocked(f"STALE_CLOSE_MARK_UNKNOWN:{security_id}:{date}")
            return position.last_mark
        if bar.suspended is None:
            raise _Blocked(f"SUSPENSION_STATUS_UNKNOWN:{security_id}:{date}")
        if bar.close is None or bar.close <= 0:
            raise _Blocked(f"CLOSE_PRICE_UNKNOWN:{security_id}:{date}")
        return bar.close

    # ------------------------------------------------------------------
    # Accounting helpers
    # ------------------------------------------------------------------

    def _allocate_lot_id(self, security_id: str, date: str) -> str:
        self.lot_counter += 1
        return f"{security_id}:{date}:L{self.lot_counter:06d}"

    def _max_affordable_quantity(
        self, date: str, security_id: str, price: Decimal, budget: Decimal, lot_size: int
    ) -> int:
        if price <= 0 or lot_size <= 0:
            return 0
        cap = min(budget, self.cash)
        quantity = int((cap / (price * Decimal(lot_size))).to_integral_value(rounding=ROUND_FLOOR)) * lot_size
        while quantity >= lot_size:
            gross = _money(price * Decimal(quantity))
            commission, other_fees = self._buy_fees(date, security_id, gross)
            if gross + commission + other_fees <= budget and gross + commission + other_fees <= self.cash:
                return quantity
            quantity -= lot_size
        return 0

    @staticmethod
    def _fee_market(security_id: str) -> str:
        return security_id.split(":", 1)[0]

    def _fee_candidates(self) -> list[FeeSchedule]:
        if self.data.fee_schedules:
            return list(self.data.fee_schedules)
        if self.data.fee_schedule is not None:
            return [self.data.fee_schedule]
        return []

    def _fee_schedule(self, date: str, security_id: str, side: str) -> FeeSchedule:
        open_at = parse_local_datetime(f"{date}T09:30:00", field="trade_open")
        matches = []
        for schedule in self._fee_candidates():
            if not schedule.synthetic and (schedule.market is None or schedule.side is None):
                raise _Blocked(
                    f"FEE_SCHEDULE_KEY_INCOMPLETE:{schedule.version}:{security_id}:{side}:{date}"
                )
            if not schedule.matches(date, self._fee_market(security_id), security_id, side):
                continue
            if schedule.known_at is None:
                if not schedule.synthetic:
                    raise _Blocked(
                        f"FEE_SCHEDULE_KNOWN_AT_MISSING:{schedule.version}:{security_id}:{side}:{date}"
                    )
            elif parse_local_datetime(schedule.known_at, field="known_at") >= open_at:
                continue
            matches.append(schedule)
        if not matches:
            raise _Blocked(f"FEE_SCHEDULE_NOT_APPLICABLE:{security_id}:{side}:{date}")
        if len(matches) > 1:
            versions = ",".join(sorted(schedule.version for schedule in matches))
            raise _Blocked(f"FEE_SCHEDULE_CONFLICT:{security_id}:{side}:{date}:{versions}")
        return matches[0]

    def _buy_fees(self, date: str, security_id: str, gross: Decimal) -> tuple[Decimal, Decimal]:
        schedule = self._fee_schedule(date, security_id, "BUY")
        if gross <= 0:
            return ZERO, ZERO
        commission = max(_money(gross * schedule.commission_rate), schedule.min_commission)
        other = _money(gross * schedule.transfer_fee_rate) + _money(gross * schedule.buy_tax_rate)
        return commission, other

    def _sell_fees(self, date: str, security_id: str, gross: Decimal) -> tuple[Decimal, Decimal]:
        schedule = self._fee_schedule(date, security_id, "SELL")
        if gross <= 0:
            return ZERO, ZERO
        commission = max(_money(gross * schedule.commission_rate), schedule.min_commission)
        other = _money(gross * schedule.sell_tax_rate) + _money(gross * schedule.transfer_fee_rate)
        return commission, other

    def _incremental_sell_fees(
        self, date: str, security_id: str, gross: Decimal
    ) -> tuple[Decimal, Decimal]:
        previous_gross = self.today_sell_gross_by_security.get(security_id, ZERO)
        previous_commission, previous_other = self.today_sell_fees_by_security.get(
            security_id, (ZERO, ZERO)
        )
        cumulative_gross = previous_gross + gross
        schedule = self._fee_schedule(date, security_id, "SELL")
        cumulative_commission = max(
            _money(cumulative_gross * schedule.commission_rate), schedule.min_commission
        )
        cumulative_other = _money(cumulative_gross * schedule.sell_tax_rate) + _money(
            cumulative_gross * schedule.transfer_fee_rate
        )
        commission = cumulative_commission - previous_commission
        other = cumulative_other - previous_other
        self.today_sell_gross_by_security[security_id] = cumulative_gross
        self.today_sell_fees_by_security[security_id] = (
            cumulative_commission,
            cumulative_other,
        )
        self.fee_entries.append(
            {
                "date": date,
                "security_id": security_id,
                "side": "SELL",
                "version": schedule.version,
                "gross": gross,
                "cumulative_gross": cumulative_gross,
                "commission": commission,
                "other_fees": other,
            }
        )
        return commission, other

    def _sellable_date(self, date: str, delay_days: int) -> str:
        index = self.full_calendar.index(date)
        target = index + max(0, delay_days)
        if target >= len(self.full_calendar):
            return "9999-12-31"
        return self.full_calendar[target]

    @staticmethod
    def _reduce_lots(
        position: Position,
        date: str,
        quantity: int,
        *,
        respect_sellable: bool = True,
    ) -> list[tuple[Lot, int]]:
        remaining = quantity
        taken: list[tuple[Lot, int]] = []
        lots = sorted(position.lots, key=lambda lot: (lot.sellable_date, lot.acquired_date))
        new_lots: list[Lot] = []
        for lot in lots:
            if remaining <= 0:
                new_lots.append(lot)
                continue
            if respect_sellable and lot.sellable_date > date:
                new_lots.append(lot)
                continue
            take = min(remaining, lot.quantity)
            remaining -= take
            taken.append((lot, take))
            if lot.quantity > take:
                new_lots.append(
                    Lot(
                        lot.quantity - take,
                        lot.acquired_date,
                        lot.sellable_date,
                        set(lot.dividend_actions),
                        lot.lot_id,
                    )
                )
        position.lots = new_lots
        if remaining > 0:
            raise _Blocked(f"LOT_QUANTITY_MISMATCH:{position.security_id}:{date}")
        return taken

    def _add_locked_exit(self, request: ExitRequest) -> None:
        if not self._has_holding(request.security_id):
            return
        requests = self.locked_exits.setdefault(request.security_id, [])
        key = (request.reason, request.trigger_date, request.priority)
        for existing in requests:
            if (existing.reason, existing.trigger_date, existing.priority) == key:
                return
        requests.append(request)
        requests.sort(key=lambda item: (item.trigger_date, item.priority, item.reason))

    def _record_simple_order(self, signal: Signal, date: str, status: str, reason: str) -> Order:
        return self._record_signal_order(signal, date, status, reason)

    def _record_signal_order(
        self,
        signal: Signal,
        date: str,
        status: str,
        reason: str | None,
        replacement_for: Signal | None = None,
        replacement_reason: str | None = None,
        *,
        requested_quantity: int | None = None,
        filled_quantity: int = 0,
        price: Decimal | None = None,
        gross: Decimal = ZERO,
        commission: Decimal = ZERO,
        other_fees: Decimal = ZERO,
    ) -> Order:
        self.order_counter += 1
        order = Order(
            order_id=f"O{self.order_counter:06d}",
            security_id=signal.security_id,
            side="BUY",
            attempt_date=date,
            signal_date=signal.signal_date,
            status=status,
            requested_quantity=(
                requested_quantity
                if requested_quantity is not None
                else (filled_quantity if filled_quantity > 0 else 0)
            ),
            filled_quantity=filled_quantity,
            price=price,
            gross=gross,
            commission=commission,
            other_fees=other_fees,
            reason=reason,
            strategy_id=signal.strategy_id,
            replacement_for=replacement_for.security_id if replacement_for is not None else None,
            replacement_reason=replacement_reason,
            original_candidate_rank=(
                replacement_for.candidate_rank if replacement_for is not None else signal.candidate_rank
            ),
            formal_candidate=signal.formal_candidate,
            industry_trigger_rank=signal.industry_trigger_rank,
            pool_rank=signal.pool_rank,
            signal_id=signal.signal_id,
        )
        self.orders.append(order)
        return order

    def _record_order(
        self,
        security_id: str,
        side: str,
        date: str,
        requested_quantity: int,
        status: str,
        *,
        filled_quantity: int = 0,
        price: Decimal | None = None,
        gross: Decimal = ZERO,
        commission: Decimal = ZERO,
        other_fees: Decimal = ZERO,
        reason: str | None = None,
        strategy_id: str | None = None,
        signal_date: str | None = None,
    ) -> Order:
        self.order_counter += 1
        order = Order(
            order_id=f"O{self.order_counter:06d}",
            security_id=security_id,
            side=side,
            attempt_date=date,
            signal_date=signal_date,
            status=status,
            requested_quantity=requested_quantity,
            filled_quantity=filled_quantity,
            price=price,
            gross=gross,
            commission=commission,
            other_fees=other_fees,
            reason=reason,
            strategy_id=strategy_id,
        )
        self.orders.append(order)
        return order

    # ------------------------------------------------------------------
    # Result
    # ------------------------------------------------------------------

    def _finalize(self) -> BacktestResult:
        final_positions = [
            snapshot for snapshot in self.position_history if self.nav_points and snapshot.date == self.nav_points[-1].date
        ]
        if self.locked_exits and (self.positions or self.legacy_positions):
            for sid in sorted(self.locked_exits):
                if self.locked_exits[sid]:
                    self.warnings.append(f"PENDING_EXIT_OUTSIDE_RANGE:{sid}")
        for pending in self.pending_batches:
            self.warnings.append(
                f"PENDING_PROPOSAL_OUTSIDE_RANGE:{pending['batch'].batch_id}"
            )
        cash_ok = all(item["cash_ok"] for item in self.reconciliation)
        equity_ok = all(item["equity_ok"] for item in self.reconciliation)
        engine_error = any(item.startswith("ENGINE_ERROR") for item in self.blockers)
        if engine_error:
            status = "FAILED"
        elif self.blockers:
            status = "BLOCKED"
        elif not cash_ok or not equity_ok:
            status = "FAILED"
            self.blockers.append("RECONCILIATION_MISMATCH")
        else:
            status = "SUCCEEDED"
        metrics = self._metrics()
        monthly_returns = self._period_returns(7)
        yearly_returns = self._period_returns(4)
        fixed_segment_returns = self._fixed_segment_returns()
        return BacktestResult(
            status=status,
            blockers=tuple(self.blockers),
            warnings=tuple(self.warnings),
            initial_cash=self.config.initial_cash,
            nav_points=list(self.nav_points),
            orders=list(self.orders),
            fills=list(self.fills),
            closed_cycles=list(self.closed_cycles),
            position_history=list(self.position_history),
            final_positions=final_positions,
            metrics=metrics,
            monthly_returns=monthly_returns,
            yearly_returns=yearly_returns,
            fixed_segment_returns=fixed_segment_returns,
            reconciliation=list(self.reconciliation),
            synthetic=self.config.synthetic,
            fee_entries=list(self.fee_entries),
            dividend_tax_entries=list(self.dividend_tax_entries),
            proposal_entries=list(self.proposal_entries),
            eligibility_entries=list(self.eligibility_entries),
        )

    def _fixed_segment_returns(self) -> dict[str, Decimal]:
        boundaries = tuple(self.config.segment_boundaries)
        if not boundaries or not self.nav_points:
            return {}
        index_by_date = {point.date: index for index, point in enumerate(self.nav_points)}
        returns: dict[str, Decimal] = {}
        previous_nav = Decimal(1)
        start_index = 0
        processed = 0
        for segment_number, boundary in enumerate(boundaries, 1):
            boundary_index = index_by_date.get(boundary)
            if boundary_index is None:
                break
            if boundary_index <= start_index:
                continue
            end_nav = self.nav_points[boundary_index - 1].nav
            returns[f"SEG{segment_number}"] = end_nav / previous_nav - 1
            previous_nav = end_nav
            start_index = boundary_index
            processed = segment_number
        returns[f"SEG{processed + 1}"] = self.nav_points[-1].nav / previous_nav - 1
        return returns

    def _period_returns(self, prefix_length: int) -> dict[str, Decimal]:
        if not self.nav_points:
            return {}
        returns: dict[str, Decimal] = {}
        previous_nav = Decimal(1)
        current_key = self.nav_points[0].date[:prefix_length]
        last_nav = Decimal(1)
        for point in self.nav_points:
            key = point.date[:prefix_length]
            if key != current_key:
                returns[current_key] = last_nav / previous_nav - 1
                previous_nav = last_nav
                current_key = key
            last_nav = point.nav
        returns[current_key] = last_nav / previous_nav - 1
        return returns

    def _metrics(self) -> dict[str, Decimal | float | None]:
        if not self.nav_points:
            return {
                "cumulative_return": None,
                "annualized_return": None,
                "cumulative_excess": None,
                "max_drawdown": None,
                "sharpe": None,
                "win_rate": None,
                "profit_loss_ratio": None,
                "buy_count": Decimal(0),
                "sell_count": Decimal(0),
                "closed_cycle_count": Decimal(0),
                "avg_daily_turnover": None,
                "position_ratio": None,
                "benchmark_return": None,
            }
        last = self.nav_points[-1]
        cumulative_return = last.nav - 1
        days = len(self.nav_points)
        annualized = None
        if last.nav > 0 and days > 0:
            annualized = float(last.nav) ** (252.0 / days) - 1.0
        benchmark_return = last.benchmark - 1 if last.benchmark is not None else None
        cumulative_excess = (
            cumulative_return - benchmark_return if benchmark_return is not None else None
        )
        max_drawdown = abs(min((point.drawdown or ZERO) for point in self.nav_points))
        returns = [float(point.daily_return) for point in self.nav_points if point.daily_return is not None]
        sharpe = None
        if len(returns) >= 2:
            mean = sum(returns) / len(returns)
            variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
            if variance > 0:
                sharpe = math.sqrt(252.0) * mean / math.sqrt(variance)
        wins = [cycle.total_pnl for cycle in self.closed_cycles if cycle.total_pnl > 0]
        losses = [cycle.total_pnl for cycle in self.closed_cycles if cycle.total_pnl < 0]
        win_rate = Decimal(len(wins)) / Decimal(len(self.closed_cycles)) if self.closed_cycles else None
        profit_loss_ratio = None
        if wins and losses:
            avg_win = sum(wins, ZERO) / Decimal(len(wins))
            avg_loss = abs(sum(losses, ZERO) / Decimal(len(losses)))
            if avg_loss > 0:
                profit_loss_ratio = avg_win / avg_loss
        turnovers = [point.turnover for point in self.nav_points if point.turnover is not None]
        avg_turnover = sum(turnovers, ZERO) / Decimal(len(turnovers)) if turnovers else None
        return {
            "cumulative_return": cumulative_return,
            "annualized_return": annualized,
            "cumulative_excess": cumulative_excess,
            "max_drawdown": max_drawdown,
            "sharpe": sharpe,
            "win_rate": win_rate,
            "profit_loss_ratio": profit_loss_ratio,
            "buy_count": Decimal(sum(1 for order in self.orders if order.side == "BUY" and order.filled_quantity > 0)),
            "sell_count": Decimal(sum(1 for order in self.orders if order.side == "SELL" and order.filled_quantity > 0)),
            "closed_cycle_count": Decimal(len(self.closed_cycles)),
            "avg_daily_turnover": avg_turnover,
            "position_ratio": last.position_ratio,
            "benchmark_return": benchmark_return,
        }


def run_backtest(data: BacktestInput, config: BacktestConfig | None = None) -> BacktestResult:
    config = config or BacktestConfig()
    engine = _Engine(data, config)
    try:
        engine._prepare()
        for index, date in enumerate(engine.dates):
            engine._run_day(date, index)
    except _Blocked as exc:
        engine.blockers.append(str(exc))
    except Exception as exc:  # pragma: no cover - defensive boundary
        engine.blockers.append(f"ENGINE_ERROR:{type(exc).__name__}:{exc}")
    return engine._finalize()
