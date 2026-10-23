"""Fixed synthetic scenarios for the F6 OD-2 cash demonstration.

F1/F3/F7 use the accepted ``mishi_radar.result_contract`` fixture instead.
Nothing in this module reads a clock, random source or network.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Mapping

BACKTEST_SCENARIOS: Mapping[str, Mapping[str, str]] = {
    "u3": {
        "label": "U3 已验收合成现金场景",
        "description": "复用 OD-2 已验收的合成算例：补买、逐批股息税、卖出与 NAV 对账。",
    },
    "failures": {
        "label": "执行受阻与重试",
        "description": "合成买入停牌、持仓跌停卖不出并在后续开盘重试；失败原因来自内核订单记录。",
    },
    "empty": {
        "label": "无信号现金曲线",
        "description": "完整输入但没有信号；成功保持现金，NAV=1，交易指标为 N/A。",
    },
    "blocked": {
        "label": "输入 UNKNOWN 阻断",
        "description": "信号可用时刻未知；内核保留已知前缀并 BLOCKED，不伪装成成功回测。",
    },
}


def trading_dates(count: int, end: date = date(2026, 10, 16)) -> tuple[str, ...]:
    values: list[str] = []
    cursor = end
    while len(values) < count:
        if cursor.weekday() < 5:
            values.append(cursor.isoformat())
        cursor -= timedelta(days=1)
    return tuple(reversed(values))
