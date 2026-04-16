from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from quant_platform_kit.common.strategies import derive_strategy_artifact_paths
from strategy_registry import (
    SCHWAB_PLATFORM,
    resolve_strategy_definition,
    resolve_strategy_metadata,
)
from us_equity_strategies import get_strategy_catalog

DEFAULT_NOTIFY_LANG = "en"


@dataclass(frozen=True)
class PlatformRuntimeSettings:
    strategy_profile: str
    strategy_display_name: str
    strategy_domain: str
    notify_lang: str
    dry_run_only: bool
    feature_snapshot_path: str | None = None
    feature_snapshot_manifest_path: str | None = None
    strategy_config_path: str | None = None
    strategy_config_source: str | None = None


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
    artifact_root = _first_non_empty(
        os.getenv("SCHWAB_STRATEGY_ARTIFACT_ROOT"),
        os.getenv("STRATEGY_ARTIFACT_ROOT"),
    )
    derived_artifact_paths = derive_strategy_artifact_paths(
        get_strategy_catalog(),
        strategy_definition.profile,
        artifact_root=artifact_root,
        repo_root=Path(__file__).resolve().parent,
    )
    strategy_config_path, strategy_config_source = resolve_strategy_config_path(
        explicit_path=_first_non_empty(
            os.getenv("SCHWAB_STRATEGY_CONFIG_PATH"),
            os.getenv("STRATEGY_CONFIG_PATH"),
        ),
        bundled_path=(
            str(derived_artifact_paths.bundled_config_path)
            if derived_artifact_paths.bundled_config_path is not None
            else None
        ),
    )
    return PlatformRuntimeSettings(
        strategy_profile=strategy_definition.profile,
        strategy_display_name=strategy_metadata.display_name,
        strategy_domain=strategy_definition.domain,
        notify_lang=os.getenv("NOTIFY_LANG", DEFAULT_NOTIFY_LANG),
        dry_run_only=resolve_bool_env(os.getenv("SCHWAB_DRY_RUN_ONLY")),
        feature_snapshot_path=_first_non_empty(
            os.getenv("SCHWAB_FEATURE_SNAPSHOT_PATH"),
            os.getenv("FEATURE_SNAPSHOT_PATH"),
            str(derived_artifact_paths.feature_snapshot_path)
            if derived_artifact_paths.feature_snapshot_path is not None
            else None,
        ),
        feature_snapshot_manifest_path=_first_non_empty(
            os.getenv("SCHWAB_FEATURE_SNAPSHOT_MANIFEST_PATH"),
            os.getenv("FEATURE_SNAPSHOT_MANIFEST_PATH"),
            str(derived_artifact_paths.feature_snapshot_manifest_path)
            if derived_artifact_paths.feature_snapshot_manifest_path is not None
            else None,
        ),
        strategy_config_path=strategy_config_path,
        strategy_config_source=strategy_config_source,
    )


def resolve_strategy_config_path(
    *,
    explicit_path: str | None,
    bundled_path: str | None,
) -> tuple[str | None, str | None]:
    path = _first_non_empty(explicit_path)
    if path is not None:
        return path, "env"

    bundled = _first_non_empty(bundled_path)
    if bundled is not None and Path(bundled).exists():
        return bundled, "bundled_canonical_default"
    return None, None


def _first_non_empty(*values: str | None) -> str | None:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return None
