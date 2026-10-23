"""WP-FX01 fixed-fixture product vertical slice.

Every input in this package is synthetic.  The package never contacts a market
data source; it only feeds fixed, versioned fixtures into the already accepted
OD-1 (``mishi_radar.strategy_core``) and OD-2 (``mishi_radar.cash_backtest``)
kernels.
"""

from __future__ import annotations

FIXTURE_VERSION = "FX01-2026-10-23-v1"
FIXTURE_MARKER = "SYNTHETIC / FIXTURE / 非真实行情"

__all__ = ["FIXTURE_MARKER", "FIXTURE_VERSION"]
