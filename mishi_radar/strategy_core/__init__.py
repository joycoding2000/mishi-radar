"""OD-1 strategy, ranking and diagnostic calculation kernel."""

from .config import (
    S01_DEFAULT_CONFIG,
    S01_DEFAULT_CONFIG_ID,
    S01_DEFAULT_CONFIG_VERSION,
    ConfigBundle,
    default_configs,
)
from .engine import (
    compute_all,
    compute_diagnostics,
    compute_strategy,
    evaluate_exit,
    signal_records,
    style_view,
)
from .model import (
    ConditionStatus,
    Eligibility,
    FinancialSnapshot,
    MarketBar,
    MarketSnapshot,
    Numeric,
    SecurityInfo,
    SignalState,
    ValueStatus,
)

__all__ = [
    "S01_DEFAULT_CONFIG",
    "S01_DEFAULT_CONFIG_ID",
    "S01_DEFAULT_CONFIG_VERSION",
    "ConfigBundle",
    "ConditionStatus",
    "Eligibility",
    "FinancialSnapshot",
    "MarketBar",
    "MarketSnapshot",
    "Numeric",
    "SecurityInfo",
    "SignalState",
    "ValueStatus",
    "compute_all",
    "compute_diagnostics",
    "compute_strategy",
    "default_configs",
    "evaluate_exit",
    "signal_records",
    "style_view",
]
