"""Approved finite parameter whitelists and immutable default identities."""

from __future__ import annotations

from dataclasses import dataclass, replace
from decimal import Decimal

DEFAULT_CONFIG_VERSION = "R3.2-2026-10-19-OD1-v1"
S01_DEFAULT_CONFIG_ID = "S01_DEFAULT"
S01_DEFAULT_CONFIG_VERSION = f"{S01_DEFAULT_CONFIG_ID}/{DEFAULT_CONFIG_VERSION}"


def _require_choice(field_name: str, value, allowed) -> None:
    if value not in allowed:
        raise ValueError(f"{field_name}={value!r} is outside the approved whitelist {sorted(allowed, key=str)}")


@dataclass(frozen=True)
class CommonConfig:
    min_listed_days: int = 120
    min_avg_amount_20: Decimal = Decimal("30000000")
    stop_loss: Decimal | None = Decimal("0.08")

    def __post_init__(self) -> None:
        _require_choice("min_listed_days", self.min_listed_days, {120, 180, 252})
        _require_choice(
            "min_avg_amount_20",
            self.min_avg_amount_20,
            {Decimal("30000000"), Decimal("50000000"), Decimal("100000000")},
        )
        _require_choice("stop_loss", self.stop_loss, {None, Decimal("0.05"), Decimal("0.08"), Decimal("0.10")})


@dataclass(frozen=True)
class S01Config:
    ma_short: int = 20
    ma_long: int = 60
    max_holding: int = 20
    config_id: str = S01_DEFAULT_CONFIG_ID
    config_version: str = S01_DEFAULT_CONFIG_VERSION

    def __post_init__(self) -> None:
        _require_choice("ma_short", self.ma_short, {10, 20, 30})
        _require_choice("ma_long", self.ma_long, {60, 90, 120})
        _require_choice("max_holding", self.max_holding, {10, 20})
        if self.ma_short >= self.ma_long:
            raise ValueError("ma_short must be smaller than ma_long")


@dataclass(frozen=True)
class S02Config:
    platform_width: Decimal = Decimal("0.15")
    shrink_ratio: Decimal = Decimal("0.8")
    breakout_volume: Decimal = Decimal("1.5")
    max_holding: int = 10

    def __post_init__(self) -> None:
        _require_choice("platform_width", self.platform_width, {Decimal("0.10"), Decimal("0.15"), Decimal("0.20")})
        _require_choice("shrink_ratio", self.shrink_ratio, {Decimal("0.6"), Decimal("0.8"), Decimal("1.0")})
        _require_choice("breakout_volume", self.breakout_volume, {Decimal("1.2"), Decimal("1.5"), Decimal("2.0")})
        _require_choice("max_holding", self.max_holding, {5, 10, 20})


@dataclass(frozen=True)
class S03Config:
    ma_distance: Decimal = Decimal("0.03")
    drawdown_low: Decimal = Decimal("0.03")
    drawdown_high: Decimal = Decimal("0.10")
    max_holding: int = 10

    def __post_init__(self) -> None:
        _require_choice("ma_distance", self.ma_distance, {Decimal("0.02"), Decimal("0.03"), Decimal("0.05")})
        _require_choice(
            "drawdown_range",
            (self.drawdown_low, self.drawdown_high),
            {
                (Decimal("0.03"), Decimal("0.08")),
                (Decimal("0.03"), Decimal("0.10")),
                (Decimal("0.05"), Decimal("0.15")),
            },
        )
        _require_choice("max_holding", self.max_holding, {5, 10, 20})


@dataclass(frozen=True)
class S04Config:
    prior_drop_threshold: Decimal = Decimal("-0.08")
    max_holding: int = 5

    def __post_init__(self) -> None:
        _require_choice(
            "prior_drop_threshold",
            self.prior_drop_threshold,
            {Decimal("-0.05"), Decimal("-0.08"), Decimal("-0.10")},
        )
        _require_choice("max_holding", self.max_holding, {3, 5, 10})


@dataclass(frozen=True)
class S05Config:
    low_vol_percentile: Decimal = Decimal("0.40")
    max_holding: int = 20

    def __post_init__(self) -> None:
        _require_choice(
            "low_vol_percentile",
            self.low_vol_percentile,
            {Decimal("0.20"), Decimal("0.30"), Decimal("0.40")},
        )
        _require_choice("max_holding", self.max_holding, {10, 20})


@dataclass(frozen=True)
class S06Config:
    breadth_threshold: Decimal = Decimal("0.60")
    strong_industry_count: int = 5
    max_per_industry: int = 2
    max_holding: int = 20
    bound_s01_config_version: str = S01_DEFAULT_CONFIG_VERSION

    def __post_init__(self) -> None:
        _require_choice(
            "breadth_threshold",
            self.breadth_threshold,
            {Decimal("0.50"), Decimal("0.60"), Decimal("0.70")},
        )
        _require_choice("strong_industry_count", self.strong_industry_count, {3, 5})
        _require_choice("max_per_industry", self.max_per_industry, {1, 2})
        _require_choice("max_holding", self.max_holding, {10, 20})
        if self.bound_s01_config_version != S01_DEFAULT_CONFIG_VERSION:
            raise ValueError("S06 must bind the fixed S01_DEFAULT/R3.2-2026-10-19-OD1-v1 identity")


@dataclass(frozen=True)
class S07Config:
    roe_threshold: Decimal = Decimal("0.10")
    rebalance_days: int = 20

    def __post_init__(self) -> None:
        _require_choice("roe_threshold", self.roe_threshold, {Decimal("0.08"), Decimal("0.10"), Decimal("0.15")})
        _require_choice("rebalance_days", self.rebalance_days, {10, 20})


@dataclass(frozen=True)
class S08Config:
    positive_days_required: int = 3
    max_holding: int = 10

    def __post_init__(self) -> None:
        _require_choice("positive_days_required", self.positive_days_required, {3, 4, 5})
        _require_choice("max_holding", self.max_holding, {5, 10, 20})


S01_DEFAULT_CONFIG = S01Config()
S02_DEFAULT_CONFIG = S02Config()
S03_DEFAULT_CONFIG = S03Config()
S04_DEFAULT_CONFIG = S04Config()
S05_DEFAULT_CONFIG = S05Config()
S06_DEFAULT_CONFIG = S06Config()
S07_DEFAULT_CONFIG = S07Config()
S08_DEFAULT_CONFIG = S08Config()
COMMON_DEFAULT_CONFIG = CommonConfig()


@dataclass(frozen=True)
class ConfigBundle:
    common: CommonConfig = COMMON_DEFAULT_CONFIG
    s01: S01Config = S01_DEFAULT_CONFIG
    s02: S02Config = S02_DEFAULT_CONFIG
    s03: S03Config = S03_DEFAULT_CONFIG
    s04: S04Config = S04_DEFAULT_CONFIG
    s05: S05Config = S05_DEFAULT_CONFIG
    s06: S06Config = S06_DEFAULT_CONFIG
    s07: S07Config = S07_DEFAULT_CONFIG
    s08: S08Config = S08_DEFAULT_CONFIG

    def with_s01(self, config: S01Config) -> "ConfigBundle":
        """Return a copy with a personal S01 configuration.

        The S06 calculation intentionally keeps using the immutable default
        S01 identity; this helper exists so callers can test that separation.
        """

        return replace(self, s01=config)


def default_configs() -> ConfigBundle:
    return ConfigBundle()
