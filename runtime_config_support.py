from __future__ import annotations

import os
from dataclasses import dataclass

from strategy_registry import (
    DEFAULT_STRATEGY_PROFILE as REGISTRY_DEFAULT_STRATEGY_PROFILE,
    SCHWAB_PLATFORM,
    resolve_strategy_definition,
    resolve_strategy_metadata,
)

DEFAULT_STRATEGY_PROFILE = REGISTRY_DEFAULT_STRATEGY_PROFILE
DEFAULT_NOTIFY_LANG = "en"


@dataclass(frozen=True)
class PlatformRuntimeSettings:
    strategy_profile: str
    strategy_display_name: str
    strategy_domain: str
    notify_lang: str
    dry_run_only: bool


def resolve_bool_env(raw_value: str | None) -> bool:
    value = str(raw_value or "").strip().lower()
    return value in {"1", "true", "yes", "on"}


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
    return PlatformRuntimeSettings(
        strategy_profile=strategy_definition.profile,
        strategy_display_name=strategy_metadata.display_name,
        strategy_domain=strategy_definition.domain,
        notify_lang=os.getenv("NOTIFY_LANG", DEFAULT_NOTIFY_LANG),
        dry_run_only=resolve_bool_env(os.getenv("SCHWAB_DRY_RUN_ONLY")),
    )
