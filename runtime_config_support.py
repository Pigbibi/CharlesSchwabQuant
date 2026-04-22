from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from quant_platform_kit.common.runtime_config import (
    resolve_bool_value,
    resolve_strategy_runtime_path_settings,
)
from strategy_registry import (
    SCHWAB_PLATFORM,
    resolve_strategy_definition,
    resolve_strategy_metadata,
)
from us_equity_strategies import get_strategy_catalog

DEFAULT_NOTIFY_LANG = "en"
DEFAULT_RESERVED_CASH_FLOOR_USD = 150.0
DEFAULT_RESERVED_CASH_RATIO = 0.03


@dataclass(frozen=True)
class PlatformRuntimeSettings:
    strategy_profile: str
    strategy_display_name: str
    strategy_domain: str
    notify_lang: str
    dry_run_only: bool
    reserved_cash_floor_usd: float = DEFAULT_RESERVED_CASH_FLOOR_USD
    reserved_cash_ratio: float = DEFAULT_RESERVED_CASH_RATIO
    feature_snapshot_path: str | None = None
    feature_snapshot_manifest_path: str | None = None
    strategy_config_path: str | None = None
    strategy_config_source: str | None = None
    strategy_plugin_mounts_json: str | None = None


def _resolve_non_negative_float_env(name: str, *, default: float) -> float:
    raw_value = os.getenv(name)
    if raw_value is None or raw_value.strip() == "":
        return float(default)
    value = float(raw_value)
    if value < 0:
        raise ValueError(f"{name} must be non-negative, got {value}")
    return value


def _resolve_ratio_env(name: str, *, default: float) -> float:
    value = _resolve_non_negative_float_env(name, default=default)
    if value > 1.0:
        raise ValueError(f"{name} must be in [0,1], got {value}")
    return value


def resolve_strategy_profile(raw_value: str | None = None) -> str:
    return resolve_strategy_definition(
        raw_value if raw_value is not None else os.getenv("STRATEGY_PROFILE"),
        platform_id=SCHWAB_PLATFORM,
    ).profile


def load_platform_runtime_settings() -> PlatformRuntimeSettings:
    strategy_definition = resolve_strategy_definition(
        os.getenv("STRATEGY_PROFILE"),
        platform_id=SCHWAB_PLATFORM,
    )
    strategy_metadata = resolve_strategy_metadata(
        strategy_definition.profile,
        platform_id=SCHWAB_PLATFORM,
    )
    runtime_paths = resolve_strategy_runtime_path_settings(
        strategy_catalog=get_strategy_catalog(),
        strategy_definition=strategy_definition,
        strategy_metadata=strategy_metadata,
        platform_env_prefix="SCHWAB",
        env=os.environ,
        repo_root=Path(__file__).resolve().parent,
    )
    return PlatformRuntimeSettings(
        strategy_profile=runtime_paths.strategy_profile,
        strategy_display_name=runtime_paths.strategy_display_name,
        strategy_domain=runtime_paths.strategy_domain,
        notify_lang=os.getenv("NOTIFY_LANG", DEFAULT_NOTIFY_LANG),
        dry_run_only=resolve_bool_value(os.getenv("SCHWAB_DRY_RUN_ONLY")),
        reserved_cash_floor_usd=_resolve_non_negative_float_env(
            "SCHWAB_MIN_RESERVED_CASH_USD",
            default=DEFAULT_RESERVED_CASH_FLOOR_USD,
        ),
        reserved_cash_ratio=_resolve_ratio_env(
            "SCHWAB_RESERVED_CASH_RATIO",
            default=DEFAULT_RESERVED_CASH_RATIO,
        ),
        feature_snapshot_path=runtime_paths.feature_snapshot_path,
        feature_snapshot_manifest_path=runtime_paths.feature_snapshot_manifest_path,
        strategy_config_path=runtime_paths.strategy_config_path,
        strategy_config_source=runtime_paths.strategy_config_source,
        strategy_plugin_mounts_json=(
            os.getenv("SCHWAB_STRATEGY_PLUGIN_MOUNTS_JSON")
            or os.getenv("STRATEGY_PLUGIN_MOUNTS_JSON")
        ),
    )
