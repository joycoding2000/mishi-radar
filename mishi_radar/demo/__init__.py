"""WP-FX01B fixed-fixture Web slice with the WP-H1-FX01 observation book.

The F1/F3/F7 pages consume the Owner-accepted ``mishi_radar.result_contract``
payloads.  H1 values manual observations with the same fixed synthetic raw
closes and reuses the accepted S01 exit decision when inputs are complete.
F6 runs the accepted OD-2 cash engine on fixed synthetic inputs.  This package
never contacts a market data source.
"""

from __future__ import annotations

from ..result_contract import (
    FIXTURE_MARKER as CONTRACT_MARKER,
    FIXTURE_VERSION as CONTRACT_FIXTURE_VERSION,
    RESULT_CONTRACT_VERSION,
)

FIXTURE_MARKER = "SYNTHETIC / FIXTURE / 非真实行情"
FIXTURE_VERSION = "FX01B-OD2-2026-10-23-v1"
CONTRACT_MARKER = CONTRACT_MARKER
CONTRACT_FIXTURE_VERSION = CONTRACT_FIXTURE_VERSION
RESULT_CONTRACT_VERSION = RESULT_CONTRACT_VERSION

__all__ = [
    "CONTRACT_FIXTURE_VERSION",
    "CONTRACT_MARKER",
    "FIXTURE_MARKER",
    "FIXTURE_VERSION",
    "RESULT_CONTRACT_VERSION",
]
