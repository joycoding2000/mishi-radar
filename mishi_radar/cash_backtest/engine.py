"""OD-2 daily cash, order, position and NAV engine.

The engine intentionally knows nothing about S01-S08 conditions.  It consumes
structured signals and exit decisions, and owns only portfolio mechanics,
execution restrictions, fees, corporate actions and accounting.
"""

from __future__ import annotations

import math
from dataclasses import replace
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from typing import Iterable, Mapping, Sequence

from .accounting import (
    allocate_sale_cost,
    cycle_total_pnl,
    remaining_open_stop_ratio,
    split_dividend_entitlement,
)
from .model import (
    BacktestConfig,
    BacktestInput,
    BacktestResult,
    ClosedCycle,
    CorporateAction,
    DailyBar,
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
        self.dividend_entitlements: dict[str, tuple[str, int]] = {}
        self.pending_actions: dict[str, CorporateAction] = {}
        self.external_dividend_claims: list[dict] = []
        self.dividend_payments: list[dict] = []
        self.cash_adjustments: list[dict] = []
        self.order_counter = 0
        self.exited_today: set[str] = set()
        self.today_buy_gross = ZERO
        self.today_sell_gross = ZERO
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
        if not self.data.fee_schedule.applies(self.start_date):
            raise _Blocked("FEE_SCHEDULE_NOT_APPLICABLE_AT_START")
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

    def _run_day(self, date: str, day_index: int) -> None:
        day = self.data.market_days[date]
        self.current_date = date
        self.exited_today = set()
        self.today_buy_gross = ZERO
        self.today_sell_gross = ZERO
        full_index = self.full_calendar.index(date)
        previous_date = self.full_calendar[full_index - 1] if full_index > 0 else None
        raw_signals = self.data.signals_by_signal_date.get(previous_date, ()) if previous_date else ()
        relevant_ids = set(self.positions) | {signal.security_id for signal in raw_signals}
        self._apply_corporate_actions(date, day, relevant_ids)
        self._process_external_dividend_claims(date)
        self._process_dividend_payments(date)

        if previous_date is not None:
            for request in self.data.exit_requests_by_signal_date.get(previous_date, ()):
                self._add_locked_exit(request)

        for position in self.positions.values():
            if position.holding_start < date:
                position.holding_days += 1

        mark_open: dict[str, Decimal] = {}
        open_values: dict[str, Decimal] = {}
        for sid, position in self.positions.items():
            price = self._mark_open(date, sid, position)
            mark_open[sid] = price
            open_values[sid] = Decimal(position.quantity) * price
        e_open = self.cash + self.receivables - self.payables + sum(open_values.values(), ZERO)
        target_weight = e_open / Decimal(self.config.top_n) if e_open > 0 else ZERO

        is_rebalance = (self.full_calendar.index(date) - self.start_index) % self.config.rebalance_days == 0
        signals = self._signals_for_trade_date(previous_date, date)
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
        targets = formal_targets[: self.config.top_n]
        target_ids = {signal.security_id for signal in targets}

        locked_ids = {sid for sid, requests in self.locked_exits.items() if requests}
        sell_plan = self._build_sell_plan(
            date,
            mark_open,
            open_values,
            target_weight,
            target_ids,
            is_rebalance,
            locked_ids,
            previous_date,
        )
        for sid in sorted(sell_plan, key=lambda item: self._sell_sort_key(item, sell_plan[item])):
            plan = sell_plan[sid]
            position = self.positions.get(sid)
            if position is None:
                continue
            self._execute_sell(
                date,
                position,
                plan["quantity"],
                plan["reasons"],
                plan["locked"],
                plan["exit_intent"],
                plan["signal_date"],
            )

        if is_rebalance:
            self._execute_buys(date, targets, mark_open, target_weight, candidate_pool)

        self._close_day(date, day, mark_open, e_open, target_weight)

    # ------------------------------------------------------------------
    # Signals and target construction
    # ------------------------------------------------------------------

    def _signals_for_trade_date(self, previous_date: str | None, trade_date: str) -> list[Signal]:
        if previous_date is None:
            return []
        signals = list(self.data.signals_by_signal_date.get(previous_date, ()))
        strategy_signals = [signal for signal in signals if signal.strategy_id == self.config.strategy_id]
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
                self._record_simple_order(
                    signal,
                    trade_date,
                    "EXPIRED",
                    "EXPIRED_INPUT_WINDOW",
                )
                continue
            if execution_date > trade_date:
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
        if signal.available_at is None:
            if self.config.require_known_signal_availability:
                raise _Blocked(f"SIGNAL_AVAILABILITY_UNKNOWN:{signal.security_id}")
            return first_open
        if signal.available_at <= first_open:
            return first_open
        for date in self.full_calendar[next_index:]:
            if date >= signal.available_at:
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
        for sid, position in self.positions.items():
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
            elif is_rebalance:
                if sid not in target_ids:
                    reasons = ["RANK_REMOVAL"]
                    quantity = position.quantity
                    exit_intent = True
                else:
                    current_value = open_values.get(sid, ZERO)
                    if current_value > target_weight:
                        sell_price = self._probe_sell_price(date, sid)
                        if sell_price is not None and sell_price > 0:
                            excess = current_value - target_weight
                            quantity = int((excess / sell_price).to_integral_value(rounding=ROUND_FLOOR))
                            if quantity > 0:
                                reasons = ["TARGET_WEIGHT_REDUCTION"]
            if quantity > 0:
                plan[sid] = {
                    "quantity": min(quantity, position.quantity),
                    "reasons": reasons,
                    "locked": locked,
                    "exit_intent": exit_intent,
                    "signal_date": signal_date,
                }
        return plan

    @staticmethod
    def _sell_sort_key(sid: str, plan: Mapping) -> tuple:
        return (0 if plan["locked"] else 1, sid)

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
            if len(self.positions) >= self.config.top_n:
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
            if len(self.positions) >= self.config.top_n:
                break
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
        sell_price = _floor_tick(bar.open * (Decimal(1) - self.data.fee_schedule.slippage_rate), rule.tick_size)
        limit_down = self._limit_down(date, sid, bar, rule)
        if limit_down is None and not (bar.no_price_limit or rule.no_price_limit):
            raise _Blocked(f"SELL_PRICE_LIMIT_UNKNOWN:{sid}:{date}")
        if limit_down is not None and (bar.open <= limit_down or sell_price <= limit_down):
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
        quantity = min(requested_quantity, sellable)
        if quantity <= 0:
            return
        will_close = quantity == position.quantity
        new_claims = self._allocate_pending_entitlements(position, quantity, date, will_close)
        gross = _money(sell_price * Decimal(quantity))
        commission, other_fees = self._sell_fees(date, gross)
        fees = commission + other_fees
        cash_in = gross - fees
        self.cash += cash_in
        self.total_fees += fees
        self.total_commission += commission
        self.total_tax += _money(gross * self.data.fee_schedule.sell_tax_rate)
        cost_sold, cost_remaining = allocate_sale_cost(position.cost_open, quantity, position.quantity)
        dividend_sold, dividend_remaining, dividend_units_remaining = split_dividend_entitlement(
            position.dividend_open, position.dividend_units, quantity
        )
        position.dividend_open = dividend_remaining
        position.dividend_units = dividend_units_remaining
        realized_trade = _money(gross - fees - cost_sold)
        position.realized_trading_pnl += realized_trade
        position.realized_dividend += dividend_sold
        position.cost_open = cost_remaining
        position.quantity -= quantity
        self._reduce_lots(position, date, quantity)
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
            del self.positions[sid]
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
        buy_price = _ceil_tick(bar.open * (Decimal(1) + self.data.fee_schedule.slippage_rate), rule.tick_size)
        current_value = Decimal(current_position.quantity) * mark_open if current_position is not None and mark_open is not None else ZERO
        budget = max(ZERO, target_weight - current_value)
        if budget <= 0:
            return False, None
        lot_size = rule.lot_size
        if lot_size <= 0:
            raise _Blocked(f"LOT_SIZE_INVALID:{sid}:{date}")
        planned_quantity = self._max_affordable_quantity(date, buy_price, budget, lot_size)

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
        commission, other_fees = self._buy_fees(date, gross)
        fees = commission + other_fees
        total_cost = gross + fees
        self.cash -= total_cost
        self.total_fees += fees
        self.total_commission += commission
        self.total_tax += _money(gross * self.data.fee_schedule.buy_tax_rate)
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
                lots=[Lot(quantity, date, sellable_date)],
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
                Lot(quantity, date, self._sellable_date(date, rule.sell_delay_days))
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

    def _allocate_pending_entitlements(
        self,
        position: Position,
        quantity_sold: int,
        date: str,
        will_close: bool,
    ) -> list[dict]:
        claims: list[dict] = []
        for key, (security_id, entitled_quantity) in list(self.dividend_entitlements.items()):
            if security_id != position.security_id or entitled_quantity <= 0:
                continue
            action = self.pending_actions.get(key)
            if action is None or action.effective_date <= date:
                continue
            sold_entitled = min(quantity_sold, entitled_quantity)
            if sold_entitled <= 0:
                continue
            if action.action_type != "CASH_DIVIDEND":
                raise _Blocked(
                    f"ENTITLEMENT_SALE_BEFORE_EFFECTIVE:{position.security_id}:{action.action_type}:{date}"
                )
            self.dividend_entitlements[key] = (security_id, entitled_quantity - sold_entitled)
            claims.append(
                {
                    "security_id": position.security_id,
                    "quantity": sold_entitled,
                    "action": action,
                    "closed_cycle_index": None,
                    "opened_on": position.holding_start,
                    "closed_on": date if will_close else None,
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
            if action.cash_per_share is None or action.dividend_tax_rate is None:
                raise _Blocked(f"EXTERNAL_DIVIDEND_TERMS_UNKNOWN:{claim['security_id']}:{date}")
            gross = _money(action.cash_per_share * Decimal(claim["quantity"]))
            tax = _money(gross * action.dividend_tax_rate)
            net = gross - tax
            self.receivables += gross
            self.payables += tax
            self.total_tax += tax
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

    def _process_record_dates(self, date: str) -> None:
        for action in self.actions_by_record.get(date, ()):
            if action.status != "IMPLEMENTED":
                if action.security_id in self.positions:
                    raise _Blocked(f"CORPORATE_ACTION_NOT_IMPLEMENTED:{action.security_id}:{action.action_type}")
                continue
            position = self.positions.get(action.security_id)
            if position is not None:
                key = _action_key(action)
                self.dividend_entitlements[key] = (action.security_id, position.quantity)
                self.pending_actions[key] = action

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

    def _apply_cash_dividend(self, action: CorporateAction, position: Position, date: str) -> None:
        if action.cash_per_share is None:
            raise _Blocked(f"DIVIDEND_CASH_PER_SHARE_MISSING:{action.security_id}:{date}")
        if action.dividend_tax_rate is None:
            raise _Blocked(f"DIVIDEND_TAX_RATE_UNKNOWN:{action.security_id}:{date}")
        if position.last_mark is not None:
            position.last_mark = max(ZERO, position.last_mark - action.cash_per_share)
        entitlement = self.dividend_entitlements.get(_action_key(action))
        if action.record_date is not None:
            quantity = entitlement[1] if entitlement is not None else 0
        else:
            quantity = position.quantity
        if quantity <= 0:
            return
        gross = _money(action.cash_per_share * Decimal(quantity))
        tax = _money(gross * action.dividend_tax_rate)
        net = gross - tax
        self.receivables += gross
        self.payables += tax
        self.total_tax += tax
        position.dividend_open += net
        position.dividend_units = quantity
        self.dividend_payments.append(
            {
                "security_id": action.security_id,
                "pay_date": action.pay_date,
                "gross": gross,
                "tax": tax,
                "net": net,
                "paid": False,
            }
        )

    def _apply_share_change(self, action: CorporateAction, position: Position, date: str) -> None:
        if action.share_multiplier is None or action.share_multiplier <= 0:
            raise _Blocked(f"SHARE_MULTIPLIER_MISSING:{action.security_id}:{date}")
        if action.record_date is not None:
            entitlement = self.dividend_entitlements.get(_action_key(action))
            entitled_quantity = entitlement[1] if entitlement is not None else 0
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
            self.cash_adjustments.append(
                {"reason": f"CASH_IN_LIEU:{action.security_id}:{date}", "amount": action.cash_in_lieu}
            )
            self.warnings.append(f"CASH_IN_LIEU:{action.security_id}:{date}:{action.cash_in_lieu}")
        delta = new_quantity - old_quantity
        if delta > 0:
            position.lots.append(
                Lot(delta, date, action.new_share_sellable_date or date)
            )
        elif delta < 0:
            self._reduce_lots(position, date, -delta, respect_sellable=False)
        position.quantity = new_quantity
        if position.dividend_units > new_quantity:
            position.dividend_units = new_quantity
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
        mark_close: dict[str, Decimal] = {}
        for sid, position in self.positions.items():
            price = self._mark_close(date, sid, position)
            mark_close[sid] = price
            position.last_mark = price
        market_value = sum(
            (Decimal(position.quantity) * mark_close[sid] for sid, position in self.positions.items()),
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
            position_count=len(self.positions),
            open_equity=open_equity,
            target_weight=target_weight,
            turnover=turnover,
            position_ratio=position_ratio,
        )
        self.nav_points.append(nav_point)
        for sid in sorted(self.positions):
            position = self.positions[sid]
            price = mark_close[sid]
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
        for sid, position in self.positions.items():
            price = mark_close[sid]
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
        open_market_value = sum(
            (Decimal(position.quantity) * mark_open.get(sid, position.last_mark or ZERO) for sid, position in self.positions.items()),
            ZERO,
        )
        close_market_value = sum(
            (Decimal(position.quantity) * mark_close.get(sid, position.last_mark or ZERO) for sid, position in self.positions.items()),
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
        return day.bars.get(security_id)

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
        return _floor_tick(bar.open * (Decimal(1) - self.data.fee_schedule.slippage_rate), rule.tick_size)

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

    def _max_affordable_quantity(self, date: str, price: Decimal, budget: Decimal, lot_size: int) -> int:
        if price <= 0 or lot_size <= 0:
            return 0
        cap = min(budget, self.cash)
        quantity = int((cap / (price * Decimal(lot_size))).to_integral_value(rounding=ROUND_FLOOR)) * lot_size
        while quantity >= lot_size:
            gross = _money(price * Decimal(quantity))
            commission, other_fees = self._buy_fees(date, gross)
            if gross + commission + other_fees <= budget and gross + commission + other_fees <= self.cash:
                return quantity
            quantity -= lot_size
        return 0

    def _buy_fees(self, date: str, gross: Decimal) -> tuple[Decimal, Decimal]:
        schedule = self.data.fee_schedule
        if not schedule.applies(date):
            raise _Blocked(f"FEE_SCHEDULE_NOT_APPLICABLE:{date}")
        if gross <= 0:
            return ZERO, ZERO
        commission = max(_money(gross * schedule.commission_rate), schedule.min_commission)
        other = _money(gross * schedule.transfer_fee_rate) + _money(gross * schedule.buy_tax_rate)
        return commission, other

    def _sell_fees(self, date: str, gross: Decimal) -> tuple[Decimal, Decimal]:
        schedule = self.data.fee_schedule
        if not schedule.applies(date):
            raise _Blocked(f"FEE_SCHEDULE_NOT_APPLICABLE:{date}")
        if gross <= 0:
            return ZERO, ZERO
        commission = max(_money(gross * schedule.commission_rate), schedule.min_commission)
        other = _money(gross * schedule.sell_tax_rate) + _money(gross * schedule.transfer_fee_rate)
        return commission, other

    def _sellable_date(self, date: str, delay_days: int) -> str:
        index = self.full_calendar.index(date)
        target = index + max(0, delay_days)
        if target >= len(self.full_calendar):
            return "9999-12-31"
        return self.full_calendar[target]

    @staticmethod
    def _reduce_lots(position: Position, date: str, quantity: int, *, respect_sellable: bool = True) -> None:
        remaining = quantity
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
            if lot.quantity > take:
                new_lots.append(Lot(lot.quantity - take, lot.acquired_date, lot.sellable_date))
        position.lots = new_lots
        if remaining > 0:
            raise _Blocked(f"LOT_QUANTITY_MISMATCH:{position.security_id}:{date}")

    def _add_locked_exit(self, request: ExitRequest) -> None:
        if request.security_id not in self.positions:
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
        if self.locked_exits and self.positions:
            for sid in sorted(self.locked_exits):
                if self.locked_exits[sid]:
                    self.warnings.append(f"PENDING_EXIT_OUTSIDE_RANGE:{sid}")
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
            reconciliation=list(self.reconciliation),
            synthetic=self.config.synthetic,
        )

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
